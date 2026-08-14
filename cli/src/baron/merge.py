"""``baron merge check`` — the merger's decision as a deterministic, fail-closed gate.

The `__MERGER__` archetype has always been specified as *a gate, not a button*: it
merges only when every precondition holds, and refuses naming the one that failed.
Until now that gate was **prose in a persona file** — the same shape as the denial
that FM4 showed a persona overriding ~15 times. ADR-028 mechanizes the checkable
half: baron evaluates the preconditions and returns a verdict the persona cannot
talk itself past, because the refusal is a return value and an exit code rather
than an instruction.

Four properties are load-bearing:

**SHA-bound, not PR-bound.** A review verdict judges a *commit*. The record is a PR
comment reading ``REVIEW:PASS <40-hex>`` / ``REVIEW:FAIL <40-hex>`` (ADR-002 §4,
ADR-008 §1). A verdict whose SHA is not the current head is stale, and stale is
refused — that is the strip-stale-verdict discipline, evaluated rather than trusted.

**A label is never an input.** Review-state labels are collected and reported as
*ignored*, never scored. A label can outlive the push that voided the verdict it
described; that near-miss (2026-07-30) is why this rule exists. Reporting them is
not scoring them — it tells a reader which misleading signal was present and
deliberately not used.

**Fail-closed.** Every unknown is a refusal. No verdict, an unparseable verdict, an
abbreviated SHA, a check run in an unrecognized state, no check runs at all, a forge
that cannot be reached — each returns REFUSE with its own reason slug. There is no
path where absence of evidence is read as evidence.

**baron checks; the persona decides (ADR-007).** This module evaluates. It never
merges, and there is deliberately no ``baron merge do``: under one shared forge
account baron cannot tell whose verdict it is reading, so autonomous merging waits
on agent identity (ADR-027). Owner-in-the-loop until then.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# --- the verdict contract -------------------------------------------------------------

#: The reviewer's published verdict (``__REVIEWER__/AGENT.md`` § The verdict). Anchored
#: to the start of a line so a verdict quoted mid-sentence in prose ("I'll post a
#: REVIEW:PASS once CI clears") is not mistaken for the record.
VERDICT_RE = re.compile(r"^[ \t]*REVIEW:(PASS|FAIL)[ \t]+(\S+)", re.M)

#: The template says: carry the FULL sha, never a branch name, never an abbreviation.
#: An abbreviated sha is not "close enough" — two different commits can share a prefix,
#: and accepting prefixes would make the equality test that the whole gate rests on
#: approximate. Abbreviated verdicts are parsed, marked malformed, and refused loudly.
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

#: Labels the gate recognizes as *review-state* claims. Listed only so the refusal can
#: name the misleading signal it ignored; membership here grants a label no power.
REVIEW_STATE_LABEL_HINTS = ("review", "approved", "changes-requested", "verdict", "lgtm")


# --- refusal reasons (stable slugs — the machine-readable half of a refusal) -----------

FORGE_UNAVAILABLE = "forge_unavailable"
PR_NOT_OPEN = "pr_not_open"
PR_DRAFT = "pr_draft"
HEAD_UNKNOWN = "head_unknown"
NO_VERDICT = "no_verdict"
STALE_VERDICT = "stale_verdict"
VERDICT_MALFORMED = "verdict_malformed"
VERDICT_AUTHOR = "verdict_author_unverified"
CHANGES_REQUESTED = "changes_requested"
PLATFORM_CHANGES_REQUESTED = "platform_changes_requested"
CI_RED = "ci_not_green"
CI_PENDING = "ci_pending"
CI_ABSENT = "ci_absent"
CI_UNKNOWN_STATE = "ci_unknown_state"
UNEVALUATED = "unevaluated"

#: Precondition names, in evaluation order. The first failing one is *the* refusal.
PRECONDITIONS = ("pr_open", "verdict_at_head", "no_changes_requested", "ci_green")

# --- check-run state buckets ----------------------------------------------------------

_CI_PASS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
_CI_FAIL = {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "ERROR", "STARTUP_FAILURE"}
_CI_PENDING = {"PENDING", "QUEUED", "IN_PROGRESS", "WAITING", "REQUESTED", "EXPECTED", ""}


@dataclass(frozen=True)
class Verdict:
    """One parsed ``REVIEW:`` comment."""

    state: str  # PASS | FAIL
    sha: str
    author: str
    created_at: str
    malformed: bool = False  # sha is not a full 40-hex — never counted as valid

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "sha": self.sha,
            "author": self.author,
            "created_at": self.created_at,
            "malformed": self.malformed,
        }


@dataclass(frozen=True)
class Precondition:
    name: str
    ok: bool
    reason: str = ""  # slug, empty when ok
    detail: str = ""  # one line a human can act on

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "ok": self.ok, "reason": self.reason, "detail": self.detail}


@dataclass(frozen=True)
class GateResult:
    """The gate's answer. ``allowed`` is true only when every precondition holds."""

    pr: int
    head: str
    preconditions: tuple[Precondition, ...]
    ignored_signals: tuple[str, ...] = ()
    verdicts: tuple[Verdict, ...] = ()
    repo: str = ""
    url: str = ""

    @property
    def allowed(self) -> bool:
        return bool(self.preconditions) and all(p.ok for p in self.preconditions)

    @property
    def refusal(self) -> Precondition | None:
        """The FIRST failing precondition — the one a refusal must name."""
        for p in self.preconditions:
            if not p.ok:
                return p
        return None

    def to_dict(self) -> dict[str, object]:
        ref = self.refusal
        return {
            "pr": self.pr,
            "repo": self.repo,
            "url": self.url,
            "head": self.head,
            "allowed": self.allowed,
            "verdict": "PASS" if self.allowed else "REFUSE",
            "refused_precondition": ref.name if ref else None,
            "reason": ref.reason if ref else None,
            "preconditions": [p.to_dict() for p in self.preconditions],
            "ignored_signals": list(self.ignored_signals),
            "verdicts_seen": [v.to_dict() for v in self.verdicts],
        }


