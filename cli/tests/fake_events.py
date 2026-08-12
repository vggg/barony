"""A recording stand-in for ``baron.events``, used as a CONTRACT DOUBLE.

Why this still exists, stated plainly. It was written (ADR-012 §4) while the
event plane was a SEPARATE, UNLANDED workstream, and it implemented the
signature ADR-012 guessed at::

    baron.events.emit(kind, attributes, *, trace_id=None)

The plane has since landed (ADR-013) with a different and better shape: an
:class:`baron.events.Event` value object and ``emit(event, cwd=None)``. ADR-012
§4 always said the row format belongs to ``baron.events``, so the plane's shape
wins and this double was rewritten to it — it now re-exports the REAL
:class:`~baron.events.Event` and implements the REAL ``emit`` signature, so it
can no longer drift from the contract without failing to import.

**What this proves and what it does not.** It proves the hook layer emits the
right kinds, the right attributes, one shared trace id per session, and that
emission failures never change an exit code. It deliberately keeps its own
tiny disk writer so these producer tests stay independent of which sink is
installed; the REAL sink stack is covered by ``test_sinks.py`` and by the
ADR-013 section of ``test_guard.py``, which runs against ``baron.sinks.disk``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# Re-exported so the double cannot drift from the plane, and so tests that
# import ``baron.events`` while the double is installed still see the real
# frozen constants.
from baron.events import (  # noqa: F401
    EVENTS_VERSION,
    FIXED_ATTR_KEYS,
    KNOWN_KINDS,
    ROW_KEYS,
    Event,
)

SINK_ENV = "BARON_EVENTS_SINK"
DEBUG_ENV = "BARON_EVENTS_DEBUG"
RELATIVE_PATH = Path(".baron") / "events.jsonl"

#: Every emit() call this process saw, in order — the in-memory assertion surface.
CALLS: list[dict] = []


def reset() -> None:
    CALLS.clear()


def sink_name() -> str:
    return (os.environ.get(SINK_ENV) or "null").strip() or "null"


def emit(event: Event, cwd: Path | None = None) -> None:
    """The REAL signature. Records, then optionally writes one flat JSONL row."""
    row = event.to_row()
    CALLS.append(
        {
            "kind": event.kind,
            "actor": event.actor,
            "subject": event.subject,
            "outcome": event.outcome,
            "attributes": dict(row["attributes"]),
            "trace_id": event.trace_id,
        }
    )
    sink = sink_name()
    if sink == "null":
        return
    if sink != "disk":
        # A realistic failure for the fail-open tests to swallow.
        raise ValueError(f"unknown event sink {sink!r}")
    root = Path(os.environ.get("BARON_EVENTS_DIR") or cwd or Path.cwd())
    path = root / RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def rows(root: Path) -> list[dict]:
    """Read back the JSONL this double wrote under ``root``."""
    path = root / RELATIVE_PATH
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
    ]
