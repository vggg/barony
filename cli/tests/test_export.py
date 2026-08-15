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

from baron import export, monorepo
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


def assert_no_miscitation(git_root: Path, result: export.Export) -> None:
    """Every emitted record's citation must reproduce the bytes that were parsed.

    This is the assertion the whole citation gate exists to satisfy, and it is
    strictly stronger than `git cat-file -e`: a miscited record — one whose
    source was edited after its last commit — has a SHA that resolves perfectly
    and returns *different text*. Only byte-equality catches that, so the gate
    tests call this rather than checking resolvability.

    `meta.dirty` records are exempt: `--allow-dirty` is the documented opt-out
    from exactly this property, and the stamp is how the caveat travels.
    """
    for record in result.records:
        assert record.commit_sha, f"{record.kind}:{record.id} has no commit_sha"
        if record.meta.get("dirty"):
            continue
        shown = run_git(git_root, "show", f"{record.commit_sha}:{record.path}")
        assert shown == (git_root / record.path).read_text(encoding="utf-8"), (
            f"{record.kind}:{record.id} cites {record.commit_sha[:8]}:{record.path}, "
            "which resolves but returns different bytes than were parsed"
        )


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
    assert_no_miscitation(collab, result)


def test_modified_source_with_a_non_ascii_path_is_skipped(collab: Path) -> None:
    """Regression: the citation gate must not fail open on a quoted path.

    Without `-z`, `git status --porcelain` renders any path containing a
    non-ASCII byte, a space or a quote in C-quoted form —
    `"_handoff/2026-01-02-caf\\303\\251.md"` — while `git ls-files -z` returns
    the raw UTF-8 name. Reconciling the two by stripping quotes leaves the octal
    escapes intact, the two names never compare equal, and the file silently
    tests *clean*: it is emitted with the SHA of its last commit while the body
    holds the newer, uncommitted text. That is precisely the confidently-wrong
    citation ADR-015 §3.2 rejects, and every ASCII-named fixture passes while it
    is live — hence this test.
    """
    rel = "_handoff/2026-01-02-café.md"
    commit_file(collab, rel, HANDOFF_OPEN, "seed: non-ascii handoff")
    assert ("handoff", "2026-01-02-café") in _by_key(export.collect(collab))

    (collab / rel).write_text(
        HANDOFF_OPEN + "\nEdited after the commit, never staged.\n", encoding="utf-8"
    )
    result = export.collect(collab)

    assert (rel, "modified") in [(s.path, s.reason) for s in result.skipped]
    assert ("handoff", "2026-01-02-café") not in _by_key(result)
    assert_no_miscitation(collab, result)


def test_parse_porcelain_z_handles_renames_and_raw_paths() -> None:
    """A unit test, because the two-field rename form is not reachable through
    `_source_state`'s pathspec (candidates are files that exist, so a rename
    *source* is never in the pathspec, and git then degrades the entry to `A`).
    The parser still has to handle it: `-z` renders a rename as
    `XY <dest>\\0<src>\\0` with no ` -> ` separator, and a parser that does not
    consume the second field would treat the bare source path as the next
    entry — slicing `entry[3:]` off a raw filename and inventing a dirty path
    that does not exist. Verified against real git output in ADR-015 §3.2."""
    payload = (
        " M findings/index.md\0"
        "R  docs/adr/ADR-001-new.md\0docs/adr/ADR-001-old.md\0"
        "?? _handoff/2026-01-02-café.md\0"
    )
    assert export._parse_porcelain_z(payload) == {
        "findings/index.md",
        "docs/adr/ADR-001-new.md",
        "docs/adr/ADR-001-old.md",  # the rename source, from its own field
        "_handoff/2026-01-02-café.md",  # raw UTF-8, never C-quoted under -z
    }


def test_staged_but_uncommitted_source_is_skipped(collab: Path) -> None:
    """`git add` without `git commit` leaves a tracked file that `git log` cannot
    name a commit for. The belt-and-braces branch must catch it, or the record
    ships with an empty `commit_sha`."""
    (collab / "docs" / "adr" / "ADR-003-staged.md").write_text(
        "# ADR-003: Staged, never committed\n", encoding="utf-8"
    )
    run_git(collab, "add", "--", "docs/adr/ADR-003-staged.md")
    result = export.collect(collab)
    assert ("adr", "ADR-003") not in _by_key(result)
    assert ("docs/adr/ADR-003-staged.md", "uncommitted") in [
        (s.path, s.reason) for s in result.skipped
    ]
    assert_no_miscitation(collab, result)


