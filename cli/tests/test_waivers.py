"""Waivers acceptance: a waived red shows as warn with the reason; an expired
waiver stops matching (the red resurfaces) AND is reported as its own warn."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from baron.cli import app

from conftest import init_repo, run_git

runner = CliRunner()


def build_collab_with_missing_repo(tmp_path: Path) -> Path:
    """A collab whose manifest names a nonexistent code repo -> one red
    `missing` finding with subject 'repo:code <path>'."""
    collab = init_repo(tmp_path / "collab")
    (collab / "manifest.yaml").write_text(
        """\
project: {name: waiver-test, description: waiver scenarios}
paths: {strategy: relative, root: .}
repos:
  - {id: code, path: ../code-gone, role: code, remote: unused}
  - {id: collab, path: ., role: collab}
backlog: {source: file, location: backlog.md}
personas:
  - {slug: fern, spec: agents/fern/persona.yaml}
""",
        encoding="utf-8",
    )
    run_git(collab, "add", "-A")
    run_git(collab, "commit", "-q", "-m", "collab: bootstrap")
    return collab


def status_findings(collab: Path) -> tuple[int, list[dict]]:
    result = runner.invoke(app, ["status", "--collab", str(collab), "--json"])
    return result.exit_code, json.loads(result.output)["findings"]


def test_unwaived_red_stays_red(tmp_path: Path, fixed_clock: object) -> None:
    collab = build_collab_with_missing_repo(tmp_path)
    exit_code, findings = status_findings(collab)
    assert exit_code == 1
    assert any(f["check"] == "missing" and f["severity"] == "red" for f in findings)


def test_waived_red_downgrades_to_warn_with_reason(
    tmp_path: Path, fixed_clock: object
) -> None:
    collab = build_collab_with_missing_repo(tmp_path)
    result = runner.invoke(
        app,
        [
            "waiver", "add", "repo:code *",
            "--reason", "code repo intentionally not cloned on this machine",
            "--handoff", "_handoff/2026-07-22-park-code-repo.md",
            "--expires", "2026-08-01",
            "--collab", str(collab),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (collab / ".baron-waivers.yaml").is_file()

    exit_code, findings = status_findings(collab)
    assert exit_code == 0, findings  # the only red is waived -> green exit
    waived = [f for f in findings if f["check"] == "missing"]
    assert waived and waived[0]["severity"] == "warn"
    assert "(waived: code repo intentionally not cloned" in waived[0]["detail"]


def test_expired_waiver_resurfaces_red_and_warns(
    tmp_path: Path, fixed_clock: object
) -> None:
    collab = build_collab_with_missing_repo(tmp_path)
    # Written directly (waiver add refuses past expiry dates by design).
    (collab / ".baron-waivers.yaml").write_text(
        """\
waivers:
  - subject: "repo:code *"
    reason: parked during the June migration
    handoff: _handoff/2026-06-01-park.md
    expires: 2026-07-01
""",
        encoding="utf-8",
    )
    exit_code, findings = status_findings(collab)
    assert exit_code == 1  # the red is back
    assert any(f["check"] == "missing" and f["severity"] == "red" for f in findings)
    expired = [f for f in findings if f["check"] == "expired-waiver"]
    assert len(expired) == 1
    assert expired[0]["severity"] == "warn"
    assert "2026-07-01" in expired[0]["detail"]
    assert "parked during the June migration" in expired[0]["detail"]


def test_malformed_waiver_entry_is_reported_not_silently_dropped(
    tmp_path: Path, fixed_clock: object
) -> None:
    collab = build_collab_with_missing_repo(tmp_path)
    (collab / ".baron-waivers.yaml").write_text(
        "waivers:\n  - reason: no subject or expiry\n", encoding="utf-8"
    )
    exit_code, findings = status_findings(collab)
    assert exit_code == 1
    assert any(f["check"] == "invalid-waiver" for f in findings)


def test_waiver_add_validations(tmp_path: Path, fixed_clock: object) -> None:
    collab = build_collab_with_missing_repo(tmp_path)
    result = runner.invoke(
        app,
        ["waiver", "add", "x *", "--reason", "r", "--handoff", "h",
         "--expires", "2026-01-01", "--collab", str(collab)],
    )
    assert result.exit_code == 1
    assert "past" in result.output
    result = runner.invoke(
        app,
        ["waiver", "add", "x *", "--reason", "r", "--handoff", "h",
         "--expires", "not-a-date", "--collab", str(collab)],
    )
    assert result.exit_code == 1


def test_waiver_list_shows_state(tmp_path: Path, fixed_clock: object) -> None:
    collab = build_collab_with_missing_repo(tmp_path)
    (collab / ".baron-waivers.yaml").write_text(
        """\
waivers:
  - subject: "old *"
    reason: long gone
    handoff: _handoff/old.md
    expires: 2026-07-01
  - subject: "repo:code *"
    reason: still parked
    handoff: _handoff/park.md
    expires: 2026-08-01
""",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["waiver", "list", "--collab", str(collab)])
    assert result.exit_code == 0, result.output
    assert "EXPIRED" in result.output
    assert "active" in result.output
    assert "still parked" in result.output


def test_add_quotes_yaml_special_characters(
    tmp_path: Path, fixed_clock: object
) -> None:
    """Regression: first live waiver had "Routed to Terrence: rebase over #98"
    — a mapping colon and a comment marker — and the hand-rolled writer
    produced unparseable YAML (found 2026-07-23 during the pilot migration).
    Clock pinned: the fixture expiry dates must stay in the future."""
    from baron import waivers as W

    W.add(
        tmp_path,
        "repo:code claude/annotator-court-ux",
        reason="Routed to Terrence: rebase over #98 + redirect frozen-ledger hunk",
        handoff="_handoff/2026-07-23-owner-branch-triage.md",
        expires="2026-08-31",
    )
    W.add(
        tmp_path,
        "repo:code claude/audio-hit-detection",
        reason="Parked for experiment B (close audio); revive via PR",
        handoff="_handoff/2026-07-23-owner-branch-triage.md",
        expires="2026-10-31",
    )
    loaded, problems = W.load(tmp_path)
    assert problems == []
    assert len(loaded) == 2
    assert loaded[0].reason.startswith("Routed to Terrence: rebase over #98")
