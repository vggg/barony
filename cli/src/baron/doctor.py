"""``baron doctor`` — the guard **wiring** self-test (ADR-017).

Why this exists: the 2026-07-22 badminton-analyzer incident merged 15 PRs under
a persona whose ``merge_pr`` denial was supposed to be enforced. Enforcement had
not failed — it had never been *installed*. The `baron guard` hook was not wired
into `.claude/settings.json`, so the denial silently degraded back to persona
text and nothing said so. That silence is the residual of FM4: a guard that is
absent looks exactly like a guard that never had to fire.

``baron doctor`` breaks the silence. It runs the checks a human would otherwise
have to remember, and it FAILS LOUDLY (nonzero exit) rather than reporting a
comfortable nothing:

1. ``cli-on-path``       — the executable the hook names resolves and runs.
2. ``hook-configured``   — project ``.claude/settings.json`` wires ``baron guard``
                           as a PreToolUse hook.
3. ``hook-matcher``      — that hook's matcher actually covers every tool guard
                           governs (Bash, Edit, Write, NotebookEdit); a matcher
                           that misses one is enforcement with a hole in it.
4. ``persona-file``      — the persona the hook names exists and parses.
5. ``rules-artifact``    — ``capability-rules.v1.yaml`` loads at a supported
                           ``rules_version``.
6. ``enforcement-path``  — a synthetic denial fed through :func:`baron.guard.process`
                           really returns exit 2 *in this install*.
7. ``fail-closed``       — malformed hook stdin also returns exit 2 (ADR-004 §2.3).
8. ``override-env``      — ``BARON_GUARD_OVERRIDE`` is not sitting set in this
                           environment (if it is, every denial is being allowed).
9. ``override-log``      — INFO only: the evidence sink is writable. Evidence is
                           fail-OPEN by design, so a broken sink must never be
                           reported as broken enforcement.

**Honesty boundary — read this before trusting a green run.** Doctor verifies
WIRING, not invocation. It proves this installation *can* enforce. It cannot
observe whether Claude Code actually executed the hook on any real tool call —
nothing outside the runtime can see that. A green doctor means "correctly
wired", never "enforcement happened". Implying otherwise would reproduce the
exact failure this command exists to catch, so the caveat is printed on every
run and is part of the machine-readable output too.

Scope note: only PROJECT-level settings are inspected
(``<dir>/.claude/settings.json`` and ``.claude/settings.local.json``). A hook
wired in the user-level ``~/.claude/settings.json`` is invisible to doctor and
will read as a FAIL — the remedy line says so. Checking a machine-global file
would make doctor's verdict depend on the developer's home directory, which is
not a property of the repo under test.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

from . import gitutil, guard, rules as rules_mod

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"
INFO = "INFO"

#: Tools ``baron guard`` is able to decide on. A PreToolUse matcher that does not
#: cover all of these leaves part of the capability surface unenforced.
GOVERNED_TOOLS: tuple[str, ...] = ("Bash", *guard.WRITE_TOOLS)

#: Project-level settings files Claude Code merges, in precedence order.
SETTINGS_FILES: tuple[str, ...] = (
    ".claude/settings.json",
    ".claude/settings.local.json",
)

#: Placeholder Claude Code expands to the project root inside a hook command.
PROJECT_DIR_TOKENS: tuple[str, ...] = ("${CLAUDE_PROJECT_DIR}", "$CLAUDE_PROJECT_DIR")

CAVEAT = (
    "NOTE: doctor verifies WIRING, not invocation. It proves this install CAN "
    "enforce — baron resolves, the hook is configured, the persona and rules "
    "parse, and a synthetic denial really exits 2. It CANNOT observe whether "
    "Claude Code actually ran the hook on a real tool call; nothing outside the "
    "runtime can. Read a green doctor as 'correctly wired', never as "
    "'enforcement happened'."
)


@dataclass
class Check:
    """One self-test result: a verdict plus, when it failed, how to fix it."""

    id: str
    status: str  # PASS | FAIL | UNKNOWN | INFO
    detail: str
    remedy: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class Report:
    dir: Path
    checks: list[Check] = field(default_factory=list)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def ok(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for c in self.checks:
            counts[c.status] = counts.get(c.status, 0) + 1
        return {
            "dir": self.dir.as_posix(),
            "verifies": "wiring",
            "caveat": CAVEAT,
            "checks": [c.to_dict() for c in self.checks],
            "summary": {
                "pass": counts.get(PASS, 0),
                "fail": counts.get(FAIL, 0),
                "unknown": counts.get(UNKNOWN, 0),
                "info": counts.get(INFO, 0),
            },
            "ok": self.ok,
        }


# --- settings.json parsing --------------------------------------------------------------


@dataclass(frozen=True)
class HookWiring:
    """What the project's settings files say about the guard hook."""

    settings_path: Path | None  # the file the guard hook was found in
    files_seen: tuple[Path, ...]  # project settings files that exist
    command: str | None  # the raw hook command string
    matchers: tuple[str, ...]  # matchers of every PreToolUse entry invoking guard
    problem: str | None  # why no guard hook was found


