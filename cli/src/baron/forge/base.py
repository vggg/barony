"""The forge Protocol — the small, runtime-checkable contract every forge
implementation (built-in or ``baron.forges`` plugin) satisfies."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


class ForgeError(RuntimeError):
    """A forge operation failed."""


class ForgeUnavailable(ForgeError):
    """The forge's prerequisite tooling (e.g. ``gh``) is not installed."""


@runtime_checkable
class Forge(Protocol):
    """What baron needs from a code host. Intent-level, mirroring the capability
    vocabulary (``open_pr``, not ``gh_pr_create``)."""

    name: str

    def available(self) -> bool:
        """True if the forge's tooling is installed and usable."""
        ...

    def default_branch(self, repo: Path) -> str | None:
        """The repo's default branch as the forge knows it."""
        ...

    def open_pr(
        self,
        repo: Path,
        *,
        title: str,
        body: str,
        base: str | None = None,
        draft: bool = False,
        head: str | None = None,
        labels: list[str] | None = None,
    ) -> str:
        """Open a pull/merge request (from ``head`` if given, else the current
        branch), applying ``labels`` (created on the forge if absent); returns
        its URL."""
        ...

    def list_open_prs(self, repo: Path) -> list[dict[str, object]]:
        """Open pull/merge requests as plain dicts (number, title, headRefName,
        labels, author, createdAt, url)."""
        ...

    def create_branch(self, repo: Path, *, branch: str, base: str, message: str) -> None:
        """Create ``branch`` on the forge at ``base`` plus one empty commit
        (message ``message``) so a PR can be opened from it — without touching
        the local checkout. Used by ``baron lock`` (PR-as-lock, ADR-002 §3)."""
        ...

    def close_pr(
        self, repo: Path, number: int, *, delete_branch: bool = False
    ) -> None:
        """Close an open pull/merge request, optionally deleting its head branch."""
        ...


# --- OPTIONAL extensions (deliberately OUTSIDE the Protocol) ---------------------------
#
# `Forge` is @runtime_checkable, and those isinstance checks test method PRESENCE.
# So adding a method to the Protocol retroactively invalidates every implementation
# that predates it — the opposite of additive. Discovered the hard way: declaring
# `get_issue` on the Protocol broke the recorded fake forge in tests/test_lock.py,
# which is exactly what would happen to a third-party `baron.forges` plugin.
#
# Optional capabilities therefore live here as a documented duck-typed contract,
# detected with hasattr at the call site and degraded to `unverifiable` when absent
# (ADR-009 §4's three states). ADR-003 §5.1's "additive" promise only holds this way.
#
#   get_issue(repo: Path, number: int) -> dict
#       One issue, normalized: {number, state, labels (list of names), title, url}.
#       Consumed by `baron decision check` for github_issues backlogs.

def supports(forge: object, capability: str) -> bool:
    """True when ``forge`` implements an optional extension named above."""
    return callable(getattr(forge, capability, None))

