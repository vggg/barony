"""ADR-027 acceptance: the merge gate passes on exactly one shape and refuses everything else.

The gate is pure over a PR snapshot, so the matrix is built from fixture dicts and a
recorded fake forge — no live ``gh``. Every refusal path in `merge.PRECONDITIONS` has a
case here, including the two the field near-misses produced: a stale verdict, and a
PR carrying an approval LABEL and nothing else.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from baron import merge
from baron.cli import app
from baron.forge.base import ForgeError

HEAD = "a" * 40
OLD = "b" * 40

runner = CliRunner()


def _comment(body: str, *, author: str = "reviewer", at: str = "2026-08-14T10:00:00Z") -> dict:
    return {"author": {"login": author}, "body": body, "createdAt": at}


def pr(
    *,
    head: str = HEAD,
    state: str = "OPEN",
    draft: bool = False,
    comments: list | None = None,
    labels: list | None = None,
    checks: list | None = None,
    review_decision: str = "",
) -> dict:
    """A snapshot that PASSES the gate, minus whatever the caller breaks."""
    return {
        "number": 128,
        "state": state,
        "isDraft": draft,
        "headRefOid": head,
        "url": "https://example.invalid/pr/128",
        "labels": labels if labels is not None else [],
        "reviewDecision": review_decision,
        "comments": comments if comments is not None else [_comment(f"REVIEW:PASS {head}")],
        "checks": checks if checks is not None else [{"name": "ci", "state": "SUCCESS"}],
    }


def refusal(result: merge.GateResult) -> tuple[str, str]:
    assert not result.allowed
    ref = result.refusal
    assert ref is not None
    return ref.name, ref.reason


# --- the pass path -----------------------------------------------------------------------


def test_pass_path():
    result = merge.evaluate(pr())
    assert result.allowed
    assert [p.name for p in result.preconditions] == list(merge.PRECONDITIONS)
    assert all(p.ok for p in result.preconditions)
    assert result.to_dict()["verdict"] == "PASS"


def test_pass_path_tolerates_extra_comments_and_a_superseded_verdict():
    """Re-review publishes a NEW verdict; the old one stays in the record."""
    result = merge.evaluate(
        pr(
            comments=[
                _comment(f"REVIEW:FAIL {OLD}", at="2026-08-13T10:00:00Z"),
                _comment("pushed a fix", author="dev", at="2026-08-13T11:00:00Z"),
                _comment(f"REVIEW:PASS {HEAD}", at="2026-08-14T10:00:00Z"),
            ]
        )
    )
    assert result.allowed


def test_skipped_and_neutral_checks_pass_beside_a_real_success():
    result = merge.evaluate(
        pr(checks=[
            {"name": "docs", "state": "SKIPPED"},
            {"name": "lint", "state": "NEUTRAL"},
            {"name": "tests", "state": "SUCCESS"},
        ])
    )
    assert result.allowed


# --- refusal: the PR itself ---------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"state": "MERGED"}, merge.PR_NOT_OPEN),
        ({"state": "CLOSED"}, merge.PR_NOT_OPEN),
        ({"draft": True}, merge.PR_DRAFT),
        ({"head": ""}, merge.HEAD_UNKNOWN),
        ({"head": "a1b2c3d"}, merge.HEAD_UNKNOWN),
    ],
)
def test_refuses_unmergeable_pr_states(kwargs, reason):
    assert refusal(merge.evaluate(pr(**kwargs))) == ("pr_open", reason)


def test_later_preconditions_are_failed_not_skipped_when_the_pr_is_unreadable():
    """Fail-closed: an unreachable check is red, never absent."""
    result = merge.evaluate(pr(state="CLOSED"))
    later = [p for p in result.preconditions if p.name != "pr_open"]
    # Every precondition after the failing one, whatever the list currently is — asserting
    # the count against PRECONDITIONS rather than a literal means adding a precondition
    # (ADR-033 added `verdict_signed`) cannot leave one silently unevaluated.
    assert len(later) == len(merge.PRECONDITIONS) - 1
    assert all(not p.ok and p.reason == merge.UNEVALUATED for p in later)


# --- refusal: the verdict ------------------------------------------------------------------


def test_refuses_when_no_verdict_exists():
    result = merge.evaluate(pr(comments=[_comment("looks good to me!", author="dev")]))
    assert refusal(result) == ("verdict_at_head", merge.NO_VERDICT)


def test_refuses_a_stale_verdict_the_head_moved_past():
    """The strip-stale-verdict discipline: a new push voids the verdict."""
    result = merge.evaluate(pr(comments=[_comment(f"REVIEW:PASS {OLD}")]))
    name, reason = refusal(result)
    assert (name, reason) == ("verdict_at_head", merge.STALE_VERDICT)
    assert OLD[:12] in result.refusal.detail and HEAD[:12] in result.refusal.detail


def test_refuses_an_abbreviated_sha_rather_than_prefix_matching():
    result = merge.evaluate(pr(comments=[_comment(f"REVIEW:PASS {HEAD[:12]}")]))
    assert refusal(result) == ("verdict_at_head", merge.VERDICT_MALFORMED)


@pytest.mark.parametrize("body", ["REVIEW:PASS HEAD", "REVIEW:PASS feat/my-branch"])
def test_refuses_a_verdict_naming_something_that_is_not_a_sha(body):
    assert refusal(merge.evaluate(pr(comments=[_comment(body)])))[0] == "verdict_at_head"


def test_a_quoted_verdict_mid_sentence_is_not_a_verdict():
    result = merge.evaluate(
        pr(comments=[_comment(f"I will post a REVIEW:PASS {HEAD} once CI clears", author="dev")])
    )
    assert refusal(result) == ("verdict_at_head", merge.NO_VERDICT)


def test_verdict_author_pin_refuses_a_self_issued_verdict():
    """Meaningful only once identities exist (ADR-027) — off by default."""
    snap = pr(comments=[_comment(f"REVIEW:PASS {HEAD}", author="dev")])
    assert merge.evaluate(snap).allowed
    result = merge.evaluate(snap, verdict_author="reviewer")
    assert refusal(result) == ("verdict_at_head", merge.VERDICT_AUTHOR)


# --- refusal: changes requested --------------------------------------------------------------


def test_refuses_an_open_review_fail_at_the_head():
    result = merge.evaluate(pr(comments=[_comment(f"REVIEW:FAIL {HEAD}")]))
    assert refusal(result) == ("no_changes_requested", merge.CHANGES_REQUESTED)


def test_a_later_pass_on_the_same_sha_does_not_clear_a_fail():
    result = merge.evaluate(
        pr(comments=[
            _comment(f"REVIEW:FAIL {HEAD}", at="2026-08-14T10:00:00Z"),
            _comment(f"REVIEW:PASS {HEAD}", at="2026-08-14T12:00:00Z"),
        ])
    )
    assert refusal(result) == ("no_changes_requested", merge.CHANGES_REQUESTED)


def test_platform_changes_requested_blocks_even_though_platform_approval_never_authorizes():
    blocked = merge.evaluate(pr(review_decision="CHANGES_REQUESTED"))
    assert refusal(blocked) == ("no_changes_requested", merge.PLATFORM_CHANGES_REQUESTED)
    # ...and the mirror: a platform APPROVAL is not a verdict.
    approved_only = merge.evaluate(pr(review_decision="APPROVED", comments=[]))
    assert refusal(approved_only) == ("verdict_at_head", merge.NO_VERDICT)


# --- refusal: CI -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "checks,reason",
    [
        ([{"name": "tests", "state": "FAILURE"}], merge.CI_RED),
        ([{"name": "tests", "state": "TIMED_OUT"}], merge.CI_RED),
        ([{"name": "tests", "state": "IN_PROGRESS"}], merge.CI_PENDING),
        ([{"name": "tests", "state": ""}], merge.CI_PENDING),
        ([], merge.CI_ABSENT),
        ([{"name": "docs", "state": "SKIPPED"}], merge.CI_ABSENT),
        ([{"name": "tests", "state": "WAT"}], merge.CI_UNKNOWN_STATE),
        ([{"name": "ok", "state": "SUCCESS"}, {"name": "e2e", "state": "FAILURE"}], merge.CI_RED),
    ],
)
def test_refuses_ci_that_is_not_demonstrably_green(checks, reason):
    assert refusal(merge.evaluate(pr(checks=checks))) == ("ci_green", reason)


# --- labels are never an input ------------------------------------------------------------------


def test_label_only_pr_is_refused_and_the_label_is_named_as_ignored():
    """The 2026-07-30 near-miss: an approval label surviving the push that voided it."""
    result = merge.evaluate(pr(comments=[], labels=["reviewed-approved", "agent-dev"]))
    assert refusal(result) == ("verdict_at_head", merge.NO_VERDICT)
    assert result.ignored_signals == ("reviewed-approved",)


def test_an_approval_label_cannot_rescue_a_stale_verdict():
    result = merge.evaluate(
        pr(comments=[_comment(f"REVIEW:PASS {OLD}")], labels=["reviewed-approved"])
    )
    assert refusal(result) == ("verdict_at_head", merge.STALE_VERDICT)


def test_a_changes_requested_label_does_not_block_a_clean_head_either():
    """Labels are inert in BOTH directions — the verdict at the head settles it."""
    result = merge.evaluate(pr(labels=["changes-requested"]))
    assert result.allowed
    assert result.ignored_signals == ("changes-requested",)


# --- forge plumbing ------------------------------------------------------------------------------


class FakeForge:
    name = "fake"

    def __init__(self, snapshot=None, error: Exception | None = None) -> None:
        self.calls: list[tuple] = []
        self.snapshot = snapshot
        self.error = error

    def available(self) -> bool:
        return True

    def get_pr(self, repo: Path, number: int, *, target_repo: str | None = None) -> dict:
        self.calls.append(("get_pr", number, target_repo))
        if self.error:
            raise self.error
        return self.snapshot or {}


class BlindForge:
    """A forge predating the optional extension — must refuse, not degrade to amber."""

    name = "blind"

    def available(self) -> bool:
        return True


def test_check_passes_the_target_repo_through():
    forge = FakeForge(pr())
    result = merge.check(forge, Path("."), 128, target_repo="example-org/gardenkit")
    assert result.allowed
    assert forge.calls == [("get_pr", 128, "example-org/gardenkit")]
    assert result.repo == "example-org/gardenkit"


@pytest.mark.parametrize(
    "forge",
    [
        BlindForge(),
        FakeForge(error=ForgeError("gh pr view failed: HTTP 404")),
        FakeForge({}),
    ],
)
def test_a_forge_that_cannot_answer_is_a_refusal_not_an_exception(forge):
    result = merge.check(forge, Path("."), 128)
    assert not result.allowed
    assert result.refusal.reason == merge.FORGE_UNAVAILABLE
    assert all(not p.ok for p in result.preconditions)


def test_code_repo_slug_prefers_the_code_repo_over_the_collab_one():
    manifest = {
        "repos": [
            {"id": "collab", "role": "collab", "remote": "git@github.com:ex/gardenkit-collab.git"},
            {"id": "code", "role": "code", "remote": "git@github.com:ex/gardenkit.git"},
        ]
    }
    assert merge.code_repo_slug(manifest) == "ex/gardenkit"
    assert merge.code_repo_slug({"repos": []}) is None


def test_normalize_checks_reads_conclusion_only_once_completed():
    from baron.forge.github import _normalize_checks

    assert _normalize_checks([
        {"name": "tests", "status": "COMPLETED", "conclusion": "SUCCESS"},
        {"name": "slow", "status": "IN_PROGRESS", "conclusion": ""},
        {"context": "legacy/status", "state": "FAILURE"},
        "junk",
    ]) == [
        {"name": "tests", "state": "SUCCESS"},
        {"name": "slow", "state": "IN_PROGRESS"},
        {"name": "legacy/status", "state": "FAILURE"},
    ]
    assert _normalize_checks(None) == []


# --- the CLI surface -------------------------------------------------------------------------------


def _invoke(monkeypatch, snapshot, *args):
    monkeypatch.setattr("baron.forge.get_forge", lambda name="github": FakeForge(snapshot))
    return runner.invoke(app, ["merge", "check", "128", *args])


def test_cli_exits_0_on_pass_and_1_on_refuse(monkeypatch, tmp_path):
    ok = _invoke(monkeypatch, pr(), "--collab", str(tmp_path), "--repo", "ex/gardenkit")
    assert ok.exit_code == 0, ok.output
    assert "VERDICT: PASS" in ok.output

    stale = _invoke(
        monkeypatch, pr(comments=[_comment(f"REVIEW:PASS {OLD}")]),
        "--collab", str(tmp_path), "--repo", "ex/gardenkit",
    )
    assert stale.exit_code == 1
    assert "VERDICT: REFUSE" in stale.output
    assert merge.STALE_VERDICT in stale.output


def test_cli_always_prints_the_identity_bound(monkeypatch, tmp_path):
    """With no signed verdict in the repo, the note must say the verdict is UNATTRIBUTED.

    Updated for ADR-033: the note used to claim attribution was impossible full stop.
    It now describes the state this PR is actually in, and points at the mechanism that
    changes it — a standing note that cannot become true is one readers stop reading.
    """
    res = _invoke(monkeypatch, pr(), "--collab", str(tmp_path), "--repo", "ex/gardenkit")
    assert "never merges" in res.output
    assert "UNATTRIBUTED" in res.output
    assert "ADR-033" in res.output


def test_cli_json_names_the_failing_precondition(monkeypatch, tmp_path):
    import json

    res = _invoke(
        monkeypatch, pr(checks=[{"name": "tests", "state": "FAILURE"}]),
        "--collab", str(tmp_path), "--repo", "ex/gardenkit", "--json",
    )
    assert res.exit_code == 1
    payload = json.loads(res.output)
    assert payload["allowed"] is False
    assert payload["refused_precondition"] == "ci_green"
    assert payload["reason"] == merge.CI_RED


def test_cli_refuses_when_gh_is_missing(monkeypatch, tmp_path):
    from baron.forge.base import ForgeUnavailable

    def boom(name="github"):
        raise ForgeUnavailable("GitHub CLI (`gh`) not found on PATH")

    monkeypatch.setattr("baron.forge.get_forge", boom)
    res = runner.invoke(app, ["merge", "check", "128", "--collab", str(tmp_path)])
    assert res.exit_code == 1
    assert merge.FORGE_UNAVAILABLE in res.output


def test_cli_resolves_the_code_repo_from_the_manifest(monkeypatch, tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        "project:\n  name: gardenkit\n"
        "repos:\n"
        "  - id: code\n    role: code\n    remote: git@github.com:ex/gardenkit.git\n"
        "  - id: collab\n    role: collab\n    remote: git@github.com:ex/gardenkit-collab.git\n",
        encoding="utf-8",
    )
    seen: list = []

    class Recording(FakeForge):
        def get_pr(self, repo, number, *, target_repo=None):
            seen.append(target_repo)
            return pr()

    monkeypatch.setattr("baron.forge.get_forge", lambda name="github": Recording(pr()))
    res = runner.invoke(app, ["merge", "check", "128", "--collab", str(tmp_path)])
    assert res.exit_code == 0, res.output
    assert seen == ["ex/gardenkit"]
