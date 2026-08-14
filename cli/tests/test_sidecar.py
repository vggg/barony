"""Acceptance for the persona sidecar (ADR-026).

Covers the deployable unit's two halves: what `baron init` EMITS
(`agents/<slug>/sidecar.sh`, executable, trigger-aware, with the runtime
invocation as a project-owned slot) and what `baron sidecar run` DOES (sync,
sweep in ritual order, invoke the project's command once, commit + push, and the
idle guard that refuses to pay for a model call with no work).

The boundary under test throughout is ADR-007: baron never supplies the runtime
command itself — a cycle with no `--cmd` is a usage error, not a default.
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from baron import sidecar
from baron.cli import app

from conftest import init_bare, init_repo, run_git

runner = CliRunner()

_PERSONA = """\
persona: Tess
slug: tess
archetype: dev
identity:
  git_name: Tess
  git_email: tess@example.local
  commit_prefix: "tess:"
  routing_label: agent-tess
runtime:
  trigger: {trigger}
"""

_MANIFEST = """\
project: {name: sidecarfix, description: sidecar fixture}
paths: {strategy: relative, root: .}
repos:
  - {id: collab, path: ., role: collab}
backlog: {source: file, location: backlog.md, park_label: parked}
personas:
  - {slug: tess, spec: agents/tess/persona.yaml}
"""

BACKLOG = """\
# backlog

