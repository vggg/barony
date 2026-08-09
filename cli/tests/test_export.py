"""P3.4 (partial) acceptance: `baron export` and its citation contract.

The load-bearing assertions here are the provenance ones. A record's value to
any downstream knowledge substrate is that `git show <commit_sha>:<path>`
returns the exact bytes it was parsed from — so the suite resolves every SHA it
emits with real git, and proves that a source which cannot honour that contract
is skipped by name rather than emitted with a SHA that lies.

The last two tests are boundary guards, not behaviour tests: this workstream is
the Cognee workstream, and its central discipline is that nothing named cognee
enters `baron` core and the ADR-003 dependency set does not move (ADR-015 §6).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from baron import export
from baron.cli import app

from conftest import REPO_ROOT, commit_file, init_repo, run_git

runner = CliRunner()


FINDINGS = """\
# Demo — findings index

Migrated rows below are frozen; full entries start at F3.

| # | Title |
|---|---|
| F1 | Frozen table row one |
| F2 | Frozen table row two |

---

## New findings (F3+)

### F3 — The seam leaks under concurrency (2026-07-01, Tess)

Reproduced twice. Feeds **ADR-002** and contradicts F1.
See [the write-up](docs/seam.md) and https://example.invalid/seam.

### F4 — Follow-up: the leak is a fsync ordering bug (2026-07-02, Moss)

Confirms F3.
"""

DECISIONS = """\
# Demo — decisions index

### D1 — Adopt the fsync fix as the default (2026-07-03, Vikram)

Ratified. Supersedes nothing; closes F4.
"""

ADR_ONE = """\
---
created: 2026-07-01
accepted: 2026-07-02
type: decision
status: accepted
decided_by: Vikram
adr: 001
related:
  - "[[docs/adr/ADR-002-second]]"
---

# ADR-001: The substrate is the database

| Field | Value |
|---|---|
| **Status** | **Accepted** |

Body of ADR-001.
"""

ADR_TWO = """\
# ADR-002: A second decision, frontmatter-free

| Field | Value |
|---|---|
| **Status** | Proposed / parked |

Body of ADR-002, which cites F3.
"""

HANDOFF_OPEN = """\
---
created: 2026-07-05
status: open
for: moss
from: tess
priority: high
---

# Review the fsync seam

Please look at F3 before Friday.
"""

HANDOFF_ARCHIVED = """\
---
created: 2026-07-04
status: done
closed: 2026-07-06
for: tess
from: moss
priority: low
---

# Earlier request, already archived

