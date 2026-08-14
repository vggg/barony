"""P3.3 acceptance: the governed-memory evaluation harness.

Three kinds of test here, and they are not interchangeable.

**Behaviour** — the harness materializes the fixture corpus into a real git
repo, exports it through the same walk a real collab repo gets, and computes the
metrics AGENT-TASKS.md 3.3 names. The load-bearing assertion is that a metric
which cannot be computed comes back ``None``, never a silent zero.

**Regression on the flagship fixture** — the 2026-08-04 identity incident is in
the fixture set on purpose (an in-corpus ADR + handoff + finding, and the survey
note deliberately left outside the exported corpora). Its numbers are pinned so
that a change to the retriever or the corpus walk cannot quietly move the one
case the harness exists to prevent.

**Boundary guards** — mirroring ``test_export.py``'s last two tests. 3.3 is the
gate on 3.4, so shipping 3.3 must not smuggle 3.4 in: no semantic retriever, no
``baron.knowledge`` entry-point group, no vendor name, no new dependency.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from baron import memeval
from baron.cli import app

from conftest import REPO_ROOT

runner = CliRunner()

FIXTURES = REPO_ROOT / "evals" / "governed-memory"

#: The flagship: the 2026-08-04 identity incident, as it exists in the fixtures.
FLAGSHIP_QUERY = "Q1-identity-flagship"
FLAGSHIP_IN_CORPUS = {
    "adr:ADR-027",
    "finding:F4",
    "handoff:2026-08-05-0900-tess-agent-identity-spike",
}
FLAGSHIP_UNREACHABLE = "wiki:research-agent-identity-lightweight"


@pytest.fixture
def report(tmp_path: Path) -> memeval.Report:
    return memeval.run(FIXTURES, tmp_path / "corpus")


# --- fixtures + materialization --------------------------------------------------------


def test_fixture_set_covers_every_case_the_spec_names() -> None:
    fx = memeval.load_fixtures(FIXTURES)
    types = {e.type for e in fx.events}
    assert {"commit", "release", "adr", "finding", "decision", "milestone"} <= types
    adr_statuses = {e.status for e in fx.events if e.type == "adr"}
    assert {"accepted", "proposed", "parked", "superseded"} <= adr_statuses
    assert any(e.duplicate_of for e in fx.events), "no duplicate event"
    assert any(e.gold.get("needs_human") for e in fx.events), "no bad/missing source-SHA case"
    assert any(e.type == "finding" and e.thesis_changing for e in fx.events)
    assert any(q.stale for q in fx.queries), "no supersession/freshness query"
    assert fx.uncommitted and fx.modified and fx.out_of_corpus


def test_materialize_reproduces_both_halves_of_the_citation_gate(tmp_path: Path) -> None:
    fx = memeval.load_fixtures(FIXTURES)
    repo = memeval.materialize(fx, tmp_path / "corpus")
    from baron import export

    result = export.collect(repo)
    reasons = {s.path: s.reason for s in result.skipped}
    assert reasons.get(fx.uncommitted[0]) == "uncommitted"
    assert reasons.get(str(fx.modified[0]["path"])) == "modified"
    # The out-of-corpus file is present in the tree and absent from the export.
    assert (repo / fx.out_of_corpus[0]).is_file()
    assert all(r.path != fx.out_of_corpus[0] for r in result.records)


def test_materialize_refuses_a_corpus_file_no_commit_names(tmp_path: Path) -> None:
    """A file added to corpus/ but forgotten in the build manifest would sit
    untracked and silently vanish from every measurement. That is exactly the
    failure this harness is supposed to expose, so it fails loudly instead."""
    fx = memeval.load_fixtures(FIXTURES)
    fx.commits = fx.commits[:2]
    with pytest.raises(memeval.MemevalError, match="named by no commit"):
        memeval.materialize(fx, tmp_path / "corpus")


def test_run_is_deterministic(tmp_path: Path) -> None:
    first = memeval.run(FIXTURES, tmp_path / "a").to_dict()
    second = memeval.run(FIXTURES, tmp_path / "b").to_dict()
    for payload in (first, second):
        payload.pop("fixtures")
        payload.pop("generated")
        payload["corpus"].pop("head")
    assert first == second


# --- retrieval -------------------------------------------------------------------------


def test_flagship_identity_case_is_retrieved_from_the_corpus(report: memeval.Report) -> None:
    """The re-derivation case. A change that stops the lexical baseline finding
    the identity decision is a regression, not a tuning choice."""
    baseline = _approach(report, "git-markdown")
    query = _query(baseline, FLAGSHIP_QUERY)
    assert set(query["found"]) == FLAGSHIP_IN_CORPUS
    assert query["first_relevant_rank"] == 1


def test_flagship_miss_is_corpus_coverage_not_ranking(report: memeval.Report) -> None:
    """The half the baseline cannot retrieve is the survey note, and the reason
    is that it lives outside the four corpora `baron export` walks — not that it
    ranked badly. That distinction is the finding P3.4 has to act on."""
    baseline = _approach(report, "git-markdown")
    query = _query(baseline, FLAGSHIP_QUERY)
    assert query["unreachable"] == [FLAGSHIP_UNREACHABLE]
    assert query["recall_at_k"] == pytest.approx(0.75)


def test_corpus_ceiling_is_below_one_and_is_reported(report: memeval.Report) -> None:
    ceiling = report.corpus["retrieval_ceiling"]
    assert ceiling is not None and 0.0 < float(ceiling) < 1.0
    assert report.corpus["out_of_corpus"] == ["wiki/research-agent-identity-lightweight.md"]


def test_uncommitted_answer_is_unreachable_by_construction(report: memeval.Report) -> None:
    """The citation gate has a retrieval cost and the harness prices it rather
    than assuming it away: the answer is on disk, uncommitted, and therefore
    outside every strategy's reach."""
    query = _query(_approach(report, "git-markdown"), "Q8-uncited-answer")
    assert query["found"] == []
    assert query["gold_reachable"] == []
    assert query["recall_at_k"] == 0.0


