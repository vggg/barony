"""``baron doctor`` acceptance — the guard WIRING self-test (ADR-017).

The failure this command exists to catch is silence: a project that believes it
is enforced because a persona says so, while the hook was never installed. So
these tests are mostly *mutation* tests — break one link in the chain and assert
doctor names it, with a remedy, at nonzero exit.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from baron import doctor as doctor_mod, guard as guard_mod, identity as identity_mod
from baron.cli import app

runner = CliRunner()

PERSONAS = "dev:carson,librarian:iris"


def _hook_command(dest: Path, command: str) -> None:
    """Rewrite the project's PreToolUse guard command."""
    path = dest / ".claude" / "settings.json"
    settings = json.loads(path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = command
    path.write_text(json.dumps(settings), encoding="utf-8")


def _script(path: Path, body: str) -> Path:
    """Write an executable POSIX shell script (a stand-in for an installed CLI)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _scaffold(tmp_path: Path) -> Path:
    """A `baron init` collab repo with the claude runtime kit COPIED into place.

    Copying is the step HYDRATE.md instructs and the step badminton-analyzer
    skipped: init generates the wiring under agents/<slug>/runtime/, and the
    runtime reads it from the project root. A scaffold without the copy is a
    project with no hook — which is its own test below.
    """
    dest = tmp_path / "collab"
    result = runner.invoke(
        app, ["init", "proj", "--dir", str(dest), "--personas", PERSONAS, "--no-git"]
    )
    assert result.exit_code == 0, result.output
    kit = dest / "agents" / "carson" / "runtime" / ".claude"
    shutil.copytree(kit, dest / ".claude")
    return dest


@pytest.fixture(autouse=True)
def _no_ambient_guard_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The developer's shell must not decide these verdicts."""
    monkeypatch.delenv(guard_mod.OVERRIDE_ENV, raising=False)
    monkeypatch.delenv(guard_mod.PERSONA_ENV, raising=False)


def _run(dest: Path, *extra: str):
    return runner.invoke(app, ["doctor", "--dir", str(dest), *extra])


def _by_id(dest: Path, *extra: str) -> dict[str, dict]:
    result = runner.invoke(app, ["doctor", "--dir", str(dest), "--json", *extra])
    payload = json.loads(result.stdout)
    return {c["id"]: c for c in payload["checks"]}


# --- the green path ---------------------------------------------------------------------


def test_wired_project_is_green(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    result = _run(dest)
    assert result.exit_code == 0, result.output
    checks = _by_id(dest)
    # Everything is PASS except the deliberately-INFO checks: the evidence sink
    # (fail-open by design) and the platform layer (not baron's to fix).
    for cid, check in checks.items():
        expected = (
            doctor_mod.INFO
            if cid in ("override-log", "platform-layer")
            else doctor_mod.PASS
        )
        assert check["status"] == expected, (cid, check)


def test_caveat_is_printed(tmp_path: Path) -> None:
    """Doctor must never let a green run read as 'enforcement happened'."""
    dest = _scaffold(tmp_path)
    result = _run(dest)
    assert "verifies WIRING, not invocation" in result.output
    assert "CANNOT observe whether" in result.output
    # Both narrower bounds are stated too, not just the headline one.
    assert "measure the executable the hook NAMES" in result.output
    assert "DOCTOR's PATH, not the runtime's" in result.output


def test_json_is_machine_readable(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    result = runner.invoke(app, ["doctor", "--dir", str(dest), "--json"])
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["verifies"] == "wiring"
    assert "verifies WIRING, not invocation" in payload["caveat"]
    assert payload["summary"]["fail"] == 0
    ids = [c["id"] for c in payload["checks"]]
    assert ids == [
        "cli-on-path",
        "hook-configured",
        "hook-matcher",
        "persona-file",
        "rules-artifact",
        "enforcement-path",
        "fail-closed",
        "override-env",
        "override-log",
        "platform-layer",
    ]


# --- the badminton failure mode ----------------------------------------------------------


def test_missing_settings_fails_loudly(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    (dest / ".claude" / "settings.json").unlink()
    result = _run(dest)
    assert result.exit_code == 1
    assert "FAIL" in result.output
    checks = _by_id(dest)
    hook = checks["hook-configured"]
    assert hook["status"] == doctor_mod.FAIL
    assert "no `baron guard` PreToolUse hook" in hook["detail"]
    assert "INSTRUCTED, not enforced" in hook["detail"]
    assert hook["remedy"]


def test_uncopied_kit_is_named_in_the_remedy(tmp_path: Path) -> None:
    """A scaffold whose runtime kit was never copied — the badminton shape."""
    dest = tmp_path / "collab"
    result = runner.invoke(
        app, ["init", "proj", "--dir", str(dest), "--personas", PERSONAS, "--no-git"]
    )
    assert result.exit_code == 0, result.output
    assert not (dest / ".claude" / "settings.json").exists()
    hook = _by_id(dest)["hook-configured"]
    assert hook["status"] == doctor_mod.FAIL
    assert "agents/carson/runtime/.claude/settings.json" in hook["remedy"]
    assert "never installed" in hook["remedy"]


def test_hook_present_but_not_baron_guard(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    (dest / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "Bash", "hooks": [{"type": "command", "command": "true"}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    hook = _by_id(dest)["hook-configured"]
    assert hook["status"] == doctor_mod.FAIL
    assert "no PreToolUse hook invokes `baron guard`" in hook["detail"]


def test_malformed_settings_json_is_a_fail_not_a_crash(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    (dest / ".claude" / "settings.json").write_text("{ not json", encoding="utf-8")
    result = _run(dest)
    assert result.exit_code == 1, result.output
    assert _by_id(dest)["hook-configured"]["status"] == doctor_mod.FAIL


# --- partial wiring ----------------------------------------------------------------------


def test_narrow_matcher_is_a_hole_in_enforcement(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    path = dest / ".claude" / "settings.json"
    settings = json.loads(path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["matcher"] = "Write"
    path.write_text(json.dumps(settings), encoding="utf-8")
    result = _run(dest)
    assert result.exit_code == 1
    matcher = _by_id(dest)["hook-matcher"]
    assert matcher["status"] == doctor_mod.FAIL
    for tool in ("Bash", "Edit", "NotebookEdit"):
        assert tool in matcher["detail"]


def test_matcher_coverage_is_regex_search_not_equality(tmp_path: Path) -> None:
    """`Edit|Write` covers NotebookEdit — matchers are regexes, and doctor reads
    them the permissive way (re.search), the same way the runtime does. Being
    wrongly loud about a correct matcher would be its own honesty failure."""
    assert doctor_mod._uncovered_tools(("Edit|Write",)) == ["Bash"]
    assert doctor_mod._uncovered_tools(("Bash|Edit|Write|NotebookEdit",)) == []
    assert doctor_mod._uncovered_tools(("Bash", "Edit|Write|NotebookEdit")) == []
    # An invalid regex covers nothing rather than crashing the run.
    assert doctor_mod._uncovered_tools(("[unclosed",)) == list(doctor_mod.GOVERNED_TOOLS)


def test_absent_matcher_covers_every_tool(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    path = dest / ".claude" / "settings.json"
    settings = json.loads(path.read_text(encoding="utf-8"))
    del settings["hooks"]["PreToolUse"][0]["matcher"]
    path.write_text(json.dumps(settings), encoding="utf-8")
    assert _by_id(dest)["hook-matcher"]["status"] == doctor_mod.PASS


def test_matcher_unknown_when_no_hook(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    (dest / ".claude" / "settings.json").unlink()
    assert _by_id(dest)["hook-matcher"]["status"] == doctor_mod.UNKNOWN


# --- persona -----------------------------------------------------------------------------


def test_corrupt_persona_fails_rather_than_crashes(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    (dest / "agents" / "carson" / "persona.yaml").write_text(
        "capabilities: [this is a list, not a mapping]\n", encoding="utf-8"
    )
    result = _run(dest)
    assert result.exit_code == 1, result.output
    persona = _by_id(dest)["persona-file"]
    assert persona["status"] == doctor_mod.FAIL
    assert "no capabilities block" in persona["detail"]
    assert "fail-closed" in persona["remedy"]


def test_deleted_persona_fails(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    (dest / "agents" / "carson" / "persona.yaml").unlink()
    persona = _by_id(dest)["persona-file"]
    assert persona["status"] == doctor_mod.FAIL
    assert "not found" in persona["detail"]


def test_persona_file_override_wins(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    (dest / "agents" / "carson" / "persona.yaml").unlink()
    other = dest / "agents" / "iris" / "persona.yaml"
    checks = _by_id(dest, "--persona-file", str(other))
    assert checks["persona-file"]["status"] == doctor_mod.PASS
    assert "--persona-file" in checks["persona-file"]["detail"]


def test_env_persona_is_the_last_resort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = _scaffold(tmp_path)
    (dest / ".claude" / "settings.json").unlink()  # no hook -> no declared persona
    monkeypatch.setenv(
        guard_mod.PERSONA_ENV, str(dest / "agents" / "carson" / "persona.yaml")
    )
    persona = _by_id(dest)["persona-file"]
    assert persona["status"] == doctor_mod.PASS
    assert guard_mod.PERSONA_ENV in persona["detail"]


def test_no_persona_anywhere_is_unknown(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    (dest / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash|Edit|Write|NotebookEdit",
                            "hooks": [{"type": "command", "command": "baron guard"}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    checks = _by_id(dest)
    assert checks["persona-file"]["status"] == doctor_mod.UNKNOWN
    assert checks["hook-configured"]["status"] == doctor_mod.PASS


# --- check 6: the enforcement path is really exercised -------------------------------------
#
# The load-bearing property, and the one a previous revision got wrong: checks 6
# and 7 must measure THE EXECUTABLE THE HOOK NAMES, not the `baron` package that
# happens to be importable in doctor's own interpreter. A project can be wired to
# a stale, shadowed or hand-rolled `baron` — that is the badminton shape — and an
# in-process probe is structurally blind to it, because it exercises the same
# object the bug assumes is fine.


def test_probe_runs_the_hooks_own_executable_by_default(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    payload = json.loads(
        runner.invoke(app, ["doctor", "--dir", str(dest), "--json"]).stdout
    )
    assert payload["probe_mode"] == "subprocess"
    assert payload["probe_argv"], payload
    assert Path(payload["probe_argv"][0]).name in ("baron", "baron.exe")
    detail = {c["id"]: c for c in payload["checks"]}["enforcement-path"]["detail"]
    assert "the command Claude Code would start does block" in detail


def test_a_fake_baron_that_allows_everything_is_caught(tmp_path: Path) -> None:
    """THE regression test.

    A hook wired to a `baron` that answers `--version` happily but exits 0 on
    `guard` is a project that is INSTRUCTED while reporting itself enforced. No
    monkeypatch can catch this — patching `baron.guard.process` patches the very
    module the in-process probe would use. Only spawning the hook's own command
    sees it.
    """
    dest = _scaffold(tmp_path)
    fake = _script(
        tmp_path / "fakebin" / "baron",
        'case "$1" in\n'
        '  --version) echo "baron, version 9.9.9"; exit 0 ;;\n'
        "  guard)     cat >/dev/null; exit 0 ;;\n"  # allows everything, silently
        "esac\n"
        "exit 0\n",
    )
    persona = dest / "agents" / "carson" / "persona.yaml"
    _hook_command(dest, f"{fake} guard --persona-file {persona}")

    result = _run(dest)
    assert result.exit_code == 1, result.output
    checks = _by_id(dest)
    # The executable itself looks fine — that is exactly why this is dangerous.
    assert checks["cli-on-path"]["status"] == doctor_mod.PASS
    assert checks["hook-configured"]["status"] == doctor_mod.PASS
    enforcement = checks["enforcement-path"]
    assert enforcement["status"] == doctor_mod.FAIL
    assert "does NOT block" in enforcement["detail"]
    assert str(fake) in enforcement["detail"]
    assert enforcement["remedy"]
    assert checks["fail-closed"]["status"] == doctor_mod.FAIL


def test_a_fake_baron_that_blocks_without_a_guard_reason_is_caught(
    tmp_path: Path,
) -> None:
    """Exit 2 with no `baron guard:` stderr is not the guard blocking."""
    dest = _scaffold(tmp_path)
    fake = _script(
        tmp_path / "fakebin" / "baron",
        'case "$1" in\n'
        "  --version) echo v; exit 0 ;;\n"
        "esac\n"
        "cat >/dev/null\n"
        "exit 2\n",
    )
    _hook_command(dest, f"{fake} guard --persona-file x.yaml")
    checks = _by_id(dest)
    assert checks["enforcement-path"]["status"] == doctor_mod.FAIL
    assert "no `baron guard:` reason" in checks["enforcement-path"]["detail"]


def test_a_fake_baron_that_crash_denies_is_caught(tmp_path: Path) -> None:
    """Exit 2 via the internal-error path is an outage, not enforcement."""
    dest = _scaffold(tmp_path)
    fake = _script(
        tmp_path / "fakebin" / "baron",
        'case "$1" in\n'
        "  --version) echo v; exit 0 ;;\n"
        "esac\n"
        "cat >/dev/null\n"
        'echo "baron guard: DENY (internal error, fail closed) — boom" >&2\n'
        "exit 2\n",
    )
    _hook_command(dest, f"{fake} guard --persona-file x.yaml")
    checks = _by_id(dest)
    assert checks["enforcement-path"]["status"] == doctor_mod.FAIL
    assert "internal-error fail-closed path" in checks["enforcement-path"]["detail"]


def test_a_fake_baron_that_errors_out_is_caught(tmp_path: Path) -> None:
    """Any non-2 exit is 'no objection' to Claude Code — so it is a FAIL."""
    dest = _scaffold(tmp_path)
    fake = _script(
        tmp_path / "fakebin" / "baron",
        'case "$1" in\n'
        "  --version) echo v; exit 0 ;;\n"
        "esac\n"
        "cat >/dev/null\n"
        'echo "ImportError: no module named baron" >&2\n'
        "exit 1\n",
    )
    _hook_command(dest, f"{fake} guard --persona-file x.yaml")
    checks = _by_id(dest)
    assert checks["enforcement-path"]["status"] == doctor_mod.FAIL
    assert "not 2" in checks["enforcement-path"]["detail"]


def test_enforcement_probe_is_independent_of_project_personas(tmp_path: Path) -> None:
    """A project whose personas grant everything must still get a real probe."""
    dest = _scaffold(tmp_path)
    persona = dest / "agents" / "carson" / "persona.yaml"
    text = persona.read_text(encoding="utf-8")
    assert "write_code" in text  # the scaffolded dev can write code
    assert _by_id(dest)["enforcement-path"]["status"] == doctor_mod.PASS


# --- the in-process fallback, and its admitted bound ----------------------------------------


def _force_in_process(dest: Path) -> None:
    """No resolvable hook executable -> checks 6/7 fall back to the module."""
    _hook_command(dest, "/nonexistent/bin/baron guard --persona-file p.yaml")


def test_fallback_is_in_process_and_says_so(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    _force_in_process(dest)
    payload = json.loads(
        runner.invoke(app, ["doctor", "--dir", str(dest), "--json"]).stdout
    )
    assert payload["probe_mode"] == "in-process"
    assert payload["probe_argv"] == []
    checks = {c["id"]: c for c in payload["checks"]}
    detail = checks["enforcement-path"]["detail"]
    assert "in-process `baron.guard` module ONLY" in detail
    assert "nothing about the command the hook would run" in detail
    # ...and it must not claim the hook's command blocks.
    assert "the command Claude Code would start does block" not in detail
    # The render also announces the degraded mode.
    assert "in-process" in _run(dest).output


def test_in_process_fallback_still_catches_a_broken_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fallback is not decorative either — it just measures less."""
    dest = _scaffold(tmp_path)
    _force_in_process(dest)
    monkeypatch.setattr(guard_mod, "process", lambda *_a, **_k: (0, ""))
    result = _run(dest)
    assert result.exit_code == 1, result.output
    checks = _by_id(dest)
    assert checks["enforcement-path"]["status"] == doctor_mod.FAIL
    assert "does NOT block" in checks["enforcement-path"]["detail"]
    assert checks["fail-closed"]["status"] == doctor_mod.FAIL


# --- wrapper hook commands (`uv run baron guard …`) -----------------------------------------


def test_wrapper_command_resolves_the_launcher_not_bare_baron(tmp_path: Path) -> None:
    """`uv run baron` must resolve `uv`, not `baron`.

    Resolving the `baron` token directly is a false FAIL on a correctly-wired
    project: `baron` may exist only inside the environment `uv run` creates.
    """
    wiring = doctor_mod.HookWiring(
        None, (), "uv run baron guard --persona-file p.yaml", ("Bash",), None
    )
    exe = doctor_mod.resolve_hook_exe(wiring, tmp_path)
    assert exe.argv == ("uv", "run", "baron")
    assert exe.launcher == "uv"
    assert exe.wrapper == "uv"
    assert exe.prefixed is True


def test_wrapper_command_is_probed_end_to_end(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    persona = dest / "agents" / "carson" / "persona.yaml"
    # A stand-in `uv` that drops its "run" argument and execs the rest.
    fake_uv = _script(tmp_path / "fakebin" / "uv", 'shift\nexec "$@"\n')
    _hook_command(dest, f"{fake_uv} run baron guard --persona-file {persona}")

    result = _run(dest)
    assert result.exit_code == 0, result.output
    checks = _by_id(dest)
    assert checks["cli-on-path"]["status"] == doctor_mod.PASS
    assert "'uv' wrapper" in checks["cli-on-path"]["detail"]
    assert checks["enforcement-path"]["status"] == doctor_mod.PASS
    assert "run baron guard" in checks["enforcement-path"]["detail"]


def test_wrapper_that_cannot_produce_a_version_is_unknown_not_fail(
    tmp_path: Path,
) -> None:
    """Doctor's value depends on people believing it when it shouts (ADR-017 §3.6).

    A resolvable wrapper that will not answer `--version` here may be a broken
    hook or an environment doctor cannot materialise. It will not guess FAIL.
    """
    dest = _scaffold(tmp_path)
    fake_uv = _script(
        tmp_path / "fakebin" / "uv",
        'echo "error: no `uv.lock` found" >&2\nexit 2\n',
    )
    _hook_command(dest, f"{fake_uv} run baron guard --persona-file p.yaml")
    cli_check = _by_id(dest)["cli-on-path"]
    assert cli_check["status"] == doctor_mod.UNKNOWN
    assert "could not get a version out of it here" in cli_check["detail"]
    assert cli_check["remedy"]


def test_unrecognised_prefix_is_not_treated_as_a_wrapper(tmp_path: Path) -> None:
    wiring = doctor_mod.HookWiring(
        None, (), "timeout 5 baron guard --persona-file p.yaml", ("Bash",), None
    )
    exe = doctor_mod.resolve_hook_exe(wiring, tmp_path)
    assert exe.wrapper is None
    assert exe.prefixed is True
    assert "unrecognised prefix" in exe.source


def test_project_dir_token_is_expanded_in_the_executable(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    fake = _script(dest / "bin" / "baron", "echo v\nexit 0\n")
    wiring = doctor_mod.HookWiring(
        None, (), '${CLAUDE_PROJECT_DIR}/bin/baron guard --persona-file p', ("Bash",), None
    )
    exe = doctor_mod.resolve_hook_exe(wiring, dest)
    assert exe.resolved == str(fake)
    assert exe.which_used is False


# --- ADR-004 §2.3: the fail-closed policy, pinned ------------------------------------------


def test_fail_closed_policy_is_pinned_adr_004_s2_3(tmp_path: Path) -> None:
    """The runtime pin behind roadmap.md's fail-open/fail-closed checkbox.

    ADR-004 §2.3 ("Fail-closed, with a logged escape hatch") says a guard that
    cannot evaluate must DENY. `guard.process` implements it on two paths
    (GuardError and the bare-Exception net); this asserts the policy holds
    end-to-end in an installed baron, which is what the 2026-08-08 hands-on run
    measured empirically. See also test_guard.py::test_malformed_stdin_denies.
    """
    code, stderr_text = guard_mod.process("{ not json", None)
    assert code == 2
    assert "fail closed" in stderr_text

    dest = _scaffold(tmp_path)
    check = _by_id(dest)["fail-closed"]
    assert check["status"] == doctor_mod.PASS
    assert "ADR-004" in check["detail"]


def test_exported_override_is_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = _scaffold(tmp_path)
    monkeypatch.setenv(guard_mod.OVERRIDE_ENV, "just for a sec")
    result = _run(dest)
    assert result.exit_code == 1
    checks = _by_id(dest)
    assert checks["override-env"]["status"] == doctor_mod.FAIL
    assert "EVERY guard denial is allowed" in checks["override-env"]["detail"]
    # ...but the probes must still measure the MECHANISM, not the escape hatch.
    assert checks["enforcement-path"]["status"] == doctor_mod.PASS
    assert checks["fail-closed"]["status"] == doctor_mod.PASS


def test_override_env_is_restored_after_the_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = _scaffold(tmp_path)
    monkeypatch.setenv(guard_mod.OVERRIDE_ENV, "sentinel")
    doctor_mod.run(dest)
    assert os.environ[guard_mod.OVERRIDE_ENV] == "sentinel"


# --- evidence is fail-open -----------------------------------------------------------------


def test_override_log_is_info_never_fail(tmp_path: Path) -> None:
    """Evidence problems must not be reported as enforcement problems."""
    dest = _scaffold(tmp_path)
    check = _by_id(dest)["override-log"]
    assert check["status"] == doctor_mod.INFO
    assert ".baron/guard-override.log" in check["detail"]


def test_gitignored_override_log_is_flagged_but_still_info(tmp_path: Path) -> None:
    dest = tmp_path / "collab"
    result = runner.invoke(
        app, ["init", "proj", "--dir", str(dest), "--personas", PERSONAS]
    )
    assert result.exit_code == 0, result.output
    shutil.copytree(dest / "agents" / "carson" / "runtime" / ".claude", dest / ".claude")
    (dest / ".gitignore").write_text(".baron/\n", encoding="utf-8")
    check = _by_id(dest)["override-log"]
    assert check["status"] == doctor_mod.INFO
    assert "gitignored" in check["detail"]
    assert runner.invoke(app, ["doctor", "--dir", str(dest)]).exit_code == 0


# --- the executable itself ------------------------------------------------------------------


def test_unresolvable_hook_executable_fails(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    path = dest / ".claude" / "settings.json"
    settings = json.loads(path.read_text(encoding="utf-8"))
    hook = settings["hooks"]["PreToolUse"][0]["hooks"][0]
    hook["command"] = "/nonexistent/bin/baron guard --persona-file x.yaml"
    path.write_text(json.dumps(settings), encoding="utf-8")
    result = _run(dest)
    assert result.exit_code == 1
    cli_check = _by_id(dest)["cli-on-path"]
    assert cli_check["status"] == doctor_mod.FAIL
    assert "silently becomes allowed" in cli_check["detail"]


def test_rules_artifact_reported_with_its_version(tmp_path: Path) -> None:
    dest = _scaffold(tmp_path)
    check = _by_id(dest)["rules-artifact"]
    assert check["status"] == doctor_mod.PASS
    assert "capability-rules v2" in check["detail"]


def test_bad_dir_is_a_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["doctor", "--dir", str(tmp_path / "nope")])
    assert result.exit_code == 2


# --- L3: the platform layer is REPORTED, never configured (ADR-034 §4.5) -----------------


def test_platform_layer_is_info_and_never_fails_the_run(tmp_path: Path) -> None:
    """An absent platform layer is not a baron misconfiguration.

    It is INFO for two independent reasons: doctor's exit code must stay
    reproducible offline, and there is no remedy baron could offer — building
    the wall crosses ADR-007.
    """
    dest = _scaffold(tmp_path)
    check = _by_id(dest)["platform-layer"]
    assert check["status"] == doctor_mod.INFO
    assert check["remedy"] == ""
    assert "never configures it" in check["detail"]
    result = runner.invoke(app, ["doctor", "--dir", str(dest), "--json"])
    assert json.loads(result.stdout)["ok"] is True


def test_platform_layer_does_not_touch_the_network_by_default(
    tmp_path: Path, monkeypatch
) -> None:
    """The one networked check is opt-in, and says so rather than guessing.

    Asserted by making any subprocess call explode: a default doctor run must
    not reach the forge at all.
    """
    import subprocess

    monkeypatch.delenv(doctor_mod.PLATFORM_NETWORK_ENV, raising=False)
    dest = _scaffold(tmp_path)
    # A real repo on a real branch, so the check reaches the point where it
    # WOULD query the forge — otherwise this would pass for the wrong reason.
    for argv in (["init", "-b", "main"], ["add", "-A"]):
        subprocess.run(["git", *argv], cwd=dest, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t.invalid", "-c", "user.name=T", "commit", "-m", "x"],
        cwd=dest,
        check=True,
        capture_output=True,
    )

    def explode(*a, **k):  # pragma: no cover - fires only on a regression
        raise AssertionError("doctor made a network/subprocess call for branch protection")

    monkeypatch.setattr(doctor_mod, "_branch_protection", explode)
    check = doctor_mod._check_platform_layer(dest)
    assert check.status == doctor_mod.INFO
    assert doctor_mod.PLATFORM_NETWORK_ENV in check.detail
    assert "not measured" in check.detail

    # ... and with the opt-in set, it DOES consult the forge probe.
    monkeypatch.setenv(doctor_mod.PLATFORM_NETWORK_ENV, "1")
    monkeypatch.setattr(doctor_mod, "_branch_protection", lambda *a: "ABSENT on 'main'")
    assert "ABSENT on 'main'" in doctor_mod._check_platform_layer(dest).detail


def test_platform_layer_reports_signing_is_not_push_authority(tmp_path: Path) -> None:
    """ADR-033 §5: per-persona SIGNING keys are not per-persona AUTHORITY.

    Reporting "identities enrolled" without that sentence is exactly the
    over-claim the check exists to prevent.
    """
    dest = _scaffold(tmp_path)
    signers = dest / identity_mod.ALLOWED_SIGNERS
    signers.parent.mkdir(parents=True, exist_ok=True)
    signers.write_text("dara@barony ssh-ed25519 AAAA fake\n", encoding="utf-8")
    detail = doctor_mod._check_platform_layer(dest).detail
    assert "signing identity is NOT push authority" in detail
    assert "owner's forge credential" in detail