def test_untracked_source_is_skipped(collab: Path) -> None:
    (collab / "_handoff" / "2026-07-08-never-committed.md").write_text(
        HANDOFF_OPEN, encoding="utf-8"
    )
    result = export.collect(collab)
    assert ("_handoff/2026-07-08-never-committed.md", "uncommitted") in [
        (s.path, s.reason) for s in result.skipped
    ]
    assert ("handoff", "2026-07-08-never-committed") not in _by_key(result)
    assert_no_miscitation(collab, result)


def test_allow_dirty_emits_but_marks_the_record(collab: Path) -> None:
    (collab / "findings" / "index.md").write_text(FINDINGS + "\nlocal edit\n", encoding="utf-8")
    result = export.collect(collab, allow_dirty=True)
    findings = [r for r in result.records if r.kind == "finding"]
    assert len(findings) == 4
    assert all(r.meta["dirty"] == "modified" for r in findings)
    assert result.skipped == []
    # ADRs were untouched, so they stay clean and unmarked.
    assert all("dirty" not in r.meta for r in result.records if r.kind == "adr")


def test_allow_dirty_still_refuses_untracked_sources(collab: Path) -> None:
    """ADR-015 §3.1: `commit_sha` is **always non-empty**. An untracked file has
    no commit to name, so `--allow-dirty` cannot cover it — the flag means
    "modified too", not "uncited too". Emitting an empty SHA here would break the
    one format invariant the CHANGELOG advertises."""
    (collab / "_handoff" / "2026-07-08-never-committed.md").write_text(
        HANDOFF_OPEN, encoding="utf-8"
    )
    (collab / "findings" / "index.md").write_text(FINDINGS + "\nlocal edit\n", encoding="utf-8")
    result = export.collect(collab, allow_dirty=True)

    assert ("handoff", "2026-07-08-never-committed") not in _by_key(result)
    assert [(s.path, s.reason) for s in result.skipped] == [
        ("_handoff/2026-07-08-never-committed.md", "uncommitted")
    ]
    # The modified source, which does have a commit, is emitted and stamped.
    assert all(r.meta["dirty"] == "modified" for r in result.records if r.kind == "finding")
    assert all(r.commit_sha for r in result.records)
    assert all(r.meta.get("dirty") != "uncommitted" for r in result.records)


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
    # `project` was added by ADR-032 §3.2. Widening the core key set is allowed
    # without a format bump (ADR-015 §5: consumers ignore unknown keys) but must
    # be a VISIBLE diff, which is this line's whole job.
    core = {
        "id", "kind", "title", "path", "commit_sha", "status", "body", "links",
        "meta", "project",
    }
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


def test_no_knowledge_entry_point_group_was_published() -> None:
    """ADR-015 §4: a published entry-point group with NO CONSUMER is public API
    that cannot be retracted, and 3.4 is gated on 3.3. No `baron.knowledge`
    group until the owner answers the projection-vs-source question.

    NARROWED AT THE OPS-PLANE MERGE (2026-08-09). This asserted
    ``groups == ["baron.forges"]`` — a global claim wider than the rule it was
    protecting. ADR-013 then published ``baron.sinks``, which is exactly the
    case ADR-015 §4 permits: it ships two built-in consumers (`null`, `disk`)
    that a test loads through real ``importlib.metadata`` discovery, so it is
    not an empty promise. The invariant that actually matters is the absence of
    a knowledge/vendor group, so that is what is now asserted — plus an
    allowlist, so a THIRD unreviewed group still fails this test.
    """
    text = (REPO_ROOT / "cli" / "pyproject.toml").read_text(encoding="utf-8")
    groups = re.findall(r'^\[project\.entry-points\."([^"]+)"\]', text, re.M)
    assert "baron.knowledge" not in groups, groups
    assert not [g for g in groups if "cognee" in g.lower()], groups
    assert set(groups) <= {"baron.forges", "baron.sinks"}, (
        f"unreviewed entry-point group published: {sorted(set(groups) - {'baron.forges', 'baron.sinks'})}"
    )


