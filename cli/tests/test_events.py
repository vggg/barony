"""ADR-013 — the observation plane's wire shape and its fail-open contract.

These tests pin the interface every other workstream codes against. If a
change here needs the assertions edited, that is a wire-shape break and needs
``EVENTS_VERSION`` bumped plus an ADR amendment — not a test edit.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from baron import clock, events
from baron.sinks import DiskSink, NullSink, Sink, SinkError, get_sink

PINNED = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def pinned_clock() -> object:
    clock.set_clock(lambda: PINNED)
    yield PINNED
    clock.reset_clock()


@pytest.fixture(autouse=True)
def _no_ambient_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    """A developer with BARON_EVENTS_SINK exported must not change results."""
    monkeypatch.delenv(events.SINK_ENV, raising=False)
    monkeypatch.delenv(events.DEBUG_ENV, raising=False)


# --- the wire shape -------------------------------------------------------------------


def test_to_row_wire_shape(pinned_clock) -> None:
    """The exact row ADR-013 §2 documents, byte for byte.

    ``ts`` comes from the INJECTED clock, proving nothing on this path calls
    ``datetime.now()`` — clock.py is the mandated single source of now, and it
    is what carries the BARON_NOW backfill hatch.
    """
    event = events.Event(
        kind="guard.decision",
        actor="dara",
        subject="git push origin main",
        outcome="deny",
        attributes={
            "tool.name": "Bash",
            "baron.capability.verb": "push_main",
            "baron.enforcement": "enforced",
            "baron.reason": "push to the default branch",
        },
        trace_id="0" * 32,
        span_id="1" * 16,
    )
    row = event.to_row()

    assert list(row) == [
        "span_name",
        "trace_id",
        "span_id",
        "start_timestamp",
        "end_timestamp",
        "attributes",
    ]
    assert list(row) == list(events.ROW_KEYS)
    assert row == {
        "span_name": "guard.decision",
        "trace_id": "00000000000000000000000000000000",
        "span_id": "1111111111111111",
        "start_timestamp": "2026-07-22T12:00:00+00:00",
        "end_timestamp": "2026-07-22T12:00:00+00:00",
        "attributes": {
            "events.version": 1,
            "baron.actor": "dara",
            "baron.subject": "git push origin main",
            "baron.outcome": "deny",
            "agent.name": "dara",
            "tool.name": "Bash",
            "session.id": "",
            "baron.capability.verb": "push_main",
            "baron.enforcement": "enforced",
            "baron.reason": "push to the default branch",
        },
    }
    # The ADR carries this JSON verbatim; keep them identical.
    assert json.loads(json.dumps(row)) == row


def test_adr_013_documents_the_same_row(pinned_clock) -> None:
    """The ADR's worked example is the test's row, not prose that drifted."""
    adr = (
        Path(__file__).resolve().parents[2]
        / "docs/adr/ADR-013-observation-plane-events-and-sinks.md"
    )
    text = adr.read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)```", text, flags=re.S)
    assert blocks, "ADR-013 must carry a verbatim JSON example of one row"
    documented = json.loads(blocks[0])

    event = events.Event(
        kind="guard.decision",
        actor="dara",
        subject="git push origin main",
        outcome="deny",
        attributes={
            "tool.name": "Bash",
            "baron.capability.verb": "push_main",
            "baron.enforcement": "enforced",
            "baron.reason": "push to the default branch",
        },
        trace_id="0" * 32,
        span_id="1" * 16,
    )
    assert documented == event.to_row()


def test_ts_defaults_to_the_injected_clock(pinned_clock) -> None:
    event = events.Event(kind="session.start", actor="iris")
    assert event.ts == PINNED
    assert event.to_row()["start_timestamp"] == "2026-07-22T12:00:00+00:00"


def test_baron_now_backfill_hatch_reaches_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BARON_NOW is honoured because ts comes from clock.now(), not the wall clock."""
    clock.reset_clock()
    monkeypatch.setenv(clock.NOW_ENV, "2026-01-02T03:04:05")
    row = events.Event(kind="session.end", actor="iris").to_row()
    assert row["start_timestamp"] == "2026-01-02T03:04:05+00:00"


def test_ids_are_generated_at_the_right_widths() -> None:
    event = events.Event(kind="tool.post")
    assert re.fullmatch(r"[0-9a-f]{32}", str(event.trace_id))
    assert re.fullmatch(r"[0-9a-f]{16}", str(event.span_id))


def test_fixed_slots_cannot_be_shadowed_by_caller_attributes(pinned_clock) -> None:
    row = events.Event(
        kind="guard.decision",
        actor="dara",
        outcome="deny",
        attributes={"baron.outcome": "allow", "events.version": 99},
    ).to_row()
    attrs = row["attributes"]
    assert attrs["baron.outcome"] == "deny"
    assert attrs["events.version"] == 1


