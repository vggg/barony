"""M4 — ``baron guard``: deterministic capability enforcement as a Claude Code
PreToolUse hook (ADR-004).

Implements the documented Claude Code hooks contract
(https://code.claude.com/docs/en/hooks — the canonical target that
https://docs.anthropic.com/en/docs/claude-code/hooks redirects to; fetched
2026-07-23):

- **Input**: the hook receives one JSON object on stdin with (among others)
  ``tool_name`` (e.g. ``"Bash"``, ``"Edit"``), ``tool_input`` (the tool's
  arguments — ``command`` for Bash, ``file_path`` for Edit/Write,
  ``notebook_path`` for NotebookEdit), and ``cwd``.
- **Output**: exit code ``0`` with no stdout means "no decision" — the call
  proceeds through the normal permission flow. Exit code ``2`` BLOCKS the tool
  call and feeds stderr to the model as the blocking reason. (A JSON
  ``hookSpecificOutput.permissionDecision`` allow/deny/ask form also exists on
  exit 0; baron deliberately uses the exit-code form instead: exit 2 + stderr
  also covers the fail-closed error paths where composing JSON might itself
  fail, and baron never emits ``"allow"`` because that would BYPASS the user's
  own permission prompts — the guard only ever objects or stays silent.)

What it enforces: the sub-tool half of the frozen v1 capability vocabulary
that Tier-3 tool allow-lists cannot reach (``push_main``, ``force_push``,
``merge_pr``, ``write_path`` scoping, ``edit_other_personas``). Whole-tool
denials stay with the Tier-3 allow-list; ``open_pr``/``run_tests`` denials
remain instruction-only (guard does not parse for them).

Honesty boundary: this is deterministic enforcement of the honest-mistake
class (a persona forgetting its capability set mid-session), not an
adversarial sandbox — a sufficiently creative shell command can evade static
parsing. Parsing is CONSERVATIVE: when the target of a git operation cannot be
determined, guard assumes the enforcement-relevant verb and denies personas
that lack it, with stderr naming the inference.

KNOWN BYPASS — command-string wrappers. The static parser inspects the tokens
of each top-level subcommand; it does NOT recurse into a shell/interpreter
invoked with an inline program string. So ``bash -c '...'``, ``sh -c "..."``,
and ``python3 -c '...'`` (and ``env``/``xargs``-style indirection) run their
payload UNINSPECTED — a ``git push origin main`` hidden inside ``bash -c`` is
NOT caught. ``bash -c`` / ``sh -c`` are common enough to hit by honest accident,
not just adversarially. This is an accepted limitation of static enforcement of
the honest-mistake class, not a guarantee. Where the boundary must actually hold
against a wrapper, use OS-level isolation (a container/sandbox) — the guard is a
nudge against forgetting, not a wall. (The pydantic-ai adapter's in-process
Shell additionally denies redirect/pipe operators and, for test-only personas,
allowlists the shell — narrowing but not closing this class.)

Escape hatch (fail-closed but not brick): ``BARON_GUARD_OVERRIDE=<reason>``
allows the call BUT appends a line to ``.baron/guard-override.log`` — a
TRACKED file, deliberately not gitignored, so overrides surface in diffs and
reviews. An override is expected to be turned into a ``_handoff/`` explaining
why the capability boundary was crossed.

Policy source: the verb→enforcement rule table (command patterns, file-op
scoping semantics, ambiguity policy) is NOT hardcoded here — it is loaded
from the packaged, versioned artifact ``data/capability-rules.v1.yaml`` via
:mod:`baron.rules` (ADR-004 addendum §4.1). This module supplies the
*mechanics* (shell splitting, refspec resolution, branch lookups, the hook
I/O contract); the rules artifact supplies the *policy* every consumer —
this hook, the pydantic-ai adapter, future runtime adapters — must share.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from . import clock
from .gitutil import default_branch, git, is_git_repo
from .rules import CapabilityRules, RulesError, load_rules

OVERRIDE_ENV = "BARON_GUARD_OVERRIDE"
PERSONA_ENV = "BARON_PERSONA_FILE"
#: Repo-relative override log — TRACKED (not gitignored): overrides must be
#: visible in diffs. Each override is expected to become a handoff.
OVERRIDE_LOG = PurePosixPath(".baron/guard-override.log")

WRITE_TOOLS = ("Edit", "Write", "NotebookEdit")


class GuardError(RuntimeError):
    """Guard could not evaluate the call — treated as a deny (fail closed)."""


def _rules() -> CapabilityRules:
    """The packaged capability rules; a broken artifact fails closed."""
    try:
        return load_rules()
    except RulesError as exc:
        raise GuardError(str(exc)) from exc


# --- persona --------------------------------------------------------------------------


@dataclass(frozen=True)
class GuardPersona:
    """The capability facts guard needs from one persona.yaml."""

    slug: str
    allow: frozenset[str]
    deny: frozenset[str]
    allow_scopes: tuple[str, ...]  # write_path parameter under allow
    deny_scopes: tuple[str, ...]  # write_path parameter under deny

    def grants(self, verb: str) -> bool:
        return verb in self.allow and verb not in self.deny


def _split_items(items: object) -> tuple[set[str], tuple[str, ...]]:
    """Normalize a capabilities list to (verbs, write_path scopes)."""
    verbs: set[str] = set()
    scopes: list[str] = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            verbs.add(item)
        elif isinstance(item, dict) and len(item) == 1:
            ((key, value),) = item.items()
            verbs.add(str(key))
            if key == "write_path":
                if isinstance(value, list):
                    scopes.extend(str(s) for s in value)
                elif value is not None:
                    scopes.append(str(value))
    return verbs, tuple(scopes)


def load_persona(path: Path) -> GuardPersona:
    if not path.is_file():
        raise GuardError(f"persona file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GuardError(f"cannot read persona file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise GuardError(f"{path}: persona is not a YAML mapping")
    caps = data.get("capabilities")
    if not isinstance(caps, dict):
        raise GuardError(f"{path}: no capabilities block")
    allow, allow_scopes = _split_items(caps.get("allow"))
    deny, deny_scopes = _split_items(caps.get("deny"))
    return GuardPersona(
        slug=str(data.get("slug", "")).strip(),
        allow=frozenset(allow),
        deny=frozenset(deny),
        allow_scopes=allow_scopes,
        deny_scopes=deny_scopes,
    )


# --- decisions ------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    allowed: bool
    verbs: tuple[str, ...]  # capability verbs this call was mapped to
    reason: str  # denial explanation ("" when allowed)


ALLOW = Decision(True, (), "")


# --- shell parsing (Bash tool) --------------------------------------------------------


def _split_shell(command: str) -> list[str]:
    """Split a shell command on ``;``, ``&``, ``|`` and newlines outside quotes.

    Deliberately simple: guard checks every top-level subcommand; command
    substitution and exotic quoting are outside the honest-mistake threat model
    (see module docstring).
    """
    segments: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    for ch in command:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch in ";|&\n":
            seg = "".join(buf).strip()
            if seg:
                segments.append(seg)
            buf = []
        else:
            buf.append(ch)
    seg = "".join(buf).strip()
    if seg:
        segments.append(seg)
    return segments


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _current_branch(repo: Path) -> str | None:
    if not repo.is_dir():
        return None
    proc = git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    name = proc.stdout.strip()
    if proc.returncode != 0 or not name or name == "HEAD":  # HEAD = detached
        return None
    return name


def _upstream_branch(repo: Path) -> str | None:
    """Branch name the current branch's upstream points at (e.g. main), or None."""
    if not repo.is_dir():
        return None
    proc = git(repo, "rev-parse", "--abbrev-ref", "@{upstream}", check=False)
    name = proc.stdout.strip()
    if proc.returncode != 0 or not name:
        return None
    return name.split("/", 1)[-1]


