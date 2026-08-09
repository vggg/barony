"""ADR-012: the hook layer as an event PRODUCER.

Boundary being tested, said honestly: ``baron.events`` (the sink protocol,
``BARON_EVENTS_SINK``, the on-disk format) is a separate workstream that had
not landed when this was written. Guard reaches it through exactly ONE
late-bound call, so everything here runs against ``tests/fake_events.py``, a
contract double implementing the agreed signature. That proves the producer
side — kinds, attributes, trace correlation, fail-open.

POST-MERGE NOTE: the plane has landed (ADR-013). The double was rewritten to
the REAL ``emit(event, cwd=None)`` signature and re-exports the REAL
``Event``, so it can no longer drift from the contract silently, and the wire
shape asserted below is ADR-013's — ADR-012 §4 always delegated the row format
to ``baron.events``. ``test_real_event_plane_matches_the_producer_contract``
is now a live assertion rather than a skipped canary.
"""

from __future__ import annotations

import inspect
import json
import os
import stat
from pathlib import Path

import pytest

import baron
from baron import guard

import fake_events

PERSONA = """\
persona: Dara
slug: dara
archetype: dev
identity:
  git_name: Dara
  git_email: dara@example.invalid
  commit_prefix: "dara:"
  routing_label: agent-dara
capabilities:
  allow:
    - read_code
    - write_code
  deny:
    - push_main
    - force_push
scope:
  summary: dev persona
  focus: [implement tickets]
session_ritual: [sync_repos]
"""


@pytest.fixture
def persona_file(tmp_path: Path) -> Path:
    path = tmp_path / "persona.yaml"
    path.write_text(PERSONA, encoding="utf-8")
    return path


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> object:
    """Install the contract double as ``baron.events`` for the duration.

    Both sys.modules and the package attribute are set: guard's ``from . import
    events`` resolves through either depending on import order.
    """
    fake_events.reset()
    monkeypatch.setitem(__import__("sys").modules, "baron.events", fake_events)
    monkeypatch.setattr(baron, "events", fake_events, raising=False)
    monkeypatch.delenv("BARON_GUARD_OVERRIDE", raising=False)
    monkeypatch.delenv("BARON_EVENTS_DEBUG", raising=False)
    monkeypatch.setenv("BARON_EVENTS_SINK", "null")
    yield fake_events
    fake_events.reset()


def _payload(event: str, cwd: Path, **extra: object) -> str:
    return json.dumps(
        {
            "session_id": "sess-abc-123",
            "transcript_path": str(cwd / "t.jsonl"),
            "hook_event_name": event,
            "cwd": str(cwd),
            **extra,
        }
    )


# --- the session lifecycle ---------------------------------------------------------