def _expand(raw: str, project_dir: Path) -> str:
    """Resolve a hook-command path the way Claude Code would."""
    out = raw
    for token in PROJECT_DIR_TOKENS:
        out = out.replace(token, project_dir.as_posix())
    return os.path.expanduser(os.path.expandvars(out))


def _is_guard_command(tokens: list[str]) -> bool:
    """True when the token list invokes ``<something>/baron guard``."""
    return _guard_exe_index(tokens) is not None


def _guard_exe_index(tokens: list[str]) -> int | None:
    for i, tok in enumerate(tokens[:-1]):
        if PurePosixPath(tok).name in ("baron", "baron.exe") and tokens[i + 1] == "guard":
            return i
    return None


def read_hook_wiring(project_dir: Path) -> HookWiring:
    """Find the ``baron guard`` PreToolUse hook in the project settings files."""
    seen: list[Path] = []
    entries: list[tuple[Path, dict]] = []
    bad_json: list[str] = []
    for rel in SETTINGS_FILES:
        path = project_dir / rel
        if not path.is_file():
            continue
        seen.append(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            bad_json.append(f"{rel}: {exc}")
            continue
        if not isinstance(data, dict):
            bad_json.append(f"{rel}: top level is not a JSON object")
            continue
        hooks = data.get("hooks")
        pre = (hooks or {}).get("PreToolUse") if isinstance(hooks, dict) else None
        for entry in pre if isinstance(pre, list) else []:
            if isinstance(entry, dict):
                entries.append((path, entry))

    if not seen:
        return HookWiring(None, (), None, (), "no project settings file")
    if bad_json and not entries:
        return HookWiring(None, tuple(seen), None, (), "; ".join(bad_json))

    command: str | None = None
    found_in: Path | None = None
    matchers: list[str] = []
    for path, entry in entries:
        for hook in entry.get("hooks") or []:
            if not isinstance(hook, dict):
                continue
            raw = str(hook.get("command") or "")
            try:
                tokens = shlex.split(raw)
            except ValueError:
                tokens = raw.split()
            if not _is_guard_command(tokens):
                continue
            if command is None:
                command, found_in = raw, path
            matchers.append(str(entry.get("matcher", "")))
    if command is None:
        problem = (
            "no PreToolUse hook invokes `baron guard`"
            if entries
            else "settings file has no hooks.PreToolUse block"
        )
        if bad_json:
            problem += f" (also: {'; '.join(bad_json)})"
        return HookWiring(None, tuple(seen), None, (), problem)
    return HookWiring(found_in, tuple(seen), command, tuple(matchers), None)


def _uncovered_tools(matchers: tuple[str, ...]) -> list[str]:
    """Governed tools no matcher selects.

    Matchers are regexes matched against the tool name. ``re.search`` is the
    permissive reading — deliberately so: doctor would rather miss a narrow
    matcher than shout at a correct one.
    """
    missing: list[str] = []
    for tool in GOVERNED_TOOLS:
        covered = False
        for m in matchers:
            if not m or m == "*":  # empty/star matcher = every tool
                covered = True
                break
            try:
                if re.search(m, tool):
                    covered = True
                    break
            except re.error:
                continue
        if not covered:
            missing.append(tool)
    return missing


def _kit_settings(project_dir: Path) -> list[Path]:
    """Un-copied `baron init` runtime kits holding a settings.json.

    This is the badminton shape exactly: the wiring was generated, and then
    never moved to where the runtime reads it.
    """
    return sorted(project_dir.glob("agents/*/runtime/.claude/settings.json"))


# --- individual checks ------------------------------------------------------------------


def _check_cli_on_path(wiring: HookWiring, project_dir: Path) -> Check:
    exe = "baron"
    source = "default"
    if wiring.command:
        try:
            tokens = shlex.split(wiring.command)
        except ValueError:
            tokens = wiring.command.split()
        idx = _guard_exe_index(tokens)
        if idx is not None:
            exe = _expand(tokens[idx], project_dir)
            source = "named by the hook command"
    resolved = shutil.which(exe) if os.sep not in exe else (exe if Path(exe).is_file() else None)
    if resolved is None:
        return Check(
            "cli-on-path",
            FAIL,
            f"`{exe}` ({source}) does not resolve to an executable — the hook "
            "would fail to start, and Claude Code treats a non-blocking hook "
            "error as no objection: every denial silently becomes allowed",
            "Install baron where the runtime's PATH can see it "
            "(`pip install barony` / `uv tool install barony`), or make the "
            "hook command an absolute path to the executable.",
        )
    try:
        proc = subprocess.run(
            [resolved, "--version"], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Check(
            "cli-on-path",
            FAIL,
            f"`{resolved} --version` could not be run: {exc}",
            "Reinstall barony, or point the hook command at a working executable.",
        )
    if proc.returncode != 0:
        return Check(
            "cli-on-path",
            FAIL,
            f"`{resolved} --version` exited {proc.returncode}: "
            f"{(proc.stderr or proc.stdout).strip()[:200]}",
            "Reinstall barony — the installed executable is broken.",
        )
    return Check(
        "cli-on-path",
        PASS,
        f"{resolved} — {proc.stdout.strip() or '(no version line)'} ({source})",
    )


def _check_hook_configured(wiring: HookWiring, project_dir: Path) -> Check:
    if wiring.command is not None:
        assert wiring.settings_path is not None
        rel = wiring.settings_path.relative_to(project_dir).as_posix()
        return Check(
            "hook-configured",
            PASS,
            f"{rel} wires a PreToolUse hook: `{wiring.command}`",
        )
    kits = _kit_settings(project_dir)
    if kits:
        kit = kits[0].relative_to(project_dir).as_posix()
        remedy = (
            f"`baron init` generated the wiring at {kit} but nothing copied it "
            "into place — this is the badminton-analyzer failure mode verbatim "
            "(the hook was never installed, so the denial degraded to persona "
            f"text). Copy the runtime kit: cp -R "
            f"{kits[0].parent.parent.as_posix()}/. {project_dir.as_posix()}/ "
            "(see adapters/claude/HYDRATE.md)."
        )
    else:
        remedy = (
            "Add a PreToolUse hook to .claude/settings.json whose command is "
            '`baron guard --persona-file "${CLAUDE_PROJECT_DIR}/agents/<slug>/'
            'persona.yaml"` with matcher "Bash|Edit|Write|NotebookEdit" (see '
            "adapters/claude/HYDRATE.md). If the hook is wired in the user-level "
            "~/.claude/settings.json instead, doctor cannot see it — it inspects "
            "project settings only."
        )
    return Check(
        "hook-configured",
        FAIL,
        f"no `baron guard` PreToolUse hook in this project ({wiring.problem}). "
        "Capability denials here are INSTRUCTED, not enforced.",
        remedy,
    )


def _check_hook_matcher(wiring: HookWiring) -> Check:
    if wiring.command is None:
        return Check(
            "hook-matcher",
            UNKNOWN,
            "no guard hook found — nothing to check the matcher of",
            "Fix hook-configured first.",
        )
    missing = _uncovered_tools(wiring.matchers)
    shown = ", ".join(f'"{m}"' if m else "(none — matches all tools)" for m in wiring.matchers)
    if missing:
        return Check(
            "hook-matcher",
            FAIL,
            f"matcher {shown} does not select {', '.join(missing)} — guard never "
            "sees those calls, so the capabilities they carry are unenforced",
            'Set the matcher to "Bash|Edit|Write|NotebookEdit" (the tools guard '
            "can decide on). If the narrowing is deliberate, say so in the "
            "persona's enforcement note so the gap is not read as coverage.",
        )
    return Check(
        "hook-matcher",
        PASS,
        f"matcher {shown} covers all governed tools ({', '.join(GOVERNED_TOOLS)})",
    )


def _resolve_persona(
    wiring: HookWiring, project_dir: Path, override: Path | None
) -> tuple[Path | None, str]:
    if override is not None:
        return override, "--persona-file"
    if wiring.command:
        try:
            tokens = shlex.split(wiring.command)
        except ValueError:
            tokens = wiring.command.split()
        for i, tok in enumerate(tokens[:-1]):
            if tok == "--persona-file":
                return Path(_expand(tokens[i + 1], project_dir)), "the hook command"
            if tok.startswith("--persona-file="):
                return (
                    Path(_expand(tok.split("=", 1)[1], project_dir)),
                    "the hook command",
                )
    env = os.environ.get(guard.PERSONA_ENV)
    if env:
        return Path(_expand(env, project_dir)), f"${guard.PERSONA_ENV}"
    return None, "nowhere"


def _check_persona_file(
    wiring: HookWiring, project_dir: Path, override: Path | None
) -> Check:
    path, source = _resolve_persona(wiring, project_dir, override)
    if path is None:
        return Check(
            "persona-file",
            UNKNOWN,
            "no persona file is named by the hook command, --persona-file, or "
            f"${guard.PERSONA_ENV}",
            "Name the acting persona in the hook command: "
            '`baron guard --persona-file "${CLAUDE_PROJECT_DIR}/agents/<slug>/persona.yaml"`. '
            "Without it every guarded call fails closed (exit 2) — enforcement "
            "is on, but nothing can proceed.",
        )
    try:
        persona = guard.load_persona(path)
    except guard.GuardError as exc:
        return Check(
            "persona-file",
            FAIL,
            f"persona named by {source} does not load: {exc}",
            "Fix or regenerate agents/<slug>/persona.yaml (`baron validate .` "
            "reports the schema errors). Until it parses, every guarded tool "
            "call in this project denies fail-closed.",
        )
    return Check(
        "persona-file",
        PASS,
        f"{path.as_posix()} ({source}) parses — slug '{persona.slug or '(unset)'}', "
        f"{len(persona.allow)} allow / {len(persona.deny)} deny verb(s)",
    )


def _check_rules_artifact() -> Check:
    try:
        loaded = rules_mod.load_rules()
    except rules_mod.RulesError as exc:
        return Check(
            "rules-artifact",
            FAIL,
            f"capability rules do not load: {exc}",
            "Reinstall barony — data/capability-rules.v1.yaml ships as package "
            "data and every consumer refuses to mis-enforce without it.",
        )
    return Check(
        "rules-artifact",
        PASS,
        f"capability-rules v{loaded.rules_version} loaded "
        f"(supported: {rules_mod.SUPPORTED_RULES_VERSION}), "
        f"{len(loaded.verbs)} verbs, ambiguity policy '{loaded.ambiguity_policy}'",
    )


#: A persona with no write capability at all — whatever the project's real
#: personas grant, this one must be denied a source write. Using a synthetic
#: persona (not the project's) is what makes check 6 a test of the MECHANISM
#: rather than of the project's particular capability grants.
_PROBE_PERSONA = """\
persona: Baron Doctor Probe
slug: baron-doctor-probe
capabilities:
  allow:
    - read_code
  deny:
    - write_code
"""


def _probe(stdin_text: str, persona_file: Path | None) -> tuple[int, str]:
    """Run one guard evaluation with the override env neutralised.

    ``BARON_GUARD_OVERRIDE`` turns every denial into an allow; leaving it set
    during the probe would measure the escape hatch instead of the mechanism.
    (That the variable is set at all is reported by its own check.)
    """
    saved = os.environ.pop(guard.OVERRIDE_ENV, None)
    try:
        return guard.process(stdin_text, persona_file)
    finally:
        if saved is not None:
            os.environ[guard.OVERRIDE_ENV] = saved


def _check_enforcement_path() -> Check:
    """End-to-end proof that a denial really blocks IN THIS INSTALL."""
    with tempfile.TemporaryDirectory(prefix="baron-doctor-") as tmp:
        root = Path(tmp)
        persona_file = root / "probe-persona.yaml"
        persona_file.write_text(_PROBE_PERSONA, encoding="utf-8")
        payload = json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": (root / "src" / "probe.py").as_posix()},
                "cwd": root.as_posix(),
            }
        )
        try:
            code, stderr_text = _probe(payload, persona_file)
        except Exception as exc:  # pragma: no cover - process() is itself fail-closed
            return Check(
                "enforcement-path",
                FAIL,
                f"the guard evaluation raised out of process(): "
                f"{type(exc).__name__}: {exc}",
                "This is a baron bug — report it. Enforcement cannot be trusted "
                "in this install.",
            )
    if code != 2:
        return Check(
            "enforcement-path",
            FAIL,
            f"a synthetic denial returned exit {code}, not 2 — the enforcement "
            "path in this install does NOT block. Every capability denial here "
            "is instruction-only, whatever the persona says.",
            "Reinstall barony from a known-good release and re-run "
            "`baron doctor`; if it still fails, the install is broken — do not "
            "describe this project as enforced.",
        )
    if "internal error" in stderr_text:
        return Check(
            "enforcement-path",
            FAIL,
            "the synthetic denial exited 2 but via the internal-error fail-closed "
            f"path, not a real capability decision: {stderr_text.splitlines()[0]}",
            "A guard that denies everything by crashing is not enforcement — it "
            "is an outage that happens to look safe. Reinstall barony and re-run.",
        )
    return Check(
        "enforcement-path",
        PASS,
        "a synthetic denied Write returned exit 2 with a capability reason — "
        "the enforcement path works end to end in this install",
    )