def _default_branch(repo: Path) -> str | None:
    if not repo.is_dir() or not is_git_repo(repo):
        return None
    return default_branch(repo)


def _analyze_push(
    args: list[str], repo: Path, rules: CapabilityRules
) -> tuple[set[str], list[str]]:
    """Map a ``git push`` argument list to capability verbs + inference notes.

    The patterns (force flags, all-branch flags, value options, fallback
    default-branch names) come from the capability-rules artifact; this
    function supplies only the parsing mechanics.
    """
    verbs: set[str] = set()
    notes: list[str] = []
    positionals: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in rules.push_force_flags or arg.startswith(
            tuple(rules.push_force_flag_prefixes)
        ):
            verbs.add(rules.push_force_verb)
            notes.append(f"force flag `{arg}`")
        elif arg in rules.push_all_branch_flags:
            verbs.add(rules.push_all_branches_verb)
            notes.append(f"`{arg}` includes the default branch")
        elif arg in rules.push_value_options:
            i += 1
        elif arg.startswith("-"):
            pass
        else:
            positionals.append(arg)
        i += 1

    default = _default_branch(repo)
    refspecs = positionals[1:]  # positionals[0] is the remote, when present
    if not refspecs:
        # Bare `git push` (or `git push <remote>`): destination is the current
        # branch's upstream / push.default. Resolve what we can; when nothing
        # resolves, CONSERVATIVELY infer push_main (the artifact's
        # ambiguity_policy: conservative-deny).
        dst = _upstream_branch(repo) or _current_branch(repo)
        if dst is None or default is None:
            verbs.add(rules.push_default_branch_verb)
            notes.append(
                "no refspec and the target branch is undeterminable — "
                f"conservatively inferred {rules.push_default_branch_verb}"
            )
        elif dst == default:
            verbs.add(rules.push_default_branch_verb)
            notes.append(f"no refspec; current branch targets the default branch '{default}'")
    prefix = rules.push_plus_refspec_prefix
    for spec in refspecs:
        if spec.startswith(prefix):  # +refspec is a force push
            verbs.add(rules.push_force_verb)
            notes.append(f"`{prefix}` refspec `{spec}`")
            spec = spec.lstrip(prefix)
        dst = spec.split(":", 1)[1] if ":" in spec else spec
        if dst.startswith("refs/heads/"):
            dst = dst[len("refs/heads/") :]
        if dst == "HEAD":
            dst = _current_branch(repo) or "HEAD"
        if default is not None:
            if dst == default:
                verbs.add(rules.push_default_branch_verb)
                notes.append(f"refspec targets the default branch '{default}'")
        elif dst in rules.push_default_branch_fallbacks:
            verbs.add(rules.push_default_branch_verb)
            notes.append(
                f"no origin remote is configured yet, so the default branch "
                f"can't be confirmed — treating `{dst}` as the default branch "
                "to stay on the safe side"
            )
    return verbs, notes


