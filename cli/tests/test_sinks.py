"""ADR-013 — the Sink Protocol, its resolution order, and the disk reference sink."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from baron import clock, events
from baron.sinks import DiskSink, NullSink, Sink, SinkError, get_sink
from baron.sinks import base as sinks_base
from baron.sinks import disk as disk_mod

from conftest import commit_file, init_repo

PINNED = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def pinned_clock() -> object:
    clock.set_clock(lambda: PINNED)
    yield PINNED
    clock.reset_clock()


@pytest.fixture(autouse=True)
def _clear_repo_root_cache() -> None:
    disk_mod._repo_root.cache_clear()
    yield
    disk_mod._repo_root.cache_clear()


# --- the Protocol surface -------------------------------------------------------------


def test_sink_protocol_surface_is_exactly_three_members() -> None:
    """FINAL AT THREE. A fourth member retroactively breaks every third-party
    sink, because @runtime_checkable makes isinstance test method PRESENCE.
    If this test fails you are about to invalidate other people's plugins;
    add a duck-typed hasattr extension instead (ADR-013 §3)."""
    assert set(Sink.__protocol_attrs__) == {"name", "emit", "close"}


def test_protocol_warning_is_present_in_the_source() -> None:
    """The hard-won comment must survive refactors — forge/base.py earned it."""
    text = Path(sinks_base.__file__).read_text(encoding="utf-8")
    assert "THREE MEMBERS, FINAL" in text
    assert "isinstance" in text and "PRESENCE" in text


def test_bind_is_a_duck_typed_extension_not_a_protocol_member() -> None:
    assert "bind" not in set(Sink.__protocol_attrs__)
    assert hasattr(DiskSink(), "bind")
    assert not hasattr(NullSink(), "bind")


class MinimalSink:
    """The smallest legal third-party sink — proves three members are enough."""

    name = "minimal"

    def __init__(self) -> None:
        self.seen: list[object] = []

    def emit(self, event: object) -> None:
        self.seen.append(event)

    def close(self) -> None:
        return None


def test_a_three_member_third_party_sink_satisfies_the_protocol() -> None:
    assert isinstance(MinimalSink(), Sink)


# --- resolution -----------------------------------------------------------------------


def test_get_sink_returns_builtins() -> None:
    assert isinstance(get_sink("null"), NullSink)
    assert isinstance(get_sink("disk"), DiskSink)
    assert get_sink().name == "null"


def test_get_sink_unknown_name_lists_builtins() -> None:
    with pytest.raises(SinkError) as excinfo:
        get_sink("nope")
    message = str(excinfo.value)
    assert "nope" in message
    assert "'disk'" in message and "'null'" in message
    assert "baron.sinks" in message


def test_get_sink_consults_the_entry_point_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Contract test against a fake entry point. Real third-party discovery is
    only observable once a second distribution is installed; this asserts the
    lookup path, mirroring how test_lock.py fakes a forge."""

    class FakeEP:
        name = "fake"

        @staticmethod
        def load() -> type:
            return MinimalSink

    monkeypatch.setattr(
        "baron.sinks.entry_points",
        lambda group=None: [FakeEP()] if group == "baron.sinks" else [],
    )
    assert isinstance(get_sink("fake"), MinimalSink)


def test_builtins_win_over_a_plugin_of_the_same_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Hijack:
        name = "disk"

        @staticmethod
        def load() -> type:
            return MinimalSink

    monkeypatch.setattr("baron.sinks.entry_points", lambda group=None: [Hijack()])
    assert isinstance(get_sink("disk"), DiskSink)


def test_the_real_entry_point_group_resolves_both_builtins() -> None:
    """Not a fake: barony's own installed metadata declares the group, so this
    exercises the actual importlib.metadata discovery path a plugin will use."""
    from importlib.metadata import entry_points

    found = {ep.name: ep.load() for ep in entry_points(group="baron.sinks")}
    assert found == {"null": NullSink, "disk": DiskSink}


def test_pyproject_declares_both_builtins_under_baron_sinks() -> None:
    text = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert '[project.entry-points."baron.sinks"]' in text
    assert 'null = "baron.sinks.null:NullSink"' in text
    assert 'disk = "baron.sinks.disk:DiskSink"' in text


# --- the null sink --------------------------------------------------------------------