- [ ] agent-tess: wire the seam
- [ ] agent-tess: parked work <!-- parked -->
- [x] agent-tess: already done
- [ ] agent-iris: someone else's
"""


def build_collab(tmp_path: Path, *, trigger: str = "cron", remote: bool = False) -> Path:
    origin = init_bare(tmp_path / "origin.git") if remote else None
    collab = init_repo(tmp_path / "collab")
    (collab / "agents" / "tess").mkdir(parents=True)
    (collab / "agents" / "tess" / "persona.yaml").write_text(
        _PERSONA.format(trigger=trigger), encoding="utf-8"
    )
    (collab / "manifest.yaml").write_text(_MANIFEST, encoding="utf-8")
    (collab / "backlog.md").write_text(BACKLOG, encoding="utf-8")
    (collab / "CONVENTIONS.md").write_text("# conventions\n", encoding="utf-8")
    (collab / "COORDINATION.md").write_text("# coordination\n", encoding="utf-8")
    run_git(collab, "add", "-A")
    run_git(collab, "commit", "-q", "-m", "collab: bootstrap")
    if origin is not None:
        run_git(collab, "remote", "add", "origin", str(origin))
        run_git(collab, "push", "-q", "-u", "origin", "main")
    return collab


def recorder(tmp_path: Path, *, exit_code: int = 0, writes: str | None = None) -> tuple[str, Path]:
    """A stand-in runtime: records the brief it was handed on stdin, optionally
    writes a coordination artifact (what a real persona's work looks like to the
    landing step), then exits with `exit_code`."""
    record = tmp_path / "record.txt"
    script = tmp_path / "fake_runtime.py"
    script.write_text(
        "import os, pathlib, sys\n"
        f"pathlib.Path({str(record)!r}).write_text(sys.stdin.read(), encoding='utf-8')\n"
        f"w = {writes!r}\n"
        "if w:\n"
        "    p = pathlib.Path(os.environ['BARON_SIDECAR_COLLAB']) / w\n"
        "    p.parent.mkdir(parents=True, exist_ok=True)\n"
        "    p.write_text('work\\n', encoding='utf-8')\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return f"{sys.executable} {script}", record


# --- what `baron init` emits -----------------------------------------------------------


def _init(tmp_path: Path, *extra: str) -> Path:
    dest = tmp_path / "gardenkit-collab"
    result = runner.invoke(
        app,
        ["init", "gardenkit", "--dir", str(dest), "--personas",
         "dev:carson,librarian:iris", *extra],
    )
    assert result.exit_code == 0, result.output
    return dest


def test_init_emits_an_executable_sidecar_per_persona(tmp_path: Path, fixed_clock: object) -> None:
    dest = _init(tmp_path)
    for slug in ("carson", "iris"):
        script = dest / "agents" / slug / "sidecar.sh"
        assert script.is_file(), f"no sidecar for {slug}"
        assert script.stat().st_mode & stat.S_IXUSR, f"{slug}: sidecar is not executable"
        text = script.read_text(encoding="utf-8")
        assert "{{" not in text  # fully hydrated
        assert f'PERSONA="{slug}"' in text
        assert "baron sidecar run" in text and "ADR-026" in text
    # The trigger is rendered from each persona's spec (ADR-026 §6 Q2): the dev
    # archetype is interactive, the librarian's cron.
    assert "Trigger: interactive" in (dest / "agents/carson/sidecar.sh").read_text(encoding="utf-8")
    assert "Trigger: cron" in (dest / "agents/iris/sidecar.sh").read_text(encoding="utf-8")
    # Committed by init like everything else it emits.
    assert run_git(dest, "status", "--porcelain").strip() == ""


def test_sidecar_runtime_slot_is_project_owned(tmp_path: Path, fixed_clock: object) -> None:
    """claude gets a working headless default; runtimes with no known one-shot
    invocation get an empty slot the launcher refuses to guess at."""
    claude = _init(tmp_path / "a").joinpath("agents/carson/sidecar.sh").read_text(encoding="utf-8")
    assert 'RUNTIME_CMD="${BARON_SIDECAR_CMD:-claude -p' in claude
    generic = (
        _init(tmp_path / "b", "--runtime", "generic")
        .joinpath("agents/carson/sidecar.sh")
        .read_text(encoding="utf-8")
    )
    assert 'RUNTIME_CMD="${BARON_SIDECAR_CMD:-}"' in generic
    assert "PROJECT-OWNED SLOT" in generic


# --- the cycle -------------------------------------------------------------------------


def test_dry_run_reports_the_plan_without_touching_anything(tmp_path: Path) -> None:
    collab = build_collab(tmp_path)
    head = run_git(collab, "rev-parse", "HEAD").strip()
    result = runner.invoke(
        app, ["sidecar", "run", "tess", "--collab", str(collab), "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert "would invoke the runtime" in result.output
    assert "wire the seam" in result.output
    # Parked, checked and other-persona items are not this persona's work.
    assert "parked work" not in result.output
    assert "already done" not in result.output
    assert "someone else's" not in result.output
    assert run_git(collab, "rev-parse", "HEAD").strip() == head
    assert run_git(collab, "status", "--porcelain").strip() == ""


def test_idle_cycle_never_wakes_the_runtime(tmp_path: Path) -> None:
    collab = build_collab(tmp_path)
    (collab / "backlog.md").write_text("# backlog\n\n- [ ] agent-iris: not mine\n", encoding="utf-8")
    run_git(collab, "commit", "-q", "-am", "collab: drain the backlog")
    cmd, record = recorder(tmp_path)

    result = runner.invoke(
        app, ["sidecar", "run", "tess", "--collab", str(collab), "--cmd", cmd, "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["idle"] is True and payload["invoked"] is False
    assert not record.exists()  # the model was never paid for


def test_cycle_invokes_the_runtime_with_a_ritual_ordered_brief(tmp_path: Path) -> None:
    collab = build_collab(tmp_path)
    cmd, record = recorder(tmp_path)
    result = runner.invoke(
        app, ["sidecar", "run", "tess", "--collab", str(collab), "--cmd", cmd]
    )
    assert result.exit_code == 0, result.output
    brief = record.read_text(encoding="utf-8")
    assert "You are Tess (tess)" in brief
    assert "- [ ] agent-tess: wire the seam" in brief
    # check_review_feedback resolves BEFORE new work (ADR-008) — load-bearing order.
    assert brief.index("LIVE review feedback") < brief.index("backlog items")
    assert "tess: <type> | <description>" in brief  # the persona's commit prefix


def test_outcome_is_committed_and_pushed(tmp_path: Path) -> None:
    collab = build_collab(tmp_path, remote=True)
    cmd, _ = recorder(tmp_path, writes="findings/F1-seam.md")
    result = runner.invoke(
        app, ["sidecar", "run", "tess", "--collab", str(collab), "--cmd", cmd, "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["invoked"] is True and payload["exit_code"] == 0
    assert payload["committed"] is True
    assert "findings/F1-seam.md" in payload["committed_paths"]
    assert payload["pushed"] is True
    # ...and the push really landed on the origin.
    origin_head = run_git(collab, "rev-parse", "origin/main").strip()
    assert origin_head == run_git(collab, "rev-parse", "HEAD").strip()
    assert run_git(collab, "log", "-1", "--format=%s").startswith("tess: session | end")


def test_failing_runtime_still_lands_what_it_committed(tmp_path: Path) -> None:
    collab = build_collab(tmp_path)
    cmd, _ = recorder(tmp_path, exit_code=3, writes="findings/F2-partial.md")
    result = runner.invoke(
        app, ["sidecar", "run", "tess", "--collab", str(collab), "--cmd", cmd, "--json"]
    )
    assert result.exit_code == 1  # the cycle is red...
    payload = json.loads(result.output)
    assert payload["exit_code"] == 3
    assert payload["committed"] is True  # ...but the evidence is not thrown away
    assert "findings/F2-partial.md" in payload["committed_paths"]


def test_no_runtime_command_is_a_usage_error_not_a_default(tmp_path: Path) -> None:
    """ADR-007: baron does not own — and never guesses — the model invocation."""
    collab = build_collab(tmp_path)
    result = runner.invoke(
        app, ["sidecar", "run", "tess", "--collab", str(collab)], env={"BARON_SIDECAR_CMD": ""}
    )
    assert result.exit_code == 2
    assert "no runtime command" in result.output
    assert "ADR-007" in result.output


def test_unknown_persona_is_refused(tmp_path: Path) -> None:
    collab = build_collab(tmp_path)
    result = runner.invoke(app, ["sidecar", "run", "ghost", "--collab", str(collab)])
    assert result.exit_code == 2
    assert "not listed" in result.output


# --- trigger / loop form (ADR-026 §6 Q2) ------------------------------------------------


def test_trigger_comes_from_the_persona_spec_and_is_overridable() -> None:
    assert sidecar.resolve_trigger({"runtime": {"trigger": "event"}}) == "event"
    assert sidecar.resolve_trigger({}) == "interactive"  # documented default
    assert sidecar.resolve_trigger({"runtime": {"trigger": "nonsense"}}) == "interactive"
    assert sidecar.resolve_trigger({"runtime": {"trigger": "cron"}}, "event") == "event"
    with pytest.raises(sidecar.SidecarError):
        sidecar.resolve_trigger({}, "hourly")


def test_watch_is_refused_for_an_interactive_persona(tmp_path: Path) -> None:
    collab = build_collab(tmp_path, trigger="interactive")
    result = runner.invoke(
        app, ["sidecar", "run", "tess", "--collab", str(collab), "--watch", "--max-cycles", "1"]
    )
    assert result.exit_code == 2
    assert "human's session" in result.output


def test_watch_cycles_a_cron_persona_and_sleeps_between(tmp_path: Path) -> None:
    collab = build_collab(tmp_path, trigger="cron")
    cmd, record = recorder(tmp_path)
    slept: list[int] = []
    reports = sidecar.watch(
        collab,
        "tess",
        interval=42,
        max_cycles=2,
        sleep=slept.append,
        cmd=cmd,
    )
    assert len(reports) == 2 and all(r.invoked for r in reports)
    assert slept == [42]  # slept between cycles, not after the last
    assert record.exists()


def test_help_documents_the_surface() -> None:
    assert runner.invoke(app, ["sidecar", "--help"]).exit_code == 0
    assert runner.invoke(app, ["sidecar", "run", "--help"]).exit_code == 0
    # Assert the FLAGS, not the rendered help: rich wraps to the terminal width,
    # so an 80-column CI runner truncates option names a wide dev box shows whole.
    import typer.main

    command = typer.main.get_command(app).commands["sidecar"].commands["run"]
    flags = {opt for param in command.params for opt in param.opts}
    assert {
        "--cmd", "--watch", "--interval", "--max-cycles", "--timeout",
        "--trigger", "--force", "--no-push", "--dry-run", "--json", "--collab",
    } <= flags
    group = typer.main.get_command(app).commands["sidecar"]
    assert "ADR-026" in (group.help or "")  # the surface names its decision record
