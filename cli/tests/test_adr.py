"""ADR-029 — the prior-art gate.

The property under test throughout: **fail-closed**. Every way of not recording a
sweep must exit nonzero, including the creative ones (empty block, corrupted block,
`hits` omitted, a corpus quietly dropped). A gate that any of those slips past is
worse than no gate, because it prints green on the failure it exists to catch —
the ADR-009 `park` lesson, re-learned on a different artifact.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from baron import adr as adr_mod
from baron.cli import app

runner = CliRunner()

GOOD_BLOCK = """<!-- BEGIN BARON PRIOR-ART -->
searched:
  - corpus: repo-adr
    location: docs/adr
    query: "identity, spawn"
    date: 2026-08-14
  - corpus: vault
    location: /vault
    query: "identity spike"
    date: 2026-08-14
hits: []
<!-- END BARON PRIOR-ART -->
"""


def write_adr(
    d: Path,
    name: str = "ADR-030-thing.md",
    *,
    status: str = "accepted",
    created: str = "2026-08-20",
    block: str = GOOD_BLOCK,
    heading: bool = True,
) -> Path:
    fm = f"---\ncreated: {created}\nstatus: {status}\nadr: 30\n---\n\n"
    body = "# ADR-030: a thing\n\n"
    if heading:
        body += "## Supersedes / Prior art\n\n"
    body += block
    p = d / name
    p.write_text(fm + body, encoding="utf-8")
    return p


def checks(d: Path, **kw) -> set[str]:
    records = adr_mod.check_dir(d, **kw)
    return {f.check for f in adr_mod.errors_of(records)}


# --- the happy path and the shape of the corpus ------------------------------------------


def test_populated_block_passes(tmp_path):
    write_adr(tmp_path)
    assert checks(tmp_path) == set()


def test_template_and_readme_are_not_records(tmp_path):
    # ADR-TEMPLATE.md carries the block with UNFILLED placeholders and a `proposed`
    # status. It must not be gated: a template forced to satisfy its own rule would
    # have to lie about what it is.
    (tmp_path / "ADR-TEMPLATE.md").write_text("---\nstatus: accepted\ncreated: 2026-08-20\n---\n# t\n")
    (tmp_path / "README.md").write_text("# index\n")
    assert adr_mod.check_dir(tmp_path) == []


def test_missing_dir_raises(tmp_path):
    with pytest.raises(adr_mod.AdrError):
        adr_mod.check_dir(tmp_path / "nope")


def test_unknown_required_corpus_raises(tmp_path):
    with pytest.raises(adr_mod.AdrError):
        adr_mod.check_dir(tmp_path, required=("repo-adr", "vibes"))


# --- fail-closed: every way of not recording a sweep --------------------------------------


def test_missing_block_is_an_error(tmp_path):
    write_adr(tmp_path, block="", heading=False)
    assert checks(tmp_path) == {"prior-art-block-missing"}


def test_empty_block_is_an_error(tmp_path):
    # The laziest bypass: keep the markers, delete the content. `searched` empty and
    # `hits` absent must BOTH fire — neither alone would.
    write_adr(tmp_path, block=f"{adr_mod.BEGIN_MARKER}\n{adr_mod.END_MARKER}\n")
    assert checks(tmp_path) == {"prior-art-searched-missing", "prior-art-hits-missing"}


def test_unclosed_marker_is_malformed_not_missing(tmp_path):
    # Corrupting the block must not be cheaper than filling it in. If malformed
    # collapsed into "absent", both would be one error — but if it ever collapsed
    # into "no block found -> skip", truncation would be a free pass.
    write_adr(tmp_path, block=f"{adr_mod.BEGIN_MARKER}\nsearched:\n")
    assert checks(tmp_path) == {"prior-art-block-malformed"}


def test_invalid_yaml_is_malformed(tmp_path):
    write_adr(tmp_path, block=f"{adr_mod.BEGIN_MARKER}\nsearched: [unclosed\n{adr_mod.END_MARKER}\n")
    assert checks(tmp_path) == {"prior-art-block-malformed"}


def test_non_mapping_block_is_malformed(tmp_path):
    write_adr(tmp_path, block=f"{adr_mod.BEGIN_MARKER}\n- just\n- a list\n{adr_mod.END_MARKER}\n")
    assert checks(tmp_path) == {"prior-art-block-malformed"}


def test_missing_required_corpus(tmp_path):
    block = f"""{adr_mod.BEGIN_MARKER}
searched:
  - corpus: repo-adr
    location: docs/adr
    query: "x"
    date: 2026-08-14
