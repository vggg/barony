"""``baron doctor`` acceptance — the guard WIRING self-test (ADR-017).

The failure this command exists to catch is silence: a project that believes it
is enforced because a persona says so, while the hook was never installed. So
these tests are mostly *mutation* tests — break one link in the chain and assert
doctor names it, with a remedy, at nonzero exit.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from baron import doctor as doctor_mod, guard as guard_mod
from baron.cli import app

runner = CliRunner()

PERSONAS = "dev:carson,librarian:iris"


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
    # Everything is PASS except the deliberately-INFO evidence check.
    for cid, check in checks.items():
        expected = doctor_mod.INFO if cid == "override-log" else doctor_mod.PASS
        assert check["status"] == expected, (cid, check)


def test_caveat_is_printed(tmp_path: Path) -> None:
    """Doctor must never let a green run read as 'enforcement happened'."""
    dest = _scaffold(tmp_path)
    result = _run(dest)
    assert "verifies WIRING, not invocation" in result.output
    assert "CANNOT observe whether" in result.output


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


def test_enforcement_check_fails_when_the_deny_path_stops_denying(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The load-bearing assertion: check 6 is not decorative.

    Monkeypatching guard.process to wave everything through must turn
    enforcement-path (and fail-closed) FAIL. If this test can be deleted without
    breaking anything, check 6 is theatre.
    """
    dest = _scaffold(tmp_path)
    monkeypatch.setattr(guard_mod, "process", lambda *_a, **_k: (0, ""))
    result = _run(dest)
    assert result.exit_code == 1, result.output
    checks = _by_id(dest)
    assert checks["enforcement-path"]["status"] == doctor_mod.FAIL
    assert "does NOT block" in checks["enforcement-path"]["detail"]
    assert checks["fail-closed"]["status"] == doctor_mod.FAIL


def test_enforcement_check_rejects_a_deny_that_is_really_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 2 via the internal-error path is an outage, not enforcement."""
    dest = _scaffold(tmp_path)
    monkeypatch.setattr(
        guard_mod,
        "process",
        lambda *_a, **_k: (2, "baron guard: DENY (internal error, fail closed) — boom"),
    )
    checks = _by_id(dest)
    assert checks["enforcement-path"]["status"] == doctor_mod.FAIL
    assert "internal-error fail-closed path" in checks["enforcement-path"]["detail"]


def test_enforcement_probe_is_independent_of_project_personas(tmp_path: Path) -> None:
    """A project whose personas grant everything must still get a real probe."""
    dest = _scaffold(tmp_path)
    persona = dest / "agents" / "carson" / "persona.yaml"
    text = persona.read_text(encoding="utf-8")
    assert "write_code" in text  # the scaffolded dev can write code
    assert _by_id(dest)["enforcement-path"]["status"] == doctor_mod.PASS


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
    import os

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
    assert "capability-rules v1" in check["detail"]


def test_bad_dir_is_a_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["doctor", "--dir", str(tmp_path / "nope")])
    assert result.exit_code == 2
