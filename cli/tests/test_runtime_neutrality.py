"""ADR-019: the observation plane is runtime-neutral — PROVED, not asserted.

Before this file, neutrality was a layering claim: ``events.KNOWN_KINDS`` names
no runtime, and Claude Code's hook names sit behind a dispatch table in
``guard``. True, and not evidence. Exactly one runtime ever wrote a row, so
nothing distinguished "the plane is neutral" from "the plane happens to have
one producer and that producer is Claude Code".

What is tested here, in the order that matters:

1. **A real second producer.** The pydantic-ai adapter's in-process seam
   (``AbstractCapability.before_tool_execute``) writes ``guard.decision`` rows
   through the REAL plane and the REAL disk sink, driven by a REAL
   ``Agent.run_sync`` — ADR-001's standard for an adapter claim.
2. **One stream, two producers, one wire shape.** Both write into the same
   ``.baron/events/`` file, and for the SAME governance fact the two rows differ
   in exactly the attributes that are supposed to differ.
3. **The ADR-018 semantics travelled.** ``baron.enforcement`` on the second
   producer is read off ``Decision.adjudicated``; both measured defects behave.
4. **A third runtime needs one public function** and nothing Claude-shaped.

Everything runs offline: ``FunctionModel`` / direct seam invocation, no API keys.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from baron import events as events_mod
from baron import guard

from conftest import REPO_ROOT

try:  # the dev group installs the extra's pins (see cli/pyproject.toml)
    import pydantic_ai  # noqa: F401

    HAS_PYDANTIC_AI = True
except ImportError:  # pragma: no cover - dev envs carry the dependency
    HAS_PYDANTIC_AI = False

needs_extra = pytest.mark.skipif(
    not HAS_PYDANTIC_AI, reason="pydantic-ai extra not installed"
)

TESS = REPO_ROOT / "tests" / "examples" / "tess" / "persona.yaml"

#: The one governance fact both producers are driven with: a persona that
#: denies `push_main` attempting exactly that. Chosen because it is adjudicated
#: (a differently-capable persona is allowed), so `enforced` is the honest label
#: and any drift toward over- or under-claiming shows up as a diff.
PUSH_MAIN = "git push origin main"


# --- harness ---------------------------------------------------------------------------


@pytest.fixture
def plane(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The REAL event plane, REAL disk sink, writing under ``tmp_path``.

    Deliberately not the ``fake_events`` contract double: this file's whole job
    is to show a second producer reaching the plane everyone else reaches, so a
    stand-in would test the wrong thing.
    """
    monkeypatch.setenv("BARON_EVENTS_SINK", "disk")
    monkeypatch.delenv("BARON_EVENTS_DEBUG", raising=False)
    monkeypatch.delenv("BARON_GUARD_OVERRIDE", raising=False)
    return tmp_path


