"""The sink Protocol — the small, runtime-checkable contract every event sink
(built-in or ``baron.sinks`` plugin) satisfies."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # avoid an import cycle: events imports sinks lazily
    from ..events import Event


class SinkError(RuntimeError):
    """A sink operation failed.

    Callers do not catch this one by one: :func:`baron.events.emit` swallows
    every exception a sink can raise (ADR-013 §4, fail-open observation).
    """


class SinkUnavailable(SinkError):
    """The sink's prerequisite (a directory, a service, a credential) is absent."""


@runtime_checkable
class Sink(Protocol):
    """Where baron's observation events go.

    THREE MEMBERS, FINAL. Do not add a method to this Protocol later.
    ``@runtime_checkable`` makes ``isinstance`` test method PRESENCE, so a
    fourth member retroactively invalidates every third-party implementation
    that was correct the day it was written — the project already got burned by
    exactly this when ``Forge`` grew a method and an existing fake stopped
    satisfying ``isinstance`` (see ``forge/base.py`` and ``tests/test_lock.py``).
    Optional capabilities live OUTSIDE the Protocol as duck-typed extensions
    discovered with ``hasattr``: a batching sink may offer ``flush()``, and a
    repo-writing sink may offer ``bind(cwd)`` (which :func:`baron.events.emit`
    calls when present). Neither is required, and neither belongs here.
    """

    name: str

    def emit(self, event: "Event") -> None:
        """Record one event. Should not raise; if it does, the caller swallows it."""
        ...

    def close(self) -> None:
        """Release any held resource. Must be idempotent."""
        ...