def test_extra_attributes_are_sorted_for_stable_rows(pinned_clock) -> None:
    row = events.Event(
        kind="guard.decision", attributes={"baron.z": 1, "baron.a": 2}
    ).to_row()
    keys = list(row["attributes"])
    assert keys[: len(events.FIXED_ATTR_KEYS) + 1] == [
        "events.version",
        *events.FIXED_ATTR_KEYS,
    ]
    assert keys[len(events.FIXED_ATTR_KEYS) + 1 :] == ["baron.a", "baron.z"]


def test_empty_actor_becomes_unknown() -> None:
    assert events.Event(kind="tool.post", actor="").actor == "unknown"


def test_kind_is_open_no_warning_no_error(capsys: pytest.CaptureFixture) -> None:
    """An unrecognised kind is legal and silent: observation, not enforcement."""
    row = events.Event(kind="thirdparty.whatever").to_row()
    assert row["span_name"] == "thirdparty.whatever"
    assert capsys.readouterr().err == ""


def test_known_kinds_registry_matches_the_module_docstring() -> None:
    """The docstring table is the registry; drift between it and KNOWN_KINDS is a bug."""
    doc = events.__doc__ or ""
    for kind in events.KNOWN_KINDS:
        assert f"``{kind}``" in doc, f"{kind} missing from the module registry table"


# --- ingester compatibility (the reason for this exact shape) -------------------------


def test_row_keys_are_the_ingesters_first_choice_keys() -> None:
    """The five top-level keys are each the FIRST entry of ingest_otel.py's flat
    key lists, which is why the audit skill reads this stream with zero new code
    and baron needs no OpenTelemetry dependency (ADR-003 / ADR-013 §6)."""
    script = (
        Path(__file__).resolve().parents[2]
        / "skills/multi-agent-audit/scripts/ingest_otel.py"
    )
    text = script.read_text(encoding="utf-8")

    def first_of(list_name: str) -> str:
        match = re.search(rf"{list_name}\s*=\s*\[\s*\"([^\"]+)\"", text)
        assert match, f"{list_name} not found in ingest_otel.py"
        return match.group(1)

    assert first_of("FLAT_NAME_KEYS") == "span_name"
    assert first_of("FLAT_TRACE_KEYS") == "trace_id"
    assert first_of("FLAT_SPANID_KEYS") == "span_id"
    assert first_of("FLAT_START_KEYS") == "start_timestamp"
    assert first_of("FLAT_END_KEYS") == "end_timestamp"
    for attr_key in ("agent.name", "tool.name", "session.id"):
        assert f'"{attr_key}"' in text, f"{attr_key} not in the ingester's key lists"


# --- emit(): the fail-open contract ---------------------------------------------------


def test_null_sink_is_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With BARON_EVENTS_SINK unset, nothing is written anywhere."""
    monkeypatch.chdir(tmp_path)
    assert events.sink_name() == "null"
    events.emit(events.Event(kind="guard.decision", actor="dara"), tmp_path)
    assert list(tmp_path.rglob("*.jsonl")) == []
    assert not (tmp_path / ".baron").exists()


def test_emit_swallows_sink_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A sink that raises must not propagate — observation is fail-OPEN."""

    class Exploding:
        name = "boom"

        def emit(self, event: object) -> None:
            raise RuntimeError("sink is on fire")

        def close(self) -> None:
            return None

    monkeypatch.setenv(events.SINK_ENV, "boom")
    monkeypatch.setattr("baron.sinks.get_sink", lambda name="null": Exploding())
    assert events.emit(events.Event(kind="guard.decision")) is None


def test_emit_swallows_an_unresolvable_sink_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(events.SINK_ENV, "does-not-exist")
    assert events.emit(events.Event(kind="guard.decision")) is None


def test_debug_env_surfaces_the_swallowed_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv(events.SINK_ENV, "does-not-exist")
    monkeypatch.setenv(events.DEBUG_ENV, "1")
    events.emit(events.Event(kind="guard.decision"))
    err = capsys.readouterr().err
    assert "sink error swallowed" in err
    assert "does-not-exist" in err


def test_emit_writes_through_to_the_disk_sink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_clock
) -> None:
    monkeypatch.setenv(events.SINK_ENV, "disk")
    events.emit(events.Event(kind="guard.override", actor="dara"), tmp_path)
    log = tmp_path / ".baron/events/2026-07-22.jsonl"
    assert json.loads(log.read_text(encoding="utf-8"))["span_name"] == "guard.override"


def test_builtin_sinks_satisfy_the_protocol() -> None:
    assert isinstance(NullSink(), Sink)
    assert isinstance(DiskSink(), Sink)
    assert isinstance(get_sink("null"), NullSink)
    assert isinstance(get_sink("disk"), DiskSink)


def test_sink_error_is_exported() -> None:
    assert issubclass(SinkError, RuntimeError)
