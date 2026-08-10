"""M4 — ``baron guard``: deterministic capability enforcement as a Claude Code
PreToolUse hook (ADR-004), plus non-blocking evidence capture on a handful of
other hook events (ADR-012).

Two jobs, deliberately asymmetric (ADR-012 §3):

- **PreToolUse — ENFORCEMENT.** Fail-CLOSED. Can return exit 2 and block.
- **Every other hook event — EVIDENCE.** Fail-OPEN, silent. Structurally
  incapable of returning exit 2; a broken event sink must never brick a
  session. ``BARON_EVENTS_DEBUG=1`` makes emission failures visible.

Implements the documented Claude Code hooks contract
(https://code.claude.com/docs/en/hooks — the canonical target that
https://docs.anthropic.com/en/docs/claude-code/hooks redirects to; fetched
2026-07-23):

- **Input**: the hook receives one JSON object on stdin with (among others)
  ``hook_event_name``, ``session_id``, ``cwd`` — carried by EVERY event — plus,
  on tool events, ``tool_name`` (e.g. ``"Bash"``, ``"Edit"``) and ``tool_input``
  (the tool's arguments — ``command`` for Bash, ``file_path`` for Edit/Write,
  ``notebook_path`` for NotebookEdit).
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

import hashlib
import json
import os
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml

from . import clock, events
from .gitutil import default_branch, git, is_git_repo
from .rules import CapabilityRules, RulesError, load_rules

OVERRIDE_ENV = "BARON_GUARD_OVERRIDE"
PERSONA_ENV = "BARON_PERSONA_FILE"
#: Opt-in diagnostic for the (otherwise silent, fail-open) evidence path.
#: Deliberately opt-in: guard's stderr is fed to the MODEL on exit 2, so
#: unsolicited noise there degrades the actual denial message (ADR-012 §3).
EVENTS_DEBUG_ENV = "BARON_EVENTS_DEBUG"
#: Repo-relative override log — TRACKED (not gitignored): overrides must be
#: visible in diffs. Each override is expected to become a handoff.
OVERRIDE_LOG = PurePosixPath(".baron/guard-override.log")

WRITE_TOOLS = ("Edit", "Write", "NotebookEdit")


# --- hook-event dispatch (ADR-012) ------------------------------------------------------

#: The ONE hook event guard is allowed to block on. Everything else is evidence.
PRE_TOOL_USE = "PreToolUse"

#: Every ``hook_event_name`` Claude Code 2.1.226 can emit, read out of the
#: installed binary's own hook-event enum (2026-08-09) rather than from prose
#: docs, which lag it. Recorded so a reader can see WHAT WAS CONSIDERED and
#: rejected — behaviourally this tuple is inert: a name in it that has no
#: handler is treated exactly like a name nobody has ever heard of (exit 0).
KNOWN_HOOK_EVENTS = (
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PostToolBatch",
    "Notification",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "StopFailure",
    "SubagentStart",
    "SubagentStop",
    "PreCompact",
    "PostCompact",
    "PermissionRequest",
    "PermissionDenied",
    "Setup",
    "TeammateIdle",
    "TaskCreated",
    "TaskCompleted",
    "Elicitation",
    "ElicitationResult",
    "ConfigChange",
    "WorktreeCreate",
    "WorktreeRemove",
    "InstructionsLoaded",
    "CwdChanged",
    "FileChanged",
    "DirectoryAdded",
    "MessageDisplay",
)


# --- the event-plane producer contract (ADR-012 §4) -------------------------------------

#: Version of the ATTRIBUTE schema this producer writes. Bumped when a
#: ``baron.*`` attribute key changes meaning or disappears; adding a key is not
#: a bump. Consumers read it from ``baron.events_version`` on every row.
EVENTS_VERSION = 1

#: Event ``kind``s guard produces. Open dotted strings, not a closed enum — the
#: event stream is OBSERVATION, where an unrecognised kind costs nothing (the
#: capability vocabulary is frozen because it is an ENFORCEMENT contract, where
#: ambiguity means mis-enforcement). This tuple is the documented registry and
#: is pinned by a test; it is not a runtime validation gate.
EVENT_KINDS = (
    "guard.decision",
    "guard.override",
    "session.start",
    "session.end",
    "tool.post",
    "tool.failure",
)


def _trace_id(session_id: str) -> str | None:
    """Derive a stable 32-hex OTel-shaped trace id from a Claude session id.

    Deterministic, so every event of one session correlates without the
    producer holding any state. ``None`` when there is no session id — better
    an unattributed row than one bucketed into a shared fake trace.
    """
    if not session_id:
        return None
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]


def _debug(message: str) -> None:
    if os.environ.get(EVENTS_DEBUG_ENV):
        print(f"baron guard [events]: {message}", file=sys.stderr)


def emit_event(
    kind: str,
    attributes: dict,
    *,
    actor: str = "unknown",
    subject: str = "",
    outcome: str = "ok",
    trace_id: str | None = None,
    cwd: Path | None = None,
) -> None:
    """Append one observation to the event plane. NEVER raises. NEVER blocks.

    Cross-workstream boundary: the sink, its config (``BARON_EVENTS_SINK``) and
    the on-disk row format belong to :mod:`baron.events`. Guard is a producer
    only and reaches it through this one function, by late import, so a baron
    build without the events plane installed degrades to a silent no-op rather
    than an ImportError at hook time.

    The contract this calls against is ADR-013's, not ADR-012's. ADR-012 §4
    specified ``emit(kind, attributes, *, trace_id=None)`` while the events
    plane was still unlanded and stated that the row format belongs to
    :mod:`baron.events`; the plane shipped with an :class:`~baron.events.Event`
    value object instead. Honouring that delegation is why this adapter exists
    rather than a second wire shape — see ADR-012 §4 (superseded-by note) and
    ADR-013 §2.
    """
    try:
        from . import events as events_mod  # type: ignore[attr-defined]
    except Exception as exc:  # events plane not installed — evidence is optional
        _debug(f"no event plane ({type(exc).__name__}: {exc}); dropped {kind}")
        return
    payload = {"baron.events_version": EVENTS_VERSION, **attributes}
    try:
        events_mod.emit(
            events_mod.Event(
                kind=kind,
                actor=actor,
                subject=subject,
                outcome=outcome,
                attributes=payload,
                trace_id=trace_id,
            ),
            cwd,
        )
    except Exception as exc:  # fail OPEN: a broken sink must not brick a session
        _debug(f"emit failed for {kind}: {type(exc).__name__}: {exc}")


def _payload_cwd(payload: dict) -> Path | None:
    """The repo a hook payload describes — handed to the sink via ``bind()``."""
    raw = payload.get("cwd")
    return Path(str(raw)) if raw else None


def _base_attrs(payload: dict) -> dict:
    """The attributes every hook-sourced event carries.

    The ``baron.*`` key namespace is FROZEN (ADR-012 §4). ``session.id`` is
    NOT under that prefix on purpose: it is one of ADR-013's fixed wire slots
    and one of the keys ``ingest_otel.py`` joins on (``SESSION_ATTR_KEYS``), so
    prefixing it would break the join the stream exists to support.
    """
    attrs: dict[str, object] = {
        "baron.hook_event": str(payload.get("hook_event_name") or PRE_TOOL_USE),
        "session.id": str(payload.get("session_id") or ""),
    }
    for key, attr in (
        ("session_id", "baron.session_id"),
        ("cwd", "baron.cwd"),
        ("agent_id", "baron.agent_id"),
        ("agent_type", "baron.agent_type"),
        ("permission_mode", "baron.permission_mode"),
    ):
        value = payload.get(key)
        if value:
            attrs[attr] = str(value)
    return attrs


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
    #: True when a capability rule from the artifact was applied AND the
    #: outcome turned on the acting persona — i.e. a differently-capable
    #: persona could have received a different answer. This is the ONLY basis
    #: on which the event plane may label a call ``enforced`` (ADR-018 §3).
    #:
    #: Deliberately NOT derived from ``verbs``: :func:`evaluate_write` returns
    #: an allow with an EMPTY verb tuple after genuinely checking ``write_code``,
    #: and returns a deny with a NON-EMPTY one (``write_path``) for a structural
    #: `..` escape that no capability could have unlocked. Those are opposite
    #: governance facts the verb tuple cannot tell apart, so every return site
    #: states this explicitly.
    adjudicated: bool = False


#: Persona-independent allow: guard looked and found no capability governing
#: this call. NOT adjudicated — no persona could have been denied here.
ALLOW = Decision(True, (), "")
#: Allow produced by applying a capability rule against THIS persona.
ALLOW_ADJUDICATED = Decision(True, (), "", adjudicated=True)


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
        # `required` empty means NO command rule matched — `ls -la`, `git status`,
        # `curl | sh`, `npm publish`. The call passed because guard governs
        # capability verbs, not general shell, so nothing was adjudicated and the
        # event must not call it enforced. `required` non-empty means every
        # matched verb was checked against this persona and held: an adjudication.
        return Decision(True, tuple(sorted(required)), "", adjudicated=bool(required))
    lines = []
    for verb in missing:
        notes = "; ".join(dict.fromkeys(required[verb])) or "matched directly"
        lines.append(f"inferred capability `{verb}` — not granted to this persona ({notes})")
    return Decision(False, tuple(missing), "\n".join(lines), adjudicated=True)


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
        # Malformed payload, not a capability judgement: guard could not tell
        # WHAT was being written, so no rule was applied. Fail closed, but do
        # not book it as enforcement.
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
            # A hard STRUCTURAL refusal that no capability can unlock — every
            # persona is denied identically. Guard really did block it (the
            # `deny` outcome records that), but no capability adjudicated it,
            # so `adjudicated` stays False and the event reads `unevaluated`.
            # Note the verb tuple is NON-EMPTY on this deny: that is the
            # consumer caveat in ADR-018 §5, not an oversight.
            return Decision(
                False,
                ("write_path",),
                f"target path escapes the collab/persona root {root} "
                f"(resolves to {normalized} via `..`) — refused",
            )

    parts = normalized.parts

    # 1. Universally writable zones (rules artifact): _handoff/ is how
    #    personas report and coordinate — gating it would brick the substrate.
    #    Persona-independent, so NOT an adjudication: no capability decided it.
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
                # The edit_other_personas rule matched and resolved in this
                # persona's favour BECAUSE of who it is — another persona would
                # have been denied. Adjudicated, with no verb required.
                return ALLOW_ADJUDICATED
            if not persona.grants("edit_other_personas"):
                return Decision(
                    False,
                    ("edit_other_personas",),
                    "path is under another persona's spec dir "
                    f"({rules.spec_dir_component}/{owner}/) and "
                    "`edit_other_personas` is not granted",
                    adjudicated=True,
                )

    # 3. Denied write_path scopes always block (even with write_code granted).
    if "write_path" in persona.deny:
        for scope in persona.deny_scopes:
            if _scope_matches(scope, parts):
                return Decision(
                    False,
                    ("write_path",),
                    f"path matches the denied write_path scope `{scope}`",
                    adjudicated=True,
                )

    # 4. write_code grants general writes (source dirs and beyond). A persona
    #    without it falls through to 5 and can be denied — so this IS a
    #    capability adjudication even though it names no verb in the tuple.
    if persona.grants("write_code"):
        return ALLOW_ADJUDICATED

    # 5. No write_code: only the persona's declared write_path scopes remain.
    #    (write_path is parametric — allow and deny legitimately coexist with
    #    different scopes, so membership in `allow` is the check, not grants().)
    if "write_path" in persona.allow:
        for scope in persona.allow_scopes:
            if _scope_matches(scope, parts):
                return ALLOW_ADJUDICATED
    scopes = ", ".join(persona.allow_scopes) or "(none declared)"
    return Decision(
        False,
        ("write_code", "write_path"),
        "persona lacks `write_code` and the path is outside its declared "
        f"write_path scopes [{scopes}] and the universal zones "
        f"({', '.join(rules.universal_write_components)}/)",
        adjudicated=True,
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


# --- evidence handlers (ADR-012) --------------------------------------------------------
#
# Every handler below is EVIDENCE ONLY. Contract, asserted by
# test_only_pretooluse_can_block: a handler returns nothing, its caller ignores
# whatever it does, and the dispatch branch returns (0, "") unconditionally.
# None of them may load a persona, evaluate a rule, or reach a deny path.


def _handle_session_start(payload: dict) -> None:
    """SessionStart — open the session record.

    Deliberately does NOT wrap ``baron session start``: ADR-007 ruled Barony
    does not own the execution loop, and a hook that mutates the collab repo on
    every session open is a side effect nobody asked for. Wrappers are built on
    demand; this is observation.
    """
    attrs = _base_attrs(payload)
    for key, attr in (("source", "baron.session_source"), ("model", "baron.model")):
        value = payload.get(key)
        if value:
            attrs[attr] = str(value)
    emit_event(
        "session.start",
        attrs,
        subject=str(payload.get("source") or "session"),
        trace_id=_trace_id(str(payload.get("session_id") or "")),
        cwd=_payload_cwd(payload),
    )


def _handle_session_end(payload: dict) -> None:
    """SessionEnd / Stop — close the session record.

    Both map to one kind: ``Stop`` fires when the main loop finishes a turn and
    ``SessionEnd`` when the session actually terminates, but for correlation
    purposes the useful fact is the same ("this trace stopped producing"). The
    originating hook is preserved in ``baron.hook_event``, so a consumer that
    cares can still tell them apart.
    """
    attrs = _base_attrs(payload)
    reason = payload.get("reason")
    if reason:
        attrs["baron.end_reason"] = str(reason)
    emit_event(
        "session.end",
        attrs,
        subject=str(payload.get("reason") or "session"),
        trace_id=_trace_id(str(payload.get("session_id") or "")),
        cwd=_payload_cwd(payload),
    )


def _handle_post_tool_use(payload: dict) -> None:
    """PostToolUse — what a tool call actually did, after the fact.

    Records the PRESENCE of ``tool_response``, never its content: responses
    carry file bodies and command output, and an evidence stream that quietly
    accumulates them is an exfiltration surface, not telemetry.
    """
    attrs = _base_attrs(payload)
    attrs["baron.tool_name"] = str(payload.get("tool_name") or "?")
    attrs["baron.has_tool_response"] = payload.get("tool_response") is not None
    duration = payload.get("duration_ms")
    if isinstance(duration, (int, float)):
        attrs["baron.duration_ms"] = duration
    attrs["tool.name"] = attrs["baron.tool_name"]
    emit_event(
        "tool.post",
        attrs,
        subject=str(attrs["baron.tool_name"]),
        trace_id=_trace_id(str(payload.get("session_id") or "")),
        cwd=_payload_cwd(payload),
    )


def _handle_post_tool_failure(payload: dict) -> None:
    """PostToolUseFailure — a tool call that errored or was interrupted."""
    attrs = _base_attrs(payload)
    attrs["baron.tool_name"] = str(payload.get("tool_name") or "?")
    attrs["baron.is_interrupt"] = bool(payload.get("is_interrupt"))
    error = payload.get("error")
    if error:
        attrs["baron.error"] = str(error)[:500]
    duration = payload.get("duration_ms")
    if isinstance(duration, (int, float)):
        attrs["baron.duration_ms"] = duration
    attrs["tool.name"] = attrs["baron.tool_name"]
    emit_event(
        "tool.failure",
        attrs,
        subject=str(attrs["baron.tool_name"]),
        outcome="error",
        trace_id=_trace_id(str(payload.get("session_id") or "")),
        cwd=_payload_cwd(payload),
    )


#: hook_event_name -> evidence handler. Absent from this table (whether the name
#: is in KNOWN_HOOK_EVENTS or invented tomorrow) means: do nothing, exit 0.
#: PreToolUse is deliberately NOT here — it is the enforcement path, not evidence.
EVIDENCE_HANDLERS = {
    "SessionStart": _handle_session_start,
    "SessionEnd": _handle_session_end,
    "Stop": _handle_session_end,
    "PostToolUse": _handle_post_tool_use,
    "PostToolUseFailure": _handle_post_tool_failure,
}


def _dispatch_evidence(hook_event: str, payload: dict) -> None:
    """Run one evidence handler. Swallows everything — see ADR-012 §3."""
    handler = EVIDENCE_HANDLERS.get(hook_event)
    if handler is None:
        return
    try:
        handler(payload)
    except Exception as exc:  # fail OPEN — evidence is never worth a blocked session
        _debug(f"{hook_event} handler failed: {type(exc).__name__}: {exc}")


# --- observation (ADR-013) ------------------------------------------------------------
#
# Emission is ONE-WAY. Nothing below can allow, deny, or change an exit code:
# every call goes through _observe(), which swallows everything. Guard is
# fail-CLOSED (ADR-004 §2.3); evidence emission is deliberately fail-OPEN, so a
# broken sink can never turn "log this" into "deny everything".


#: ``enforced`` — a capability rule matched AND the outcome turned on the acting
#: persona. The only value that claims baron mechanised something.
ENFORCEMENT_ENFORCED = "enforced"
#: ``unevaluated`` — guard saw the call and did NOT adjudicate it: out of
#: jurisdiction, no rule matched, a structural refusal, or guard fell closed.
ENFORCEMENT_UNEVALUATED = "unevaluated"
#: ``unknown`` — the rules artifact could not be read, so guard cannot say
#: whether anything was adjudicable. Refusing to guess, as everywhere else.
ENFORCEMENT_UNKNOWN = "unknown"

#: The COMPLETE vocabulary of ``baron.enforcement`` ON AN EVENT. Pinned by test.
#: ``instructed`` is deliberately absent — see :func:`_enforcement_class`.
ENFORCEMENT_VALUES: tuple[str, ...] = (
    ENFORCEMENT_ENFORCED,
    ENFORCEMENT_UNEVALUATED,
    ENFORCEMENT_UNKNOWN,
)


@dataclass
class _Trace:
    """What one PreToolUse evaluation observed, for the event it emits.

    Threaded through :func:`process` and read at each emission site. Holds only
    what the event already carries; it is not a second copy of the verdict.
    """

    tool: str = "?"
    actor: str = "unknown"
    subject: str = "?"
    session_id: str = ""
    cwd: Path = field(default_factory=Path.cwd)
    verbs: tuple[str, ...] = ()
    #: Mirrors :attr:`Decision.adjudicated`. Defaults to FALSE and is only ever
    #: raised by :meth:`record` copying a real :class:`Decision` — so every path
    #: that returns without producing one (out-of-jurisdiction tool, malformed
    #: payload, fail-closed error, fail-closed bypass) is ``unevaluated`` BY
    #: CONSTRUCTION rather than because someone remembered. That default is the
    #: fix for the ADR-013 §9.1 defect where unadjudicated calls read `enforced`.
    adjudicated: bool = False

    def record(self, decision: Decision) -> None:
        """Copy the evaluation's observable facts onto the trace.

        ``adjudicated`` is COPIED, never inferred from ``verbs`` — the verb
        tuple is wrong in both directions (see :attr:`Decision.adjudicated`).
        """
        self.verbs = decision.verbs
        self.adjudicated = decision.adjudicated


def _enforcement_class(trace: _Trace) -> str:
    """The honest ``baron.enforcement`` for ONE evaluation (ADR-018 §3).

    This is a per-call OBSERVATION — "did a capability adjudicate THIS call?" —
    not a property of the verbs involved. ``enforced`` requires both halves of
    :attr:`Decision.adjudicated`: a capability rule matched AND the outcome
    turned on the acting persona. Everything else is ``unevaluated``, except an
    unreadable rules artifact, which is ``unknown`` because guard cannot even
    tell what was adjudicable.

    Note what is NOT here: ``instructed``. That is a static posture property of
    a (persona, verb, runtime) triple — "declared and nothing checks it" — and
    guard cannot observe it at a tool call: nothing at the PreToolUse hook says
    whether persona prose covered this command. Emitting it would assert a
    control baron never measured, which is the over-claim ADR-002/ADR-008
    exist to prevent. The posture axis is real and lives on ``baron rules list``
    (``CapabilityRules.label``), joined offline via the artifact.

    ``not-applicable`` is also gone: "guard has no jurisdiction here" and "guard
    looked and no rule matched" are the same governance fact — baron did not
    adjudicate — so they share one label rather than splitting a distinction no
    consumer can act on.
    """
    if trace.adjudicated:
        return ENFORCEMENT_ENFORCED
    try:
        _rules()
    except GuardError:
        return ENFORCEMENT_UNKNOWN  # broken artifact; do not guess a label
    return ENFORCEMENT_UNEVALUATED


def _observe(
    trace: _Trace,
    *,
    kind: str,
    outcome: str,
    reason: str = "",
    error: str = "",
) -> None:
    """Emit one observation event. Never raises, never affects the verdict.

    Routes through :func:`emit_event`, the ONE late-bound door guard uses to
    reach the plane (ADR-012 §4). Binding ``baron.events`` at module import
    instead would make a baron build without the plane an ImportError at hook
    time — the failure mode the late import exists to prevent.
    """
    try:
        attributes: dict[str, object] = {
            "tool.name": trace.tool,
            "session.id": trace.session_id,
            "baron.capability.verb": ",".join(trace.verbs),
            "baron.enforcement": _enforcement_class(trace),
            "baron.reason": reason,
        }
        if error:
            attributes["baron.error"] = error
        emit_event(
            kind,
            attributes,
            actor=trace.actor or "unknown",
            subject=trace.subject,
            outcome=outcome,
            trace_id=_trace_id(trace.session_id),
            cwd=trace.cwd,
        )
    except Exception:  # belt and braces: emit_event already swallows
        return None


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
    """Evaluate one Claude Code hook payload.

    Returns ``(exit_code, stderr_text)`` per the documented contract
    (https://code.claude.com/docs/en/hooks): exit 0 = no objection (normal
    permission flow applies), exit 2 = block, stderr fed to the model.

    Dispatch (ADR-012 §2) on ``hook_event_name``:

    - absent, or ``"PreToolUse"`` → the ENFORCEMENT path below, unchanged.
      Absent means PreToolUse for back-compatibility: guard shipped before it
      read the field, and payloads/tests predating this change must keep working.
    - a name in :data:`EVIDENCE_HANDLERS` → emit one observation, exit 0.
    - anything else → exit 0 immediately. Unknown events never block. This is
      the whole reason the table has a default: Claude Code's event set grows
      (2.1.226 emits 31 distinct names), and an event baron has never heard of
      must be inert, not fatal.

    Fail-closed applies to the ENFORCEMENT path only: any internal error is a
    deny with actionable stderr — unless BARON_GUARD_OVERRIDE is set, which
    allows AND logs. Malformed JSON and empty stdin are BOTH denies (exit 2);
    they share the JSONDecodeError path, and both are pinned by tests because
    ADR-004 §2.3 makes them policy, not incidental behaviour.

    Evidence paths fail OPEN and silently (``BARON_EVENTS_DEBUG=1`` to see
    them). The asymmetry is deliberate: a guard that cannot decide must deny,
    but an event sink that cannot write must not take the session with it.

    Fail-closed: any internal error is a deny with actionable stderr — unless
    BARON_GUARD_OVERRIDE is set, which allows AND logs.

    Additionally emits one observation event per verdict (ADR-013). That path
    is fail-OPEN and cannot change the returned exit code — see :func:`_observe`.
    Everything the event carries lives on one :class:`_Trace`, whose
    ``adjudicated`` field defaults to False, so an emission from a path that
    never produced a :class:`Decision` is ``unevaluated`` by construction
    (ADR-018).
    """
    override = os.environ.get(OVERRIDE_ENV)
    trace = _Trace()
    tool = "?"
    target = "?"
    cwd = trace.cwd
    payload: dict = {}
    try:
        try:
            parsed = json.loads(stdin_text)
        except json.JSONDecodeError as exc:
            raise GuardError(f"hook stdin is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise GuardError("hook stdin is not a JSON object")
        payload = parsed

        # Dispatch BEFORE anything that can raise a deny. Neither branch below
        # can reach exit 2: _dispatch_evidence swallows everything and the
        # return is unconditional.
        hook_event = str(payload.get("hook_event_name") or PRE_TOOL_USE)
        if hook_event != PRE_TOOL_USE:
            _dispatch_evidence(hook_event, payload)
            return 0, ""

        tool = str(payload.get("tool_name", "?"))
        trace.tool = tool
        trace.session_id = str(payload.get("session_id") or "")
        tool_input = payload.get("tool_input")
        if tool_input is None:
            tool_input = {}
        if not isinstance(tool_input, dict):
            raise GuardError("tool_input is not a JSON object")
        raw_cwd = payload.get("cwd")
        if raw_cwd:
            cwd = Path(str(raw_cwd))
            trace.cwd = cwd
        target = str(
            tool_input.get("command")
            or tool_input.get("file_path")
            or tool_input.get("notebook_path")
            or "?"
        )
        trace.subject = target

        if tool != "Bash" and tool not in WRITE_TOOLS:
            # Unknown tools pass: a capability gate, not an allowlist. No event
            # either — guard reached no verdict, and one row per Read/Grep would
            # bury the verdicts this stream exists to record. A PostToolUse
            # observer (kind ``tool.post``) is the right home for that traffic.
            return 0, ""

        if persona_file is None:
            raise GuardError(
                f"no persona file — pass --persona-file or set {PERSONA_ENV}"
            )
        persona = load_persona(persona_file)
        trace.actor = persona.slug or persona_file.name
        if tool == "Bash":
            decision = evaluate_bash(str(tool_input.get("command") or ""), cwd, persona)
        else:
            decision = evaluate_write(tool, tool_input, cwd, persona)
    except GuardError as exc:
        # No Decision was produced, so `trace.adjudicated` is still False and
        # the event reads `unevaluated` (or `unknown` if the rules artifact is
        # what broke). Guard blocked precisely BECAUSE it could not evaluate;
        # booking that as enforcement would count a broken deployment as
        # working governance — ADR-018 §3.
        if override:
            log_override(cwd, tool, target, f"[fail-closed bypass] {override}")
            _observe(
                trace, kind="guard.override", outcome="override",
                reason=f"[fail-closed bypass] {override}", error=str(exc),
            )
            return 0, ""
        _observe(
            trace, kind="guard.decision", outcome="error",
            reason=str(exc), error=str(exc),
        )
        return 2, f"baron guard: DENY (fail closed) — {exc}\n{_remedy()}"
    except Exception as exc:  # fail-closed on internal bugs, never fail-open
        detail = f"{type(exc).__name__}: {exc}"
        if override:
            log_override(cwd, tool, target, f"[internal-error bypass] {override}")
            _observe(
                trace, kind="guard.override", outcome="override",
                reason=f"[internal-error bypass] {override}", error=detail,
            )
            return 0, ""
        _observe(
            trace, kind="guard.decision", outcome="error",
            reason=detail, error=detail,
        )
        return 2, (
            f"baron guard: DENY (internal error, fail closed) — "
            f"{detail}\n{_remedy()}"
        )

    # Copied from the Decision, never inferred from the verb tuple.
    trace.record(decision)
    if decision.allowed:
        _observe(
            trace, kind="guard.decision", outcome="allow", reason=decision.reason,
        )
        return 0, ""
    if override:
        log_override(cwd, tool, target, override)
        _observe(trace, kind="guard.override", outcome="override", reason=override)
        return 0, ""
    _observe(trace, kind="guard.decision", outcome="deny", reason=decision.reason)
    persona_name = persona.slug or persona_file.name
    reason = decision.reason.replace("\n", "\n  ")  # indent continuation lines
    return 2, (
        f"baron guard: DENY {tool} for persona '{persona_name}' ({persona_file})\n"
        f"  target: {target}\n"
        f"  {reason}\n"
        f"{_remedy()}"
    )