# --- parsing ---------------------------------------------------------------------------


def parse_verdicts(comments: list[dict]) -> list[Verdict]:
    """Every ``REVIEW:`` verdict in ``comments``, oldest first.

    Malformed ones (abbreviated sha, branch name, ``HEAD``) are RETAINED and flagged,
    not dropped: a refusal that says "your verdict names `4f2a1b` — carry the full
    sha" is actionable, where "no verdict found" on a PR that visibly has one reads
    as a baron bug and invites the merger to override it by hand.
    """
    out: list[Verdict] = []
    for c in comments or []:
        body = str(c.get("body") or "")
        author = c.get("author")
        login = str(author.get("login") if isinstance(author, dict) else author or "")
        created = str(c.get("createdAt") or c.get("created_at") or "")
        for m in VERDICT_RE.finditer(body):
            raw = m.group(2)
            sha = raw.lower()
            out.append(
                Verdict(
                    state=m.group(1),
                    sha=sha,
                    author=login,
                    created_at=created,
                    malformed=not FULL_SHA_RE.match(sha),
                )
            )
    out.sort(key=lambda v: v.created_at)
    return out


def label_names(pr: dict) -> list[str]:
    """gh returns ``[{"name": ...}]``; fakes and other forges may use plain strings."""
    out: list[str] = []
    for label in pr.get("labels") or []:
        out.append(str(label.get("name", "")) if isinstance(label, dict) else str(label))
    return [x for x in out if x]


def _review_state_labels(pr: dict) -> list[str]:
    lowered = [(name, name.lower()) for name in label_names(pr)]
    return [name for name, low in lowered if any(h in low for h in REVIEW_STATE_LABEL_HINTS)]


def _bucket(state: str) -> str:
    up = (state or "").upper()
    if up in _CI_PASS:
        return "pass"
    if up in _CI_FAIL:
        return "fail"
    if up in _CI_PENDING:
        return "pending"
    return "unknown"