# --- ADR-032: the coordination-monorepo walk -------------------------------------------
#
# The bug: at an ADR-025 monorepo root `baron export` walked no project subdir
# and reported **0 records**, while a run inside each subdir returned real
# counts. Same silent-false-zero class as ADR-025 §6.8's health bug — a zero
# that means "I looked in the wrong directory" while reading as "nothing is
# there". These tests fail on the pre-ADR-032 code at the assertion that the
# root sees what the subdirs see.


PROJECT_ADR = """\
---
created: 2026-08-01
type: decision
status: accepted
adr: 001
---

# ADR-001: {title}

| Field | Value |
|---|---|
| **Status** | **Accepted** |

{title} body.
"""

PROJECT_FINDINGS = """\
# {name} — findings index

### F1 — {title} (2026-08-02, Tess)

Measured in {name}.
"""


def _manifest(name: str) -> str:
    return f"project:\n  name: {name}\n  collab_repo: .\n"


@pytest.fixture
def monorepo_root(tmp_path: Path) -> Path:
    """A coordination monorepo (ADR-025): one git repo, two project subdirs.

    Deliberately gives BOTH projects an `ADR-001` — legitimate, since ADR numbers
    are per-project — so the aggregation is forced to key on the project too.
    """
    root = init_repo(tmp_path / "fleet-coordination")
    commit_file(
        root,
        ".baron-monorepo.yaml",
        "layout: monorepo\nversion: 1\nprojects:\n"
        "  - dir: _meta\n    name: meta\n"
        "  - dir: barony\n    name: barony\n",
        "seed: marker",
    )
    for subdir, name in (("_meta", "meta"), ("barony", "barony")):
        commit_file(root, f"{subdir}/manifest.yaml", _manifest(name), f"seed: {name} manifest")
        commit_file(
            root,
            f"{subdir}/docs/adr/ADR-001-topology.md",
            PROJECT_ADR.format(title=f"{name} topology"),
            f"seed: {name} adr",
        )
        commit_file(
            root,
            f"{subdir}/findings/index.md",
            PROJECT_FINDINGS.format(name=name, title=f"{name} leaks under load"),
            f"seed: {name} findings",
        )
    return root


def _root_export(root: Path) -> export.Export:
    repo = monorepo.load(root)
    return export.collect_portfolio(
        root, [(p.dir, p.name) for p in repo.projects], unregistered=repo.unregistered
    )


def test_monorepo_root_export_is_not_silently_zero(monorepo_root: Path) -> None:
    """THE REGRESSION. The root must see exactly what the subdirs see.

    Pre-fix, the left-hand side of the final assertion was 0 while the right-hand
    side was 4 — and `baron export` said "no records" rather than "this is a
    monorepo root, here is what I did not walk".
    """
    per_project = {
        name: export.collect(monorepo_root / name if name != "meta" else monorepo_root / "_meta")
        for name in ("meta", "barony")
    }
    assert all(len(e.records) == 2 for e in per_project.values()), {
        k: len(v.records) for k, v in per_project.items()
    }

    result = _root_export(monorepo_root)
    assert result.layout == "monorepo"
    assert len(result.records) == sum(len(e.records) for e in per_project.values()) == 4


def test_monorepo_export_carries_per_project_provenance(monorepo_root: Path) -> None:
    result = _root_export(monorepo_root)
    assert {r.project for r in result.records} == {"meta", "barony"}
    assert {p.dir: p.records for p in result.projects} == {"_meta": 2, "barony": 2}
    payload = result.to_dict()
    assert payload["summary"]["by_project"] == {"meta": 2, "barony": 2}
    assert payload["layout"] == "monorepo"


def test_monorepo_export_does_not_call_cross_project_ids_duplicates(
    monorepo_root: Path,
) -> None:
    """Both projects hold an `ADR-001` and an `F1`. Keying on `(kind, id)` alone
    would drop half the corpus into `duplicates[]` — trading the silent zero for
    a silent halving, which is the same bug wearing a different number."""
    result = _root_export(monorepo_root)
    assert result.duplicates == []
    adrs = sorted(
        (r.project, r.path) for r in result.records if r.kind == "adr"
    )
    assert adrs == [
        ("barony", "barony/docs/adr/ADR-001-topology.md"),
        ("meta", "_meta/docs/adr/ADR-001-topology.md"),
    ]


