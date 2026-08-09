"""The null sink — the default. Baron observes nothing unless asked to.

This is not a placeholder: it is the shipped default so that installing barony
never starts writing files an operator did not ask for. Opt in with
``BARON_EVENTS_SINK=disk``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import Event


class NullSink:
    """Discards every event."""

    name = "null"

    def emit(self, event: "Event") -> None:
        return None

    def close(self) -> None:
        return None