# --- the gate ---------------------------------------------------------------------------


def _unevaluated(names: tuple[str, ...], because: str) -> list[Precondition]:
    """Preconditions that could not be reached are recorded as FAILED, not skipped.

    A skipped precondition renders as an absence, and an absence is what a reader
    rounds down to "fine". Fail-closed means an unreachable check is a red one.
    """
    return [
        Precondition(n, False, UNEVALUATED, f"not evaluated — {because}; fail-closed")
        for n in names
    ]


def _check_pr_open(pr: dict, head: str) -> Precondition:
    state = str(pr.get("state") or "").upper()
    if state != "OPEN":
        return Precondition(
            "pr_open", False, PR_NOT_OPEN,
            f"PR state is {state or 'UNKNOWN'}, not OPEN",
        )
    if bool(pr.get("isDraft")):
        return Precondition("pr_open", False, PR_DRAFT, "PR is a draft — mark it ready first")
    if not FULL_SHA_RE.match(head):
        return Precondition(
            "pr_open", False, HEAD_UNKNOWN,
            f"head sha is {head or '(absent)'!r}, not a full 40-hex sha — the whole gate "
            f"rests on comparing it, so an unusable head is a refusal",
        )
    return Precondition("pr_open", True, detail="open, not a draft, head sha resolved")


def _check_verdict_at_head(
    verdicts: list[Verdict], head: str, *, verdict_author: str | None
) -> Precondition:
    at_head = [v for v in verdicts if v.sha == head]
    valid = [v for v in at_head if not v.malformed]

    if verdict_author and valid:
        wrong = [v for v in valid if v.author != verdict_author]
        valid = [v for v in valid if v.author == verdict_author]
        if not valid:
            return Precondition(
                "verdict_at_head", False, VERDICT_AUTHOR,
                f"the verdict(s) at {head[:12]} were posted by "
                f"{', '.join(sorted({v.author or '?' for v in wrong}))}, not the required "
                f"reviewer {verdict_author!r}",
            )
    if valid:
        return Precondition(
            "verdict_at_head", True,
            detail=f"{len(valid)} verdict(s) bound to the current head {head[:12]}",
        )
    if verdicts:
        newest = verdicts[-1]
        # A malformed sha never equals the head, so it would otherwise be reported as
        # "stale" — which sends the reviewer off to re-review code nobody objected to.
        # The newest verdict's OWN defect is the one worth naming.
        if newest.malformed:
            return Precondition(
                "verdict_at_head", False, VERDICT_MALFORMED,
                f"the newest verdict names {newest.sha!r} — carry the FULL 40-hex sha, never "
                f"an abbreviation, a branch name or HEAD; baron will not prefix-match, "
                f"because two commits can share a prefix",
            )
        return Precondition(
            "verdict_at_head", False, STALE_VERDICT,
            f"newest verdict is REVIEW:{newest.state} {newest.sha[:12]} but the head is now "
            f"{head[:12]} — the head moved since review, so the verdict is void; re-review "
            f"at the current head",
        )
    return Precondition(
        "verdict_at_head", False, NO_VERDICT,
        f"no REVIEW:PASS/REVIEW:FAIL comment on this PR at all — nothing has reviewed "
        f"{head[:12]}",
    )