def test_session_lifecycle_writes_one_correlated_trace(
    tmp_path: Path, persona_file: Path, events, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SessionStart -> PostToolUse x2 -> SessionEnd = four rows, one trace id."""
    monkeypatch.setenv("BARON_EVENTS_SINK", "disk")
    monkeypatch.setenv("BARON_EVENTS_DIR", str(tmp_path))

    feed = [
        _payload("SessionStart", tmp_path, source="startup", model="opus"),
        _payload(
            "PostToolUse",
            tmp_path,
            tool_name="Bash",
            tool_input={"command": "ls"},
            tool_response={"stdout": "a\n"},
            duration_ms=12,
        ),
        _payload(
            "PostToolUse",
            tmp_path,
            tool_name="Write",
            tool_input={"file_path": "x.md"},
            tool_response={"ok": True},
        ),
        _payload("SessionEnd", tmp_path, reason="clear"),
    ]
    for text in feed:
        code, stderr = guard.process(text, persona_file)
        assert (code, stderr) == (0, "")

    rows = fake_events.rows(tmp_path)
    assert len(rows) == 4, rows
    assert [r["span_name"] for r in rows] == [
        "session.start",
        "tool.post",
        "tool.post",
        "session.end",
    ]
    trace_ids = {r["trace_id"] for r in rows}
    assert len(trace_ids) == 1
    (trace_id,) = trace_ids
    assert trace_id == guard._trace_id("sess-abc-123")
    assert len(trace_id) == 32 and int(trace_id, 16) >= 0  # OTel-shaped

    # Attribute contract: version stamped, session carried, response PRESENCE
    # only (never the body — tool_response holds file contents and stdout).
    for row in rows:
        attrs = row["attributes"]
        assert attrs["baron.events_version"] == guard.EVENTS_VERSION
        assert attrs["baron.session_id"] == "sess-abc-123"
    assert rows[1]["attributes"]["baron.has_tool_response"] is True
    assert rows[1]["attributes"]["baron.tool_name"] == "Bash"
    assert rows[1]["attributes"]["baron.duration_ms"] == 12
    assert not any("stdout" in json.dumps(r["attributes"]) for r in rows)
    assert rows[0]["attributes"]["baron.session_source"] == "startup"
    assert rows[3]["attributes"]["baron.end_reason"] == "clear"


def test_stop_and_session_end_share_a_kind_but_keep_their_hook_name(
    tmp_path: Path, persona_file: Path, events
) -> None:
    for event in ("Stop", "SessionEnd"):
        assert guard.process(_payload(event, tmp_path), persona_file) == (0, "")
    kinds = [c["kind"] for c in fake_events.CALLS]
    assert kinds == ["session.end", "session.end"]
    assert [c["attributes"]["baron.hook_event"] for c in fake_events.CALLS] == [
        "Stop",
        "SessionEnd",
    ]


def test_post_tool_use_failure_records_the_error(
    tmp_path: Path, persona_file: Path, events
) -> None:
    code, _ = guard.process(
        _payload(
            "PostToolUseFailure",
            tmp_path,
            tool_name="Bash",
            error="exit status 1: boom",
            is_interrupt=False,
        ),
        persona_file,
    )
    assert code == 0
    (call,) = fake_events.CALLS
    assert call["kind"] == "tool.failure"
    assert call["attributes"]["baron.error"] == "exit status 1: boom"
    assert call["attributes"]["baron.is_interrupt"] is False


def test_unhandled_events_emit_nothing(tmp_path: Path, persona_file: Path, events) -> None:
    for event in ("PreCompact", "Notification", "TaskCompleted", "Invented"):
        assert guard.process(_payload(event, tmp_path), persona_file) == (0, "")
    assert fake_events.CALLS == []


# --- the enforcement path is also a producer ---------------------------------------


def test_pretooluse_allow_and_deny_both_emit(
    tmp_path: Path, persona_file: Path, events
) -> None:
    """A stream that only records denials cannot answer "how often did the
    boundary hold?" — the question the 0.53 fidelity measurement needed."""
    allow = json.dumps(
        {
            "session_id": "sess-abc-123",
            "hook_event_name": "PreToolUse",
            "cwd": str(tmp_path),
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
        }
    )
    deny = json.dumps(
        {
            "session_id": "sess-abc-123",
            "hook_event_name": "PreToolUse",
            "cwd": str(tmp_path),
            "tool_name": "Bash",
            "tool_input": {"command": "git push origin main"},
        }
    )
    assert guard.process(allow, persona_file) == (0, "")
    code, stderr = guard.process(deny, persona_file)
    assert code == 2 and "push_main" in stderr

    assert [c["kind"] for c in fake_events.CALLS] == ["guard.decision"] * 2
    assert [c["outcome"] for c in fake_events.CALLS] == ["allow", "deny"]
    denial = fake_events.CALLS[1]["attributes"]
    assert denial["baron.actor"] == "dara"
    assert denial["baron.capability.verb"] == "push_main"
    assert denial["tool.name"] == "Bash"
    assert denial["baron.subject"] == "git push origin main"
    # Correlation: the denial lands in the same trace as the session events.
    assert fake_events.CALLS[1]["trace_id"] == guard._trace_id("sess-abc-123")


def test_override_emits_its_own_kind(
    tmp_path: Path, persona_file: Path, events, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BARON_GUARD_OVERRIDE", "hotfix, owner approved")
    payload = json.dumps(
        {
            "session_id": "sess-abc-123",
            "hook_event_name": "PreToolUse",
            "cwd": str(tmp_path),
            "tool_name": "Bash",
            "tool_input": {"command": "git push origin main"},
        }
    )
    assert guard.process(payload, persona_file) == (0, "")
    assert [c["kind"] for c in fake_events.CALLS] == ["guard.override"]


def test_fail_closed_deny_still_emits(tmp_path: Path, events) -> None:
    code, _ = guard.process(
        json.dumps(
            {
                "session_id": "sess-abc-123",
                "hook_event_name": "PreToolUse",
                "cwd": str(tmp_path),
                "tool_name": "Bash",
                "tool_input": {"command": "git push origin main"},
            }
        ),
        None,  # no persona file -> fail-closed deny
    )
    assert code == 2
    (call,) = fake_events.CALLS
    assert call["kind"] == "guard.decision" and call["outcome"] == "error"
    assert "persona file" in call["attributes"]["baron.reason"]


def test_every_emitted_kind_is_in_the_documented_registry(
    tmp_path: Path, persona_file: Path, events, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EVENT_KINDS is a registry, not a runtime gate (kinds are open dotted
    strings) — but nothing may emit a kind the docs never mention."""
    monkeypatch.setenv("BARON_GUARD_OVERRIDE", "")  # falsy: not an override
    feed = [
        _payload("SessionStart", tmp_path),
        _payload("SessionEnd", tmp_path),
        _payload("Stop", tmp_path),
        _payload("PostToolUse", tmp_path, tool_name="Bash"),
        _payload("PostToolUseFailure", tmp_path, tool_name="Bash", error="x"),
        _payload(
            "PreToolUse", tmp_path, tool_name="Bash", tool_input={"command": "ls"}
        ),
        _payload(
            "PreToolUse",
            tmp_path,
            tool_name="Bash",
            tool_input={"command": "git push origin main"},
        ),
        _payload("PreToolUse", tmp_path, tool_name="WebFetch", tool_input={}),
    ]
    for text in feed:
        guard.process(text, persona_file)
    emitted = {c["kind"] for c in fake_events.CALLS}
    assert emitted <= set(guard.EVENT_KINDS), emitted - set(guard.EVENT_KINDS)
    assert "guard.decision" in emitted
    assert {c["outcome"] for c in fake_events.CALLS} >= {"allow", "deny"}
    # The registry guard publishes must not drift from the plane's own.
    import baron.events as real_events
    assert set(guard.EVENT_KINDS) == set(real_events.KNOWN_KINDS)


def test_baron_attribute_namespace_is_frozen(
    tmp_path: Path, persona_file: Path, events
) -> None:
    """Every attribute key guard writes is either under ``baron.`` or one of
    ADR-013's fixed wire slots.

    CORRECTED AT MERGE. This test used to assert that EVERY key is
    ``baron.``-prefixed, on the reasoning that the prefix is what the audit
    skill joins on. That was wrong in the other direction: ``ingest_otel.py``
    joins on the BARE keys ``agent.name`` / ``tool.name`` / ``session.id``
    (its ``AGENT_KEYS`` / ``TOOL_NAME_KEYS`` / ``SESSION_ATTR_KEYS``), and
    ADR-013 makes them fixed slots on every row. Prefixing them would break
    the join. What is frozen is the ``baron.`` namespace plus this closed set.
    """
    import baron.events as real_events

    guard.process(
        _payload("PostToolUse", tmp_path, tool_name="Bash", tool_response={}),
        persona_file,
    )
    (call,) = fake_events.CALLS
    allowed = set(real_events.FIXED_ATTR_KEYS) | {"events.version"}
    stray = [
        k for k in call["attributes"] if not k.startswith("baron.") and k not in allowed
    ]
    assert not stray, stray


# --- fail-OPEN: the asymmetry (ADR-012 §3) ------------------------------------------


def test_evidence_handlers_never_block_on_an_unknown_sink(
    tmp_path: Path, persona_file: Path, events, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BARON_EVENTS_SINK", "no-such-sink")
    for event in sorted(guard.EVIDENCE_HANDLERS):
        assert guard.process(_payload(event, tmp_path), persona_file) == (0, "")


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_evidence_handlers_never_block_on_a_readonly_baron_dir(
    tmp_path: Path, persona_file: Path, events, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BARON_EVENTS_SINK", "disk")
    monkeypatch.setenv("BARON_EVENTS_DIR", str(tmp_path))
    baron_dir = tmp_path / ".baron"
    baron_dir.mkdir()
    baron_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # r-x: cannot create events.jsonl
    try:
        for event in sorted(guard.EVIDENCE_HANDLERS):
            assert guard.process(_payload(event, tmp_path), persona_file) == (0, "")
    finally:
        baron_dir.chmod(stat.S_IRWXU)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_sink_failure_does_not_change_guard_exit_code(
    tmp_path: Path, persona_file: Path, events, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE asymmetry, locked: enforcement stays fail-CLOSED, evidence fails OPEN.
    A dead sink must not flip a deny to an allow, nor an allow to a deny."""
    deny = json.dumps(
        {
            "session_id": "s",
            "hook_event_name": "PreToolUse",
            "cwd": str(tmp_path),
            "tool_name": "Bash",
            "tool_input": {"command": "git push origin main"},
        }
    )
    allow = json.dumps(
        {
            "session_id": "s",
            "hook_event_name": "PreToolUse",
            "cwd": str(tmp_path),
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        }
    )
    healthy = (guard.process(deny, persona_file)[0], guard.process(allow, persona_file)[0])

    monkeypatch.setenv("BARON_EVENTS_SINK", "no-such-sink")
    broken = (guard.process(deny, persona_file)[0], guard.process(allow, persona_file)[0])
    assert healthy == broken == (2, 0)


def test_missing_event_plane_is_a_silent_no_op(
    tmp_path: Path, persona_file: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """A baron build WITHOUT baron.events installed must behave exactly as
    before this change — no ImportError at hook time, nothing on stderr."""
    import sys

    monkeypatch.delenv("BARON_EVENTS_DEBUG", raising=False)
    monkeypatch.setitem(sys.modules, "baron.events", None)  # forces ImportError
    monkeypatch.delattr(baron, "events", raising=False)
    assert guard.process(_payload("SessionStart", tmp_path), persona_file) == (0, "")
    assert capsys.readouterr().err == ""


def test_events_debug_makes_the_silence_diagnosable(
    tmp_path: Path, persona_file: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Silent-by-default is a choice, not an accident: guard's stderr is fed to
    the MODEL on exit 2, so unsolicited event noise degrades denial messages."""
    import sys

    monkeypatch.setenv("BARON_EVENTS_DEBUG", "1")
    monkeypatch.setitem(sys.modules, "baron.events", None)
    monkeypatch.delattr(baron, "events", raising=False)
    assert guard.process(_payload("SessionStart", tmp_path), persona_file) == (0, "")
    assert "no event plane" in capsys.readouterr().err


# --- the cross-workstream contract ---------------------------------------------------

#: The signature guard calls. Changing it here is a breaking change to a
#: contract another workstream owns — ADR-013 §2 (superseding the provisional
#: one ADR-012 §4 guessed at while the plane was unlanded).
PRODUCER_CONTRACT = "(event, cwd=None)"


def test_the_double_implements_the_documented_contract() -> None:
    """The double is only worth something if it is the shape guard promises."""
    sig = inspect.signature(fake_events.emit)
    assert list(sig.parameters) == ["event", "cwd"]
    sig.bind(fake_events.Event(kind="guard.decision"), None)


def test_real_event_plane_matches_the_producer_contract() -> None:
    """Merge canary, now LIVE. The plane has landed, so this no longer skips:
    it fails loudly if ``baron.events.emit`` stops accepting the call guard
    actually makes, or if the double drifts away from the real ``Event``."""
    events_mod = pytest.importorskip("baron.events")
    sig = inspect.signature(events_mod.emit)
    try:
        sig.bind(events_mod.Event(kind="guard.decision"), None)
    except TypeError as exc:  # pragma: no cover - contract break
        pytest.fail(
            f"baron.events.emit{sig} cannot accept guard's call "
            f"{PRODUCER_CONTRACT}: {exc}"
        )
    assert fake_events.Event is events_mod.Event, "the double drifted from the plane"
