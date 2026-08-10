#!/usr/bin/env python3
"""
ingest_otel.py — Ingest exported OpenTelemetry trace/event FILES and emit
session-level metrics JSON for the multi-agent-audit telemetry mode.

Consumes FILES only — never live endpoints. Zero infra, zero secrets,
reproducible. Accepted input shapes (autodetected per file):

  1. OTLP-JSON        — a JSON object with `resourceSpans` and/or
                        `resourceLogs` (the OTLP `http/json` payload shape;
                        e.g. what an OTel Collector `file` exporter writes,
                        or Claude Code's OTLP export captured to disk).
  2. Flat JSONL       — one JSON object per line; each object is a span or
                        a log-event row. Liberal key handling covers
                        Logfire `records`-table exports (`span_name`,
                        `trace_id`, `start_timestamp`, `attributes`) and
                        Phoenix span-dataframe exports (`name`, `span_kind`,
                        `status_code`, `context.trace_id`,
                        `attributes.<dotted>` flattened columns).
  3. Flat JSON array  — same rows as (2), wrapped in a single JSON list.

Be liberal in what you accept; be explicit about what you could not parse
(per-file `unparseable` count in the output's `ingest.files` block).

Semantic conventions recognized (first match wins, span before event):
  sessions    — `session.id` (Claude Code), `session_id`,
                `gen_ai.conversation.id`; fallback: trace_id (then the
                session-count confidence is downgraded to `inferred`).
  human turns — `claude_code.user_prompt` events (docs:
                https://code.claude.com/docs/en/monitoring-usage),
                `gen_ai.user.message` events, `claude_code.interaction`
                spans (used only when a session has zero user-prompt
                events, to avoid double counting).
  tool calls  — `claude_code.tool` / `claude_code.tool.execution` spans,
                `claude_code.tool_result` events, any record with
                `tool_name` / `tool.name` / `gen_ai.tool.name`, or
                OpenInference `openinference.span.kind == "TOOL"`.
                Deduplicated by `tool_use_id` when present.
  LLM calls   — `claude_code.llm_request` spans, `claude_code.api_request`
                events, any record with `gen_ai.system`, or OpenInference
                span kind `LLM`. Deduplicated/merged by `request_id` /
                `client_request_id` (span wins on conflict; event fills
                gaps — e.g. Claude Code puts cost on the api_request
                event, not on the llm_request span).
  tokens      — `input_tokens`/`output_tokens` (Claude Code),
                `gen_ai.usage.input_tokens`/`.output_tokens` (OTel GenAI
                semconv, e.g. Logfire), `llm.token_count.prompt`/
                `.completion` (OpenInference, e.g. Phoenix).
  cost        — `cost_usd`, `cost_usd_micros` (Claude Code api_request
                event), `gen_ai.usage.cost`. NEVER estimated from token
                counts — absent attrs are reported `not measurable`.
  tasks       — `workflow.run_id` (Claude Code), `task.id`, `task_id`,
                `gen_ai.task.id`. Absent => human-turns-per-task is
                `not measurable (attribute absent)`.
  baron       — rows from barony's observation plane (ADR-013): span names
                `guard.decision` / `guard.override` / `session.start` /
                `session.end` / `tool.post` / `tool.failure`, identified by
                the `baron.outcome` attribute. These are governance evidence
                ABOUT a call, produced by baron's own hook process. They are
                SPLIT OUT of the activity plane before sessions are built —
                see `partition_guard_records` — and counted on their own axis
                as `guard_decisions` / `baron_events_by_kind`. An export of
                baron rows alone therefore reports the activity metrics as
                `not measurable`, with a note saying why, rather than
                inventing a session out of hook timings.

HONESTY RULE (inherited from SKILL.md): every emitted metric carries a
confidence label — `measured` (with source files), `inferred` (with a note
saying why it is partial), or `not measurable` (with the missing attribute
named). Nothing is ever estimated to fill a row.

Usage:
  python3 ingest_otel.py <export-file> [<export-file> ...] \
      [--output <metrics.json>] [--session-attr KEY] [--pretty]

Read-only on inputs. Writes only --output (default: stdout).
Stdlib only; Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

INGESTER_VERSION = "1.1"

# --- attribute conventions -------------------------------------------------

SESSION_ATTR_KEYS = ["session.id", "session_id", "gen_ai.conversation.id",
                     "conversation.id"]
INPUT_TOKEN_KEYS = ["input_tokens", "gen_ai.usage.input_tokens",
                    "gen_ai.usage.prompt_tokens", "llm.token_count.prompt"]
OUTPUT_TOKEN_KEYS = ["output_tokens", "gen_ai.usage.output_tokens",
                     "gen_ai.usage.completion_tokens",
                     "llm.token_count.completion"]
CACHE_READ_KEYS = ["cache_read_tokens", "gen_ai.usage.cache_read_tokens"]
CACHE_CREATE_KEYS = ["cache_creation_tokens",
                     "gen_ai.usage.cache_creation_tokens"]
COST_USD_KEYS = ["cost_usd", "gen_ai.usage.cost"]
COST_MICROS_KEYS = ["cost_usd_micros"]
TOOL_NAME_KEYS = ["tool_name", "tool.name", "gen_ai.tool.name"]
TASK_KEYS = ["workflow.run_id", "task.id", "task_id", "gen_ai.task.id"]
AGENT_KEYS = ["agent.name", "agent_id", "subagent_type", "service.name",
              "user.email"]
MODEL_KEYS = ["model", "gen_ai.request.model", "gen_ai.response.model",
              "llm.model_name"]
REQUEST_ID_KEYS = ["request_id", "client_request_id", "gen_ai.response.id"]

# --- barony observation plane (v1.1) ---------------------------------------
# The FROZEN `baron.` attribute namespace (barony ADR-013 §"Reserved keys").
# These rows are governance evidence ABOUT tool calls, emitted by baron's own
# hook process, so they are counted on their own axis and split out of the
# activity plane in `compute_metrics` BEFORE sessions are built. See
# `partition_guard_records` for the exact list of metrics that exclusion
# covers, and barony ADR-018 for the measured contamination it prevents.
# Only the keys this ingester READS are listed. The namespace also carries
# `baron.actor`, `baron.subject`, `baron.reason`, `baron.capability.verb` and
# `baron.enforcement`; none is consumed at v1.1, and `baron.enforcement`
# deliberately so — see compute_guard_metrics.
BARON_ATTR_KEYS = {
    "outcome": "baron.outcome",
}
#: Every span name baron's plane emits (ADR-013 `events.KNOWN_KINDS`), plus
#: ADR-014's `baron.guard.evaluate` so an export from that (unmerged, and
#: possibly third-party) producer partitions correctly too. Membership is a
#: convenience: the `baron.outcome` attribute is what actually identifies a
#: row, so a kind added to the registry tomorrow is handled without a change
#: here.
BARON_OBSERVATION_SPAN_NAMES = {"guard.decision", "guard.override",
                                "session.start", "session.end", "tool.post",
                                "tool.failure", "baron.guard.evaluate"}
#: The subset that is an adjudication of a tool call, as opposed to evidence
#: that one happened. Only these are counted in `guard_decisions`.
BARON_DECISION_SPAN_NAMES = {"guard.decision", "guard.override",
                             "baron.guard.evaluate"}
#: Canonical outcomes, always present in the counts (0 when unseen) so a
#: dashboard column never silently disappears. `ok` is what the evidence kinds
#: carry; it is listed because `guard_decisions` counts decision rows only and
#: an unexpected `ok` there would be a producer change worth seeing.
BARON_OUTCOMES = ("allow", "deny", "error", "ok", "override")

HUMAN_EVENT_NAMES = {"claude_code.user_prompt", "gen_ai.user.message",
                     "user_prompt"}
INTERACTION_SPAN_NAMES = {"claude_code.interaction"}
LLM_SPAN_NAMES = {"claude_code.llm_request"}
LLM_EVENT_NAMES = {"claude_code.api_request"}
TOOL_SPAN_NAMES = {"claude_code.tool", "claude_code.tool.execution"}
TOOL_EVENT_NAMES = {"claude_code.tool_result"}


# --- small helpers ---------------------------------------------------------

def first_attr(attrs: dict, keys: list[str]):
    for k in keys:
        if k in attrs and attrs[k] is not None:
            return attrs[k]
    return None


def to_number(v):
    """Coerce OTLP string-encoded ints / numeric strings to numbers."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            try:
                return float(v)
            except ValueError:
                return None
    return None