def _analyze_merge(repo: Path, rules: CapabilityRules) -> tuple[set[str], list[str]]:
    """``git merge`` while ON the default branch lands commits on it directly."""
    verb = rules.merge_on_default_branch_verb
    current = _current_branch(repo)
    default = _default_branch(repo)
    if current is None or default is None:
        return {verb}, [
            "cannot determine the current/default branch for `git merge` — "
            "conservatively treated as a merge into the default branch"
        ]
    if current == default:
        return {verb}, [
            f"`git merge` while on the default branch '{default}' lands commits on it"
        ]
    return set(), []


def evaluate_bash(command: str, cwd: Path, persona: GuardPersona) -> Decision:
    """Map a Bash command to capability verbs and check them against the persona.

    Non-git/gh commands pass — guard governs capability verbs, not general
    shell (an allowlist is the Tier-3 adapter's job, not this hook's).
    """
    rules = _rules()
    required: dict[str, list[str]] = {}
    for segment in _split_shell(command):
        tokens = _tokens(segment)
        while tokens and _ENV_ASSIGN_RE.match(tokens[0]):
            tokens = tokens[1:]
        if not tokens:
            continue
        prog = PurePosixPath(tokens[0]).name
        if prog == "git":
            repo = cwd
            sub: str | None = None
            args: list[str] = []
            i = 1
            while i < len(tokens):
                tok = tokens[i]
                if tok in rules.git_global_value_options:
                    if tok == "-C" and i + 1 < len(tokens):
                        candidate = Path(tokens[i + 1])
                        repo = candidate if candidate.is_absolute() else cwd / candidate
                    i += 2
                    continue
                if tok.startswith("-"):
                    i += 1
                    continue
                sub = tok
                args = tokens[i + 1 :]
                break
            if sub == "push":
                verbs, notes = _analyze_push(args, repo, rules)
            elif sub == "merge":
                verbs, notes = _analyze_merge(repo, rules)
            else:
                verbs, notes = set(), []
            for verb in verbs:
                required.setdefault(verb, []).extend(notes)
        elif prog == "gh":
            rest = [t for t in tokens[1:] if not t.startswith("-")]
            sub_path = list(rules.gh_pr_merge_subcommand)
            n = len(sub_path)
            if any(
                rest[i : i + n] == sub_path for i in range(len(rest) - n + 1)
            ):  # tolerate global flags with values before the subcommand
                required.setdefault(rules.gh_pr_merge_verb, []).append(
                    f"`gh {' '.join(sub_path)}`"
                )

    missing = [v for v in sorted(required) if not persona.grants(v)]
    if not missing:
        return Decision(True, tuple(sorted(required)), "")
    lines = []
    for verb in missing:
        notes = "; ".join(dict.fromkeys(required[verb])) or "matched directly"
        lines.append(f"inferred capability `{verb}` — not granted to this persona ({notes})")
    return Decision(False, tuple(missing), "\n".join(lines))