def _check_no_changes_requested(pr: dict, verdicts: list[Verdict], head: str) -> Precondition:
    """A block at the current head is decisive, even when a PASS sits beside it.

    Same sha means the same code: a later PASS at an unchanged head does not answer the
    FAIL, it disagrees with it — and baron refuses rather than picking the answer the
    caller wants. Push the fix, get a verdict on the new head.
    """
    fails = [v for v in verdicts if v.sha == head and v.state == "FAIL" and not v.malformed]
    if fails:
        return Precondition(
            "no_changes_requested", False, CHANGES_REQUESTED,
            f"REVIEW:FAIL is open at the current head {head[:12]} (from "
            f"{fails[-1].author or 'unknown'}) — a later PASS on the SAME sha does not "
            f"clear it; address it and push",
        )
    # A platform review can BLOCK but can never AUTHORIZE (ADR-002 §4: the comment is the
    # verdict surface). The asymmetry is deliberate — ignoring a human's explicit
    # changes-requested because it came through the wrong surface is not fail-closed.
    if str(pr.get("reviewDecision") or "").upper() == "CHANGES_REQUESTED":
        return Precondition(
            "no_changes_requested", False, PLATFORM_CHANGES_REQUESTED,
            "the forge reports an open changes-requested review — it never counts as an "
            "approval, but it does count as a block",
        )
    return Precondition(
        "no_changes_requested", True, detail="no open REVIEW:FAIL and no platform block"
    )


def _check_ci_green(checks: list[dict], head: str) -> Precondition:
    if not checks:
        return Precondition(
            "ci_green", False, CI_ABSENT,
            f"no check runs reported on {head[:12]} — absence of CI is not green",
        )
    buckets = [(str(c.get("name") or "?"), _bucket(str(c.get("state") or ""))) for c in checks]
    failed = [n for n, b in buckets if b == "fail"]
    pending = [n for n, b in buckets if b == "pending"]
    unknown = [
        f"{n}={c.get('state')!r}"
        for (n, b), c in zip(buckets, checks)
        if b == "unknown"
    ]
    if failed:
        return Precondition(
            "ci_green", False, CI_RED,
            f"failing on {head[:12]}: {', '.join(sorted(failed))}",
        )
    if pending:
        return Precondition(
            "ci_green", False, CI_PENDING,
            f"still running on {head[:12]}: {', '.join(sorted(pending))} — pending is not green",
        )
    if unknown:
        return Precondition(
            "ci_green", False, CI_UNKNOWN_STATE,
            f"unrecognized check state on {head[:12]}: {', '.join(sorted(unknown))} — baron "
            f"refuses what it cannot interpret",
        )
    if not any(str(c.get("state") or "").upper() == "SUCCESS" for c in checks):
        return Precondition(
            "ci_green", False, CI_ABSENT,
            f"every check on {head[:12]} was skipped or neutral — nothing actually ran, so "
            f"there is no evidence to be green about",
        )
    return Precondition("ci_green", True, detail=f"{len(checks)} check(s) green on {head[:12]}")


def evaluate(pr: dict, *, verdict_author: str | None = None) -> GateResult:
    """Evaluate the merge gate against one PR snapshot. Pure — no I/O.

    ``pr`` is the normalized snapshot a forge returns (see
    ``GitHubForge.get_pr``): number, state, isDraft, headRefOid, comments, labels,
    reviewDecision, checks, url. Taking ONE snapshot rather than querying per
    precondition is what makes the head-sha comparison meaningful: verdict, labels
    and checks are all read against the same observed head.
    """
    number = int(pr.get("number") or 0)
    head = str(pr.get("headRefOid") or "").lower()
    verdicts = parse_verdicts(list(pr.get("comments") or []))
    ignored = tuple(_review_state_labels(pr))

    open_check = _check_pr_open(pr, head)
    if not open_check.ok:
        checks = [open_check, *_unevaluated(PRECONDITIONS[1:], f"pr_open failed ({open_check.reason})")]
    else:
        checks = [
            open_check,
            _check_verdict_at_head(verdicts, head, verdict_author=verdict_author),
            _check_no_changes_requested(pr, verdicts, head),
            _check_ci_green(list(pr.get("checks") or []), head),
        ]
    return GateResult(
        pr=number,
        head=head,
        preconditions=tuple(checks),
        ignored_signals=ignored,
        verdicts=tuple(verdicts),
        repo=str(pr.get("repo") or ""),
        url=str(pr.get("url") or ""),
    )


