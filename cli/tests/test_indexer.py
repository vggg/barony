"""M3 acceptance: `baron index` — marker-delimited README block + ledger checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from baron import handoff, indexer

from conftest import init_repo, run_git


@pytest.fixture
def collab(tmp_path: Path) -> Path:
    repo = init_repo(tmp_path / "collab")
    (repo / "findings").mkdir()
    (repo / "findings" / "index.md").write_text(
        "# Findings\n\n"
        "| F1 | one |\n"
        "| F2 | two |\n\n"
        "### F4 — gap above (2026-07-01, Tess)\n\nBody.\n",
        encoding="utf-8",
    )
    (repo / "decisions").mkdir()
    (repo / "decisions" / "index.md").write_text(
        "# Decisions\n\n### D1 — one (2026-07-01, Tess)\n\nx\n### D1 — dup (2026-07-02, Rex)\n\ny\n",
        encoding="utf-8",
    )
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "bootstrap")
    return repo


def test_index_block_created_and_regenerated(collab: Path, fixed_clock: object) -> None:
    handoff.create(collab, for_="tess", from_="rex", title="Open one")
    done = handoff.create(collab, for_="rex", from_="tess", title="Done one")
    handoff.close(collab, done)

    readme = indexer.update_readme(collab)
    text = readme.read_text(encoding="utf-8")
    assert indexer.BEGIN_MARKER in text and indexer.END_MARKER in text
    assert "1 open · 0 done · 1 archived" in text
    assert "| [2026-07-22-1200-rex-open-one.md](2026-07-22-1200-rex-open-one.md) | tess | rex | 0 |" in text

    # Custom prose outside the markers survives regeneration.
    readme.write_text("PREFACE\n\n" + text + "\nEPILOGUE\n", encoding="utf-8")
    indexer.update_readme(collab)
    regenerated = readme.read_text(encoding="utf-8")
    assert regenerated.startswith("PREFACE")
    assert "EPILOGUE" in regenerated
    assert regenerated.count(indexer.BEGIN_MARKER) == 1


def test_ledger_checks_report_gaps_and_duplicates(collab: Path) -> None:
    findings_report = indexer.check_ledger(collab, "finding")
    assert findings_report is not None
    assert findings_report.duplicates == []
    assert findings_report.gaps == [3]  # F3 missing between F2 and F4

    decisions_report = indexer.check_ledger(collab, "decision")
    assert decisions_report is not None
    assert decisions_report.duplicates == [1]  # D1 claimed twice
