"""P2.1 — `baron decision reconcile` / `check` acceptance (ADR-009, park only).

The load-bearing test here is `test_labelled_but_open_without_declaration_is_outstanding`:
it pins the exact state D57 recorded for epic #214 — labelled `parked`, comment
posted, LEFT OPEN — which is the state FM6's root cause describes. An earlier
revision of the design would have called that discharged.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from baron import decision
from baron.cli import app

runner = CliRunner()

INDEX = """# Decisions

### D56 — An earlier decision (2026-07-31, Vikram)

Prose the Librarian wrote.

### D57 — VLM commodity intelligence is the product (2026-07-31, Vikram)

Prose that must never be touched by generation.

### D58 — A later decision (2026-08-01, Vikram)

More prose.
"""


def _collab(tmp_path: Path, *, source="file", park_label=None, backlog="- SHU-1 epic #214\n"):
    root = tmp_path / "collab"
    (root / "decisions").mkdir(parents=True)
    (root / "decisions/index.md").write_text(INDEX, encoding="utf-8")
    (root / "backlog.md").write_text(backlog, encoding="utf-8")
    m = {"backlog": {"source": source, "location": "backlog.md"}}
    if park_label:
        m["backlog"]["park_label"] = park_label
    return root, m


def test_reconcile_writes_a_block_without_touching_prose(tmp_path: Path) -> None:
    root, _ = _collab(tmp_path)
    decision.reconcile(root, 57, parks=[decision.Park("214")], commit=False)
    text = (root / "decisions/index.md").read_text(encoding="utf-8")

    assert "Prose that must never be touched by generation." in text
    assert decision.BEGIN_MARKER in text and decision.END_MARKER in text
    # The block lands inside D57, not D56 or D58.
    d57 = text.split("### D57")[1].split("### D58")[0]
    assert decision.BEGIN_MARKER in d57
    assert "### D56" in text and "### D58" in text
    assert decision.BEGIN_MARKER not in text.split("### D57")[0]


def test_reconcile_is_idempotent(tmp_path: Path) -> None:
    root, _ = _collab(tmp_path)
    decision.reconcile(root, 57, parks=[decision.Park("214")], commit=False)
    merged = decision.reconcile(root, 57, parks=[decision.Park("214")], commit=False)
    assert len(merged) == 1
    text = (root / "decisions/index.md").read_text(encoding="utf-8")
    assert text.count(decision.BEGIN_MARKER) == 1
    # ...and a second, different park accumulates rather than replacing.
    merged = decision.reconcile(root, 57, parks=[decision.Park("215")], commit=False)
    assert sorted(p.issue for p in merged) == ["214", "215"]


def test_malformed_block_is_reported_never_rewritten(tmp_path: Path) -> None:
    """ADR-003 §2.6 precedent: report, don't silently repair AUTHORED data."""
    root, _ = _collab(tmp_path)
    p = root / "decisions/index.md"
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "Prose that must never be touched by generation.",
            f"Prose\n\n{decision.BEGIN_MARKER}\npark: [oops\n",  # no END marker
        ),
        encoding="utf-8",
    )
    before = p.read_text(encoding="utf-8")
    with pytest.raises(decision.DecisionError, match="without a closing"):
        decision.reconcile(root, 57, parks=[decision.Park("214")], commit=False)
    assert p.read_text(encoding="utf-8") == before, "the file must not be modified"


def test_unknown_decision_number_refuses(tmp_path: Path) -> None:
    root, _ = _collab(tmp_path)
    with pytest.raises(decision.DecisionError, match="no `### D999` entry"):
        decision.reconcile(root, 999, parks=[decision.Park("1")], commit=False)


# --- discharge semantics: the heart of ADR-009 §3.2 -------------------------------------

def test_labelled_but_open_without_declaration_is_outstanding(tmp_path: Path) -> None:
    """THE regression that defines this feature.

    D57 recorded epic #214 as `PARKED (label 'parked' + decision comment)` and left
    it OPEN — and FM6's root cause is that #214 "sat open generating work". A design
    that calls this discharged reproduces the failure it cites. Here the backlog file
    still lists the item and no park_label is declared, so the only discharge is
    removing it.
    """
    root, m = _collab(tmp_path, backlog="- SHU-1 epic #214 (parked, see D57)\n")
    decision.reconcile(root, 57, parks=[decision.Park("#214")], commit=False)
    findings = decision.check(root, m)
    assert [f.state for f in findings] == [decision.OUTSTANDING]
    assert "park_label is not declared" in findings[0].message


