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


def test_single_project_plane_is_the_collab_dir(collab: Path, fixed_clock) -> None:
    """Regression guard for the fix below: in the default layout the plane IS
    ``<collab>/.baron/events`` and is not flagged shared. Nothing about the
    monorepo fix may change this."""
    _seed(collab)
    rep = health.collect(collab)
    assert rep.verdicts == 2
    assert rep.plane == (collab / ".baron" / "events").as_posix()
    assert rep.plane_shared is False
    assert (collab / ".baron" / "events").is_dir()  # written where we read


# --- ADR-025 §6.8: the plane is repo-wide, and the read must follow the write -----


@pytest.fixture
def mono_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A monorepo-shaped project: one git repo at the root, the project a plain
    subdir with no git repo of its own (which is what makes the sink's git
    top-level resolution land ABOVE the project)."""
    root = init_repo(tmp_path / "fleet")
    project = root / "barony"
    project.mkdir()
    (project / "manifest.yaml").write_text("project:\n  name: barony\n", encoding="utf-8")
    run_git(root, "add", "-A")
    run_git(root, "commit", "-q", "-m", "init")
    monkeypatch.setenv("BARON_EVENTS_SINK", "disk")
    return project


def test_verdict_read_follows_the_write_in_a_monorepo(mono_project: Path, fixed_clock) -> None:
    """THE BUG (Stage 2 dogfood): `record` wrote to the git top-level while
    `read` joined `.baron/events` onto the project subdir, so a well-formed
    verdict on disk read back as zero rows. Fails on 94e4285."""
    root = mono_project.parent
    verdict.record(mono_project, author="atlas", pr=43, head="94e4285", verdict="approved",
                   mutations_run=4, mutations_killed=4)

    # The sink wrote at the ROOT — assert that first, so a later change to the
    # WRITE side cannot make this test pass for the wrong reason.
    assert (root / ".baron" / "events").is_dir()
    assert not (mono_project / ".baron" / "events").exists()

    rows = verdict.read(mono_project)
    assert len(rows) == 1 and rows[0]["pr"] == 43
    assert verdict.read(root) == rows  # the same plane from either directory


def test_health_counts_the_monorepo_verdict(mono_project: Path, fixed_clock) -> None:
    rep = health.collect(mono_project)
    assert rep.verdicts == 0  # nothing emitted yet — an honest zero
    verdict.record(mono_project, author="atlas", pr=43, head="94e4285", verdict="approved",
                   mutations_run=4, mutations_killed=4)

    rep = health.collect(mono_project)
    assert rep.verdicts == 1                      # 0 on 94e4285
    assert rep.mutations_run == 4 and rep.mutations_killed == 4
    out = health.render(rep)
    assert "1 verdict(s) recorded" in out
    # ...and it no longer advises enabling a sink that is already enabled.
    assert "nothing to measure" not in out
    assert "BARON_EVENTS_SINK=disk" not in out


def test_monorepo_health_names_the_shared_plane(mono_project: Path, fixed_clock) -> None:
    """The honest bound stays intact — and gains provenance: the report says
    WHERE it read, and that those rows are the whole repo's."""
    root = mono_project.parent
    verdict.record(mono_project, author="atlas", pr=43, head="94e4285", verdict="approved")
    rep = health.collect(mono_project)
    assert rep.plane == (root / ".baron" / "events").as_posix()
    assert rep.plane_shared is True
    assert "repo-wide" in health.render(rep)
    assert rep.to_dict()["plane"] == {"dir": rep.plane, "shared": True, "measured": True}


def test_zero_verdicts_states_the_plane_it_read(mono_project: Path, fixed_clock) -> None:
    out = health.render(health.collect(mono_project))
    assert "nothing to measure" in out
    assert "plane read:" in out  # a zero is attributable, not merely reassuring
