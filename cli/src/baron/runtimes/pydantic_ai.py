"""pydantic-ai runtime adapter: persona.yaml → a live, guarded ``Agent``.

Hydrates a runtime-neutral persona spec onto pydantic-ai + the official
capability library pydantic-ai-harness, at the fidelity documented in
``adapters/pydantic-ai/HYDRATE.md`` (the emitted-project copy of which is the
user-facing contract):

- **Instructions** composed from the persona's identity, scope, session
  ritual, and capability allow/deny lines.
- **Whole-tool denials via capability omission** — no shell-granting verb
  means NO ``Shell`` capability at all; no write verb at all means a natively
  read-only ``FileSystem`` (``protected_patterns=['*', '**/*']`` — the
  harness itself rejects writes to protected paths).
- **Sub-tool denials via in-process interception** — a guard capability
  implements ``AbstractCapability.before_tool_execute`` (the documented
  interception seam: raising ``ModelRetry`` vetoes the call and feeds the
  reason to the model) and evaluates every shell command / file write through
  :mod:`baron.guard`'s evaluators, which consume the versioned
  ``capability-rules.v1.yaml`` artifact (:mod:`baron.rules`) — the SAME rule
  table the Claude Code PreToolUse hook uses, hence identical decisions.

API facts verified against the tested pins — **harness 0.10.0 / pydantic-ai-slim
2.14.1–2.19.x** (the ``barony[pydantic-ai]`` extra pins harness ``>=0.10,<0.11``
+ slim ``>=2.14.1,<3``; https://pydantic.dev/docs/ai/harness/,
https://pydantic.dev/docs/ai/overview/):

- ``Agent(model, instructions=..., capabilities=[...])``.
- ``pydantic_ai.capabilities.AbstractCapability.before_tool_execute(ctx, *,
  call, tool_def, args)`` — "Raise ModelRetry to skip execution and ask the
  model to redo the tool call."
- harness ``FileSystem(root_dir, protected_patterns=...)`` — protected paths
  are read-only (writes rejected); tools: read_file, write_file, edit_file,
  list_directory, search_files, find_files, create_directory, file_info.
- harness ``Shell(cwd, allowed_commands=..., denied_commands=...,
  denied_operators=...)`` — ``allowed_commands`` is an executable-name allowlist
  and is mutually exclusive with ``denied_commands`` (the harness raises if both
  are non-empty; its ``denied_commands`` DEFAULTS to a destructive-command list,
  so an allowlist must pass ``denied_commands=[]``). ``denied_operators`` blocks
  shell operators by substring (``>`` also matches ``>>``). Tools: run_command
  (signature ``(command: str, *, timeout_seconds: float | None)``),
  start_command, check_command, stop_command.
- harness ``pydantic_ai_harness.context.RepoContext(workspace_dir=...,
  filenames=..., autoload_instructions=...)`` — auto-loads CLAUDE.md/AGENTS.md
  from the working dir (additive; wired only when a ``collab_root`` is given).
- ``pydantic_ai.models.test.TestModel`` / the ``"test"`` model string run
  fully offline (used by the test suite; no API keys).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:
    from pydantic_ai import Agent, ModelRetry
    from pydantic_ai.capabilities import AbstractCapability
    from pydantic_ai_harness import FileSystem, Shell
except ImportError as exc:  # pragma: no cover - exercised via subprocess test
    raise ImportError(
        "baron's pydantic-ai runtime adapter requires the optional extra. "
        "Install it with:  pip install 'barony[pydantic-ai]'  "
        "(or: uv tool install './cli[pydantic-ai]' from the bootstrap repo). "
        f"Missing dependency: {exc.name or exc}"
    ) from exc

# RepoContext is an additive read-context capability (auto-loads CLAUDE.md /
# AGENTS.md). It is optional per HYDRATE.md's "additive, not required" framing:
# a harness without it simply omits the layer, so import failure is not fatal.
try:
    from pydantic_ai_harness.context import RepoContext
except ImportError:  # pragma: no cover - older/newer harness without context
    RepoContext = None  # type: ignore[assignment,misc]

from .. import guard
from ..guard import GuardPersona

#: Verbs whose *grant* needs the shell capability (the adapter capability
#: map's `shell` Grants rows — adapters/pydantic-ai/HYDRATE.md).
SHELL_VERBS: frozenset[str] = frozenset(
    {"open_pr", "run_tests", "merge_pr", "push_main", "force_push"}
)
#: Verbs whose *grant* needs file-write tools (`write` Grants rows).
WRITE_VERBS: frozenset[str] = frozenset(
    {"write_code", "write_path", "edit_other_personas"}
)
#: Everything read-only: the harness rejects writes to protected paths, so
#: protecting every path makes FileSystem natively read-only.
READONLY_PROTECTED_PATTERNS: tuple[str, ...] = ("*", "**/*")
#: Common test runners seeded into Shell.denied_commands when `run_tests` is
#: DENIED (adapter policy on top of the instructed-only baseline — the rules
#: artifact deliberately defines no run_tests detection).
TEST_RUNNER_COMMANDS: tuple[str, ...] = ("pytest", "tox", "nox", "unittest")
#: Least-privilege Shell allowlist for a persona whose ONLY shell-implying grant
#: is `run_tests` (e.g. a reviewer): the shell is restricted to test-runner
#: executables. The harness matches the executable name (``tokens[0]``) exactly,
#: so `python -m pytest` / `make test` are DELIBERATELY EXCLUDED — allowing
#: `python`/`make` would re-open a general-purpose interpreter/runner and defeat
#: least privilege. A run_tests-only persona invokes the runner directly
#: (`pytest ...`). Superset of TEST_RUNNER_COMMANDS.
TEST_RUNNER_ALLOWLIST: tuple[str, ...] = (
    "pytest",
    "py.test",
    "tox",
    "nox",
    "unittest",
    "coverage",
)
#: Shell operators blocked on EVERY hydrated Shell. Redirects and pipes are the
#: out-of-root write / exfil vector the static guard cannot inspect (it splits
#: on these operators and checks segments, but a `>` redirect writes a file the
#: guard never sees as a write tool). The harness denies operators by substring,
#: so `>` also catches `>>`, `2>`, `&>`.
SHELL_DENIED_OPERATORS: tuple[str, ...] = (">", ">>", "|")

#: FileSystem tools that write; their path argument is checked by the guard.
_WRITE_TOOLS: frozenset[str] = frozenset({"write_file", "edit_file", "create_directory"})
_SHELL_COMMAND_TOOLS: frozenset[str] = frozenset({"run_command", "start_command"})


class HydrationError(ValueError):
    """The persona spec cannot be hydrated (missing/invalid fields)."""


def _load_yaml(persona_file: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(persona_file.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise HydrationError(f"cannot read persona file {persona_file}: {exc}") from exc
    if not isinstance(data, dict):
        raise HydrationError(f"{persona_file}: persona is not a YAML mapping")
    return data


_ALLOW_LINES = {
    "read_code": "You may read the code repo.",
    "read_collab": "You may read the collab repo.",
    "write_code": "You may create and modify code and tests.",
    "open_pr": "You may open pull requests.",
    "run_tests": "You may run the test/coverage suite.",
    "merge_pr": "You may merge pull requests.",
    "push_main": "You may push directly to the default branch.",
    "force_push": "You may force-push.",
    "edit_other_personas": "You may edit other personas' spec files.",
}
_DENY_LINES = {
    "read_code": "Never read the code repo.",
    "read_collab": "Never read the collab repo.",
    "write_code": "Never create or modify code (report via your allowed scopes instead).",
    "open_pr": "Never open a pull request (hand off instead).",
    "run_tests": "Never run the test suite.",
    "merge_pr": "Never merge a pull request.",
    "push_main": "Never push directly to the default branch (PRs only).",
    "force_push": "Never force-push, ever.",
    "edit_other_personas": "Never edit another persona's spec files.",
}
# NOTE: every token in schemas.RITUAL_TOKENS must have a line here — a missing one
# degrades to the bare token name and the rule silently disappears from this runtime.
# Guarded by cli/tests/test_schemas.py::test_every_ritual_token_renders_on_every_runtime.
_RITUAL_LINES = {
    "sync_repos": "Bring every configured repo up to date (pull each repo with a remote).",
    "read_conventions": "Read the collab repo's CONVENTIONS.md and COORDINATION.md.",
    "check_handoffs": "Check _handoff/ for open items addressed to you or `all`.",
    "check_review_feedback": (
        "Before claiming new work, sweep your open PRs: compare each latest verdict "
        "comment's head SHA to the PR's current head, and act on the verdicts that are "
        "LIVE (SHA matches). A verdict at an older SHA is void and needs a re-review. "
        "Never treat a review-state label as the evidence."
    ),
    "check_backlog": "Read the project backlog (source per the manifest).",
}


def _capability_lines(items: object, table: dict[str, str], scope_fmt: str) -> list[str]:
    lines: list[str] = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            lines.append(table.get(item, item))
        elif isinstance(item, dict) and len(item) == 1:
            ((verb, scopes),) = item.items()
            if verb == "write_path":
                rendered = ", ".join(
                    f"{s}/" for s in (scopes if isinstance(scopes, list) else [scopes])
                )
                lines.append(scope_fmt.format(scopes=rendered))
    return lines


def compose_instructions(spec: dict[str, Any], persona_file: Path) -> str:
    """Render the persona body: identity, scope, ritual, allow/deny lines.

    Same shape as the other adapters' persona bodies (claude / code-puppy
    HYDRATE.md step 3): honest about what is enforced vs. instructed.
    """
    name = str(spec.get("persona", "")).strip()
    archetype = str(spec.get("archetype", "")).strip()
    identity = spec.get("identity") or {}
    scope = spec.get("scope") or {}
    caps = spec.get("capabilities") or {}
    if not name or not isinstance(identity, dict) or not isinstance(caps, dict):
        raise HydrationError(f"{persona_file}: persona/identity/capabilities missing")

    focus = scope.get("focus") if isinstance(scope, dict) else None
    ritual = spec.get("session_ritual")
    allow_lines = _capability_lines(
        caps.get("allow"), _ALLOW_LINES, "You may write these collab scopes: {scopes}."
    )
    deny_lines = _capability_lines(
        caps.get("deny"), _DENY_LINES, "Never write these collab scopes: {scopes}."
    )

    parts = [
        f"You are {name}, the {archetype or 'project'} persona for this project.",
        "",
        str(scope.get("summary", "")).strip() if isinstance(scope, dict) else "",
        "",
        "## Identity",
        f"- Git author: {identity.get('git_name', '')} / {identity.get('git_email', '')}",
        f"- Commit prefix: {identity.get('commit_prefix', '')}",
        f"- Routing label: {identity.get('routing_label', '')}",
        "Before committing, set per-repo git config:",
        f'  git config user.name "{identity.get("git_name", "")}"',
        f'  git config user.email "{identity.get("git_email", "")}"',
        "",
        "## Scope",
    ]
    parts += [f"- {f}" for f in focus or []]
    parts += ["", "## Session-start ritual (every session, in order)"]
    parts += [
        f"- {_RITUAL_LINES.get(str(tok), str(tok))}"
        for tok in (ritual if isinstance(ritual, list) else [])
    ]
    parts += ["", "## What you may do"]
    parts += [f"- {line}" for line in allow_lines]
    parts += [
        "",
        "## What never happens (denials are ENFORCED in-process by the baron guard"
        " capability for git/write operations; the rest is on you)",
    ]
    parts += [f"- {line}" for line in deny_lines]
    parts += [
        "- Never git add -A / git add . (stage only intended files; avoids leaking secrets).",
        "",
        f"(Generated from {persona_file.name}; the persona.yaml is canonical.)",
    ]
    return "\n".join(p for p in parts if p is not None)


# --- the in-process guard capability ---------------------------------------------------


@dataclass
class BaronGuardCapability(AbstractCapability):
    """Vetoes tool calls that map to capability verbs the persona lacks.

    Consumes the SAME rule table as ``baron guard`` (the packaged
    ``capability-rules.v1.yaml``, via :mod:`baron.guard`'s evaluators), so a
    persona behaves identically under Claude Code's PreToolUse hook and under
    this in-process hook. Denials raise ``ModelRetry`` — the documented veto:
    execution is skipped and the reason is fed back to the model, mirroring
    the Claude hook's exit-2 + stderr contract.
    """

    persona: GuardPersona
    root: Path = field(default_factory=Path.cwd)

    def check(self, tool_name: str, args: dict[str, Any]) -> str | None:
        """Return a denial reason for this tool call, or None to allow.

        Pure decision logic (unit-testable without a run context).
        """
        if tool_name in _SHELL_COMMAND_TOOLS:
            command = str(args.get("command") or "")
            decision = guard.evaluate_bash(command, self.root, self.persona)
            if not decision.allowed:
                return decision.reason
        elif tool_name in _WRITE_TOOLS:
            raw = str(args.get("path") or "")
            target = Path(raw)
            if not target.is_absolute():
                target = self.root / target
            decision = guard.evaluate_write(
                tool_name, {"file_path": str(target)}, self.root, self.persona
            )
            if not decision.allowed:
                return decision.reason
        return None

    async def before_tool_execute(self, ctx, *, call, tool_def, args):  # type: ignore[override]
        tool_args = args if isinstance(args, dict) else {}
        reason = self.check(call.tool_name, tool_args)
        if reason is not None:
            persona_name = self.persona.slug or "persona"
            raise ModelRetry(
                f"baron guard: DENY {call.tool_name} for persona '{persona_name}'\n"
                f"  {reason}\n"
                "Route the work through a persona that holds the capability, or "
                "hand off to the owner."
            )
        return args


# --- hydration plan --------------------------------------------------------------------


@dataclass(frozen=True)
class HydrationPlan:
    """The capability configuration `build_agent` derived from one persona."""

    slug: str
    instructions: str
    filesystem: FileSystem
    shell: Shell | None
    guard_capability: BaronGuardCapability
    model: str | Any
    repo_context: AbstractCapability | None = None

    @property
    def capabilities(self) -> list[AbstractCapability]:
        caps: list[AbstractCapability] = [self.filesystem]
        if self.shell is not None:
            caps.append(self.shell)
        if self.repo_context is not None:
            caps.append(self.repo_context)
        caps.append(self.guard_capability)
        return caps


def plan(
    persona_file: Path,
    collab_root: Path | None = None,
    model: str | Any | None = None,
) -> HydrationPlan:
    """Derive the capability plan for one persona (no Agent constructed yet)."""
    persona_file = Path(persona_file)
    spec = _load_yaml(persona_file)
    try:
        gp = guard.load_persona(persona_file)
    except guard.GuardError as exc:
        raise HydrationError(str(exc)) from exc
    root = Path(collab_root) if collab_root is not None else Path.cwd()

    # write_path is parametric: allow and deny legitimately coexist with
    # different scopes, so membership in `allow` is the write signal there
    # (mirrors guard.evaluate_write); plain verbs use grants().
    has_write = (
        gp.grants("write_code")
        or gp.grants("edit_other_personas")
        or "write_path" in gp.allow
    )
    # Broad "dev" write signals a persona that plausibly needs a general shell
    # (build tools, linters, git staging) — distinct from the narrow write_path
    # ledger scopes a reviewer holds, which use FileSystem, not Shell. Only the
    # former should keep a broad shell; a run_tests-only reviewer gets a
    # test-runner allowlist even when it may also write findings/_handoff.
    has_dev_write = gp.grants("write_code") or gp.grants("edit_other_personas")
    shell_verbs = {v for v in SHELL_VERBS if gp.grants(v)}

    # FileSystem: always present (reads); natively read-only when the persona
    # holds no write verb at all (whole-tool denial by configuration).
    if has_write:
        filesystem = FileSystem(root_dir=root)
    else:
        filesystem = FileSystem(
            root_dir=root, protected_patterns=list(READONLY_PROTECTED_PATTERNS)
        )

    # Shell: whole-tool omission when no shell verb is granted. Otherwise least
    # privilege, driven by the persona's actual verbs:
    #   * ONLY shell need is run_tests (a reviewer shape, no dev write verbs) ->
    #     an allowlisted shell restricted to test runners. Without this, such a
    #     persona got a FULL shell (curl/rm/arbitrary git push all passed, since
    #     the guard only vetoes 3 git sub-verbs). allowed_commands is mutually
    #     exclusive with denied_commands, so we pass denied_commands=[].
    #   * broader shell verbs (dev with write_code/open_pr) -> keep the broad
    #     shell (its work needs it) but block redirect/pipe operators so a `>`
    #     redirect can't write out of root behind the guard's back. A denied
    #     run_tests still seeds denied_commands with common test runners.
    shell: Shell | None = None
    if shell_verbs:
        if shell_verbs == {"run_tests"} and not has_dev_write:
            shell = Shell(
                cwd=root,
                allowed_commands=list(TEST_RUNNER_ALLOWLIST),
                denied_commands=[],  # allow/deny lists are mutually exclusive
                denied_operators=list(SHELL_DENIED_OPERATORS),
            )
        else:
            denied_commands: list[str] = []
            if "run_tests" in gp.deny:
                denied_commands = list(TEST_RUNNER_COMMANDS)
            shell = Shell(
                cwd=root,
                denied_commands=denied_commands,
                denied_operators=list(SHELL_DENIED_OPERATORS),
            )

    # RepoContext: additive read-context layer that auto-loads CLAUDE.md /
    # AGENTS.md from the working copy. Wired ONLY when a collab_root is given
    # (per HYDRATE.md's "additive, not required"); guarded against harness API
    # drift with a clean fallback (the persona is already injected as
    # instructions, so its absence never changes governance behavior).
    repo_context: AbstractCapability | None = None
    if collab_root is not None and RepoContext is not None:
        try:
            repo_context = RepoContext(
                workspace_dir=root,
                filenames=("CLAUDE.md", "AGENTS.md"),
                autoload_instructions=True,
            )
        except Exception:  # pragma: no cover - API-drift guard, non-fatal
            repo_context = None

    resolved_model: str | Any | None = model
    if resolved_model is None:
        runtime = spec.get("runtime") or {}
        hint = runtime.get("model_hint") if isinstance(runtime, dict) else None
        resolved_model = str(hint) if hint else "test"

    return HydrationPlan(
        slug=gp.slug or persona_file.stem,
        instructions=compose_instructions(spec, persona_file),
        filesystem=filesystem,
        shell=shell,
        guard_capability=BaronGuardCapability(persona=gp, root=root),
        model=resolved_model,
        repo_context=repo_context,
    )


def build_agent(
    persona_file: Path,
    collab_root: Path | None = None,
    model: str | Any | None = None,
) -> Agent:
    """Hydrate ``persona.yaml`` into a live, guarded ``pydantic_ai.Agent``.

    ``model`` accepts a pydantic-ai model string (``"anthropic:..."``) or a
    Model instance; defaults to the persona's ``runtime.model_hint``, else the
    offline ``"test"`` model (swap it for real work).
    """
    p = plan(persona_file, collab_root=collab_root, model=model)
    resolved = p.model
    if resolved == "test":
        # The bare "test" model string means TestModel(call_tools='all'),
        # which CALLS every registered tool with schema-generated args — a
        # placeholder smoke run would really write files / run commands.
        # The offline placeholder must be inert: no tool calls.
        from pydantic_ai.models.test import TestModel

        resolved = TestModel(call_tools=[])
    return Agent(
        resolved,
        name=p.slug,
        instructions=p.instructions,
        capabilities=p.capabilities,
    )