Nothing outstanding.
"""


@pytest.fixture
def collab(tmp_path: Path) -> Path:
    """A committed, clean collab repo carrying all four corpora."""
    repo = init_repo(tmp_path / "collab")
    commit_file(repo, "findings/index.md", FINDINGS, "seed: findings")
    commit_file(repo, "decisions/index.md", DECISIONS, "seed: decisions")
    commit_file(repo, "docs/adr/ADR-001-substrate.md", ADR_ONE, "seed: adr 001")
    commit_file(repo, "docs/adr/ADR-002-second.md", ADR_TWO, "seed: adr 002")
    commit_file(repo, "_handoff/2026-07-05-review-seam.md", HANDOFF_OPEN, "seed: handoff")
    commit_file(
        repo,
        "_handoff/archive/2026/2026-07-04-earlier.md",
        HANDOFF_ARCHIVED,
        "seed: archived handoff",
    )
    return repo


def _by_key(result: export.Export) -> dict[tuple[str, str], export.Record]:
    return {(r.kind, r.id): r for r in result.records}


# --- coverage --------------------------------------------------------------------------


def test_exports_one_record_per_artifact(collab: Path) -> None:
    result = export.collect(collab)
    keys = _by_key(result)
    assert set(keys) == {
        ("adr", "ADR-001"),
        ("adr", "ADR-002"),
        ("decision", "D1"),
        ("finding", "F1"),
        ("finding", "F2"),
        ("finding", "F3"),
        ("finding", "F4"),
        ("handoff", "2026-07-05-review-seam"),
        ("handoff", "2026-07-04-earlier"),
    }
    assert result.skipped == []
    assert result.duplicates == []


def test_titles_bodies_and_status_come_from_the_right_place(collab: Path) -> None:
    keys = _by_key(export.collect(collab))

    f3 = keys[("finding", "F3")]
    assert f3.title == "The seam leaks under concurrency"
    assert f3.meta["date"] == "2026-07-01"
    assert f3.meta["author"] == "Tess"
    assert f3.meta["form"] == "heading"
    assert "Reproduced twice" in f3.body
    # The next `### ` heading ends the entry — F4's prose must not leak in.
    assert "fsync ordering bug" not in f3.body
    # Ledger entries carry no lifecycle field in the canon; inventing one would
    # be an overclaim, so status is honestly null.
    assert f3.status is None

    f1 = keys[("finding", "F1")]
    assert f1.title == "Frozen table row one"
    assert f1.body == ""
    assert f1.meta["form"] == "table-row"

    adr1 = keys[("adr", "ADR-001")]
    assert adr1.title == "ADR-001: The substrate is the database"
    assert adr1.status == "accepted"  # frontmatter wins
    assert adr1.meta["decided_by"] == "Vikram"
    assert adr1.meta["created"] == "2026-07-01"  # yaml date -> ISO string

    adr2 = keys[("adr", "ADR-002")]
    assert adr2.status == "Proposed / parked"  # no frontmatter -> Status table row

    handoff = keys[("handoff", "2026-07-05-review-seam")]
    assert handoff.title == "Review the fsync seam"
    assert handoff.status == "open"
    assert handoff.meta["for"] == "moss"
    assert handoff.meta["archived"] is False
    # age_days is a function of today and would break run-to-run stability.
    assert "age_days" not in handoff.meta
    assert keys[("handoff", "2026-07-04-earlier")].meta["archived"] is True


def test_heading_form_wins_over_a_table_row_for_the_same_id(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "collab")
    commit_file(
        repo,
        "findings/index.md",
        "| F1 | Row title |\n\n### F1 — Heading title (2026-07-01, Tess)\n\nReal body.\n",
        "seed",
    )
    records = [r for r in export.collect(repo).records if r.kind == "finding"]
    assert len(records) == 1
    assert records[0].title == "Heading title"
    assert records[0].body == "Real body."


# --- the citation contract -------------------------------------------------------------


def test_every_commit_sha_resolves_and_reproduces_the_source(collab: Path) -> None:
    result = export.collect(collab)
    assert result.records
    for record in result.records:
        assert record.commit_sha, f"{record.kind}:{record.id} has no commit_sha"
        # The acceptance check, run against real git.
        assert (
            subprocess.run(
                ["git", "-C", str(collab), "cat-file", "-e", f"{record.commit_sha}^{{commit}}"],
                capture_output=True,
            ).returncode
            == 0
        )
        # And the stronger property the SHA exists for: the bytes match.
        shown = run_git(collab, "show", f"{record.commit_sha}:{record.path}")
        assert shown == (collab / record.path).read_text(encoding="utf-8")


def test_records_are_byte_stable_across_consecutive_runs(collab: Path, fixed_clock: object) -> None:
    first = export.collect(collab).to_dict()
    second = export.collect(collab).to_dict()
    assert first == second
    assert [r["id"] for r in first["records"]] == [r["id"] for r in second["records"]]  # type: ignore[index]


def test_modified_source_is_skipped_by_name_not_miscited(collab: Path) -> None:
    (collab / "findings" / "index.md").write_text(
        FINDINGS + "\n### F5 — Uncommitted edit (2026-07-09, Tess)\n\nNot yet in git.\n",
        encoding="utf-8",
    )
    result = export.collect(collab)
    assert not [r for r in result.records if r.kind == "finding"]
    assert [(s.path, s.reason) for s in result.skipped] == [("findings/index.md", "modified")]
    assert result.skipped[0].records == 5
    # Everything else still exports — one dirty file is not a global failure.
    assert {r.kind for r in result.records} == {"adr", "decision", "handoff"}


def test_untracked_source_is_skipped(collab: Path) -> None:
    (collab / "_handoff" / "2026-07-08-never-committed.md").write_text(
        HANDOFF_OPEN, encoding="utf-8"
    )
    result = export.collect(collab)
    assert ("_handoff/2026-07-08-never-committed.md", "uncommitted") in [
        (s.path, s.reason) for s in result.skipped
    ]
    assert ("handoff", "2026-07-08-never-committed") not in _by_key(result)


def test_allow_dirty_emits_but_marks_the_record(collab: Path) -> None:
    (collab / "findings" / "index.md").write_text(FINDINGS + "\nlocal edit\n", encoding="utf-8")
    result = export.collect(collab, allow_dirty=True)
    findings = [r for r in result.records if r.kind == "finding"]
    assert len(findings) == 4
    assert all(r.meta["dirty"] == "modified" for r in findings)
    assert result.skipped == []
    # ADRs were untouched, so they stay clean and unmarked.
    assert all("dirty" not in r.meta for r in result.records if r.kind == "adr")


def test_collab_below_the_git_root_still_produces_a_working_citation(tmp_path: Path) -> None:
    """`git show <sha>:<path>` resolves paths from the REPO ROOT, and
    `git status --porcelain` reports from the repo root while `git ls-files`
    reports from the cwd. A collab repo nested inside a larger repo is where all
    three disagree — so `path` is repo-root-relative and `repo_prefix` recovers
    the collab-relative form."""
    outer = init_repo(tmp_path / "outer")
    commit_file(outer, "collab/findings/index.md", FINDINGS, "seed: nested findings")
    nested = outer / "collab"

    result = export.collect(nested)
    assert result.repo_prefix == "collab/"
    record = _by_key(result)[("finding", "F3")]
    assert record.path == "collab/findings/index.md"
    assert result.skipped == []  # the status/ls-files path bases were reconciled
    # The citation works verbatim, which is the whole reason for the prefix.
    assert run_git(outer, "show", f"{record.commit_sha}:{record.path}") == FINDINGS


def test_head_is_recorded(collab: Path) -> None:
    result = export.collect(collab)
    assert result.head == run_git(collab, "rev-parse", "HEAD").strip()


# --- links -----------------------------------------------------------------------------


def test_links_carry_type_and_exclude_self_reference(collab: Path) -> None:
    keys = _by_key(export.collect(collab))
    f3 = {(link["type"], link["target"]) for link in keys[("finding", "F3")].links}
    assert ("ref", "ADR-002") in f3
    assert ("ref", "F1") in f3
    assert ("path", "docs/seam.md") in f3
    assert ("url", "https://example.invalid/seam") in f3
    assert ("ref", "F3") not in f3  # never link a record to itself

    adr1 = {(link["type"], link["target"]) for link in keys[("adr", "ADR-001")].links}
    assert ("wikilink", "docs/adr/ADR-002-second") in adr1  # from frontmatter `related`


def test_extract_links_is_deterministic_and_deduped() -> None:
    text = "F1 and F1 again, [[wiki]], [a](b.md), [a](b.md), https://x.invalid/y"
    once = export.extract_links(text)
    assert once == export.extract_links(text)
    assert once == sorted(once, key=lambda link: (link["type"], link["target"]))
    assert len(once) == len({(link["type"], link["target"]) for link in once})


# --- selection + errors ------------------------------------------------------------------


def test_kind_filter(collab: Path) -> None:
    result = export.collect(collab, kinds={"decision"})
    assert {r.kind for r in result.records} == {"decision"}


def test_no_archived_excludes_archived_handoffs(collab: Path) -> None:
    result = export.collect(collab, include_archived=False)
    ids = {r.id for r in result.records if r.kind == "handoff"}
    assert ids == {"2026-07-05-review-seam"}


def test_unknown_kind_is_rejected(collab: Path) -> None:
    with pytest.raises(export.ExportError, match="unknown kind"):
        export.collect(collab, kinds={"transcript"})


def test_non_git_directory_is_an_error_not_a_degraded_export(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    (plain / "findings").mkdir(parents=True)
    (plain / "findings" / "index.md").write_text("### F1 — x (2026-07-01, T)\n", encoding="utf-8")
    with pytest.raises(export.ExportError, match="not a git repository"):
        export.collect(plain)


def test_repo_with_no_commits_is_an_error(tmp_path: Path) -> None:
    empty = init_repo(tmp_path / "empty")
    with pytest.raises(export.ExportError, match="no commits"):
        export.collect(empty)


def test_missing_corpora_export_cleanly(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "bare-collab")
    commit_file(repo, "README.md", "# nothing governed yet\n", "seed")
    result = export.collect(repo)
    assert result.records == []
    assert "no records" in export.render_table(result)


# --- CLI ---------------------------------------------------------------------------------


def test_cli_json_shape(collab: Path) -> None:
    result = runner.invoke(app, ["export", "--collab", str(collab), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["format"] == export.FORMAT
    assert payload["summary"]["records"] == 9
    assert payload["summary"]["by_kind"] == {"adr": 2, "decision": 1, "finding": 4, "handoff": 2}
    core = {"id", "kind", "title", "path", "commit_sha", "status", "body", "links", "meta"}
    for record in payload["records"]:
        assert set(record) == core, "the record wire shape is a contract — see ADR-015 §5"


def test_cli_table_and_kind_filter(collab: Path) -> None:
    result = runner.invoke(app, ["export", "--collab", str(collab), "--kind", "adr"])
    assert result.exit_code == 0, result.output
    assert "ADR-001" in result.output
    assert "F3" not in result.output
    assert "2 record(s)" in result.output


def test_cli_reports_skipped_sources_in_the_table(collab: Path) -> None:
    (collab / "decisions" / "index.md").write_text(DECISIONS + "\nedit\n", encoding="utf-8")
    result = runner.invoke(app, ["export", "--collab", str(collab)])
    assert result.exit_code == 0, result.output
    assert "warning skipped decisions/index.md: modified" in result.output


def test_cli_non_git_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["export", "--collab", str(tmp_path)])
    assert result.exit_code == 2


def test_export_help_surface() -> None:
    assert runner.invoke(app, ["export", "--help"]).exit_code == 0


# --- boundary guards (ADR-003 / ADR-015 §6) -----------------------------------------------


def test_baron_core_never_imports_or_mentions_cognee() -> None:
    """The Cognee workstream's hard line: an adapter lives in a separate
    distribution or nowhere. If this fails, `baron` core has grown a knowledge
    backend and ADR-015's premise is void."""
    src = REPO_ROOT / "cli" / "src" / "baron"
    hits = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in src.rglob("*.py")
        if "cognee" in path.read_text(encoding="utf-8").lower()
    ]
    assert hits == [], f"cognee referenced in baron core: {hits}"


def test_runtime_dependencies_are_still_typer_and_pyyaml_only() -> None:
    """ADR-003's dependency policy, asserted rather than trusted. `baron export`
    is deliberately buildable with zero new dependencies."""
    text = (REPO_ROOT / "cli" / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"^dependencies = \[(.*?)^\]", text, re.M | re.S)
    assert block is not None
    names = re.findall(r'"\s*([A-Za-z0-9_.-]+)', block.group(1))
    assert names == ["typer", "pyyaml"], names


def test_no_new_entry_point_group_was_published() -> None:
    """ADR-015 §4: a published entry-point group with no consumer is public API
    that cannot be retracted, and 3.4 is gated on 3.3. `baron.forges` stays the
    only group until the owner answers the projection-vs-source question."""
    text = (REPO_ROOT / "cli" / "pyproject.toml").read_text(encoding="utf-8")
    groups = re.findall(r'^\[project\.entry-points\."([^"]+)"\]', text, re.M)
    assert groups == ["baron.forges"], groups
