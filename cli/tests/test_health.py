"""ADR-024 acceptance: review.verdict emission + `baron health` rollup.

The plane's default sink is null (D4), so tests opt in with BARON_EVENTS_SINK=disk,
record verdicts through the CLI path, and assert the aggregation mirrors the pilot's
metrics-report (mutation-kill, claim-drift+understating, reviewer escape, per-author).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baron import health, verdict

from conftest import init_repo, run_git


@pytest.fixture
def collab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = init_repo(tmp_path / "collab")
    (repo / "manifest.yaml").write_text("project:\n  name: t\n", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "init")
    monkeypatch.setenv("BARON_EVENTS_SINK", "disk")  # opt in to recording
    return repo


def _seed(collab: Path) -> None:
    verdict.record(collab, author="carson", pr=12, head="a1b2c3d", verdict="approved",
                   mutations_run=10, mutations_killed=8, drift_instances=2, drift_understating=1)
    verdict.record(collab, author="carson", pr=13, head="e4f5g6h", verdict="changes",
                   mutations_run=6, mutations_killed=6, drift_instances=1, escape=True,
                   note="missed on PR11 earlier head")


def test_record_then_read_roundtrips(collab: Path, fixed_clock) -> None:
    _seed(collab)
    rows = verdict.read(collab)
    assert len(rows) == 2
    r = next(x for x in rows if x["pr"] == 12)
    assert r["mutations_run"] == 10 and r["mutations_killed"] == 8
    assert r["drift_instances"] == 2 and r["drift_understating"] == 1
    assert r["author"] == "carson" and r["verdict"] == "approved"


def test_health_aggregates(collab: Path, fixed_clock) -> None:
    _seed(collab)
    rep = health.collect(collab)
    assert rep.verdicts == 2
    assert rep.mutations_run == 16 and rep.mutations_killed == 14
    assert rep.kill_rate == 14 / 16
    assert rep.drift_instances == 3 and rep.drift_understating == 1 and rep.prs == 2
    assert len(rep.escapes) == 1 and rep.escapes[0]["pr"] == 13
    assert rep.by_author["carson"]["verdicts"] == 2
    assert rep.by_author["carson"]["mut_killed"] == 14


def test_no_verdicts_is_honest_not_empty(collab: Path, fixed_clock) -> None:
    rep = health.collect(collab)
    assert rep.verdicts == 0 and rep.kill_rate is None
    out = health.render(rep)
    assert "nothing to measure" in out


def test_health_degrades_without_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_clock) -> None:
    repo = init_repo(tmp_path / "bare")  # no manifest.yaml -> baron status can't run
    run_git(repo, "commit", "-q", "--allow-empty", "-m", "init")
    monkeypatch.setenv("BARON_EVENTS_SINK", "disk")
    verdict.record(repo, author="rex", pr=1, head="deadbee", verdict="approved", mutations_run=2, mutations_killed=2)
    rep = health.collect(repo)  # must NOT raise
    assert rep.verdicts == 1
    assert any("status unavailable" in s for s in rep.stalls)


def test_since_filters_out_older_verdicts(collab: Path, fixed_clock) -> None:
    _seed(collab)  # recorded at the fixed clock (2026-07-22)
    assert health.collect(collab, since="2026-07-22").verdicts == 2   # inclusive prefix
    assert health.collect(collab, since="2026-08-01").verdicts == 0   # all before the cutoff


def test_to_dict_shape(collab: Path, fixed_clock) -> None:
    _seed(collab)
    d = health.collect(collab).to_dict()
    assert d["mutation_kill"]["rate"] == 14 / 16
    assert d["claim_drift"]["understating"] == 1
    assert d["reviewer_escapes"] == 1