def test_monorepo_export_citations_resolve_from_the_root(monorepo_root: Path) -> None:
    """`path` must stay repo-root-relative (ADR-015 §3.1) across the aggregation,
    so `git show <sha>:<path>` still reproduces the bytes — now with the subdir
    prefix that the per-project walk's `repo_prefix` supplies."""
    result = _root_export(monorepo_root)
    assert result.records, "nothing to check"
    assert_no_miscitation(monorepo_root, result)


def test_monorepo_export_reports_unregistered_subdirs_without_including_them(
    monorepo_root: Path,
) -> None:
    commit_file(monorepo_root, "stowaway/manifest.yaml", _manifest("stowaway"), "seed: stowaway")
    commit_file(
        monorepo_root,
        "stowaway/findings/index.md",
        PROJECT_FINDINGS.format(name="stowaway", title="not registered"),
        "seed: stowaway findings",
    )
    result = _root_export(monorepo_root)
    assert result.unregistered == ["stowaway"]
    assert "stowaway" not in {r.project for r in result.records}
    assert "stowaway/" in export.render_table(result)


def test_monorepo_export_survives_one_unreadable_project(monorepo_root: Path) -> None:
    """One bad leg must not zero the portfolio — ADR-015 §3.2's "one uncommitted
    handoff should not destroy the other 283 records", one level up."""
    repo = monorepo.load(monorepo_root)
    result = export.collect_portfolio(
        monorepo_root,
        [(p.dir, p.name) for p in repo.projects] + [("ghost", "ghost")],
    )
    assert "ghost" in result.unreadable
    assert len(result.records) == 4