def rows(root: Path) -> list[dict]:
    """Every JSONL row written under ``root``, in file order."""
    out: list[dict] = []
    for path in sorted((root / ".baron" / "events").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                out.append(json.loads(line))
    return out


def hook(tool: str, tool_input: dict, cwd: Path, session_id: str = "sess-claude") -> str:
    return json.dumps(
        {
            "session_id": session_id,
            "hook_event_name": "PreToolUse",
            "cwd": str(cwd),
            "tool_name": tool,
            "tool_input": tool_input,
        }
    )


@dataclass
class FakeCall:
    """The one field the seam reads off pydantic-ai's ``ToolCallPart``."""

    tool_name: str


@dataclass
class FakeCtx:
    """The two ids the seam reads off pydantic-ai's ``RunContext``."""

    conversation_id: str | None = "conv-pyd"
    run_id: str | None = None


def drive(capability, tool_name: str, args: dict, ctx: FakeCtx | None = None):
    """Invoke the pydantic-ai seam directly and return its ModelRetry, if any.

    Direct invocation for the fine-grained semantic cases; the real-Agent path
    is covered by :func:`test_pydantic_ai_is_a_real_producer_on_the_real_plane`,
    which is the evidence that this seam is the one the runtime calls.
    """
    from pydantic_ai import ModelRetry

    try:
        asyncio.run(
            capability.before_tool_execute(
                ctx if ctx is not None else FakeCtx(),
                call=FakeCall(tool_name),
                tool_def=None,
                args=args,
            )
        )
    except ModelRetry as exc:
        return exc
    return None


def tess_capability(root: Path):
    from baron.runtimes.pydantic_ai import plan

    return plan(TESS, collab_root=root).guard_capability


# --- 1. a real second producer ---------------------------------------------------------


@needs_extra
def test_pydantic_ai_is_a_real_producer_on_the_real_plane(plane: Path) -> None:
    """A real ``Agent.run_sync`` scripts `git push origin main`; the row lands.

    ADR-001 accepts an adapter on evidence from a real runtime. So this drives
    pydantic-ai's own tool-call machinery — its model, its capability
    dispatch, its ``before_tool_execute`` invocation — and then reads the file
    the real ``DiskSink`` wrote. Nothing here is baron calling itself.
    """
    from pydantic_ai.messages import ModelResponse, RetryPromptPart, TextPart, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    from baron.runtimes.pydantic_ai import build_agent

    def scripted(messages, info) -> ModelResponse:
        if any(isinstance(p, RetryPromptPart) for p in messages[-1].parts):
            return ModelResponse(parts=[TextPart("refused")])
        return ModelResponse(
            parts=[ToolCallPart(tool_name="run_command", args={"command": PUSH_MAIN})]
        )

    agent = build_agent(TESS, collab_root=plane, model=FunctionModel(scripted))
    assert agent.run_sync("Ship it").output == "refused"

    written = rows(plane)
    assert len(written) == 1, written
    row = written[0]
    assert row["span_name"] == "guard.decision"
    attrs = row["attributes"]
    assert attrs["baron.runtime"] == "pydantic-ai"
    assert attrs["baron.trigger"] == "before_tool_execute"
    assert attrs["baron.outcome"] == "deny"
    assert attrs["baron.enforcement"] == "enforced"
    assert attrs["baron.capability.verb"] == "push_main"
    assert attrs["baron.actor"] == "tess"
    assert attrs["agent.name"] == "tess"
    assert attrs["tool.name"] == "run_command"
    assert attrs["baron.subject"] == PUSH_MAIN
    assert attrs["events.version"] == events_mod.EVENTS_VERSION
    # The sink's own invariant holds for a non-Claude producer too.
    assert (plane / ".baron/events/.gitignore").read_text(encoding="utf-8") == "*\n"


# --- 2. one stream, two producers, one wire shape --------------------------------------

#: The attributes that MAY differ between two producers observing the same
#: governance fact — and the only ones. `tool.name` differs because the
#: runtimes name their own tools (`Bash` vs `run_command`), which is the point
#: of a runtime-NATIVE value under a neutral key; `session.id` differs because
#: they are genuinely different sessions.
MAY_DIFFER = {"baron.runtime", "baron.trigger", "tool.name", "session.id"}


@needs_extra
def test_two_producers_one_stream_one_wire_shape(plane: Path) -> None:
    """Claude Code and pydantic-ai append to the SAME log, in the same shape.

    This is the neutrality claim stated as a diff: everything that carries a
    governance meaning — the verdict, the verb, the enforcement label, the
    actor, the subject — is byte-identical, and the differences are exactly the
    two attributes ADR-019 added to say WHO produced the row and WHERE.
    """
    assert guard.process(hook("Bash", {"command": PUSH_MAIN}, plane), TESS)[0] == 2
    assert drive(tess_capability(plane), "run_command", {"command": PUSH_MAIN})

    claude, pyd = rows(plane)
    assert [r["span_name"] for r in (claude, pyd)] == ["guard.decision"] * 2
    assert set(claude) == set(pyd) == set(events_mod.ROW_KEYS)

    a, b = claude["attributes"], pyd["attributes"]
    assert set(a) == set(b), "the two producers write different attribute keys"
    differing = {k for k in a if a[k] != b[k]}
    assert differing == MAY_DIFFER, differing

    assert a["baron.runtime"] == "claude-code" and b["baron.runtime"] == "pydantic-ai"
    assert a["baron.trigger"] == "PreToolUse"
    assert b["baron.trigger"] == "before_tool_execute"
    for key in ("baron.outcome", "baron.capability.verb", "baron.enforcement",
                "baron.actor", "agent.name", "baron.subject", "baron.reason"):
        assert a[key] == b[key], key
    assert a["baron.enforcement"] == "enforced"


@needs_extra
def test_the_second_producer_respects_the_frozen_attribute_namespace(plane: Path) -> None:
    """A new producer is a new chance to leak a key. ADR-013's namespace rule —
    ``baron.``-prefixed or one of the fixed wire slots — binds it too."""
    drive(tess_capability(plane), "run_command", {"command": PUSH_MAIN})
    (row,) = rows(plane)
    allowed = set(events_mod.FIXED_ATTR_KEYS) | {"events.version"}
    stray = [k for k in row["attributes"] if not k.startswith("baron.") and k not in allowed]
    assert not stray, stray


def test_baron_hook_event_is_gone_from_the_wire(plane: Path) -> None:
    """The rename is complete, not additive. ``baron.hook_event`` was Claude
    Code's vocabulary sitting on a neutral wire; carrying it on as an alias
    would keep the leak and add a second name for the same fact (ADR-019 §3)."""
    feed = [
        hook("Bash", {"command": PUSH_MAIN}, plane),
        json.dumps({"session_id": "s", "hook_event_name": "SessionStart", "cwd": str(plane)}),
        json.dumps(
            {"session_id": "s", "hook_event_name": "PostToolUse",
             "cwd": str(plane), "tool_name": "Bash", "tool_response": {}}
        ),
    ]
    for text in feed:
        guard.process(text, TESS)
    written = rows(plane)
    assert len(written) == 3, written
    assert not any("baron.hook_event" in r["attributes"] for r in written)
    assert all(r["attributes"]["baron.runtime"] == "claude-code" for r in written)
    # The evidence rows keep the runtime-native seam name under the neutral key.
    assert [r["attributes"]["baron.trigger"] for r in written] == [
        "PreToolUse",
        "SessionStart",
        "PostToolUse",
    ]


# --- 3. the ADR-018 semantics travelled to the second producer -------------------------


@needs_extra
def test_structural_refusal_is_unevaluated_on_the_second_producer(plane: Path) -> None:
    """ADR-013 §9.1's over-count defect, checked on the NEW producer.

    A `..` escape is refused identically for every persona, so nothing
    adjudicated it — `unevaluated`, with a NON-EMPTY verb tuple (ADR-018 §5).
    A second producer that re-derived the label from the rules artifact would
    print `enforced` here, which is the bug ADR-018 removed.
    """
    assert drive(tess_capability(plane), "write_file", {"path": "../../outside.md"})
    (row,) = rows(plane)
    attrs = row["attributes"]
    assert attrs["baron.outcome"] == "deny"
    assert attrs["baron.enforcement"] == "unevaluated"
    assert attrs["baron.capability.verb"] == "write_path"


@needs_extra
def test_adjudicated_allow_is_enforced_on_the_second_producer(plane: Path) -> None:
    """ADR-013 §9.1's under-count defect, checked on the NEW producer: a write
    allowed BECAUSE the persona holds `write_code` names no verb, and is still
    `enforced` — a persona without it is denied at the same path."""
    assert drive(tess_capability(plane), "write_file", {"path": "src/x.py"}) is None
    (row,) = rows(plane)
    attrs = row["attributes"]
    assert attrs["baron.outcome"] == "allow"
    assert attrs["baron.enforcement"] == "enforced"
    assert attrs["baron.capability.verb"] == ""


@needs_extra
def test_a_call_no_rule_matched_is_unevaluated(plane: Path) -> None:
    assert drive(tess_capability(plane), "run_command", {"command": "git status"}) is None
    (row,) = rows(plane)
    assert row["attributes"]["baron.outcome"] == "allow"
    assert row["attributes"]["baron.enforcement"] == "unevaluated"


@needs_extra
@pytest.mark.parametrize("tool", ["read_file", "list_directory", "search_files"])
def test_out_of_jurisdiction_tools_emit_nothing(plane: Path, tool: str) -> None:
    """Mirrors the hook exactly: `Read`/`Grep` produce no row under PreToolUse,
    so the read tools produce none here. A row per read would bury the verdicts
    the stream exists to record — and would also inflate any denominator
    computed over `guard.decision` rows."""
    assert drive(tess_capability(plane), tool, {"path": "README.md"}) is None
    assert guard.process(hook("Read", {"file_path": "README.md"}, plane), TESS) == (0, "")
    assert rows(plane) == []


# --- correlation and fail-open, on the second producer ---------------------------------


@needs_extra
def test_one_conversation_correlates_into_one_trace(plane: Path) -> None:
    """The same derivation the hook uses: a stable hash of the session id, so
    every row of one working session shares a trace without the producer
    holding state. pydantic-ai's `conversation_id` is the session analogue."""
    cap = tess_capability(plane)
    ctx = FakeCtx(conversation_id="conv-42")
    drive(cap, "run_command", {"command": "git status"}, ctx)
    drive(cap, "run_command", {"command": PUSH_MAIN}, ctx)
    written = rows(plane)
    assert len(written) == 2
    assert {r["trace_id"] for r in written} == {guard._trace_id("conv-42")}


@needs_extra
def test_no_ids_means_no_fabricated_correlation(plane: Path) -> None:
    """Better an unattributed row than two unrelated calls bucketed into one
    fake trace — the rule `guard._trace_id` already states for Claude."""
    cap = tess_capability(plane)
    empty = FakeCtx(conversation_id=None, run_id=None)
    drive(cap, "run_command", {"command": "git status"}, empty)
    drive(cap, "run_command", {"command": "git status"}, empty)
    written = rows(plane)
    assert len({r["trace_id"] for r in written}) == 2
    assert all(r["attributes"]["session.id"] == "" for r in written)


@needs_extra
def test_run_id_is_the_fallback_when_there_is_no_conversation(plane: Path) -> None:
    drive(
        tess_capability(plane),
        "run_command",
        {"command": "git status"},
        FakeCtx(conversation_id=None, run_id="run-7"),
    )
    (row,) = rows(plane)
    assert row["attributes"]["session.id"] == "run-7"


@needs_extra
def test_a_guard_error_is_observed_as_error_and_still_propagates(
    plane: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The adapter's ERROR POLICY is unchanged by ADR-019 — only observed.

    A `GuardError` still escapes ``before_tool_execute`` and aborts the run
    rather than becoming a ``ModelRetry``; converting it into a veto would be a
    behaviour change to enforcement, not an observability one. What is new is
    the row, and its label: no ``Decision`` was produced, so it cannot read
    ``enforced``. A guard that crashes on every call must not report perfect
    enforcement (ADR-018 §3) — on this producer as on the hook.

    Honest bound on the fixture: the error is INJECTED into the evaluator, so
    the rules artifact itself is still readable and the label is `unevaluated`.
    A genuinely unreadable artifact would additionally fail
    `_enforcement_class`'s own `_rules()` lookup and read `unknown` — the same
    two-way split the hook path has, asserted there in `test_guard.py`.
    """
    cap = tess_capability(plane)
    monkeypatch.setattr(
        guard, "evaluate_bash", lambda *a, **k: (_ for _ in ()).throw(
            guard.GuardError("capability-rules.v1.yaml is unreadable")
        )
    )
    with pytest.raises(guard.GuardError):
        drive(cap, "run_command", {"command": PUSH_MAIN})

    (row,) = rows(plane)
    attrs = row["attributes"]
    assert attrs["baron.runtime"] == "pydantic-ai"
    assert attrs["baron.outcome"] == "error"
    assert attrs["baron.enforcement"] == "unevaluated"
    assert "unreadable" in attrs["baron.error"]


@needs_extra
def test_a_broken_sink_cannot_stop_the_veto(
    plane: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE asymmetry (ADR-013 C4), re-checked on the second producer: guard is
    fail-CLOSED, evidence fail-OPEN. A dead sink must not turn a deny into an
    allow — in-process, that means the ModelRetry still gets raised."""
    cap = tess_capability(plane)
    healthy = drive(cap, "run_command", {"command": PUSH_MAIN})
    monkeypatch.setenv("BARON_EVENTS_SINK", "no-such-sink")
    broken = drive(cap, "run_command", {"command": PUSH_MAIN})
    assert healthy is not None and broken is not None
    assert "push_main" in str(broken)
    assert drive(cap, "run_command", {"command": "git status"}) is None


# --- 4. how a THIRD runtime registers --------------------------------------------------


def test_known_runtimes_is_the_landed_set_and_code_puppy_is_absent() -> None:
    """Pinned. This tuple grows with a landed adapter, never with an intention.

    `code-puppy` is absent DELIBERATELY and the gap is stated rather than
    papered over: it has no PreToolUse equivalent — no seam that can observe a
    tool call before it executes (docs/BACKLOG.md, ADR-019 §6). Adding it here
    on the strength of a post-hoc log would put a row on the plane claiming an
    adjudication that never happened, which is the exact over-claim this
    project exists to catch. It is a real, honest hole in the neutrality proof:
    two producers, not three, and the third one is blocked on the runtime.
    """
    assert guard.KNOWN_RUNTIMES == ("claude-code", "pydantic-ai")
    assert "code-puppy" not in guard.KNOWN_RUNTIMES


def test_a_third_runtime_needs_only_the_public_seam(plane: Path) -> None:
    """A runtime baron has never heard of, in a dozen lines and no new machinery.

    This is the ADR-019 §5 registration recipe executed literally: evaluate
    through the shared evaluator, hand the resulting Decision to
    `observe_decision` with your own runtime id and seam name. Nothing
    Claude-shaped is required — no hook payload, no `hook_event_name`, no
    subprocess, no stdin JSON.
    """
    persona = guard.load_persona(TESS)

    def acme_before_run(command: str) -> bool:  # the imaginary runtime's seam
        decision = guard.evaluate_bash(command, plane, persona)
        guard.observe_decision(
            decision,
            runtime="acme-runner",
            trigger="on_command",
            tool="sh",
            subject=command,
            outcome="allow" if decision.allowed else "deny",
            actor=persona.slug,
            session_id="acme-1",
            cwd=plane,
            reason=decision.reason,
        )
        return decision.allowed

    assert acme_before_run(PUSH_MAIN) is False
    (row,) = rows(plane)
    assert set(row) == set(events_mod.ROW_KEYS)
    attrs = row["attributes"]
    assert attrs["baron.runtime"] == "acme-runner"
    assert attrs["baron.trigger"] == "on_command"
    assert attrs["baron.enforcement"] == "enforced"
    assert attrs["baron.capability.verb"] == "push_main"
    assert row["trace_id"] == guard._trace_id("acme-1")


def test_the_seam_cannot_be_talked_into_claiming_enforcement(plane: Path) -> None:
    """The public API must not become a way around ADR-018.

    `observe_decision` takes no `enforcement` argument and derives nothing from
    its other parameters: a caller passing no Decision gets `unevaluated` even
    while asserting a deny outcome and naming a verb-bearing subject. The only
    way to get `enforced` on the wire is to hand over a Decision that earned it.
    """
    guard.observe_decision(
        None,
        runtime="acme-runner",
        trigger="on_command",
        tool="sh",
        subject=PUSH_MAIN,
        outcome="deny",
        actor="tess",
        session_id="acme-2",
        cwd=plane,
        reason="we totally enforced this, honest",
    )
    (row,) = rows(plane)
    assert row["attributes"]["baron.enforcement"] == "unevaluated"
    assert row["attributes"]["baron.capability.verb"] == ""


def test_a_producer_that_does_not_identify_itself_is_unknown_not_claude(
    plane: Path,
) -> None:
    """The default direction matters. `_Trace` defaults to `unknown`, so a
    producer that forgets is unattributed — never silently attributed to the
    runtime that happened to be first. Same rule as ADR-018's `adjudicated`
    default: the failure mode is under-claiming."""
    assert guard._Trace().runtime == guard.RUNTIME_UNKNOWN
    assert guard._Trace().trigger == ""
    guard.observe_decision(
        None, runtime="", trigger="", tool="sh", subject="x",
        outcome="allow", cwd=plane,
    )
    (row,) = rows(plane)
    assert row["attributes"]["baron.runtime"] == "unknown"


@needs_extra
def test_every_landed_producer_names_itself(plane: Path) -> None:
    """Sweep: across both producers and every kind either emits, no row is
    anonymous and no row names a runtime outside the pinned set."""
    feed = [
        hook("Bash", {"command": PUSH_MAIN}, plane),
        hook("Bash", {"command": "git status"}, plane),
        hook("Write", {"file_path": str(plane / "src" / "x.py")}, plane),
        json.dumps({"session_id": "s", "hook_event_name": "SessionStart", "cwd": str(plane)}),
        json.dumps({"session_id": "s", "hook_event_name": "SessionEnd", "cwd": str(plane)}),
        json.dumps(
            {"session_id": "s", "hook_event_name": "PostToolUse",
             "cwd": str(plane), "tool_name": "Bash", "tool_response": {}}
        ),
        json.dumps(
            {"session_id": "s", "hook_event_name": "PostToolUseFailure",
             "cwd": str(plane), "tool_name": "Bash", "error": "boom"}
        ),
    ]
    for text in feed:
        guard.process(text, TESS)
    cap = tess_capability(plane)
    drive(cap, "run_command", {"command": PUSH_MAIN})
    drive(cap, "write_file", {"path": "src/y.py"})

    written = rows(plane)
    assert len(written) == 9, [r["span_name"] for r in written]
    runtimes = {r["attributes"]["baron.runtime"] for r in written}
    assert runtimes == set(guard.KNOWN_RUNTIMES)
    assert guard.RUNTIME_UNKNOWN not in runtimes
    assert all(r["attributes"]["baron.trigger"] for r in written)
    assert all(
        r["attributes"]["baron.enforcement"] in guard.ENFORCEMENT_VALUES
        for r in written
        if "baron.enforcement" in r["attributes"]
    )