def test_null_sink_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    sink = NullSink()
    sink.emit(events.Event(kind="guard.decision"))
    sink.close()
    assert list(tmp_path.iterdir()) == []


# --- the disk sink --------------------------------------------------------------------


def test_disk_sink_writes_one_jsonl_line_per_event(
    tmp_path: Path, pinned_clock
) -> None:
    sink = DiskSink(tmp_path)
    sink.emit(events.Event(kind="guard.decision", actor="dara", outcome="allow"))
    sink.emit(events.Event(kind="guard.override", actor="dara", outcome="override"))
    sink.close()

    log = tmp_path / ".baron/events/2026-07-22.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rows = [json.loads(line) for line in lines]
    assert [r["span_name"] for r in rows] == ["guard.decision", "guard.override"]
    assert [r["attributes"]["baron.outcome"] for r in rows] == ["allow", "override"]


def test_disk_sink_writes_a_scoped_gitignore(tmp_path: Path, pinned_clock) -> None:
    DiskSink(tmp_path).emit(events.Event(kind="session.start"))
    marker = tmp_path / ".baron/events/.gitignore"
    assert marker.read_text(encoding="utf-8") == "*\n"


def test_the_gitignore_does_not_untrack_the_override_log(
    tmp_path: Path, pinned_clock
) -> None:
    """The scoped ignore lives INSIDE .baron/events/, so .baron/guard-override.log
    stays TRACKED — the governance property this must not silently remove."""
    repo = init_repo(tmp_path / "repo")
    commit_file(repo, ".baron/guard-override.log", "seed\n", "seed override log")

    DiskSink(repo).emit(events.Event(kind="guard.override", actor="dara"))

    import subprocess

    tracked = subprocess.run(
        ["git", "-C", str(repo), "ls-files", ".baron"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    assert ".baron/guard-override.log" in tracked
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "events" not in status, f"event stream leaked into git status: {status!r}"


def test_disk_sink_rotates_by_utc_date(tmp_path: Path) -> None:
    sink = DiskSink(tmp_path)
    for day in (21, 22):
        clock.set_clock(
            lambda d=day: datetime(2026, 7, d, 12, 0, tzinfo=timezone.utc)
        )
        sink.emit(events.Event(kind="tool.post"))
    clock.reset_clock()
    names = sorted(p.name for p in (tmp_path / ".baron/events").glob("*.jsonl"))
    assert names == ["2026-07-21.jsonl", "2026-07-22.jsonl"]


def test_disk_sink_resolves_the_repo_root_not_the_subdirectory(
    tmp_path: Path, pinned_clock
) -> None:
    repo = init_repo(tmp_path / "repo")
    commit_file(repo, "README.md", "hi\n", "init")
    nested = repo / "cli/src"
    nested.mkdir(parents=True)

    DiskSink(nested).emit(events.Event(kind="guard.decision"))
    assert (repo / ".baron/events/2026-07-22.jsonl").exists()
    assert not (nested / ".baron").exists()


def test_repo_root_is_resolved_once_per_process(tmp_path: Path, pinned_clock) -> None:
    """git rev-parse per event would be a latency regression on the hook path."""
    repo = init_repo(tmp_path / "repo")
    commit_file(repo, "README.md", "hi\n", "init")
    sink = DiskSink(repo)
    for _ in range(5):
        sink.emit(events.Event(kind="tool.post"))
    assert disk_mod._repo_root.cache_info().misses == 1
    assert disk_mod._repo_root.cache_info().hits == 4


def test_bind_repoints_the_sink(tmp_path: Path, pinned_clock) -> None:
    other = tmp_path / "other"
    other.mkdir()
    sink = DiskSink(tmp_path)
    sink.bind(other)
    sink.emit(events.Event(kind="guard.decision"))
    assert (other / ".baron/events/2026-07-22.jsonl").exists()
    assert not (tmp_path / ".baron").exists()


def test_disk_sink_raises_sink_error_when_the_path_is_unwritable(
    tmp_path: Path, pinned_clock
) -> None:
    """It raises — and events.emit() is what swallows it (ADR-013 §4)."""
    blocker = tmp_path / ".baron"
    blocker.write_text("not a directory\n", encoding="utf-8")
    with pytest.raises(SinkError):
        DiskSink(tmp_path).emit(events.Event(kind="guard.decision"))