def test_supersession_prefers_the_current_record(report: memeval.Report) -> None:
    retrieval = _approach(report, "git-markdown").retrieval
    assert retrieval is not None
    assert retrieval.supersession_queries >= 2
    assert retrieval.supersession_accuracy == 1.0


def test_every_retrieved_record_carries_a_citation_that_resolves(
    report: memeval.Report,
) -> None:
    retrieval = _approach(report, "git-markdown").retrieval
    assert retrieval is not None
    assert retrieval.citations_checked > 0
    assert retrieval.citation_accuracy == 1.0


def test_lexical_retriever_returns_nothing_when_no_term_matches() -> None:
    from baron.export import Record

    records = [
        Record(id="X1", kind="finding", title="alpha", path="p.md", commit_sha="a", status=None,
               body="beta gamma")
    ]
    query = memeval.Query(id="q", text="zzzz qqqq", relevant=[])
    assert memeval.LexicalRetriever().rank(query, records) == []


# --- propagation -----------------------------------------------------------------------


def test_hooks_beat_the_baseline_on_duplicates_and_schema(report: memeval.Report) -> None:
    baseline = _approach(report, "git-markdown").propagation
    hooks = _approach(report, "hooks").propagation
    assert baseline is not None and hooks is not None
    # The measured delta, and the two places it comes from: a reworded re-report
    # of an already-propagated event, and knowing which kind of note to write.
    assert hooks.duplicate_suppression is not None
    assert baseline.duplicate_suppression is not None
    assert hooks.duplicate_suppression > baseline.duplicate_suppression
    assert baseline.schema_accuracy == 0.0
    assert hooks.schema_accuracy == 1.0
    assert hooks.intervention_tax is not None and baseline.intervention_tax is not None
    assert hooks.intervention_tax < baseline.intervention_tax


def test_missing_source_sha_is_flagged_for_a_human_not_propagated() -> None:
    fx = memeval.load_fixtures(FIXTURES)
    metrics = memeval.score_propagation(memeval.HooksPropagator(), fx)
    row = next(r for r in metrics.per_event if r["id"] == "E12")
    assert row["propagated"] is False
    assert row["needs_human"] is True
    assert "sha" in str(row["reason"]).lower()
    assert metrics.flagged >= 1


def test_baseline_cannot_see_a_missing_sha_and_says_so() -> None:
    """Not a bug in the baseline — the point. A keyword match over a subject
    line has no SHA to check, so the bad-source case reads as a normal event."""
    fx = memeval.load_fixtures(FIXTURES)
    metrics = memeval.score_propagation(memeval.LexicalPropagator(), fx)
    row = next(r for r in metrics.per_event if r["id"] == "E12")
    assert row["needs_human"] is False


