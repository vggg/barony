"""The disk sink — append-only JSONL under ``.baron/events/``, the reference
implementation of the Sink Protocol.

Layout::

    .baron/events/.gitignore        # "*\\n" — written once, scoped to this dir
    .baron/events/2026-07-22.jsonl  # one JSON object per line, append-only

Rotation is by UTC date, taken from the event's own ``ts`` (i.e. from
:mod:`baron.clock`, so ``BARON_NOW`` backfill lands in the right file). There is
no size cap and no pruning: a governance stream that silently deletes its own
evidence is worse than one that grows, and ``find .baron/events -mtime +N`` is
a better retention policy than anything baron could guess.

**Why gitignored, when ``.baron/guard-override.log`` is tracked.** They are
different kinds of artifact. An override is a small number of deliberate human
acts — evidence, and it belongs in the diff. Events are high-volume machine
observation — telemetry, and it belongs on the local disk. The ``.gitignore``
written here contains ``*`` and lives INSIDE ``.baron/events/``, deliberately
not at ``.baron/`` level, so it cannot un-track the override log in any
downstream repo (ADR-013 §6).

Encoding is stdlib :mod:`json` only — ADR-003's dependency policy (typer +
pyyaml) rules out orjson, and one short row per tool call does not need it.

HONEST BOUND — concurrent writers. Each event is one ``open(..., "a")`` plus one
``write()``. On POSIX, an ``O_APPEND`` write under ``PIPE_BUF`` (4 KiB) will not
interleave, which covers ordinary rows; a row carrying a very long command string
can exceed that and, with several agents writing the same repo at the same
instant, could in principle interleave. No file locking is taken. This is
telemetry, not the ledger — a torn row costs one unparseable line in an analysis,
and paying lock complexity on guard's hot path to prevent it is the wrong trade.
It has not been observed; it is stated because it has not been ruled out either.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from ..gitutil import git
from .base import SinkError

if TYPE_CHECKING:
    from ..events import Event

#: Repo-relative event directory. Machine-written state lives under ``.baron/``;
#: human-authored config stays at the repo root (``.baron-waivers.yaml``).
EVENTS_DIR = PurePosixPath(".baron/events")


@lru_cache(maxsize=32)
def _repo_root(cwd: str) -> Path:
    """The git top-level for ``cwd``, or ``cwd`` itself outside a repo.

    Cached: ``guard._repo_root`` shells out to ``git rev-parse`` on every call,
    and paying that per event on the PreToolUse hot path is a latency
    regression. Keyed by string so the cache is hashable and cheap.
    """
    path = Path(cwd)
    if path.is_dir():
        proc = git(path, "rev-parse", "--show-toplevel", check=False)
        top = proc.stdout.strip()
        if proc.returncode == 0 and top:
            return Path(top)
    return path


class DiskSink:
    """Appends one JSON line per event to ``<repo root>/.baron/events/<date>.jsonl``."""

    name = "disk"

    def __init__(self, cwd: Path | None = None) -> None:
        self._cwd = Path(cwd) if cwd is not None else Path.cwd()

    def bind(self, cwd: Path) -> None:
        """Duck-typed optional extension (NOT part of the Sink Protocol): point
        this sink at the repo the observed call happened in. ``baron guard``
        gets its cwd from the hook payload, which need not be the process cwd."""
        self._cwd = Path(cwd)

    def directory(self) -> Path:
        return _repo_root(str(self._cwd)) / Path(*EVENTS_DIR.parts)

    def path_for(self, event: "Event", directory: Path | None = None) -> Path:
        assert event.ts is not None  # Event.__post_init__ guarantees it
        base = self.directory() if directory is None else directory
        return base / f"{event.ts.date().isoformat()}.jsonl"

    def emit(self, event: "Event") -> None:
        directory = self.directory()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SinkError(f"cannot create {directory}: {exc}") from exc
        self._ensure_gitignore(directory)
        line = json.dumps(event.to_row(), default=str, sort_keys=False) + "\n"
        try:
            # Append mode: one open per event. Hook processes are short-lived and
            # a held handle would lose buffered rows when one is killed.
            with open(self.path_for(event, directory), "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as exc:
            raise SinkError(f"cannot append to the event log: {exc}") from exc

    @staticmethod
    def _ensure_gitignore(directory: Path) -> None:
        marker = directory / ".gitignore"
        if marker.exists():
            return
        try:
            marker.write_text("*\n", encoding="utf-8")
        except OSError as exc:
            raise SinkError(f"cannot write {marker}: {exc}") from exc

    def close(self) -> None:
        return None
