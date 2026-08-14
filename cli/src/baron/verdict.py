"""``review.verdict`` — reviewer/merger verdicts on the observation plane (ADR-024).

Fleet-health's reviewer-quality metrics (mutation-kill, claim-drift, reviewer
**escape rate**) are judgements a reviewer makes per verdict. Rather than a bespoke
JSONL (the badminton pilot's ``logs/metrics.jsonl``), they ride the ADR-013 event
plane: one more ``kind``, git-native, **default sink ``null``** so adopters opt in.

``record`` emits; ``read`` rolls the plane's ``.baron/events/*.jsonl`` back into
verdict dicts for ``baron health``. Metrics live under the additive ``baron.review.*``
attribute namespace. Emission is fail-open (ADR-013): a verdict that isn't recorded
is simply absent — ``baron health`` measures what was emitted and says so.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import events
from .sinks.disk import events_dir as plane_dir

_INT_FIELDS = ("mutations_run", "mutations_killed", "drift_instances", "drift_understating")


def record(
    collab: Path,
    *,
    author: str,
    pr: int,
    head: str,
    verdict: str,
    mutations_run: int = 0,
    mutations_killed: int = 0,
    drift_instances: int = 0,
    drift_understating: int = 0,
    escape: bool = False,
    altitude: int | None = None,
    note: str = "",
) -> None:
    """Emit one ``review.verdict`` event onto the plane (honours BARON_EVENTS_SINK)."""
    attrs: dict[str, object] = {
        "baron.review.pr": pr,
        "baron.review.head": head,
        "baron.review.author": author,
        "baron.review.mutations_run": mutations_run,
        "baron.review.mutations_killed": mutations_killed,
        "baron.review.drift_instances": drift_instances,
        "baron.review.drift_understating": drift_understating,
        "baron.review.escape": bool(escape),
        "baron.review.note": note,
    }
    if altitude is not None:
        attrs["baron.review.altitude"] = altitude
    ev = events.Event(
        kind="review.verdict",
        actor=author,
        subject=f"PR #{pr}@{head}",
        outcome=verdict,
        attributes=attrs,
    )
    events.emit(ev, cwd=collab)


def read(collab: Path, *, since: str | None = None) -> list[dict[str, object]]:
    """Every ``review.verdict`` row on the plane, newest-agnostic, as flat dicts.

    ``since`` is an ISO-date/prefix; rows whose ``start_timestamp`` sorts before it
    are dropped (same UTC-ISO prefix match the pilot's metrics-report used).
    Returns [] when the disk sink was never enabled — nothing to measure, not an error.

    The read resolves the plane through :func:`baron.sinks.disk.events_dir` — the
    SAME resolution the write took. Joining ``.baron/events`` onto ``collab``
    instead is correct only when the collab dir IS the git top-level; in a
    coordination monorepo it reads an empty subdir while the verdicts sit at the
    root (ADR-025 §6.8).
    """
    events_dir = plane_dir(collab)
    if not events_dir.is_dir():
        return []
    out: list[dict[str, object]] = []
    for f in sorted(events_dir.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("span_name") != "review.verdict":
                continue
            if since and str(row.get("start_timestamp", "")) < since:
                continue
            a = row.get("attributes", {})
            rec: dict[str, object] = {
                "ts": row.get("start_timestamp", ""),
                "verdict": a.get("baron.outcome", ""),
                "pr": a.get("baron.review.pr"),
                "head": a.get("baron.review.head", ""),
                "author": a.get("baron.review.author", a.get("baron.actor", "")),
                "escape": bool(a.get("baron.review.escape", False)),
                "altitude": a.get("baron.review.altitude"),
                "note": a.get("baron.review.note", ""),
            }
            for k in _INT_FIELDS:
                try:
                    rec[k] = int(a.get(f"baron.review.{k}", 0) or 0)
                except (TypeError, ValueError):
                    rec[k] = 0
            out.append(rec)
    return out
