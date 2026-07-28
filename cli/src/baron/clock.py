"""Injectable clock — the single source of "now" for every baron command.

Every date baron writes (ledger entry dates, handoff created/closed dates, SLA
ages) comes from :func:`today` / :func:`now`. Tests inject a fixed clock via
:func:`set_clock`; production uses the system clock (UTC).

Backfill/testing seam — ``BARON_NOW``: set this env var to an ISO date
(``2026-07-01``) or datetime (``2026-07-01T09:30:00``) and the DEFAULT clock
reports that instant instead of the wall clock, for seeding dated demo history
or backfilling ledgers. It is a deliberate testing/backfill hatch, NOT for
normal operation; a malformed value raises rather than silently mis-dating. An
explicit :func:`set_clock` (the test harness) takes precedence over the env.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Callable

ClockFn = Callable[[], datetime]

NOW_ENV = "BARON_NOW"


def _parse_baron_now(raw: str) -> datetime:
    """Parse ``BARON_NOW`` (ISO date or datetime) to a tz-aware UTC datetime."""
    value = raw.strip()
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(value), datetime.min.time())
        except ValueError as exc:
            raise ValueError(
                f"{NOW_ENV}={raw!r} is not an ISO date (YYYY-MM-DD) or datetime "
                "(YYYY-MM-DDTHH:MM:SS)"
            ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _default_now() -> datetime:
    override = os.environ.get(NOW_ENV)
    if override:
        return _parse_baron_now(override)
    return datetime.now(timezone.utc)


#: Back-compat alias — the bare system clock, ignoring ``BARON_NOW``.
_system_now = _default_now


_now_fn: ClockFn = _default_now


def set_clock(fn: ClockFn) -> None:
    """Replace the clock (tests). Pass a zero-arg callable returning a datetime."""
    global _now_fn
    _now_fn = fn


def reset_clock() -> None:
    """Restore the default clock (system clock, honoring ``BARON_NOW``)."""
    global _now_fn
    _now_fn = _default_now


def now() -> datetime:
    return _now_fn()


def today() -> date:
    return now().date()
