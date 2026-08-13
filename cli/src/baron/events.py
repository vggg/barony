"""The observation plane — one event shape, emitted to a pluggable sink (ADR-013).

**This module observes. It never decides.** Nothing here can allow, deny, or
alter the outcome of any baron command. Guard enforcement (ADR-004 §2.3) is
fail-CLOSED: an internal error becomes a deny. Evidence emission is the
deliberate mirror image — fail-OPEN and silent: :func:`emit` swallows every
exception a sink can raise, because a broken or full log destination must never
brick a session. Set ``BARON_EVENTS_DEBUG=1`` to print swallowed sink errors to
stderr while debugging a sink.

Wire shape. One JSON object per line, chosen so that the existing file-based
ingester in ``skills/multi-agent-audit/scripts/ingest_otel.py`` reads it with
**zero new code and no OpenTelemetry dependency** (ADR-003's typer+pyyaml
policy holds). The five top-level keys are each the FIRST entry of that
script's ``FLAT_NAME_KEYS`` / ``FLAT_TRACE_KEYS`` / ``FLAT_SPANID_KEYS`` /
``FLAT_START_KEYS`` / ``FLAT_END_KEYS``, and ``agent.name`` / ``tool.name`` /
``session.id`` are already in its ``AGENT_KEYS`` / ``TOOL_NAME_KEYS`` /
``SESSION_ATTR_KEYS``::

    {"span_name": "guard.decision",
     "trace_id": "<32 hex>", "span_id": "<16 hex>",
     "start_timestamp": "2026-07-22T12:00:00+00:00",
     "end_timestamp": "2026-07-22T12:00:00+00:00",
     "attributes": {"events.version": 1, "baron.actor": "dara",
                    "baron.subject": "git push origin main",
                    "baron.outcome": "deny", "agent.name": "dara",
                    "tool.name": "Bash", "session.id": "", ...}}

``kind`` is an OPEN dotted string, not a closed enum. The capability
vocabulary is frozen because it is an enforcement contract where ambiguity
means mis-enforcement; this stream is observation, where an unrecognised kind
costs an analyst one ``grep``. There is deliberately **no runtime warning** for
an unknown kind — it would fire on every third-party event and train people to
ignore guard output. What *is* frozen instead is the ``baron.`` ATTRIBUTE-key
namespace, because that is what the ingester actually parses.

Kind registry (v1) — additions land here in the same change as their emitter:

===================  ===========================================  ==================================
kind                 emitted when                                 typical ``baron.outcome``
===================  ===========================================  ==================================
``guard.decision``   guard evaluated a tool call (ADR-004)        ``allow`` / ``deny`` / ``error``
``guard.override``   ``BARON_GUARD_OVERRIDE`` allowed a call      ``override``
``session.start``    a session brief was rendered (ADR-007)       ``ok``
``session.end``      an end report was rendered (ADR-007)         ``ok``
``tool.post``        a PostToolUse hook observed a completed call ``ok`` / ``error``
``tool.failure``     a tool call reported failure                 ``error``
``review.verdict``   a reviewer/merger verdict + metrics (ADR-024) the verdict (``approved`` / ``changes`` / …)
===================  ===========================================  ==================================

Reserved ``baron.*`` attribute keys (frozen for v1; new keys are additive):

- ``baron.actor`` / ``baron.subject`` / ``baron.outcome`` — always present.
- ``baron.runtime`` — WHICH runtime's producer emitted the row
  (``"claude-code"``, ``"pydantic-ai"``; ``"unknown"`` when a producer did not
  say). This plane is runtime-NEUTRAL, not Claude-Code's: read this attribute
  before comparing anything across rows (ADR-019 §2).
- ``baron.trigger`` — WHICH seam in that runtime fired (``"PreToolUse"``,
  ``"before_tool_execute"``, …). The key is neutral; the VALUE is deliberately
  the runtime's own name for the seam and is only meaningful read together
  with ``baron.runtime``. Replaces ADR-012's ``baron.hook_event`` (ADR-019 §3).
- ``baron.capability.verb`` — comma-joined capability verbs a call mapped to.
- ``baron.enforcement`` — ``"enforced"`` | ``"unevaluated"`` | ``"unknown"``, a
  PER-CALL OBSERVATION: did a capability adjudicate THIS call? ``enforced``
  requires that a rule matched AND the outcome turned on the acting persona.
  Read off ``guard.Decision.adjudicated``; never derived from the rules
  artifact, which describes the *verb* and not this evaluation (ADR-018 §2,
  which supersedes ADR-013 §4.1). ``instructed`` is deliberately NOT a value
  here — it is a static posture property of a (persona, verb, runtime) triple
  and lives on ``baron rules list`` only.
- ``baron.reason`` — human-readable explanation carried by the source decision.

**CONSUMER CAVEAT — read before aggregating.** ``baron.capability.verb`` CAN be
non-empty on a row whose ``baron.enforcement`` is ``unevaluated``: a write that
escapes the repo root carries ``write_path`` but is a structural refusal that no
capability adjudicated. Any verb-level aggregation ("how often was ``write_path``
enforced?") must filter on ``baron.enforcement == "enforced"`` FIRST and count
verbs second. The inverse also holds — an EMPTY verb tuple does not mean "not
enforced" (a write allowed by ``write_code`` names no verb). ``baron.enforcement``
is the field to read; the verb tuple is detail, not a proxy. ADR-018 §5.

Sink selection is the ``BARON_EVENTS_SINK`` environment variable, default
``"null"``. Baron emits nothing unless an operator opts in. The variable is the
only live selector in v1; the manifest ``events:`` block is declared in the
schema so manifests can carry the intent without validation noise, but no
command reads it yet (ADR-013 §7 — reading YAML on guard's per-tool-call hot
path is a latency regression that needs its own measurement).
"""