def refused(reason: str, detail: str, *, pr: int = 0, repo: str = "") -> GateResult:
    """A refusal that never reached the PR at all (no forge, no snapshot).

    Every precondition is marked failed rather than absent, so a caller that scores
    the list gets the same answer as one that reads ``allowed``.
    """
    first = Precondition(PRECONDITIONS[0], False, reason, detail)
    rest = _unevaluated(PRECONDITIONS[1:], f"the PR could not be read ({reason})")
    return GateResult(pr=pr, head="", preconditions=(first, *rest), repo=repo)


# --- forge plumbing ----------------------------------------------------------------------


def _slug_from_remote(remote: str) -> str | None:
    if not isinstance(remote, str) or "/" not in remote:
        return None
    slug = remote.rstrip("/").removesuffix(".git")
    parts = slug.replace(":", "/").split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else None


def code_repo_slug(manifest: dict) -> str | None:
    """``owner/name`` of the manifest's CODE repo.

    A merger runs from the collab repo, so letting ``gh`` resolve the repo from cwd
    answers about the collab repo's same-numbered PR — a wrong answer that looks
    authoritative (the failure mode ADR-009 hit with ``get_issue``).
    """
    for r in manifest.get("repos") or []:
        if not isinstance(r, dict):
            continue
        if r.get("role") == "code" or r.get("id") == "code":
            slug = _slug_from_remote(str(r.get("remote") or ""))
            if slug:
                return slug
    return None


def check(
    forge,
    repo_dir: Path,
    number: int,
    *,
    target_repo: str | None = None,
    verdict_author: str | None = None,
) -> GateResult:
    """Fetch one PR snapshot through ``forge`` and evaluate the gate against it.

    A forge that cannot answer — not installed, no ``get_pr`` extension, an API
    error — is a REFUSE, never an exception the caller might swallow into a merge.
    """
    from .forge.base import ForgeError, supports

    if not supports(forge, "get_pr"):
        return refused(
            FORGE_UNAVAILABLE,
            f"forge {getattr(forge, 'name', '?')!r} cannot read PRs (no get_pr) — the gate "
            f"has no evidence to evaluate",
            pr=number, repo=target_repo or "",
        )
    try:
        snapshot = forge.get_pr(repo_dir, number, target_repo=target_repo)
    except ForgeError as exc:
        return refused(
            FORGE_UNAVAILABLE, f"{exc.__class__.__name__}: {exc}",
            pr=number, repo=target_repo or "",
        )
    if not isinstance(snapshot, dict) or not snapshot:
        return refused(
            FORGE_UNAVAILABLE, f"the forge returned no PR #{number}",
            pr=number, repo=target_repo or "",
        )
    snapshot.setdefault("number", number)
    if target_repo:
        snapshot.setdefault("repo", target_repo)
    return evaluate(snapshot, verdict_author=verdict_author)


# --- rendering -----------------------------------------------------------------------------

#: Printed on every run, pass or refuse. baron evaluated preconditions; it did not merge,
#: and it cannot tell WHOSE verdict it read while every persona shares one forge account.
IDENTITY_NOTE = (
    "note: `baron merge check` verifies and reports — it never merges. Under one shared "
    "forge account baron cannot attest WHO posted a verdict, so merging stays "
    "owner-in-the-loop until agent identity (ADR-027) is deployed."
)


def render(result: GateResult) -> list[str]:
    where = f"{result.repo}#{result.pr}" if result.repo else f"PR #{result.pr}"
    lines = [f"=== merge gate — {where} @ {result.head[:12] or '(no head)'} ==="]
    for p in result.preconditions:
        mark = "PASS" if p.ok else "FAIL"
        lines.append(f"  {mark}  {p.name:22s} {p.detail}")
    if result.ignored_signals:
        lines.append(
            "  ----  labels IGNORED by design (index, not record): "
            + ", ".join(result.ignored_signals)
        )
    if result.allowed:
        lines.append("VERDICT: PASS — every merge precondition holds.")
    else:
        ref = result.refusal
        assert ref is not None
        lines.append(f"VERDICT: REFUSE — {ref.name} [{ref.reason}]: {ref.detail}")
    lines.append(IDENTITY_NOTE)
    return lines