# --- write-tool paths (Edit / Write / NotebookEdit) -----------------------------------


def _scope_matches(scope: str, parts: tuple[str, ...]) -> bool:
    """True if ``scope`` (a path fragment like ``wiki`` or ``findings``) appears
    as a contiguous component run in the target path."""
    scope_parts = tuple(p for p in PurePosixPath(scope).parts if p != ".")
    if not scope_parts:
        return False
    n = len(scope_parts)
    return any(parts[i : i + n] == scope_parts for i in range(len(parts) - n + 1))


def evaluate_write(
    tool_name: str, tool_input: dict, cwd: Path, persona: GuardPersona
) -> Decision:
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw:
        return Decision(
            False,
            (),
            f"{tool_name} call carries no file_path/notebook_path — fail closed",
        )
    rules = _rules()
    path = Path(str(raw))
    if not path.is_absolute():
        path = cwd / path
    normalized = Path(os.path.normpath(path))

    # 0. Defense-in-depth: a target that normalizes to OUTSIDE the collab/persona
    #    root (a `../outside.md` escaping above cwd) is denied here — the harness
    #    FS jail catches direct writes, but a Shell `>` redirect escapes both, so
    #    the guard refuses the escape itself rather than relying on the jail.
    #    Only checkable when the root is absolute (the normalized target then is
    #    too); a relative cwd can't anchor the comparison, so skip rather than
    #    risk a false positive.
    root = Path(os.path.normpath(cwd))
    if root.is_absolute() and normalized.is_absolute():
        try:
            normalized.relative_to(root)
        except ValueError:
            return Decision(
                False,
                ("write_path",),
                f"target path escapes the collab/persona root {root} "
                f"(resolves to {normalized} via `..`) — refused",
            )

    parts = normalized.parts

    # 1. Universally writable zones (rules artifact): _handoff/ is how
    #    personas report and coordinate — gating it would brick the substrate.
    if any(c in parts for c in rules.universal_write_components):
        return ALLOW

    # 2. Another persona's spec dir (agents/<other-slug>/...) needs
    #    edit_other_personas; a persona's OWN agents/<slug>/ dir is its own
    #    surface (COORDINATION.md Owner row) and always writable.
    if rules.spec_dir_component in parts:
        idx = parts.index(rules.spec_dir_component)
        if idx + 2 <= len(parts) - 1:  # there is a slug dir AND a file below it
            owner = parts[idx + 1]
            if owner == persona.slug:
                return ALLOW
            if not persona.grants("edit_other_personas"):
                return Decision(
                    False,
                    ("edit_other_personas",),
                    "path is under another persona's spec dir "
                    f"({rules.spec_dir_component}/{owner}/) and "
                    "`edit_other_personas` is not granted",
                )

    # 3. Denied write_path scopes always block (even with write_code granted).
    if "write_path" in persona.deny:
        for scope in persona.deny_scopes:
            if _scope_matches(scope, parts):
                return Decision(
                    False,
                    ("write_path",),
                    f"path matches the denied write_path scope `{scope}`",
                )

    # 4. write_code grants general writes (source dirs and beyond).
    if persona.grants("write_code"):
        return ALLOW

    # 5. No write_code: only the persona's declared write_path scopes remain.
    #    (write_path is parametric — allow and deny legitimately coexist with
    #    different scopes, so membership in `allow` is the check, not grants().)
    if "write_path" in persona.allow:
        for scope in persona.allow_scopes:
            if _scope_matches(scope, parts):
                return ALLOW
    scopes = ", ".join(persona.allow_scopes) or "(none declared)"
    return Decision(
        False,
        ("write_code", "write_path"),
        "persona lacks `write_code` and the path is outside its declared "
        f"write_path scopes [{scopes}] and the universal zones "
        f"({', '.join(rules.universal_write_components)}/)",
    )


