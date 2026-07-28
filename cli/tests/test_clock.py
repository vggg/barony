"""Clock seam tests — the BARON_NOW backfill/testing override (B2)."""

from __future__ import annotations

from datetime import date

import pytest

from baron import clock


@pytest.fixture(autouse=True)
def _default_clock() -> object:
    """Ensure the DEFAULT (env-honoring) clock is active, and restore after."""
    clock.reset_clock()
    yield
    clock.reset_clock()


def test_baron_now_date_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(clock.NOW_ENV, "2026-03-15")
    assert clock.today() == date(2026, 3, 15)
    # date-only anchors at midnight UTC
    assert clock.now().hour == 0
    assert clock.now().tzinfo is not None


def test_baron_now_datetime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(clock.NOW_ENV, "2026-03-15T09:30:00")
    now = clock.now()
    assert (now.year, now.month, now.day, now.hour, now.minute) == (2026, 3, 15, 9, 30)
    assert now.tzinfo is not None  # naive input gets UTC attached


def test_baron_now_malformed_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(clock.NOW_ENV, "not-a-date")
    with pytest.raises(ValueError, match="BARON_NOW"):
        clock.now()


def test_no_env_uses_system_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(clock.NOW_ENV, raising=False)
    # a real, recent year — not a fixed backfill value
    assert clock.today().year >= 2024


def test_set_clock_takes_precedence_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(clock.NOW_ENV, "2026-03-15")
    from datetime import datetime, timezone

    pinned = datetime(2020, 1, 1, tzinfo=timezone.utc)
    clock.set_clock(lambda: pinned)
    try:
        assert clock.today() == date(2020, 1, 1)  # explicit clock wins
    finally:
        clock.reset_clock()