def test_declared_label_discharges(tmp_path: Path) -> None:
    root, m = _collab(
        tmp_path, park_label="parked", backlog="- SHU-1 epic #214 <!-- parked --> see D57\n"
    )
    decision.reconcile(root, 57, parks=[decision.Park("#214")], commit=False)
    findings = decision.check(root, m)
    assert [f.state for f in findings] == [decision.DISCHARGED]


def test_absence_is_never_proof_of_discharge(tmp_path: Path) -> None:
    """ABSENCE IS NOT PROOF — the correction that mattered most.

    An earlier cut discharged when the id matched no line. Review showed that is
    indistinguishable from the id simply failing to match: `--park 214` against
    `GH-214 ... ACTIVE` handed out the STRONG discharge on a live epic, and any typo
    became a permanently green obligation. baron cannot tell 'removed' from 'never
    matched', so it must say so rather than guess in the unsafe direction.
    """
    root, m = _collab(tmp_path, backlog="- SHU-2 something else\n")
    decision.reconcile(root, 57, parks=[decision.Park("#214")], commit=False)
    findings = decision.check(root, m)
    assert findings[0].state == decision.UNVERIFIABLE
    assert "cannot distinguish" in findings[0].message


def test_prefixed_id_mismatch_does_not_discharge(tmp_path: Path) -> None:
    """`--park 214` vs `GH-214 ... ACTIVE` — the second false DISCHARGED found."""
    root, m = _collab(tmp_path, backlog="- [ ] GH-214 Epic: storage rewrite — ACTIVE\n")
    decision.reconcile(root, 57, parks=[decision.Park("214")], commit=False)
    assert decision.check(root, m)[0].state != decision.DISCHARGED


@pytest.mark.parametrize("line", [
    "- [ ] #214 Epic — was parked, REOPENED, ACTIVE\n",          # bare token (round 2)
    "- [ ] #214 Epic — was (parked) under D57, REOPENED, ACTIVE\n",  # delimited (round 3)
    "- [ ] #214 Epic — see [parked] items, ACTIVE\n",             # bracketed in prose
    "## Parked items\n- [ ] #214 Epic ACTIVE\n",                  # marker on a heading
])
def test_park_marker_cannot_be_written_by_prose(tmp_path: Path, line: str) -> None:
    """Three marker rules have been tried; two were defeated by ordinary prose.

    A bare token fell to `was parked, REOPENED`. `[parked]`/`(parked)` fell to
    `was (parked) under D57, REOPENED, ACTIVE` — a sentence taken from this module's
    own docstring. The marker must be something an author cannot write while merely
    DESCRIBING the item: an HTML comment.
    """
    root, m = _collab(tmp_path, park_label="parked", backlog=line)
    decision.reconcile(root, 57, parks=[decision.Park("#214")], commit=False)
    assert decision.check(root, m)[0].state != decision.DISCHARGED


def test_html_comment_marker_discharges(tmp_path: Path) -> None:
    root, m = _collab(
        tmp_path, park_label="parked", backlog="- [ ] #214 Epic <!-- parked -->\n"
    )
    decision.reconcile(root, 57, parks=[decision.Park("#214")], commit=False)
    assert decision.check(root, m)[0].state == decision.DISCHARGED


def test_unverifiable_is_not_green(tmp_path: Path) -> None:
    """THE round-3 blocker. Moving absence DISCHARGED->UNVERIFIABLE produced the
    identical exit code, so nothing a CI gate can see actually changed. An
    obligation baron could not verify is not an obligation discharged."""
    root, m = _collab(tmp_path, backlog="- [ ] GH-214 Epic ACTIVE\n")
    decision.reconcile(root, 57, parks=[decision.Park("#214")], commit=False)
    findings = decision.check(root, m)
    assert findings[0].state == decision.UNVERIFIABLE
    assert not decision.is_green(findings), "unverifiable must not exit 0"


def test_missing_backlog_file_is_outstanding_not_green(tmp_path: Path) -> None:
    """Deleting the declared backlog must not be a way to turn the gate green."""
    root, m = _collab(tmp_path)
    decision.reconcile(root, 57, parks=[decision.Park("#214")], commit=False)
    (root / "backlog.md").unlink()
    findings = decision.check(root, m)
    assert findings[0].state == decision.OUTSTANDING
    assert decision.has_outstanding(findings)


def test_declared_label_but_item_unmarked_is_outstanding(tmp_path: Path) -> None:
    root, m = _collab(tmp_path, park_label="parked", backlog="- SHU-1 epic #214 active\n")
    decision.reconcile(root, 57, parks=[decision.Park("#214")], commit=False)
    findings = decision.check(root, m)
    assert findings[0].state == decision.OUTSTANDING
    assert "still be offered this work" in findings[0].message


