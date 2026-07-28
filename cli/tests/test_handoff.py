"""M3 acceptance: handoff lifecycle — create, close (archive, never delete), list."""

from __future__ import annotations

from pathlib import Path

import pytest

from baron import handoff

from conftest import init_repo, run_git


@pytest.fixture
def collab(tmp_path: Path) -> Path:
    repo = init_repo(tmp_path / "collab")
    (repo / "README.md").write_text("# collab\n", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "bootstrap")
    return repo


def test_create_writes_standard_frontmatter(collab: Path, fixed_clock: object) -> None:
    path = handoff.create(
        collab, for_="tess", from_="rex", title="Review the tracker seam", priority="high"
    )
    assert path.name == "2026-07-22-review-the-tracker-seam.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\ncreated: 2026-07-22\nstatus: open\nfor: tess\nfrom: rex\npriority: high\n---\n")
    assert "# Review the tracker seam" in text
    # committed
    log = run_git(collab, "log", "--oneline", "-1")
    assert "handoff | open" in log


def test_close_flips_status_archives_and_preserves_history(
    collab: Path, fixed_clock: object
) -> None:
    path = handoff.create(collab, for_="tess", from_="rex", title="Close me")
    dest = handoff.close(collab, path, note="Done, see F9.")
    assert dest == collab / "_handoff" / "archive" / "2026" / path.name
    assert not path.exists()
    text = dest.read_text(encoding="utf-8")
    assert "status: done" in text
    assert "closed: 2026-07-22" in text
    assert "> **Closed 2026-07-22.** Done, see F9." in text
    # git mv preserved history: --follow finds the create commit.
    rel = dest.relative_to(collab).as_posix()
    log = run_git(collab, "log", "--follow", "--oneline", "--", rel)
    assert "handoff | open" in log
    assert "handoff | close" in log


def test_create_body_file_content_lands_under_frontmatter(
    collab: Path, fixed_clock: object
) -> None:
    body = "## Context\n\nThe seam needs a second look.\n"
    path = handoff.create(
        collab, for_="tess", from_="rex", title="Big review", body=body
    )
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\ncreated: 2026-07-22\n")
    assert "# Big review\n" in text
    # body appears after the title heading, under the frontmatter
    assert "## Context" in text
    assert text.index("## Context") > text.index("# Big review")


def test_close_prefix_attributes_the_commit(collab: Path, fixed_clock: object) -> None:
    path = handoff.create(collab, for_="tess", from_="rex", title="Close mine")
    handoff.close(collab, path, prefix="tess:")
    log = run_git(collab, "log", "--oneline", "-1")
    assert "tess: handoff | close" in log
    # default stays baron:
    other = handoff.create(collab, for_="a", from_="b", title="Default close")
    handoff.close(collab, other)
    log = run_git(collab, "log", "--oneline", "-1")
    assert "baron: handoff | close" in log


def test_close_refuses_non_open(collab: Path, fixed_clock: object) -> None:
    path = handoff.create(collab, for_="a", from_="b", title="Already done")
    handoff.close(collab, path)
    archived = collab / "_handoff" / "archive" / "2026" / path.name
    with pytest.raises(handoff.HandoffError, match="not `open`"):
        handoff.close(collab, archived)


def test_list_and_open_filter(collab: Path, fixed_clock: object) -> None:
    a = handoff.create(collab, for_="tess", from_="rex", title="Still open")
    b = handoff.create(collab, for_="rex", from_="tess", title="Done soon")
    handoff.close(collab, b)
    items = handoff.iter_handoffs(collab)
    assert [h.path.name for h in items] == [a.name]
    everything = handoff.iter_handoffs(collab, include_archived=True)
    assert {h.status for h in everything} == {"open", "done"}
    open_only = [h for h in everything if h.status == "open"]
    assert len(open_only) == 1 and open_only[0].age_days == 0
