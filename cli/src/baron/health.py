"""``baron health`` (ADR-024) — fleet health from the substrate, read-only.

Two halves, per ADR-024:
- **reviewer-quality** — mutation-kill, claim-drift (+understating), reviewer **escape
  rate**, per-author — rolled up from ``review.verdict`` events on the plane.
- **stalls/divergence** — reused from ``baron status`` (this command sits BESIDE status
  and calls into it; it does not subsume it).

Honest bound (ADR-024 §5): this measures **what was emitted**, not what happened. A fleet
that records no verdicts shows a clean board — so the report states its coverage
(verdicts seen) rather than implying health from silence.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import status, verdict


@dataclass
class HealthReport:
    verdicts: int
    mutations_run: int
    mutations_killed: int
    drift_instances: int
    drift_understating: int
    prs: int
    escapes: list[dict[str, object]]
    by_author: dict[str, dict[str, int]]
    stalls: list[str]        # human-readable stall/divergence lines from `baron status`
    since: str | None = None

    @property
    def kill_rate(self) -> float | None:
        return (self.mutations_killed / self.mutations_run) if self.mutations_run else None

    def to_dict(self) -> dict[str, object]:
        return {
            "since": self.since,
            "verdicts": self.verdicts,
            "mutation_kill": {
                "killed": self.mutations_killed, "run": self.mutations_run,
                "rate": self.kill_rate,
            },
            "claim_drift": {
                "instances": self.drift_instances, "understating": self.drift_understating,
                "prs": self.prs,
                "per_pr": (self.drift_instances / self.prs) if self.prs else 0.0,
            },
            "reviewer_escapes": len(self.escapes),
            "escapes": self.escapes,
            "by_author": self.by_author,
            "stalls": self.stalls,
        }


def collect(collab: Path, *, since: str | None = None) -> HealthReport:
    rows = verdict.read(collab, since=since)

    def s(key: str) -> int:
        return sum(int(r.get(key, 0) or 0) for r in rows)

    by_author: dict[str, dict[str, int]] = defaultdict(
        lambda: {"verdicts": 0, "drift": 0, "mut_killed": 0, "mut_run": 0}
    )
    for r in rows:
        a = str(r.get("author") or "unknown")
        by_author[a]["verdicts"] += 1
        by_author[a]["drift"] += int(r.get("drift_instances", 0) or 0)
        by_author[a]["mut_killed"] += int(r.get("mutations_killed", 0) or 0)
        by_author[a]["mut_run"] += int(r.get("mutations_run", 0) or 0)

    # Stalls/divergence come from `baron status` (no network: fetch=False).
    # Degrade gracefully: health must still report verdict metrics even where
    # status can't run (no manifest.yaml / not a collab repo).
    stalls: list[str] = []
    try:
        findings = status.collect(collab, fetch=False)
    except (FileNotFoundError, ValueError) as exc:
        stalls.append(f"(stalls unchecked — baron status unavailable: {exc})")
        findings = []
    for f in findings:
        if f.severity == status.RED and f.check in (
            "handoff-overdue", "unmerged-branch", "ahead", "behind",
        ):
            stalls.append(f"[{f.check}] {f.subject} — {f.detail}")

    return HealthReport(
        verdicts=len(rows),
        mutations_run=s("mutations_run"),
        mutations_killed=s("mutations_killed"),
        drift_instances=s("drift_instances"),
        drift_understating=s("drift_understating"),
        prs=len({r.get("pr") for r in rows if r.get("pr") is not None}),
        escapes=[r for r in rows if r.get("escape")],
        by_author=dict(by_author),
        stalls=stalls,
        since=since,
    )


def render(rep: HealthReport) -> str:
    win = f"since {rep.since}" if rep.since else "all time"
    lines = [f"=== fleet health ({win}) — {rep.verdicts} verdict(s) recorded ==="]
    if rep.verdicts == 0:
        lines.append("  (no review.verdict events on the plane — nothing to measure.")
        lines.append("   enable it with BARON_EVENTS_SINK=disk and `baron verdict record`.)")
    else:
        rate = f"{100 * rep.kill_rate:.0f}%" if rep.kill_rate is not None else "n/a"
        lines.append(
            f"MUTATION KILL RATE   {rep.mutations_killed}/{rep.mutations_run} ({rate})"
            "   <- test-suite defense (survivors = undefended code)"
        )
        per_pr = f"{rep.drift_instances / rep.prs:.1f}/PR" if rep.prs else "n/a"
        lines.append(
            f"CLAIM DRIFT          {rep.drift_instances} over {rep.prs} PR(s) ({per_pr}); "
            f"{rep.drift_understating} UNDERSTATING (overclaim-only checks miss these)"
        )
        lines.append(
            f"REVIEWER ESCAPES     {len(rep.escapes)}"
            "   <- defects caught now that a PRIOR review of an earlier head passed"
        )
        for e in rep.escapes:
            lines.append(f"                       #{e.get('pr')} {e.get('note', '')}")
        lines.append("by author:")
        for a, d in sorted(rep.by_author.items()):
            lines.append(
                f"  {a:12} {d['verdicts']} verdicts, {d['drift']} drift, "
                f"mut {d['mut_killed']}/{d['mut_run']}"
            )
    lines.append("")
    if rep.stalls:
        lines.append(f"STALLS / DIVERGENCE ({len(rep.stalls)}) — from `baron status`:")
        lines += [f"  {s}" for s in rep.stalls]
    else:
        lines.append("STALLS / DIVERGENCE  none (baron status is green on those checks)")
    return "\n".join(lines)