def test_github_source_without_fetch_is_unverifiable_not_green(tmp_path: Path) -> None:
    root, m = _collab(tmp_path, source="github_issues")
    decision.reconcile(root, 57, parks=[decision.Park("214")], commit=False)
    findings = decision.check(root, m)
    assert [f.state for f in findings] == [decision.UNVERIFIABLE]
    assert not decision.has_outstanding(findings)  # never scored as either


def test_unsupported_backlog_source_is_unverifiable(tmp_path: Path) -> None:
    root, m = _collab(tmp_path, source="jira")
    decision.reconcile(root, 57, parks=[decision.Park("PROJ-1")], commit=False)
    assert [f.state for f in decision.check(root, m)] == [decision.UNVERIFIABLE]


def test_forge_park_open_and_unlabelled_is_the_fm6_state(tmp_path: Path) -> None:
    class Forge:
        def get_issue(self, repo, number, *, target_repo=None):
            return {"number": number, "state": "OPEN", "labels": ["epic"]}

    root, m = _collab(tmp_path, source="github_issues", park_label="parked")
    decision.reconcile(root, 57, parks=[decision.Park("214")], commit=False)
    findings = decision.check(root, m, forge=Forge(), repo=root)
    assert findings[0].state == decision.OUTSTANDING
    assert "FM6 state" in findings[0].message


def test_forge_park_closed_or_labelled_discharges(tmp_path: Path) -> None:
    class Closed:
        def get_issue(self, repo, number, *, target_repo=None):
            return {"state": "CLOSED", "labels": []}

    class Labelled:
        def get_issue(self, repo, number, *, target_repo=None):
            return {"state": "OPEN", "labels": ["parked"]}

    root, m = _collab(tmp_path, source="github_issues", park_label="parked")
    decision.reconcile(root, 57, parks=[decision.Park("214")], commit=False)
    for forge in (Closed(), Labelled()):
        assert decision.check(root, m, forge=forge, repo=root)[0].state == decision.DISCHARGED


def test_no_recorded_obligations_is_green_not_warned(tmp_path: Path) -> None:
    """Q4 default: block-less legacy decisions are opt-in, not nagged."""
    root, m = _collab(tmp_path)
    assert decision.check(root, m) == []


def test_cli_roundtrip_and_exit_codes(tmp_path: Path) -> None:
    root, m = _collab(tmp_path, backlog="- SHU-1 epic #214 still here\n")
    (root / "manifest.yaml").write_text(yaml.safe_dump({
        "project": {"name": "p", "description": "d"},
        "paths": {"strategy": "relative", "root": "."},
        "repos": [{"id": "collab", "path": ".", "role": "collab"}],
        "backlog": m["backlog"],
        "personas": [{"slug": "a", "spec": "agents/a/persona.yaml"}],
    }), encoding="utf-8")

    r = runner.invoke(app, ["decision", "reconcile", "57", "--park", "#214",
                            "--collab", str(root), "--no-commit"])
    assert r.exit_code == 0, r.output
    assert "1 park obligation(s) recorded" in r.output

    r = runner.invoke(app, ["decision", "check", "--collab", str(root)])
    assert r.exit_code == 1, r.output          # outstanding -> non-zero, CI-usable
    assert "OUTSTANDING" in r.output


def test_optional_forge_extension_is_not_in_the_protocol(tmp_path: Path) -> None:
    """`get_issue` must stay OUT of the @runtime_checkable Protocol.

    Those isinstance checks test method PRESENCE, so putting an optional capability
    on the Protocol retroactively invalidates every implementation that predates it
    — the opposite of additive. This is not hypothetical: declaring `get_issue` on
    the Protocol broke the recorded fake forge in test_lock.py, which is exactly what
    would happen to a third-party `baron.forges` plugin.
    """
    from baron.forge.base import Forge, supports

    class OldPlugin:  # implements only the pre-existing surface
        name = "old"
        def available(self): return True
        def default_branch(self, repo): return "main"
        def open_pr(self, repo, **kw): return "url"
        def list_open_prs(self, repo): return []
        def create_branch(self, repo, **kw): return None
        def close_pr(self, repo, number, **kw): return None

    old = OldPlugin()
    assert isinstance(old, Forge), "adding an optional method must not invalidate older forges"
    assert not supports(old, "get_issue")

    # ...and a park check against such a forge degrades to unverifiable, not a crash.
    root, m = _collab(tmp_path, source="github_issues")
    decision.reconcile(root, 57, parks=[decision.Park("214")], commit=False)
    findings = decision.check(root, m, forge=old, repo=root)
    assert findings[0].state == decision.UNVERIFIABLE
    assert "get_issue" in findings[0].message