def _check_fail_closed() -> Check:
    """Pin ADR-004 §2.3 at runtime: a broken hook denies, it does not wave through."""
    code, stderr_text = _probe("{ this is not json", None)
    if code != 2 or "fail closed" not in stderr_text:
        return Check(
            "fail-closed",
            FAIL,
            f"malformed hook stdin returned exit {code} ({stderr_text.splitlines()[0] if stderr_text else 'no stderr'}) "
            "— ADR-004 §2.3 requires a deny. A guard that fails OPEN is worse "
            "than no guard: it reports enforcement it is not doing.",
            "Reinstall barony; this install's guard does not implement the "
            "documented fail-closed policy.",
        )
    return Check(
        "fail-closed",
        PASS,
        "malformed hook stdin returns exit 2 (ADR-004 §2.3 fail-closed policy "
        "holds in this install)",
    )


def _check_override_env() -> Check:
    value = os.environ.get(guard.OVERRIDE_ENV)
    if value:
        return Check(
            "override-env",
            FAIL,
            f"{guard.OVERRIDE_ENV} is set in this environment "
            f"(={value!r}) — while it is set, EVERY guard denial is allowed "
            f"and merely logged to {guard.OVERRIDE_LOG}",
            f"Unset it (`unset {guard.OVERRIDE_ENV}`). The escape hatch is meant "
            "to be set for one deliberate command, not exported for a session; "
            "an exported override is indistinguishable from having no guard.",
        )
    return Check(
        "override-env",
        PASS,
        f"{guard.OVERRIDE_ENV} is not set — denials are not being waved through",
    )