hits: []
{adr_mod.END_MARKER}
"""
    write_adr(tmp_path, block=block)
    # The vault is the corpus the motivating incident's prior art lived in. Dropping
    # it silently would leave the gate green on exactly that failure.
    assert checks(tmp_path) == {"prior-art-corpus-missing"}
    # ...and a project without a vault can say so explicitly.
    assert checks(tmp_path, required=("repo-adr",)) == set()


def test_corpus_vocabulary_is_closed(tmp_path):
    block = GOOD_BLOCK.replace("corpus: repo-adr", "corpus: had a think about it")
    write_adr(tmp_path, block=block)
    # Unknown corpus -> the entry is incomplete AND repo-adr is now unsearched.
    assert checks(tmp_path) == {"prior-art-search-incomplete", "prior-art-corpus-missing"}


@pytest.mark.parametrize("drop", ["query", "date"])
def test_search_entry_needs_query_and_date(tmp_path, drop):
    block = "\n".join(
        ln for ln in GOOD_BLOCK.splitlines() if not ln.strip().startswith(f"{drop}:")
    ) + "\n"
    write_adr(tmp_path, block=block)
    assert checks(tmp_path) == {"prior-art-search-incomplete"}


def test_hits_key_must_be_written_even_when_empty(tmp_path):
    block = GOOD_BLOCK.replace("hits: []\n", "")
    write_adr(tmp_path, block=block)
    # Omission is indistinguishable from never having looked; `hits: []` is a claim.
    assert checks(tmp_path) == {"prior-art-hits-missing"}


def test_hits_none_is_not_hits_missing(tmp_path):
    # `hits:` with nothing after it parses to None. The key IS present — the author
    # made the claim — so this passes, unlike an omitted key.
    write_adr(tmp_path, block=GOOD_BLOCK.replace("hits: []", "hits:"))
    assert checks(tmp_path) == set()


@pytest.mark.parametrize(
    "hit,expected",
    [
        ("  - disposition: cites\n    note: x", {"prior-art-hit-incomplete"}),  # no ref
        ("  - ref: a.md\n    disposition: maybe", {"prior-art-hit-incomplete"}),  # bad disp
        ("  - ref: a.md\n    disposition: distinct", {"prior-art-hit-incomplete"}),  # no note
        ("  - ref: a.md\n    disposition: distinct\n    note: does not apply", set()),
        ("  - ref: a.md\n    disposition: cites", set()),  # `cites` needs no note
    ],
)
def test_hit_shape(tmp_path, hit, expected):
    write_adr(tmp_path, block=GOOD_BLOCK.replace("hits: []", f"hits:\n{hit}"))
    assert checks(tmp_path) == expected


# --- who is gated ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,gated",
    [
        ("accepted", True),
        ("Accepted with changes", True),
        ("Accepted 2026-08-20 — owner gave go", True),
        ("proposed", False),
        ("Rejected", False),
        ("Adopted in part · transport RETIRED", False),
    ],
)
def test_only_accepted_is_gated(tmp_path, status, gated):
    write_adr(tmp_path, status=status, block="", heading=False)
    assert bool(checks(tmp_path)) is gated


def test_status_table_row_is_read_when_frontmatter_has_none(tmp_path):
    p = tmp_path / "ADR-031-x.md"
    p.write_text(
        "---\ncreated: 2026-08-20\n---\n\n# ADR-031\n\n"
        "| Field | Value |\n|---|---|\n| **Status** | Accepted (2026-08-20) |\n",
        encoding="utf-8",
    )
    # Same precedence export.py uses. Two readers disagreeing about an ADR's status
    # would be worse than either being wrong.
    assert checks(tmp_path) == {"prior-art-block-missing"}


def test_pre_effective_date_adrs_are_exempt_not_passing(tmp_path):
    write_adr(tmp_path, created="2026-08-01", block="", heading=False)
    assert checks(tmp_path) == set()
    (rec,) = adr_mod.check_dir(tmp_path)
    assert rec.gated is False and "before the gate's effective date" in rec.exempt_reason
    # ...and the whole-corpus audit still surfaces it.
    assert checks(tmp_path, since=date(1970, 1, 1)) == {"prior-art-block-missing"}


def test_undated_adr_is_exempt_with_a_reason(tmp_path):
    p = tmp_path / "ADR-032-x.md"
    p.write_text("---\nstatus: accepted\n---\n\n# ADR-032\n", encoding="utf-8")
    (rec,) = adr_mod.check_dir(p.parent)
    assert rec.gated is False and "cannot date it" in rec.exempt_reason


# --- warnings do not block --------------------------------------------------------------------


def test_stale_sweep_warns_but_does_not_block(tmp_path):
    write_adr(tmp_path, created="2026-12-01")
    records = adr_mod.check_dir(tmp_path)
    assert adr_mod.errors_of(records) == []
    assert {f.check for f in adr_mod.warnings_of(records)} == {"prior-art-search-stale"}


def test_missing_heading_warns(tmp_path):
    write_adr(tmp_path, heading=False)
    records = adr_mod.check_dir(tmp_path)
    assert adr_mod.errors_of(records) == []
    assert "prior-art-section-missing" in {f.check for f in adr_mod.warnings_of(records)}


def test_unresolved_supersedes_ref_warns_only(tmp_path):
    # Superseding an ADR that lives on an unmerged branch is legitimate — the
    # numbering convention reserves those numbers. Never an error.
    write_adr(
        tmp_path,
        block=GOOD_BLOCK.replace(
            "hits: []", "hits:\n  - ref: docs/adr/ADR-099-ghost.md\n    disposition: supersedes"
        ),
    )
    records = adr_mod.check_dir(tmp_path)
    assert adr_mod.errors_of(records) == []
    assert {f.check for f in adr_mod.warnings_of(records)} == {"prior-art-ref-unresolved"}


def test_resolvable_supersedes_ref_is_silent(tmp_path):
    write_adr(tmp_path, name="ADR-028-old.md", status="proposed", block="", heading=False)
    write_adr(
        tmp_path,
        block=GOOD_BLOCK.replace(
            "hits: []", "hits:\n  - ref: docs/adr/ADR-028-old.md\n    disposition: supersedes"
        ),
    )
    assert adr_mod.warnings_of(adr_mod.check_dir(tmp_path)) == []


# --- the command surface -----------------------------------------------------------------------


def test_cli_exits_1_on_violation_and_0_when_clean(tmp_path):
    write_adr(tmp_path, block="", heading=False)
    res = runner.invoke(app, ["adr", "check", str(tmp_path)])
    assert res.exit_code == 1
    assert "prior-art-block-missing" in res.stdout
    assert "BLOCKED" in res.stdout

    write_adr(tmp_path)
    assert runner.invoke(app, ["adr", "check", str(tmp_path)]).exit_code == 0


def test_cli_warnings_do_not_fail_the_gate(tmp_path):
    write_adr(tmp_path, heading=False)
    res = runner.invoke(app, ["adr", "check", str(tmp_path)])
    assert res.exit_code == 0
    assert "WARNING" in res.stdout


def test_cli_usage_errors_exit_2(tmp_path):
    assert runner.invoke(app, ["adr", "check", str(tmp_path / "nope")]).exit_code == 2
    assert runner.invoke(app, ["adr", "check", str(tmp_path), "--since", "yesterday"]).exit_code == 2
    assert runner.invoke(app, ["adr", "check", str(tmp_path), "--require", "vibes"]).exit_code == 2


def test_cli_json_reports_exempt_separately_from_passing(tmp_path):
    import json

    write_adr(tmp_path, created="2026-08-01", block="", heading=False)
    res = runner.invoke(app, ["adr", "check", str(tmp_path), "--json"])
    payload = json.loads(res.stdout)
    assert payload["summary"] == {
        "records": 1, "gated": 0, "exempt": 1, "errors": 0, "warnings": 0
    }
    assert payload["records"][0]["exempt_reason"]


def test_cli_require_flag_narrows_the_corpus(tmp_path):
    write_adr(
        tmp_path,
        block=GOOD_BLOCK.replace(
            '  - corpus: vault\n    location: /vault\n    query: "identity spike"\n    date: 2026-08-14\n', ""
        ),
    )
    assert runner.invoke(app, ["adr", "check", str(tmp_path)]).exit_code == 1
    assert runner.invoke(
        app, ["adr", "check", str(tmp_path), "--require", "repo-adr"]
    ).exit_code == 0


def test_scaffold_prints_a_block_that_passes_its_own_gate(tmp_path):
    # The scaffold is the thing authors paste. If its own shape did not satisfy the
    # checker, every first run would be a false refusal — so this is the one test
    # that keeps the template and the rule from drifting apart.
    res = runner.invoke(app, ["adr", "scaffold"])
    assert res.exit_code == 0
    filled = (
        res.stdout
        .replace("<the terms you actually searched>", "identity")
        .replace("<YYYY-MM-DD>", "2026-08-20")
        .replace("<vault path or name>", "/vault")
    )
    write_adr(tmp_path, block=filled, heading=False)
    assert checks(tmp_path) == set()


# --- dogfood: the repo's own corpus ---------------------------------------------------------


def test_this_repo_passes_its_own_gate():
    adr_dir = Path(__file__).resolve().parents[2] / "docs" / "adr"
    if not adr_dir.is_dir():  # pragma: no cover - installed-package runs
        pytest.skip("running outside a repo checkout")
    records = adr_mod.check_dir(adr_dir)
    assert adr_mod.errors_of(records) == []
    # ADR-029 itself is gated, not grandfathered — a gate whose own record is exempt
    # is the label-is-not-evidence failure in miniature.
    gated = {r.number for r in records if r.gated}
    assert 29 in gated