from __future__ import annotations

import os
import secrets
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Mapping

from . import clock

#: Bumped when the wire shape changes incompatibly. Emitted as ``events.version``.
EVENTS_VERSION = 1

#: Environment variable naming the sink (see :func:`baron.sinks.get_sink`).
SINK_ENV = "BARON_EVENTS_SINK"
#: Set to ``1`` to print swallowed sink errors to stderr.
DEBUG_ENV = "BARON_EVENTS_DEBUG"
#: Emit nothing unless an operator opts in.
DEFAULT_SINK = "null"

#: The kinds baron itself emits. Informational — NOT validated, NOT closed.
KNOWN_KINDS: tuple[str, ...] = (
    "guard.decision",
    "guard.override",
    "session.start",
    "session.end",
    "tool.post",
    "tool.failure",
    "review.verdict",   # ADR-024: a reviewer/merger verdict + its fleet-health metrics
)

#: Attribute slots every row carries, in wire order, after ``events.version``.
FIXED_ATTR_KEYS: tuple[str, ...] = (
    "baron.actor",
    "baron.subject",
    "baron.outcome",
    "agent.name",
    "tool.name",
    "session.id",
)

#: Top-level row keys, in wire order.
ROW_KEYS: tuple[str, ...] = (
    "span_name",
    "trace_id",
    "span_id",
    "start_timestamp",
    "end_timestamp",
    "attributes",
)


@dataclass(frozen=True)
class Event:
    """One observation. Immutable; ``ts`` comes from :mod:`baron.clock`.

    ``ts`` MUST NOT be filled from ``datetime.now()`` anywhere: ``clock.now()``
    is the mandated single source of "now" and carries the ``BARON_NOW``
    backfill hatch that makes seeded demo history and tests deterministic.
    """

    kind: str
    actor: str = "unknown"
    subject: str = ""
    outcome: str = "ok"
    attributes: Mapping[str, object] = field(default_factory=dict)
    ts: datetime | None = None
    trace_id: str | None = None
    span_id: str | None = None

    def __post_init__(self) -> None:
        if self.ts is None:
            object.__setattr__(self, "ts", clock.now())
        if not self.trace_id:
            object.__setattr__(self, "trace_id", secrets.token_hex(16))  # 32 hex
        if not self.span_id:
            object.__setattr__(self, "span_id", secrets.token_hex(8))  # 16 hex
        if not self.actor:
            object.__setattr__(self, "actor", "unknown")

    def to_row(self) -> dict[str, object]:
        """The wire shape: one flat, ingester-compatible JSON object."""
        extra = {str(k): v for k, v in dict(self.attributes).items()}
        tool_name = str(extra.pop("tool.name", "") or "")
        session_id = str(extra.pop("session.id", "") or "")
        agent_name = str(extra.pop("agent.name", "") or "") or self.actor
        for slot in ("events.version", "baron.actor", "baron.subject", "baron.outcome"):
            extra.pop(slot, None)  # the fixed slots win; callers cannot shadow them

        assert self.ts is not None  # set in __post_init__
        stamp = self.ts.isoformat()
        attributes: dict[str, object] = {
            "events.version": EVENTS_VERSION,
            "baron.actor": self.actor,
            "baron.subject": self.subject,
            "baron.outcome": self.outcome,
            "agent.name": agent_name,
            "tool.name": tool_name,
            "session.id": session_id,
        }
        for key in sorted(extra):  # sorted: byte-stable rows for diffs and tests
            attributes[key] = extra[key]
        return {
            "span_name": self.kind,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "start_timestamp": stamp,
            "end_timestamp": stamp,
            "attributes": attributes,
        }


def sink_name() -> str:
    """The configured sink name (``BARON_EVENTS_SINK``, default ``null``)."""
    return (os.environ.get(SINK_ENV) or DEFAULT_SINK).strip() or DEFAULT_SINK


def _debug(exc: BaseException) -> None:
    if os.environ.get(DEBUG_ENV) == "1":
        print(f"baron events: sink error swallowed — {type(exc).__name__}: {exc}",
              file=sys.stderr)


def emit(event: Event, cwd: Path | None = None) -> None:
    """Send one event to the configured sink. **Never raises.**

    ``cwd`` locates the repo for sinks that write into it; it is handed over
    through the duck-typed optional ``bind()`` extension rather than the Sink
    Protocol, which stays at three members (see :mod:`baron.sinks.base`).
    """
    try:
        from .sinks import get_sink  # local import: sinks must not import events

        sink = get_sink(sink_name())
        bind = getattr(sink, "bind", None)
        if callable(bind) and cwd is not None:
            bind(cwd)
        sink.emit(event)
    except Exception as exc:  # fail-OPEN: observation must never brick a session
        _debug(exc)