def parse_ts(v):
    """Parse a timestamp into epoch seconds (float). None if unparseable.

    Numeric heuristic: >1e17 nanos, >1e14 micros, >1e11 millis, else seconds.
    Strings: numeric strings via the same rule, else ISO 8601.
    """
    if v is None:
        return None
    n = to_number(v)
    if n is not None:
        n = float(n)
        if n > 1e17:
            return n / 1e9
        if n > 1e14:
            return n / 1e6
        if n > 1e11:
            return n / 1e3
        return n
    if isinstance(v, str):
        s = v.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    return None


def iso(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z")


def decode_otlp_value(v: dict):
    if not isinstance(v, dict):
        return v
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:
        return to_number(v["intValue"])
    if "doubleValue" in v:
        return to_number(v["doubleValue"])
    if "boolValue" in v:
        return v["boolValue"]
    if "arrayValue" in v:
        return [decode_otlp_value(x)
                for x in (v["arrayValue"].get("values") or [])]
    if "kvlistValue" in v:
        return decode_otlp_attrs(v["kvlistValue"].get("values") or [])
    return None


def decode_otlp_attrs(attr_list) -> dict:
    out = {}
    for kv in attr_list or []:
        if isinstance(kv, dict) and "key" in kv:
            out[kv["key"]] = decode_otlp_value(kv.get("value", {}))
    return out


# --- record loading --------------------------------------------------------
# Internal record model: dict with keys
#   kind ("span"|"event"), name, trace_id, span_id, start, end (epoch s),
#   attrs (resource attrs merged under record attrs), status_error (bool),
#   source (file basename)

def _record_status_error(status: dict | None, attrs: dict) -> bool:
    code = (status or {}).get("code")
    if code in (2, "2", "STATUS_CODE_ERROR", "ERROR", "Error", "error"):
        return True
    success = attrs.get("success")
    if isinstance(success, str) and success.lower() == "false":
        return True
    if success is False:  # explicit boolean False => error
        return True
    if attrs.get("error_type"):
        return True
    return False


def records_from_otlp(doc: dict, source: str):
    """Yield internal records from an OTLP-JSON document."""
    records = []
    n_spans = n_events = 0
    has_logs_stream = "resourceLogs" in doc

    for rs in doc.get("resourceSpans") or []:
        res_attrs = decode_otlp_attrs(
            (rs.get("resource") or {}).get("attributes"))
        for ss in rs.get("scopeSpans") or rs.get("instrumentationLibrarySpans") or []:
            for span in ss.get("spans") or []:
                attrs = dict(res_attrs)
                attrs.update(decode_otlp_attrs(span.get("attributes")))
                records.append({
                    "kind": "span",
                    "name": span.get("name") or "",
                    "trace_id": span.get("traceId"),
                    "span_id": span.get("spanId"),
                    "start": parse_ts(span.get("startTimeUnixNano")),
                    "end": parse_ts(span.get("endTimeUnixNano")),
                    "attrs": attrs,
                    "status_error": _record_status_error(
                        span.get("status"), attrs),
                    "source": source,
                })
                n_spans += 1

    for rl in doc.get("resourceLogs") or []:
        res_attrs = decode_otlp_attrs(
            (rl.get("resource") or {}).get("attributes"))
        for sl in rl.get("scopeLogs") or []:
            for lr in sl.get("logRecords") or []:
                attrs = dict(res_attrs)
                attrs.update(decode_otlp_attrs(lr.get("attributes")))
                body = lr.get("body")
                body_s = decode_otlp_value(body) if isinstance(body, dict) \
                    else (body if isinstance(body, str) else None)
                name = (attrs.get("event.name") or lr.get("eventName")
                        or (body_s if isinstance(body_s, str) else "") or "")
                ts = parse_ts(lr.get("timeUnixNano")
                              or lr.get("observedTimeUnixNano"))
                records.append({
                    "kind": "event",
                    "name": name,
                    "trace_id": lr.get("traceId"),
                    "span_id": lr.get("spanId"),
                    "start": ts,
                    "end": None,
                    "attrs": attrs,
                    "status_error": _record_status_error(None, attrs),
                    "source": source,
                })
                n_events += 1

    return records, n_spans, n_events, has_logs_stream


FLAT_NAME_KEYS = ["span_name", "name", "Name"]
FLAT_TRACE_KEYS = ["trace_id", "traceId", "context.trace_id"]
FLAT_SPANID_KEYS = ["span_id", "spanId", "context.span_id"]
FLAT_START_KEYS = ["start_timestamp", "start_time", "startTime", "timestamp",
                   "time"]
FLAT_END_KEYS = ["end_timestamp", "end_time", "endTime"]


def record_from_flat(obj: dict, source: str):
    """Normalize one flat JSONL/array row (Logfire / Phoenix style)."""
    if not isinstance(obj, dict):
        return None
    attrs = {}
    raw_attrs = obj.get("attributes")
    if isinstance(raw_attrs, dict):
        attrs.update(raw_attrs)
    elif isinstance(raw_attrs, list):  # OTLP-style kv list smuggled into JSONL
        attrs.update(decode_otlp_attrs(raw_attrs))
    # Phoenix dataframe exports flatten attrs into dotted columns.
    for k, v in obj.items():
        if isinstance(k, str) and k.startswith("attributes."):
            attrs[k[len("attributes."):]] = v
    # Phoenix span_kind column -> OpenInference kind attr.
    if "span_kind" in obj and "openinference.span.kind" not in attrs:
        attrs["openinference.span.kind"] = obj["span_kind"]

    name = str(first_attr(obj, FLAT_NAME_KEYS) or "")
    start = parse_ts(first_attr(obj, FLAT_START_KEYS))
    end = parse_ts(first_attr(obj, FLAT_END_KEYS))

    event_name = attrs.get("event.name") or obj.get("event.name")
    kind = obj.get("kind")
    is_event = (kind == "event"
                or (isinstance(event_name, str) and event_name != ""))
    if is_event and event_name:
        name = event_name

    status = None
    sc = obj.get("status_code") or obj.get("status")
    if sc is not None:
        status = {"code": sc if not isinstance(sc, dict) else sc.get("code")}

    return {
        "kind": "event" if is_event else "span",
        "name": name,
        "trace_id": first_attr(obj, FLAT_TRACE_KEYS),
        "span_id": first_attr(obj, FLAT_SPANID_KEYS),
        "start": start,
        "end": end,
        "attrs": attrs,
        "status_error": _record_status_error(status, attrs),
        "source": source,
    }


def load_file(path: Path):
    """Load one export file. Returns (records, file_report)."""
    source = path.name
    report = {"path": str(path), "format": None, "spans": 0, "events": 0,
              "unparseable": 0, "has_logs_stream": False, "notes": []}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        report["format"] = "unreadable"
        report["notes"].append(f"could not read file: {e}")
        return [], report

    records: list[dict] = []

    # Whole-file JSON first (OTLP-JSON object, or a flat array).
    doc = None
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        doc = None

    if isinstance(doc, dict) and ("resourceSpans" in doc
                                  or "resourceLogs" in doc
                                  or "resourceMetrics" in doc):
        report["format"] = "otlp-json"
        recs, n_spans, n_events, has_logs = records_from_otlp(doc, source)
        records.extend(recs)
        report["spans"], report["events"] = n_spans, n_events
        report["has_logs_stream"] = has_logs
        if "resourceMetrics" in doc:
            report["notes"].append(
                "resourceMetrics present but not ingested (metrics stream "
                "carries aggregates, not per-session events); use the "
                "spans/logs streams for session-level analysis")
        return records, report

    if isinstance(doc, list):
        report["format"] = "json-array"
        rows = doc
    elif isinstance(doc, dict):
        report["format"] = "json-object"
        rows = [doc]
    else:
        report["format"] = "jsonl"
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                report["unparseable"] += 1

    for row in rows:
        rec = record_from_flat(row, source)
        if rec is None:
            report["unparseable"] += 1
            continue
        records.append(rec)
        if rec["kind"] == "event":
            report["events"] += 1
        else:
            report["spans"] += 1
    if report["unparseable"]:
        report["notes"].append(
            f"{report['unparseable']} row(s) were not parseable JSON "
            "objects and were skipped")
    return records, report


# --- classification --------------------------------------------------------

def is_human_turn_event(rec) -> bool:
    return rec["kind"] == "event" and rec["name"] in HUMAN_EVENT_NAMES


def is_interaction_span(rec) -> bool:
    return (rec["kind"] == "span"
            and (rec["name"] in INTERACTION_SPAN_NAMES
                 or "user_prompt_length" in rec["attrs"]
                 or "user_prompt" in rec["attrs"]))


def is_llm_record(rec) -> bool:
    if rec["kind"] == "span":
        if rec["name"] in LLM_SPAN_NAMES:
            return True
        if "gen_ai.system" in rec["attrs"]:
            return True
        if rec["attrs"].get("openinference.span.kind") == "LLM":
            return True
        return False
    return rec["name"] in LLM_EVENT_NAMES


def is_tool_record(rec) -> bool:
    if is_llm_record(rec) or is_human_turn_event(rec):
        return False
    if rec["kind"] == "span":
        if rec["name"] in TOOL_SPAN_NAMES:
            return True
        if rec["attrs"].get("openinference.span.kind") == "TOOL":
            return True
        return first_attr(rec["attrs"], TOOL_NAME_KEYS) is not None
    return rec["name"] in TOOL_EVENT_NAMES


def is_baron_observation_record(rec) -> bool:
    """A row from barony's observation plane (ADR-013), not agent activity.

    Matched on the `baron.outcome` attribute — the one slot ADR-013 puts on
    EVERY row — or on a known span name, so a kind added to the registry
    tomorrow still partitions correctly. An agent-activity span has no reason
    to carry `baron.outcome`, so this cannot claim an ordinary export's rows.
    """
    return (rec["kind"] == "span"
            and (BARON_ATTR_KEYS["outcome"] in rec["attrs"]
                 or rec["name"] in BARON_OBSERVATION_SPAN_NAMES))


def is_baron_decision_record(rec) -> bool:
    """A baron row that ADJUDICATED a call, rather than witnessing one."""
    return (is_baron_observation_record(rec)
            and rec["name"] in BARON_DECISION_SPAN_NAMES)


def partition_guard_records(records):
    """Split (activity_records, baron_records). v1.1; barony ADR-018.

    A baron row is its hook's record OF a tool call. It is not agent activity,
    and everything derived from agent activity must be computed without it:

      * SESSION GROUPING — baron rows carry `session.id`, which is in
        `SESSION_ATTR_KEYS`. Left in, an export of baron rows alone produces a
        session that never happened.
      * `session_duration_total_s` / `_p50_s` — a guard row is one PreToolUse
        hook process. Grouped into a session it publishes the hook's own
        wall-clock, labelled `measured`, in a field an auditor reads as agent
        working time. That is the specific dishonesty this split exists to
        prevent.
      * `distinct_agent_identities` — baron rows carry `agent.name` (the
        persona slug, defaulting to `baron.actor`, itself defaulting to
        `"unknown"`), so a persona that guard merely EVALUATED — and a literal
        `"unknown"` — would join the roster of agents observed working.
      * `tool_calls_total` / `_by_name` / `tool_error_rate` — ADR-013 puts
        `tool.name` in the fixed slots of every row, which is correct for
        joining but means `is_tool_record` returns True for them. Guard
        evaluating eleven calls is not eleven tool calls, and a
        `session.start` row is not a tool named `session.start`.

    NAME. It is `partition_guard_records` because that is the name the fix
    carries in barony ADR-014 §9.1 and in the branch it is ported from, and
    guard is what emits most rows. It partitions the whole `baron.`
    observation namespace, not only the guard kinds — the evidence kinds
    (`tool.post`, `session.start`, …) reach the ingester through the same
    file and carry the same contaminating attributes.

    Returns the ORIGINAL list object as `activity_records` when no baron rows
    are present, so the no-baron path is unchanged and allocation-free.
    """
    baron = [r for r in records if is_baron_observation_record(r)]
    if not baron:
        return records, baron
    return [r for r in records if not is_baron_observation_record(r)], baron


#: Absence note for an activity metric when the export contains baron evidence
#: and nothing else. Saying "no parseable records" here would be false — the
#: records parsed fine, they are just not activity.
GUARD_ONLY_ABSENT = (
    "no agent-activity records — every record in this export is a barony "
    "observation-plane row (`baron.outcome` present), which v1.1 excludes "
    "from the activity plane. A hook process's own timings are not a session, "
    "a duration, or an agent's working time, and are not published as one "
    "(barony ADR-018). The baron rows ARE counted, in `guard_decisions` / "
    "`baron_events_by_kind`.")

#: Suffix for a mixed export (activity + baron) where the activity side cannot
#: supply the metric. Without it the reader sees "no spans stream in export"
#: while looking at a file full of spans.
GUARD_PRESENT_SUFFIX = (
    "; the barony observation-plane row(s) in this export are governance "
    "evidence about tool calls, excluded from the activity plane by design "
    "(barony ADR-018), so they cannot supply this metric")


def absent_activity(base_note, baron_records, baron_only):
    """`not_measurable` for an activity metric, with a note that is TRUE.

    With no baron rows this returns exactly the pre-1.1 note, which is what
    keeps the change additive for every pre-1.1 export.
    """
    if baron_only:
        return not_measurable(GUARD_ONLY_ABSENT)
    if baron_records:
        return not_measurable(base_note + GUARD_PRESENT_SUFFIX)
    return not_measurable(base_note)


def count_values(recs, key, canonical):
    """Count one attribute's values. `canonical` keys are always present.

    Unrecognised values are counted under their own key rather than dropped —
    a producer that starts emitting a new value must show up in the numbers,
    not vanish from them. Returns (counts, sorted unrecognised values).
    """
    counts = {k: 0 for k in canonical}
    unknown = []
    for r in recs:
        v = r["attrs"].get(key)
        v = "(absent)" if v is None else str(v)
        if v not in counts:
            unknown.append(v)
        counts[v] = counts.get(v, 0) + 1
    return dict(sorted(counts.items())), sorted(set(unknown))


def compute_guard_metrics(baron_records, src_names):
    """Counts over the withheld barony partition (v1.1; ADR-018).

    `baron_records` is the partition from :func:`partition_guard_records` —
    the same rows withheld from the activity plane, counted here so they are
    excluded from the pre-existing metrics without being discarded.

    Two new aggregate keys; no existing metric changes shape. Both are
    `measured` whenever any baron row is present — they are DIRECT COUNTS of
    an attribute that is either there or not. Nothing here is inferred: with
    no baron rows both come back `not measurable` with the attribute named.

    DELIBERATELY ABSENT: a count of `baron.enforcement`. That attribute is
    under correction (DECISIONS-FOR-REVIEW D1; ADR-013 §9.1 measured it
    booking structural refusals as `enforced` and genuine persona-dependent
    allows as `not-applicable`). Publishing a `measured` aggregate over a
    field whose producer-side definition is known wrong is the over-claim this
    project exists to catch. It lands when the label does — ADR-018 §5.
    """
    if not baron_records:
        absent = not_measurable(
            "attribute absent — no barony observation-plane rows "
            "(baron.outcome) in export; barony emits them when "
            "BARON_EVENTS_SINK=disk is set (default is `null`, which "
            "discards)")
        return {"guard_decisions": absent, "baron_events_by_kind": absent}

    decisions = [r for r in baron_records if is_baron_decision_record(r)]
    counts, unknown = count_values(decisions, BARON_ATTR_KEYS["outcome"],
                                   BARON_OUTCOMES)
    note = (f"direct count over {len(decisions)} of {len(baron_records)} "
            "barony rows — the adjudication kinds (guard.decision, "
            "guard.override) only; the evidence kinds are in "
            "`baron_events_by_kind`. `deny` is a capability denial, `error` "
            "is a fail-closed deny because guard could not evaluate at all — "
            "they are different operational signals and are never folded "
            "together. WHAT THIS IS NOT: it is not a fidelity score. It "
            "measures the traffic mix of one export, which shifts with "
            "whatever the agents happened to run")
    if unknown:
        note += (f"; unrecognised outcome value(s) {unknown} were counted "
                 "under their own keys rather than dropped")

    by_kind: dict[str, int] = {}
    for r in baron_records:
        by_kind[r["name"]] = by_kind.get(r["name"], 0) + 1

    return {
        "guard_decisions": measured(counts, src_names, note=note),
        "baron_events_by_kind": measured(
            dict(sorted(by_kind.items())), src_names,
            note=(f"every one of the {len(baron_records)} barony "
                  "observation-plane row(s) withheld from the activity "
                  "plane, by span name. Published so the exclusion is "
                  "auditable rather than silent: nothing partitioned out is "
                  "discarded without appearing here")),
    }


def session_key(rec, session_attr: str | None):
    """Return (key, method) for grouping a record into a session."""
    if session_attr:
        v = rec["attrs"].get(session_attr)
        if v is not None:
            return str(v), f"attribute {session_attr}"
    v = first_attr(rec["attrs"], SESSION_ATTR_KEYS)
    if v is not None:
        return str(v), "session attribute"
    if rec["trace_id"]:
        return f"trace:{rec['trace_id']}", "trace_id fallback"
    return f"file:{rec['source']}", "file fallback"


# --- metric wrappers (the honesty rule, mechanized) ------------------------

def measured(value, sources, note=None):
    d = {"value": value, "confidence": "measured",
         "source": sorted(set(sources))}
    if note:
        d["note"] = note
    return d


def inferred(value, sources, note):
    return {"value": value, "confidence": "inferred",
            "source": sorted(set(sources)), "note": note}


def not_measurable(note):
    return {"value": "not measurable", "confidence": "not measurable",
            "note": note}


def sum_metric(pairs, sources, absent_note, kind_label):
    """Aggregate (value_or_None) pairs into a labeled sum.

    pairs: list of per-record values, None where the attribute was absent.
    All present  -> measured; some -> inferred (coverage note);
    none present -> not measurable (absent_note).
    """
    present = [v for v in pairs if v is not None]
    if not pairs:
        return not_measurable(
            f"no {kind_label} records in export — {absent_note}")
    if not present:
        return not_measurable(f"attribute absent — {absent_note}")
    total = sum(present)
    if len(present) == len(pairs):
        return measured(total, sources)
    return inferred(
        total, sources,
        f"attribute present on {len(present)}/{len(pairs)} {kind_label} "
        "records; total covers only those — do not extrapolate")


# --- session building + metrics -------------------------------------------

def build_sessions(records, session_attr=None):
    sessions: dict[str, dict] = {}
    for rec in records:
        key, method = session_key(rec, session_attr)
        s = sessions.setdefault(key, {
            "session_id": key, "identity_method": method,
            "records": [], "sources": set(),
        })
        # Prefer the strongest identity method seen for the session.
        if "fallback" not in method and "fallback" in s["identity_method"]:
            s["identity_method"] = method
        s["records"].append(rec)
        s["sources"].add(rec["source"])
    return sessions


def dedupe_tool_records(recs):
    """Merge tool spans + tool_result events by tool_use_id."""
    by_id: dict[str, dict] = {}
    anonymous = []
    for r in recs:
        tid = r["attrs"].get("tool_use_id") or r["attrs"].get(
            "gen_ai.tool.call.id")
        if tid is None:
            anonymous.append(r)
            continue
        cur = by_id.get(str(tid))
        if cur is None or (cur["kind"] == "event" and r["kind"] == "span"):
            # span is the authoritative record; keep error flag from either
            err = r["status_error"] or (cur["status_error"] if cur else False)
            r = dict(r)
            r["status_error"] = err
            by_id[str(tid)] = r
        else:
            cur["status_error"] = cur["status_error"] or r["status_error"]
    return list(by_id.values()) + anonymous


def dedupe_llm_records(recs):
    """Merge llm spans + api_request events by request id (span wins,
    event fills attribute gaps — Claude Code puts cost on the event)."""
    by_id: dict[str, dict] = {}
    anonymous = []
    for r in recs:
        rid = first_attr(r["attrs"], REQUEST_ID_KEYS)
        if rid is None:
            anonymous.append(r)
            continue
        rid = str(rid)
        cur = by_id.get(rid)
        if cur is None:
            by_id[rid] = dict(r, attrs=dict(r["attrs"]))
            continue
        primary, secondary = (cur, r) if cur["kind"] == "span" or \
            r["kind"] == "event" else (r, cur)
        merged_attrs = dict(secondary["attrs"])
        merged_attrs.update(primary["attrs"])   # span attrs win
        primary = dict(primary, attrs=merged_attrs)
        primary["status_error"] = cur["status_error"] or r["status_error"]
        by_id[rid] = primary
    return list(by_id.values()) + anonymous


def record_duration_ms(rec):
    d = to_number(rec["attrs"].get("duration_ms"))
    if d is not None:
        return d
    if rec["start"] is not None and rec["end"] is not None:
        return (rec["end"] - rec["start"]) * 1000.0
    return None


def llm_cost_usd(attrs):
    v = to_number(first_attr(attrs, COST_USD_KEYS))
    if v is not None:
        return v
    m = to_number(first_attr(attrs, COST_MICROS_KEYS))
    if m is not None:
        return m / 1e6
    return None


def compute_session(s, file_reports_by_name):
    recs = s["records"]
    tools = dedupe_tool_records([r for r in recs if is_tool_record(r)])
    llms = dedupe_llm_records([r for r in recs if is_llm_record(r)])
    human_events = [r for r in recs if is_human_turn_event(r)]
    interactions = [r for r in recs if is_interaction_span(r)]

    # Human turns: user-prompt events preferred; interaction spans only as
    # a substitute (never summed — an interaction wraps a user prompt).
    if human_events:
        human_turns = len(human_events)
    elif interactions:
        human_turns = len(interactions)
    else:
        # Only claim a measured zero when at least one contributing file
        # actually exported a logs/events stream.
        has_logs = any(
            file_reports_by_name.get(src, {}).get("has_logs_stream")
            for src in s["sources"])
        human_turns = 0 if has_logs else None

    times = [t for r in recs for t in (r["start"], r["end"])
             if t is not None]
    start = min(times) if times else None
    end = max(times) if times else None

    agents = sorted({str(v) for r in recs
                     for v in [first_attr(r["attrs"], AGENT_KEYS)]
                     if v is not None})
    models = sorted({str(v) for r in llms
                     for v in [first_attr(r["attrs"], MODEL_KEYS)]
                     if v is not None})
    tasks = sorted({str(v) for r in recs
                    for v in [first_attr(r["attrs"], TASK_KEYS)]
                    if v is not None})

    def tok(keys):
        return [to_number(first_attr(r["attrs"], keys)) for r in llms]

    return {
        "session_id": s["session_id"],
        "identity_method": s["identity_method"],
        "source_files": sorted(s["sources"]),
        "start": iso(start),
        "end": iso(end),
        "duration_s": round(end - start, 3)
        if start is not None and end is not None else None,
        "agents": agents,
        "models": models,
        "tasks": tasks,
        "human_turns": human_turns,
        "tool_calls": len(tools),
        "tool_errors": sum(1 for r in tools if r["status_error"]),
        "tool_calls_by_name": _count_by(
            tools, lambda r: str(first_attr(r["attrs"], TOOL_NAME_KEYS)
                                 or r["name"] or "(unnamed)")),
        "llm_calls": len(llms),
        "input_tokens": _sum_or_none(tok(INPUT_TOKEN_KEYS)),
        "output_tokens": _sum_or_none(tok(OUTPUT_TOKEN_KEYS)),
        "cache_read_tokens": _sum_or_none(tok(CACHE_READ_KEYS)),
        "cache_creation_tokens": _sum_or_none(tok(CACHE_CREATE_KEYS)),
        "cost_usd": _sum_or_none([llm_cost_usd(r["attrs"]) for r in llms],
                                 round_to=6),
        "_tok_pairs": {
            "input": tok(INPUT_TOKEN_KEYS),
            "output": tok(OUTPUT_TOKEN_KEYS),
            "cache_read": tok(CACHE_READ_KEYS),
            "cache_creation": tok(CACHE_CREATE_KEYS),
            "cost": [llm_cost_usd(r["attrs"]) for r in llms],
        },
    }


def _count_by(items, keyfn):
    out: dict[str, int] = {}
    for it in items:
        k = keyfn(it)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def _sum_or_none(vals, round_to=None):
    present = [v for v in vals if v is not None]
    if not present:
        return None
    total = sum(present)
    if round_to is not None and isinstance(total, float):
        total = round(total, round_to)
    return total


def compute_metrics(records, file_reports, session_attr=None):
    sources = [r["path"] for r in file_reports]
    src_names = [Path(p).name for p in sources]
    reports_by_name = {Path(r["path"]).name: r for r in file_reports}

    # v1.1 — split barony observation rows out BEFORE anything is grouped.
    # Everything below this line sees agent activity only; the baron rows are
    # counted on their own axis at the end. See partition_guard_records for
    # what leaked when this was missing (barony ADR-018).
    activity_records, baron_records = partition_guard_records(records)
    baron_only = bool(baron_records) and not activity_records

    sessions_raw = build_sessions(activity_records, session_attr)
    sessions = [compute_session(s, reports_by_name)
                for s in sessions_raw.values()]
    sessions.sort(key=lambda s: (s["start"] or "", s["session_id"]))

    agg: dict[str, dict] = {}

    # session count + identity honesty
    fallback_sessions = [s for s in sessions
                         if "fallback" in s["identity_method"]]
    if not sessions:
        agg["session_count"] = absent_activity(
            "no spans or events could be parsed from the input files",
            baron_records, baron_only)
    elif fallback_sessions:
        agg["session_count"] = inferred(
            len(sessions), src_names,
            f"{len(fallback_sessions)}/{len(sessions)} sessions keyed by "
            "trace_id because no session attribute (session.id / "
            "gen_ai.conversation.id) is present; one trace may not equal "
            "one user session")
    else:
        agg["session_count"] = measured(len(sessions), src_names)

    durations = [s["duration_s"] for s in sessions
                 if s["duration_s"] is not None]
    if durations:
        agg["session_duration_total_s"] = measured(
            round(sum(durations), 3), src_names)
        agg["session_duration_p50_s"] = measured(
            round(statistics.median(durations), 3), src_names)
    else:
        agg["session_duration_total_s"] = absent_activity(
            "attribute absent — no records carried parseable timestamps",
            baron_records, baron_only)
        agg["session_duration_p50_s"] = agg["session_duration_total_s"]

    # tool calls
    n_tools = sum(s["tool_calls"] for s in sessions)
    n_tool_errors = sum(s["tool_errors"] for s in sessions)
    # Counted over the ACTIVITY records, not `file_reports`, so a file of pure
    # baron rows is not mistaken for a spans stream (which would publish a
    # `measured` zero tool calls for an export that never described any).
    # Equivalent to the pre-1.1 `any(r["spans"] for r in file_reports)` when no
    # baron rows are present: load_file counts exactly the span records it
    # returns.
    any_spans = any(r["kind"] == "span" for r in activity_records)
    if n_tools or any_spans:
        agg["tool_calls_total"] = measured(n_tools, src_names)
        agg["tool_errors_total"] = measured(
            n_tool_errors, src_names,
            note="error = OTLP status ERROR, success=false, or error_type "
                 "present; spans with unset status count as ok (OTLP "
                 "contract: STATUS_CODE_UNSET is not an error)")
        agg["tool_error_rate"] = (
            measured(round(n_tool_errors / n_tools, 4), src_names)
            if n_tools else not_measurable(
                "no tool-call spans/events in export"))
        by_name: dict[str, int] = {}
        for s in sessions:
            for k, v in s["tool_calls_by_name"].items():
                by_name[k] = by_name.get(k, 0) + v
        agg["tool_calls_by_name"] = measured(dict(sorted(by_name.items())),
                                             src_names)
    else:
        agg["tool_calls_total"] = absent_activity(
            "no spans stream in export — tool calls require trace spans "
            "or tool_result events", baron_records, baron_only)
        agg["tool_errors_total"] = agg["tool_calls_total"]
        agg["tool_error_rate"] = agg["tool_calls_total"]
        agg["tool_calls_by_name"] = agg["tool_calls_total"]

    # llm calls + tokens + cost
    n_llm = sum(s["llm_calls"] for s in sessions)
    agg["llm_calls_total"] = measured(n_llm, src_names) if sessions else \
        absent_activity("no parseable records", baron_records, baron_only)
    tok_specs = [
        ("input_tokens_total", "input",
         "no input-token attribute (input_tokens / "
         "gen_ai.usage.input_tokens / llm.token_count.prompt) on any LLM "
         "record"),
        ("output_tokens_total", "output",
         "no output-token attribute (output_tokens / "
         "gen_ai.usage.output_tokens / llm.token_count.completion) on any "
         "LLM record"),
        ("cache_read_tokens_total", "cache_read",
         "no cache-read-token attribute (cache_read_tokens / "
         "gen_ai.usage.cache_read_tokens) on any LLM record"),
        ("cache_creation_tokens_total", "cache_creation",
         "no cache-creation-token attribute (cache_creation_tokens) on "
         "any LLM record"),
        ("cost_usd_total", "cost",
         "no cost attribute (cost_usd / cost_usd_micros / "
         "gen_ai.usage.cost) on any LLM record; cost is NEVER estimated "
         "from token counts"),
    ]
    for out_key, pair_key, absent_note in tok_specs:
        pairs = [v for s in sessions for v in s["_tok_pairs"][pair_key]]
        m = sum_metric(pairs, src_names, absent_note, "LLM")
        if isinstance(m.get("value"), float):
            m["value"] = round(m["value"], 6)
        agg[out_key] = m

    # human turns (the INTERVENTION TAX input)
    turn_vals = [s["human_turns"] for s in sessions]
    known = [v for v in turn_vals if v is not None]
    if not sessions:
        agg["human_turns_total"] = absent_activity(
            "no parseable records", baron_records, baron_only)
    elif not known:
        agg["human_turns_total"] = not_measurable(
            "attribute absent — no user-prompt events "
            "(claude_code.user_prompt / gen_ai.user.message) or "
            "interaction spans in export, and no logs/events stream was "
            "present to confirm a true zero; export the logs stream "
            "(Claude Code: OTEL_LOGS_EXPORTER=otlp) to measure this")
    else:
        total = sum(known)
        if len(known) == len(turn_vals):
            agg["human_turns_total"] = measured(
                total, src_names,
                note="user-prompt events preferred; interaction spans "
                     "counted only for sessions with zero user-prompt "
                     "events (no double counting)")
        else:
            agg["human_turns_total"] = inferred(
                total, src_names,
                f"human turns measurable on {len(known)}/{len(turn_vals)} "
                "sessions (others lacked a logs/events stream); total "
                "covers only those")
        n_meas = len(known)
        agg["human_turns_per_session_mean"] = (
            measured(round(total / n_meas, 4), src_names)
            if len(known) == len(turn_vals) else inferred(
                round(total / n_meas, 4), src_names,
                "mean over the sessions where human turns were "
                "measurable"))

    if "human_turns_per_session_mean" not in agg:
        agg["human_turns_per_session_mean"] = agg["human_turns_total"]

    # human turns per task — only when task-boundary attrs exist
    all_tasks = sorted({t for s in sessions for t in s["tasks"]})
    if all_tasks and known:
        note = (f"{sum(known)} human turns / {len(all_tasks)} distinct "
                "task ids (workflow.run_id / task.id); task COMPLETION "
                "status is not encoded in the export, so this is per "
                "observed task, not per completed task")
        ratio = round(sum(known) / len(all_tasks), 4)
        if len(known) == len(turn_vals):
            agg["human_turns_per_task"] = measured(ratio, src_names,
                                                   note=note)
        else:
            agg["human_turns_per_task"] = inferred(
                ratio, src_names,
                note + "; human turns were only measurable on "
                f"{len(known)}/{len(turn_vals)} sessions")
    else:
        agg["human_turns_per_task"] = not_measurable(
            "attribute absent — no task-boundary attribute "
            "(workflow.run_id / task.id / gen_ai.task.id) on any record"
            if not all_tasks else
            "human turns not measurable (see human_turns_total), so the "
            "per-task ratio cannot be computed")

    agg["distinct_models"] = measured(
        sorted({m for s in sessions for m in s["models"]}), src_names) \
        if sessions else absent_activity("no parseable records",
                                         baron_records, baron_only)
    # The roster of agents OBSERVED WORKING. A persona that guard merely
    # evaluated is not on it — see partition_guard_records.
    agg["distinct_agent_identities"] = measured(
        sorted({a for s in sessions for a in s["agents"]}), src_names,
        note="from agent.name / agent_id / subagent_type / service.name / "
             "user.email attributes") \
        if sessions else absent_activity("no parseable records",
                                         baron_records, baron_only)

    # Barony observation plane (v1.1) — appended last so every pre-existing
    # key above keeps its position, and computed over the withheld partition
    # so the two planes cannot double count each other.
    agg.update(compute_guard_metrics(baron_records, src_names))

    for s in sessions:
        s.pop("_tok_pairs", None)

    return {
        "telemetry_metrics_version": INGESTER_VERSION,
        "generated": datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"),
        "ingest": {"files": file_reports},
        "sessions": sessions,
        "aggregate": agg,
    }


# --- cli -------------------------------------------------------------------

def main(argv):
    ap = argparse.ArgumentParser(
        description="Ingest OTel trace-export files; emit audit telemetry "
                    "metrics JSON.")
    ap.add_argument("files", nargs="+", type=Path,
                    help="OTLP-JSON or flat JSONL/array export files")
    ap.add_argument("--output", type=Path, default=None,
                    help="write metrics JSON here (default: stdout)")
    ap.add_argument("--session-attr", default=None,
                    help="attribute key to group sessions by (overrides "
                         "the built-in session.id conventions)")
    ap.add_argument("--pretty", action="store_true",
                    help="indent the JSON output")
    args = ap.parse_args(argv[1:])

    all_records = []
    file_reports = []
    for p in args.files:
        if not p.exists():
            print(f"error: input file not found: {p}", file=sys.stderr)
            return 1
        recs, report = load_file(p)
        all_records.extend(recs)
        file_reports.append(report)

    if not all_records:
        print("error: no parseable spans or events in any input file",
              file=sys.stderr)
        for r in file_reports:
            print(f"  {r['path']}: format={r['format']} "
                  f"unparseable={r['unparseable']}", file=sys.stderr)
        return 2

    metrics = compute_metrics(all_records, file_reports, args.session_attr)
    out = json.dumps(metrics, indent=2 if args.pretty else None)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out + "\n")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
