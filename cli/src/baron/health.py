"""``baron health`` (ADR-024) — fleet health from the substrate, read-only.

Two halves, per ADR-024:
- **reviewer-quality** — mutation-kill, claim-drift (+understating), reviewer **escape
  rate**, per-author — rolled up from ``review.verdict`` events on the plane.
- **stalls/divergence** — reused from ``baron status`` (this command sits BESIDE status
  and calls into it; it does not subsume it).

Honest bound (ADR-024 §5): this measures **what was emitted**, not what happened. A fleet
that records no verdicts shows a clean board — so the report states its coverage
(verdicts seen) rather than implying health from silence.

That bound is about *emission*. It was never a licence to miss rows that WERE emitted:
the plane hangs off the git top-level, so in a coordination monorepo (ADR-025) it lives
at the root and is shared by every project in the clone. The report therefore names the
plane it read and says when that plane is repo-wide, so "0 verdicts" always means
"nothing was emitted" and never "I looked in the wrong directory" (ADR-025 §6.8).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import status, verdict
from .sinks.disk import events_dir as plane_dir


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
    #: The event directory this report's verdicts were read from — the same
    #: resolution the sink writes through. Named in the output so a zero is
    #: attributable to an empty plane rather than to a mis-resolved path.
    plane: str = ""
    #: True when that plane sits above the collab dir (a monorepo subdir): the
    #: rows are the WHOLE repo's, not this project's alone.
    plane_shared: bool = False
    #: False when a caller deliberately took the verdict half elsewhere (the
    #: portfolio rollup reads the shared plane once). Distinguishes "measured
    #: zero" from "not measured here" in the rendered output.
    verdicts_measured: bool = True

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
            "plane": {
                "dir": self.plane,
                "shared": self.plane_shared,
                "measured": self.verdicts_measured,
            },
        }


def collect(
    collab: Path,
    *,
    since: str | None = None,
    include_verdicts: bool = True,
    include_stalls: bool = True,
) -> HealthReport:
    """Roll the plane + `baron status` up into one report.

    ``include_verdicts=False`` skips the verdict half for callers that read the
    plane themselves — the portfolio rollup does, because one monorepo plane
    read once per project would report N× the verdicts that exist.
    ``include_stalls=False`` skips the `baron status` half for callers pointing
    at a directory that is not itself a project (the monorepo root).
    """
    rows = verdict.read(collab, since=since) if include_verdicts else []
    plane = plane_dir(collab)

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
    findings: list[status.StatusFinding] = []
    if include_stalls:
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
        plane=plane.as_posix(),
        plane_shared=plane.parent.parent.resolve() != collab.resolve(),
        verdicts_measured=include_verdicts,
    )


def render(rep: HealthReport) -> str:
    win = f"since {rep.since}" if rep.since else "all time"
    lines = [f"=== fleet health ({win}) — {rep.verdicts} verdict(s) recorded ==="]
    if not rep.verdicts_measured:
        lines.append("  (verdicts not measured here — the observation plane is shared by every")
        lines.append("   project in this repo and is rolled up ONCE at the portfolio level.)")
    elif rep.verdicts == 0:
        lines.append("  (no review.verdict events on the plane — nothing to measure.")
        lines.append("   enable it with BARON_EVENTS_SINK=disk and `baron verdict record`.)")
        if rep.plane:
            lines.append(f"   plane read: {rep.plane}")
    else:
        if rep.plane_shared:
            lines.append(
                "  NOTE: the plane is repo-wide — these rows are every project's in this"
            )
            lines.append(f"        clone, not this project's alone ({rep.plane}).")
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