def test_rates_with_an_empty_denominator_are_none_not_zero() -> None:
    assert memeval._f(0, 0) is None
    assert memeval._f(0, 3) == 0.0


# --- report surface --------------------------------------------------------------------


def test_cli_table_names_the_honesty_bound_and_the_unmeasured_approaches() -> None:
    result = runner.invoke(app, ["memeval", "--fixtures", str(FIXTURES)])
    assert result.exit_code == 0, result.output
    assert memeval.HONESTY_BOUND in result.output
    assert result.output.count("NOT MEASURED") == 2
    assert "semantic" in result.output


def test_cli_json_reports_unavailable_approaches_without_numbers() -> None:
    result = runner.invoke(app, ["memeval", "--fixtures", str(FIXTURES), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["format"] == memeval.FORMAT
    assert payload["honesty_bound"] == memeval.HONESTY_BOUND
    unavailable = [a for a in payload["approaches"] if not a["available"]]
    assert {a["name"] for a in unavailable} == {"semantic", "hooks+semantic"}
    for entry in unavailable:
        assert entry["retrieval"] is None and entry["propagation"] is None
        assert "P3.4" in entry["reason"]


def test_cli_exits_2_on_a_bad_fixture_path(tmp_path: Path) -> None:
    result = runner.invoke(app, ["memeval", "--fixtures", str(tmp_path)])
    assert result.exit_code == 2
    assert "fixtures.yaml" in result.output


def test_unknown_approach_is_refused(tmp_path: Path) -> None:
    with pytest.raises(memeval.MemevalError, match="unknown approach"):
        memeval.run(FIXTURES, tmp_path / "corpus", approaches=["telepathy"])


# --- boundary guards: 3.3 must not smuggle in 3.4 ---------------------------------------


def test_no_semantic_retriever_is_registered() -> None:
    """ADR-031 §5. The seam is an in-process dict, and it is empty of anything
    semantic: 3.4 selects a backend, 3.3 only measures. If this fails, a backend
    arrived through the harness instead of through the gate it is meant to be."""
    assert set(memeval.RETRIEVERS) == {"lexical"}
    assert set(memeval.PROPAGATORS) == {"lexical", "hooks"}


def test_the_two_semantic_approaches_are_declared_and_unmeasured(
    report: memeval.Report,
) -> None:
    """They appear in the report — 3.3 asks for a four-way comparison — but as
    named holes, never as estimates."""
    names = [a.approach.name for a in report.approaches]
    assert names == ["git-markdown", "hooks", "semantic", "hooks+semantic"]
    for result in report.approaches:
        if result.approach.retriever == "semantic":
            assert not result.available
            assert result.retrieval is None and result.propagation is None


def test_memeval_names_no_vendor() -> None:
    text = (REPO_ROOT / "cli" / "src" / "baron" / "memeval.py").read_text(encoding="utf-8")
    assert "cognee" not in text.lower()


def test_no_knowledge_entry_point_group_was_published_by_3_3() -> None:
    """Mirrors ``test_export.py``. Shipping the harness must not publish the
    plugin seam the harness is supposed to gate."""
    text = (REPO_ROOT / "cli" / "pyproject.toml").read_text(encoding="utf-8")
    groups = re.findall(r'^\[project\.entry-points\."([^"]+)"\]', text, re.M)
    assert "baron.knowledge" not in groups, groups
    assert set(groups) <= {"baron.forges", "baron.sinks"}, groups


def test_harness_added_no_runtime_dependency() -> None:
    """ADR-003's dependency policy. The harness is stdlib + typer + pyyaml; an
    embedding library or a vector store arriving here would be 3.4 by stealth."""
    text = (REPO_ROOT / "cli" / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"^dependencies = \[(.*?)\]", text, re.S | re.M)
    assert block is not None
    names = re.findall(r'"([A-Za-z0-9_.-]+)', block.group(1))
    assert sorted(names) == ["pyyaml", "typer"], names


# --- helpers ---------------------------------------------------------------------------


def _approach(report: memeval.Report, name: str) -> memeval.ApproachResult:
    return next(a for a in report.approaches if a.approach.name == name)


def _query(result: memeval.ApproachResult, query_id: str) -> dict[str, object]:
    assert result.retrieval is not None
    return next(q for q in result.retrieval.per_query if q["id"] == query_id)
