"""A stand-in for the ``baron.events`` plane, used as a CONTRACT DOUBLE.

Why this exists, stated plainly (ADR-012 §4): the event plane
(``baron.events``, ``BARON_EVENTS_SINK``, the sink protocol, the on-disk row
format) is a SEPARATE workstream that had not landed when the hook producer
was written. Guard therefore reaches the plane through exactly one late-bound
call and this module implements the agreed signature so the producer side can
be tested end-to-end today:

    baron.events.emit(kind: str,
                      attributes: dict[str, object],
                      *, trace_id: str | None = None) -> None

**What this proves and what it does not.** It proves guard emits the right
kinds, the right ``baron.*`` attributes, and one shared trace id per session,
and that emission failures never change an exit code. It does NOT prove
interoperability with the real plane — that is asserted separately by
``test_events_contract.py::test_real_event_plane_matches_the_producer_contract``,
which skips until ``baron.events`` actually exists and fails loudly the moment
it exists with a different signature.

The disk behaviour here mirrors what the producer needs from the real sink:
``BARON_EVENTS_SINK=disk`` writes one flat JSONL row per event to
``.baron/events.jsonl``, in the shape ``ingest_otel.record_from_flat`` already
parses (``span_name`` / ``trace_id`` / ``start_timestamp`` / ``attributes``).
Any other value (including the default) is a no-op, mirroring the real plane's
null default. An unknown sink name raises — that is how the fail-open test
gets a realistic failure to swallow.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

SINK_ENV = "BARON_EVENTS_SINK"
RELATIVE_PATH = Path(".baron") / "events.jsonl"

#: Every emit() call this process saw, in order — the in-memory assertion surface.
CALLS: list[dict] = []


def reset() -> None:
    CALLS.clear()


def emit(kind: str, attributes: dict, *, trace_id: str | None = None) -> None:
    CALLS.append({"kind": kind, "attributes": dict(attributes), "trace_id": trace_id})
    sink = os.environ.get(SINK_ENV) or "null"
    if sink == "null":
        return
    if sink != "disk":
        raise ValueError(f"unknown event sink {sink!r}")
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "span_name": kind,
        "kind": "event",
        "event.name": kind,
        "trace_id": trace_id,
        "span_id": uuid.uuid4().hex[:16],
        "start_timestamp": now,
        "end_timestamp": now,
        "attributes": attributes,
    }
    path = Path(os.environ.get("BARON_EVENTS_DIR") or Path.cwd()) / RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def rows(root: Path) -> list[dict]:
    """Read back the JSONL the disk sink wrote under ``root``."""
    path = root / RELATIVE_PATH
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
    ]