def _check_override_log(project_dir: Path) -> Check:
    """INFO only. The override log is EVIDENCE, and evidence is fail-open.

    A guard whose enforcement works but whose audit trail cannot be written must
    still enforce; reporting a sink problem as an enforcement FAIL would invert
    that. Loud detail, no failure.
    """
    root = project_dir
    if gitutil.is_git_repo(project_dir):
        proc = gitutil.git(project_dir, "rev-parse", "--show-toplevel", check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            root = Path(proc.stdout.strip())
    log_path = root / Path(*guard.OVERRIDE_LOG.parts)
    parent = log_path.parent
    probe_dir = parent if parent.is_dir() else root
    writable = os.access(probe_dir, os.W_OK)
    ignored = False
    if gitutil.is_git_repo(root):
        proc = gitutil.git(
            root, "check-ignore", "-q", guard.OVERRIDE_LOG.as_posix(), check=False
        )
        ignored = proc.returncode == 0
    bits = [
        f"{log_path.as_posix()} — "
        f"{'exists' if log_path.is_file() else 'not created yet'}, "
        f"directory {'writable' if writable else 'NOT writable'}"
    ]
    if ignored:
        bits.append(
            "WARNING: it is gitignored, which removes the governance property "
            "ADR-004 §2.3 relies on (overrides must be visible in diffs). Not a "
            "FAIL — evidence is fail-open — but worth fixing."
        )
    return Check("override-log", INFO, " ".join(bits))


# --- entry point --------------------------------------------------------------------------


def run(project_dir: Path, *, persona_file: Path | None = None) -> Report:
    """Run every wiring check against ``project_dir`` (read-only)."""
    project_dir = project_dir.resolve()
    wiring = read_hook_wiring(project_dir)
    return Report(
        project_dir,
        [
            _check_cli_on_path(wiring, project_dir),
            _check_hook_configured(wiring, project_dir),
            _check_hook_matcher(wiring),
            _check_persona_file(wiring, project_dir, persona_file),
            _check_rules_artifact(),
            _check_enforcement_path(),
            _check_fail_closed(),
            _check_override_env(),
            _check_override_log(project_dir),
        ],
    )


def render(report: Report) -> str:
    lines = [
        "baron doctor — guard WIRING self-test",
        f"project dir: {report.dir.as_posix()}",
        "",
    ]
    width = max(len(c.id) for c in report.checks)
    for c in report.checks:
        lines.append(f"{c.status:7s} {c.id.ljust(width)}  {c.detail}")
        if c.remedy:
            lines.append(f"{'':7s} {'':{width}}  -> {c.remedy}")
    counts: dict[str, int] = {}
    for c in report.checks:
        counts[c.status] = counts.get(c.status, 0) + 1
    lines.append(
        f"-- {counts.get(PASS, 0)} pass, {counts.get(FAIL, 0)} fail, "
        f"{counts.get(UNKNOWN, 0)} unknown, {counts.get(INFO, 0)} info"
    )
    lines += ["", CAVEAT]
    return "\n".join(lines)