# --- regressions for the three FALSE DISCHARGEDs found in review -------------------------

@pytest.mark.parametrize("backlog,why", [
    ("- SHU-1 epic #214 unparked and active\n", "the NEGATION of the park label"),
    ("- SHU-1 epic #214 in unparkedland\n", "the label inside a longer word"),
])
def test_park_label_must_match_as_a_token_not_a_substring(tmp_path, backlog, why) -> None:
    """`unparked` contains `parked`. Substring matching discharged the park on the
    negation of its own label."""
    root, m = _collab(tmp_path, park_label="parked", backlog=backlog)
    decision.reconcile(root, 57, parks=[decision.Park("#214")], commit=False)
    findings = decision.check(root, m)
    assert findings[0].state == decision.OUTSTANDING, why


def test_issue_id_format_mismatch_is_not_reported_absent(tmp_path) -> None:
    """The worst of the three: `--park #214` against a line reading `issue 214 ...`
    matched nothing and was reported ABSENT — the STRONG discharge — while the item
    sat in the backlog, active."""
    root, m = _collab(tmp_path, backlog="- issue 214 Epic ACTIVE\n")
    decision.reconcile(root, 57, parks=[decision.Park("#214")], commit=False)
    findings = decision.check(root, m)
    assert findings[0].state == decision.OUTSTANDING
    assert "absent" not in findings[0].message


def test_issue_id_does_not_match_a_longer_id(tmp_path) -> None:
    """`--park 214` was discharged by an unrelated `SHU-2140`."""
    root, m = _collab(tmp_path, backlog="- SHU-2140 an unrelated item\n")
    decision.reconcile(root, 57, parks=[decision.Park("214")], commit=False)
    # 2140 must NOT satisfy 214 — and with no real match the answer is unverifiable,
    # never discharged (see test_absence_is_never_proof_of_discharge).
    assert decision.check(root, m)[0].state == decision.UNVERIFIABLE
    # ...and when the real one IS present alongside, it must be found.
    (root / "backlog.md").write_text("- SHU-2140 unrelated\n- epic 214 active\n", encoding="utf-8")
    assert decision.check(root, m)[0].state == decision.OUTSTANDING


def test_malformed_block_is_outstanding_not_green(tmp_path) -> None:
    """Corrupting the block must not be the easiest way to turn the gate green."""
    root, m = _collab(tmp_path)
    decision.reconcile(root, 57, parks=[decision.Park("#214")], commit=False)
    p = root / "decisions/index.md"
    p.write_text(p.read_text(encoding="utf-8").replace(decision.END_MARKER, ""), encoding="utf-8")
    findings = decision.check(root, m)
    assert findings[0].state == decision.OUTSTANDING
    assert decision.has_outstanding(findings)


def test_duplicate_decision_headings_refuse(tmp_path) -> None:
    """Writing into the first would silently orphan the second's obligations."""
    root, _ = _collab(tmp_path)
    p = root / "decisions/index.md"
    p.write_text(p.read_text(encoding="utf-8") + "\n### D57 — a duplicate (2026-08-04, x)\n",
                 encoding="utf-8")
    with pytest.raises(decision.DecisionError, match="appears 2 times"):
        decision.reconcile(root, 57, parks=[decision.Park("1")], commit=False)


def test_forge_park_targets_the_declared_repo(tmp_path) -> None:
    """Without --repo, gh answers the COLLAB repo's same-numbered issue."""
    seen = {}

    class Forge:
        def get_issue(self, repo, number, *, target_repo=None):
            seen["target"] = target_repo
            return {"state": "OPEN", "labels": ["parked"]}

    root, m = _collab(tmp_path, source="github_issues", park_label="parked")
    m["backlog"]["location"] = "vggg/badminton-analyzer"
    decision.reconcile(root, 57, parks=[decision.Park("214")], commit=False)
    decision.check(root, m, forge=Forge(), repo=root)
    assert seen["target"] == "vggg/badminton-analyzer"


def test_unresolvable_park_repo_refuses_rather_than_querying_the_wrong_one(tmp_path) -> None:
    class Forge:
        def get_issue(self, repo, number, *, target_repo=None):
            raise AssertionError("must not query when the repo cannot be resolved")

    root, m = _collab(tmp_path, source="github_issues")
    decision.reconcile(root, 57, parks=[decision.Park("214", repo="code")], commit=False)
    findings = decision.check(root, m, forge=Forge(), repo=root)
    assert findings[0].state == decision.UNVERIFIABLE
    assert "refusing to query a different repo" in findings[0].message
