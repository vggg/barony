"""Sink abstraction — pluggable destinations for baron's observation events.

Two ship built-in: ``null`` (the default — discards) and ``disk`` (append-only
JSONL under ``.baron/events/``). Other sinks arrive as plugins through the
``baron.sinks`` entry-point group, mirroring ``baron.forges`` exactly: a plugin
distribution registers

    [project.entry-points."baron.sinks"]
    logfire = "barony_logfire:LogfireSink"

and an operator selects it with ``BARON_EVENTS_SINK=logfire``.

This group exists so that wiring Logfire, Phoenix, or an internal collector
never requires an OpenTelemetry dependency in baron core (ADR-003 holds; see
ADR-013 §6). The disk sink's wire shape is already what the file-based
ingester in ``skills/multi-agent-audit`` parses, so the file route needs no
plugin at all.
"""

from __future__ import annotations

from importlib.metadata import entry_points

from .base import Sink, SinkError, SinkUnavailable
from .disk import DiskSink
from .null import NullSink

__all__ = [
    "DiskSink",
    "NullSink",
    "Sink",
    "SinkError",
    "SinkUnavailable",
    "get_sink",
]

_BUILTIN: dict[str, type] = {"null": NullSink, "disk": DiskSink}


def get_sink(name: str = "null") -> Sink:
    """Resolve a sink by name: built-ins first, then ``baron.sinks`` plugins."""
    if name in _BUILTIN:
        return _BUILTIN[name]()
    for ep in entry_points(group="baron.sinks"):
        if ep.name == name:
            sink_cls = ep.load()
            return sink_cls()
    raise SinkError(
        f"no sink named {name!r} — built-ins: {sorted(_BUILTIN)}; "
        "plugins register under the 'baron.sinks' entry-point group"
    )