def test_cli_export_at_a_monorepo_root_reports_records(monorepo_root: Path) -> None:
    result = runner.invoke(app, ["export", "--collab", str(monorepo_root), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["layout"] == "monorepo"
    assert payload["summary"]["records"] == 4
    assert payload["summary"]["projects"] == 2


def test_single_project_export_is_unchanged_by_the_monorepo_path(collab: Path) -> None:
    """No-regression: a standalone collab repo takes the single-layout branch,
    reports `layout: "single"`, and still emits the same nine records."""
    result = export.collect(collab)
    assert result.layout == "single"
    assert result.projects == []
    assert len(result.records) == 9
    assert_no_miscitation(collab, result)

    cli = runner.invoke(app, ["export", "--collab", str(collab), "--json"])
    assert cli.exit_code == 0, cli.output
    payload = json.loads(cli.stdout)
    assert payload["layout"] == "single"
    assert payload["summary"]["records"] == 9


# --- ADR-032: the widened corpus (status + note) ----------------------------------------
#
# P3.3 (ADR-031) measured the lexical baseline retrieving the flagship gold
# record at rank 1; its ONLY miss was a research note in `wiki/` that this
# walker never visited. Coverage, not ranking — so these lock what the walker
# now reaches, and that the citation gate came with it rather than being
# relaxed for the new corpora.


RESEARCH_NOTE = """\
---
type: research
status: draft
related:
  - "[[docs/adr/ADR-001-substrate]]"
---

# Lightweight agent identity — survey

Compared three approaches. Feeds ADR-001.
"""

CURATED_STATUS = """\
# Demo — status

Phase 2 is green. See F3.
"""


def test_curated_status_and_notes_are_exported(collab: Path) -> None:
    commit_file(collab, "wiki/status.md", CURATED_STATUS, "seed: status")
    commit_file(collab, "wiki/research-identity.md", RESEARCH_NOTE, "seed: note")
    commit_file(collab, "docs/notes/seam-measurements.md", "# Seam measurements\n", "seed: note 2")

    result = export.collect(collab, kinds=set(export.KIND_ORDER))
    keys = _by_key(result)
    assert ("status", "wiki/status") in keys
    assert ("note", "wiki/research-identity") in keys
    assert ("note", "docs/notes/seam-measurements") in keys
    # ...and `wiki/status.md` is claimed ONCE, by the kind that describes it.
    assert ("note", "wiki/status") not in keys
    assert_no_miscitation(collab, result)


def test_note_records_keep_frontmatter_status_links_and_corpus(collab: Path) -> None:
    commit_file(collab, "wiki/research-identity.md", RESEARCH_NOTE, "seed: note")
    record = _by_key(export.collect(collab, kinds=set(export.KIND_ORDER)))[("note", "wiki/research-identity")]
    assert record.title == "Lightweight agent identity — survey"
    assert record.status == "draft"
    assert record.meta["corpus"] == "wiki"
    assert {"type": "ref", "target": "ADR-001"} in record.links
    assert {"type": "wikilink", "target": "docs/adr/ADR-001-substrate"} in record.links


def test_the_citation_gate_covers_the_new_corpora_too(collab: Path) -> None:
    """ADR-015 §3.2 is not relaxed for `note`/`status`: an untracked research
    note is skipped and NAMED, never emitted with an empty or borrowed SHA."""
    (collab / "wiki").mkdir(parents=True, exist_ok=True)
    (collab / "wiki" / "draft.md").write_text("# Uncommitted draft\n", encoding="utf-8")
    result = export.collect(collab, kinds=set(export.KIND_ORDER))
    assert ("note", "wiki/draft") not in _by_key(result)
    assert ("wiki/draft.md", "uncommitted") in {(s.path, s.reason) for s in result.skipped}
    # and --allow-dirty still cannot cover an untracked source
    assert ("note", "wiki/draft") not in _by_key(
        export.collect(collab, kinds=set(export.KIND_ORDER), allow_dirty=True)
    )


def test_kind_filter_selects_the_new_corpora(collab: Path) -> None:
    commit_file(collab, "wiki/research-identity.md", RESEARCH_NOTE, "seed: note")
    result = export.collect(collab, kinds={"note"})
    assert {r.kind for r in result.records} == {"note"}

    ledgers_only = export.collect(collab, kinds=set(export.LEDGER_KINDS))
    assert {r.kind for r in ledgers_only.records} <= set(export.LEDGER_KINDS)
    assert len(ledgers_only.records) == 9


def test_notes_do_not_re_export_adrs_when_the_trees_overlap(collab: Path) -> None:
    """`--adr-dir` can point inside a note dir. Guard against the same file
    coming back twice under two kinds and two IDs."""
    commit_file(collab, "wiki/adr/ADR-009-nested.md", ADR_ONE, "seed: nested adr")
    result = export.collect(collab, adr_dir="wiki/adr")
    paths = [r.path for r in result.records]
    assert paths.count("wiki/adr/ADR-009-nested.md") == 1
    assert _by_key(result)[("adr", "ADR-009")].kind == "adr"


def test_records_are_byte_stable_with_the_widened_corpus(collab: Path) -> None:
    commit_file(collab, "wiki/status.md", CURATED_STATUS, "seed: status")
    commit_file(collab, "wiki/research-identity.md", RESEARCH_NOTE, "seed: note")
    first = json.dumps(export.collect(collab).to_dict(), sort_keys=True)
    second = json.dumps(export.collect(collab).to_dict(), sort_keys=True)
    assert first == second


def test_the_widened_corpus_is_opt_in_not_the_default(collab: Path) -> None:
    """ADR-032 §3.1 (amended). The default record set is the four ledgers, so
    merging the widened corpus does not silently move the counts under an
    existing consumer — `baron memeval` (ADR-031) is one, and its pinned numbers
    move if this regresses. `--wide` / an explicit `--kind` is how you ask.
    """
    commit_file(collab, "wiki/status.md", CURATED_STATUS, "seed: status")
    commit_file(collab, "wiki/research-identity.md", RESEARCH_NOTE, "seed: note")

    default = export.collect(collab)
    assert {r.kind for r in default.records} <= set(export.LEDGER_KINDS)
    assert ("note", "wiki/research-identity") not in _by_key(default)
    assert ("status", "wiki/status") not in _by_key(default)

    wide = export.collect(collab, kinds=set(export.KIND_ORDER))
    assert ("note", "wiki/research-identity") in _by_key(wide)
    assert ("status", "wiki/status") in _by_key(wide)
    assert export.DEFAULT_KINDS == export.LEDGER_KINDS