# --- override log ---------------------------------------------------------------------


def _repo_root(cwd: Path) -> Path:
    if cwd.is_dir():
        proc = git(cwd, "rev-parse", "--show-toplevel", check=False)
        top = proc.stdout.strip()
        if proc.returncode == 0 and top:
            return Path(top)
    return cwd


def log_override(cwd: Path, tool: str, target: str, reason: str) -> Path:
    """Append one override line to the TRACKED .baron/guard-override.log."""
    root = _repo_root(cwd)
    log_path = root / Path(*OVERRIDE_LOG.parts)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{clock.now().isoformat()}\t{tool}\t{target}\t{reason}\n"
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(line)
    return log_path


# --- entry point ----------------------------------------------------------------------


def _remedy() -> str:
    return (
        "If this operation is deliberate: re-run with "
        f'{OVERRIDE_ENV}="<reason>" set — the call will be allowed and the '
        f"override appended to {OVERRIDE_LOG} (a TRACKED file; turn the "
        "override into a _handoff/ explaining it). Otherwise route the work "
        "through a persona that holds the capability."
    )


def process(stdin_text: str, persona_file: Path | None) -> tuple[int, str]:
    """Evaluate one PreToolUse hook payload.

    Returns ``(exit_code, stderr_text)`` per the documented contract
    (https://code.claude.com/docs/en/hooks): exit 0 = no objection (normal
    permission flow applies), exit 2 = block, stderr fed to the model.
    Fail-closed: any internal error is a deny with actionable stderr — unless
    BARON_GUARD_OVERRIDE is set, which allows AND logs.
    """
    override = os.environ.get(OVERRIDE_ENV)
    tool = "?"
    target = "?"
    cwd = Path.cwd()
    try:
        try:
            payload = json.loads(stdin_text)
        except json.JSONDecodeError as exc:
            raise GuardError(f"hook stdin is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise GuardError("hook stdin is not a JSON object")
        tool = str(payload.get("tool_name", "?"))
        tool_input = payload.get("tool_input")
        if tool_input is None:
            tool_input = {}
        if not isinstance(tool_input, dict):
            raise GuardError("tool_input is not a JSON object")
        raw_cwd = payload.get("cwd")
        if raw_cwd:
            cwd = Path(str(raw_cwd))
        target = str(
            tool_input.get("command")
            or tool_input.get("file_path")
            or tool_input.get("notebook_path")
            or "?"
        )

        if tool != "Bash" and tool not in WRITE_TOOLS:
            return 0, ""  # unknown tools pass: a capability gate, not an allowlist

        if persona_file is None:
            raise GuardError(
                f"no persona file — pass --persona-file or set {PERSONA_ENV}"
            )
        persona = load_persona(persona_file)
        if tool == "Bash":
            decision = evaluate_bash(str(tool_input.get("command") or ""), cwd, persona)
        else:
            decision = evaluate_write(tool, tool_input, cwd, persona)
    except GuardError as exc:
        if override:
            log_override(cwd, tool, target, f"[fail-closed bypass] {override}")
            return 0, ""
        return 2, f"baron guard: DENY (fail closed) — {exc}\n{_remedy()}"
    except Exception as exc:  # fail-closed on internal bugs, never fail-open
        if override:
            log_override(cwd, tool, target, f"[internal-error bypass] {override}")
            return 0, ""
        return 2, (
            f"baron guard: DENY (internal error, fail closed) — "
            f"{type(exc).__name__}: {exc}\n{_remedy()}"
        )

    if decision.allowed:
        return 0, ""
    if override:
        log_override(cwd, tool, target, override)
        return 0, ""
    persona_name = persona.slug or persona_file.name
    reason = decision.reason.replace("\n", "\n  ")  # indent continuation lines
    return 2, (
        f"baron guard: DENY {tool} for persona '{persona_name}' ({persona_file})\n"
        f"  target: {target}\n"
        f"  {reason}\n"
        f"{_remedy()}"
    )
