#!/usr/bin/env python3
"""
test_ingest_otel.py — checks for the telemetry-mode scripts
(scripts/ingest_otel.py + scripts/merge_telemetry.py) against the
hand-crafted fixtures in tests/fixtures/.

Covers:
  1. OTLP-JSON ingestion (2 Claude Code sessions: spans + log events,
     span/event dedupe by tool_use_id / request_id, token+cost totals,
     user-prompt counting without double counting interaction spans,
     human-turns-per-task from workflow.run_id).
  2. Flat JSONL ingestion (Logfire-style rows + a Phoenix-style flattened
     row; trace_id session fallback => `inferred` session count).
  3. The honesty rule: absent attributes come back `not measurable` with
     the missing attribute named — never an estimated number; partially
     present attributes come back `inferred` with a coverage note.
  4. merge_telemetry.py: additive merge (git-derived values untouched),
     `otel:<file>` source tags, in-place-overwrite refusal, markdown table.
  5. (v1.1) barony observation-plane rows: the WIRE-SHAPE proof —
     fixtures/baron_events.jsonl is the verbatim output of a real
     `baron guard` run through the DiskSink (see fixtures/gen_baron_events
     .py), and the unmodified loader parses it. Plus the PARTITION: those
     rows fabricate no session, duration, agent or tool call; the
     ADDITIVITY LOCK against a pre-1.1 golden; and the CONTAMINATION LOCK,
     which pairs each pre-1.1 fixture with the baron export and demands
     every activity metric hold still.

Run:  python3 tests/test_ingest_otel.py
Stdlib only. Exit code 0 iff all checks pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
FIXTURES = TESTS_DIR / "fixtures"

sys.path.insert(0, str(SCRIPTS_DIR))
import ingest_otel  # noqa: E402
import merge_telemetry  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        print(f"  ✓ {name}")
        PASS += 1
    else:
        print(f"  ✗ {name}  {detail}")
        FAIL += 1


def ingest(paths: list[Path]) -> dict:
    records, reports = [], []
    for p in paths:
        recs, rep = ingest_otel.load_file(p)
        records.extend(recs)
        reports.append(rep)
    return ingest_otel.compute_metrics(records, reports)


def approx(a, b, tol=1e-6) -> bool:
    return isinstance(a, (int, float)) and abs(a - b) <= tol


OTLP = FIXTURES / "otlp_two_sessions.json"
FLAT = FIXTURES / "flat_spans.jsonl"
MISSING = FIXTURES / "missing_attrs.jsonl"
BARON = FIXTURES / "baron_events.jsonl"
GOLDEN = FIXTURES / "golden_pre_baron_metrics.json"


def test_otlp_fixture():
    print("--- OTLP-JSON fixture (2 Claude Code sessions) ---")
    m = ingest([OTLP])
    rep = m["ingest"]["files"][0]
    check("format detected otlp-json", rep["format"] == "otlp-json",
          f"got {rep['format']}")
    check("8 spans + 7 events parsed",
          rep["spans"] == 8 and rep["events"] == 7,
          f"got spans={rep['spans']} events={rep['events']}")
    check("no unparseable rows", rep["unparseable"] == 0)
    check("logs stream detected", rep["has_logs_stream"] is True)

    agg = m["aggregate"]
    sc = agg["session_count"]
    check("session_count == 2, measured",
          sc["value"] == 2 and sc["confidence"] == "measured", str(sc))

    sessions = {s["session_id"]: s for s in m["sessions"]}
    check("session ids sess-a / sess-b",
          set(sessions) == {"sess-a", "sess-b"}, str(set(sessions)))
    a, b = sessions.get("sess-a", {}), sessions.get("sess-b", {})
    check("sess-a human_turns == 2 (user_prompt events, interaction spans "
          "not double counted)", a.get("human_turns") == 2,
          str(a.get("human_turns")))
    check("sess-b human_turns == 1", b.get("human_turns") == 1)
    check("sess-a tool_calls == 3 (tool_result event deduped by "
          "tool_use_id)", a.get("tool_calls") == 3,
          str(a.get("tool_calls")))
    check("sess-a tool_errors == 1", a.get("tool_errors") == 1)
    check("sess-a llm_calls == 2 (api_request events merged by request_id)",
          a.get("llm_calls") == 2, str(a.get("llm_calls")))
    check("sess-b llm_calls == 1 (event-only LLM call counted)",
          b.get("llm_calls") == 1, str(b.get("llm_calls")))
    check("sess-a input_tokens == 2000", a.get("input_tokens") == 2000,
          str(a.get("input_tokens")))
    check("sess-a cost_usd == 0.02 (cost from api_request events)",
          approx(a.get("cost_usd"), 0.02), str(a.get("cost_usd")))
    check("sess-a duration 300s", approx(a.get("duration_s"), 300.0),
          str(a.get("duration_s")))
    check("sess-b duration 13s", approx(b.get("duration_s"), 13.0),
          str(b.get("duration_s")))
    check("sess-a tasks == [wf_1]", a.get("tasks") == ["wf_1"],
          str(a.get("tasks")))

    check("tool_calls_total == 4 measured",
          agg["tool_calls_total"]["value"] == 4
          and agg["tool_calls_total"]["confidence"] == "measured")
    check("tool_error_rate == 0.25",
          approx(agg["tool_error_rate"]["value"], 0.25),
          str(agg["tool_error_rate"]))
    check("tool_calls_by_name Bash=2 Edit=1 Read=1",
          agg["tool_calls_by_name"]["value"] ==
          {"Bash": 2, "Edit": 1, "Read": 1},
          str(agg["tool_calls_by_name"]["value"]))
    check("llm_calls_total == 3", agg["llm_calls_total"]["value"] == 3)
    check("input_tokens_total == 2500 measured",
          agg["input_tokens_total"]["value"] == 2500
          and agg["input_tokens_total"]["confidence"] == "measured",
          str(agg["input_tokens_total"]))
    check("output_tokens_total == 600 measured",
          agg["output_tokens_total"]["value"] == 600)
    check("cache_read_tokens_total == 6000 measured",
          agg["cache_read_tokens_total"]["value"] == 6000
          and agg["cache_read_tokens_total"]["confidence"] == "measured",
          str(agg["cache_read_tokens_total"]))
    check("cache_creation_tokens_total == 50 (event fills span gap)",
          agg["cache_creation_tokens_total"]["value"] == 50,
          str(agg["cache_creation_tokens_total"]))
    check("cost_usd_total == 0.025 measured (micros + usd attrs combined)",
          approx(agg["cost_usd_total"]["value"], 0.025)
          and agg["cost_usd_total"]["confidence"] == "measured",
          str(agg["cost_usd_total"]))
    check("human_turns_total == 3 measured",
          agg["human_turns_total"]["value"] == 3
          and agg["human_turns_total"]["confidence"] == "measured",
          str(agg["human_turns_total"]))
    check("human_turns_per_session_mean == 1.5",
          approx(agg["human_turns_per_session_mean"]["value"], 1.5))
    hpt = agg["human_turns_per_task"]
    check("human_turns_per_task == 1.5 measured (workflow.run_id present)",
          approx(hpt["value"], 1.5) and hpt["confidence"] == "measured",
          str(hpt))
    check("per-task note admits completion status is not encoded",
          "not per completed task" in (hpt.get("note") or ""))
    check("session_duration_p50_s == 156.5",
          approx(agg["session_duration_p50_s"]["value"], 156.5),
          str(agg["session_duration_p50_s"]))
    check("session_duration_total_s == 313",
          approx(agg["session_duration_total_s"]["value"], 313.0))
    check("distinct_models sorted",
          agg["distinct_models"]["value"] ==
          ["claude-haiku-4-5", "claude-sonnet-4-5"],
          str(agg["distinct_models"]["value"]))
    check("measured metrics carry the source file",
          agg["input_tokens_total"].get("source") ==
          ["otlp_two_sessions.json"],
          str(agg["input_tokens_total"].get("source")))
    return m


def test_flat_fixture():
    print("--- flat JSONL fixture (Logfire/Phoenix style rows) ---")
    m = ingest([FLAT])
    rep = m["ingest"]["files"][0]
    check("format detected jsonl", rep["format"] == "jsonl",
          f"got {rep['format']}")
    agg = m["aggregate"]
    sc = agg["session_count"]
    check("session_count == 1, INFERRED (trace_id fallback, no "
          "session.id)", sc["value"] == 1 and sc["confidence"] == "inferred",
          str(sc))
    s = m["sessions"][0]
    check("identity method is trace_id fallback",
          s["identity_method"] == "trace_id fallback",
          s["identity_method"])
    check("duration 600s from ISO timestamps",
          approx(s["duration_s"], 600.0), str(s["duration_s"]))
    check("human_turns == 1 (gen_ai.user.message event)",
          s["human_turns"] == 1, str(s["human_turns"]))
    check("Phoenix-style flattened row parsed as a tool call "
          "(span_kind=TOOL, attributes.tool.name, context.trace_id)",
          s["tool_calls"] == 1 and
          agg["tool_calls_by_name"]["value"] == {"run_sql": 1},
          f"tool_calls={s['tool_calls']} "
          f"by_name={agg['tool_calls_by_name']['value']}")
    check("status_code ERROR counted as tool error",
          s["tool_errors"] == 1 and
          approx(agg["tool_error_rate"]["value"], 1.0))
    check("gen_ai.usage.* tokens measured (900/250)",
          agg["input_tokens_total"]["value"] == 900
          and agg["output_tokens_total"]["value"] == 250,
          str(agg["input_tokens_total"]))
    cost = agg["cost_usd_total"]
    check("cost NOT MEASURABLE (attribute absent) — never estimated "
          "from tokens", cost["value"] == "not measurable"
          and cost["confidence"] == "not measurable"
          and "attribute absent" in cost["note"], str(cost))
    hpt = agg["human_turns_per_task"]
    check("human_turns_per_task NOT MEASURABLE (no task-boundary attrs)",
          hpt["confidence"] == "not measurable"
          and "task-boundary" in hpt["note"], str(hpt))
    check("agent identity picked up from agent.name",
          agg["distinct_agent_identities"]["value"] == ["researcher"],
          str(agg["distinct_agent_identities"]["value"]))


def test_missing_attrs_fixture():
    print("--- missing-attrs fixture (honesty: not measurable) ---")
    m = ingest([MISSING])
    rep = m["ingest"]["files"][0]
    check("1 unparseable row reported explicitly",
          rep["unparseable"] == 1, str(rep["unparseable"]))
    agg = m["aggregate"]
    tok = agg["input_tokens_total"]
    check("tokens NOT MEASURABLE with missing attrs named",
          tok["value"] == "not measurable"
          and "attribute absent" in tok["note"]
          and "gen_ai.usage.input_tokens" in tok["note"], str(tok))
    check("cost NOT MEASURABLE", agg["cost_usd_total"]["value"] ==
          "not measurable")
    ht = agg["human_turns_total"]
    check("human turns NOT MEASURABLE (no markers, no logs stream — "
          "not a claimed zero)", ht["value"] == "not measurable"
          and "logs" in ht["note"], str(ht))
    check("tool_calls_total == 1 measured (unset status = ok per OTLP)",
          agg["tool_calls_total"]["value"] == 1
          and agg["tool_errors_total"]["value"] == 0,
          str(agg["tool_calls_total"]))
    check("llm_calls_total == 1 (call counted even though tokens absent)",
          agg["llm_calls_total"]["value"] == 1)


def test_combined():
    print("--- combined multi-file ingest (mixed coverage => inferred) ---")
    m = ingest([OTLP, FLAT, MISSING])
    agg = m["aggregate"]
    sc = agg["session_count"]
    check("session_count == 4, inferred (2/4 trace-fallback)",
          sc["value"] == 4 and sc["confidence"] == "inferred", str(sc))
    tok = agg["input_tokens_total"]
    check("input tokens 3400 INFERRED with 4/5 coverage note",
          tok["value"] == 3400 and tok["confidence"] == "inferred"
          and "4/5" in tok["note"], str(tok))
    ht = agg["human_turns_total"]
    check("human turns 4 INFERRED (3/4 sessions measurable)",
          ht["value"] == 4 and ht["confidence"] == "inferred"
          and "3/4" in ht["note"], str(ht))
    hpt = agg["human_turns_per_task"]
    check("human_turns_per_task downgraded to inferred under partial "
          "coverage", hpt["confidence"] == "inferred", str(hpt))


def test_cli():
    print("--- ingest_otel.py CLI ---")
    r = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "ingest_otel.py"), str(OTLP),
         "--pretty"], capture_output=True, text=True)
    check("exit 0 on valid input", r.returncode == 0, r.stderr[:200])
    try:
        out = json.loads(r.stdout)
        ok = out["aggregate"]["session_count"]["value"] == 2
    except (json.JSONDecodeError, KeyError):
        ok = False
    check("stdout is valid metrics JSON", ok)

    with tempfile.TemporaryDirectory() as td:
        garbage = Path(td) / "garbage.txt"
        garbage.write_text("csv,not,otel\n1,2,3\n")
        r2 = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "ingest_otel.py"),
             str(garbage)], capture_output=True, text=True)
        check("exit 2 when nothing parseable", r2.returncode == 2,
              f"rc={r2.returncode}")


def test_merge():
    print("--- merge_telemetry.py ---")
    telemetry = ingest([OTLP])
    snapshot = {
        "schema_version": "1.1",
        "audit_run": {"timestamp": "2026-07-23T00:00:00Z",
                      "project_name": "fixture"},
        "metrics": {
            "autonomy": {
                "intervention_tax": {"value": 0.62,
                                     "confidence": "inferred",
                                     "note": "git-derived fix-up proxy"},
            },
        },
    }
    merged = merge_telemetry.merge(snapshot, telemetry)

    tele = merged["metrics"]["telemetry"]
    check("metrics.telemetry block present with expected keys",
          "human_turns_per_task" in tele and "cost_usd_total" in tele,
          str(sorted(tele)))
    check("telemetry entries carry an otel:<file> source tag",
          tele["human_turns_per_task"].get("source") ==
          "otel:otlp_two_sessions.json",
          str(tele["human_turns_per_task"].get("source")))
    it = merged["metrics"]["autonomy"]["intervention_tax"]
    check("git-derived intervention_tax UNTOUCHED (additive merge)",
          it == snapshot["metrics"]["autonomy"]["intervention_tax"],
          str(it))
    promo = merged["metrics"]["autonomy"].get("human_turns_per_task_otel")
    check("intervention-tax input promoted as *_otel key, measured 1.5",
          promo is not None and approx(promo.get("value"), 1.5)
          and promo.get("confidence") == "measured", str(promo))
    check("dual-lens reminder recorded in telemetry_provenance",
          "INTENDED" in merged["telemetry_provenance"]["note"])

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        snap_p = td / "snapshot.json"
        tel_p = td / "telemetry.json"
        out_p = td / "merged.json"
        snap_p.write_text(json.dumps(snapshot))
        tel_p.write_text(json.dumps(telemetry))

        r = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "merge_telemetry.py"),
             "--snapshot", str(snap_p), "--telemetry", str(tel_p),
             "--output", str(out_p), "--markdown"],
            capture_output=True, text=True)
        check("CLI exit 0 and merged file written",
              r.returncode == 0 and out_p.exists(), r.stderr[:200])
        check("markdown table has a Source column",
              "| Metric | Value | Confidence | Source |" in r.stdout
              and "otel:" in r.stdout, r.stdout[:200])

        r2 = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "merge_telemetry.py"),
             "--snapshot", str(snap_p), "--telemetry", str(tel_p),
             "--output", str(snap_p)], capture_output=True, text=True)
        check("refuses to overwrite the snapshot in place (frozen rule)",
              r2.returncode == 1 and "frozen" in r2.stderr,
              f"rc={r2.returncode}")


def test_baron_wire_shape():
    """UNIT 1 — the loader must parse baron's own stream with ZERO changes.

    baron_events.jsonl is NOT hand-written: fixtures/gen_baron_events.py
    drives the real `baron guard` CLI with BARON_EVENTS_SINK=disk and copies
    what the sink wrote. If this fails, the wire shape in baron's events.py is
    wrong and must be fixed THERE — patching the ingester to accept a bad
    shape would defeat the purpose of the check.
    """
    print("--- barony observation plane: wire shape (v1.1) ---")
    records, rep = ingest_otel.load_file(BARON)
    check("format detected jsonl", rep["format"] == "jsonl", str(rep["format"]))
    check("every row parsed (no unparseable)", rep["unparseable"] == 0
          and rep["spans"] == 11 and rep["events"] == 0, str(rep))

    r = records[0]
    check("name == the emitted kind (guard.decision)",
          r["name"] == "guard.decision", r["name"])
    check("trace_id carried through", isinstance(r["trace_id"], str)
          and len(r["trace_id"]) == 32, str(r["trace_id"]))
    check("start parses to a datetime",
          isinstance(r["start"], float)
          and ingest_otel.iso(r["start"]).startswith("20"),
          str(r["start"]))
    check("end parses and is >= start",
          isinstance(r["end"], float) and r["end"] >= r["start"],
          f"{r['start']} -> {r['end']}")
    check("attrs carry agent.name, session.id and baron.outcome",
          {"agent.name", "session.id", "baron.outcome"} <= set(r["attrs"]),
          str(sorted(r["attrs"])))
    check("rows are classified as spans, not events",
          all(x["kind"] == "span" for x in records))

    # The join keys that make the partition NECESSARY. If a future wire shape
    # drops them the partition is still correct, but this test should be the
    # thing that notices the producer changed.
    check("every row carries session.id — which is why leaving them in "
          "fabricates a session",
          all("session.id" in x["attrs"] for x in records))
    check("guard rows carry tool.name, so the UNPARTITIONED ingester counts "
          "them as tool calls",
          any(ingest_otel.is_tool_record(x) for x in records))
    check("no row is an LLM call or a human turn",
          not any(ingest_otel.is_llm_record(x)
                  or ingest_otel.is_human_turn_event(x) for x in records))

    kinds = {x["name"] for x in records}
    check("the fixture covers adjudication AND evidence kinds — both reach "
          "the ingester through the same file",
          {"guard.decision", "guard.override"} <= kinds
          and {"tool.post", "session.start"} <= kinds, str(sorted(kinds)))
    check("every row is recognised as barony observation-plane evidence",
          all(ingest_otel.is_baron_observation_record(x) for x in records))
    check("only the adjudication kinds are decisions",
          sum(ingest_otel.is_baron_decision_record(x) for x in records) == 9,
          str(sum(ingest_otel.is_baron_decision_record(x) for x in records)))


def test_baron_rows_are_not_agent_activity():
    """A baron-only export must fabricate NO session, duration, agent or tool.

    Measured on this fixture with the partition removed, all labelled
    `measured`: session_count 1, session_duration_total_s 0.91 (the hook
    processes' own wall-clock), distinct_agent_identities
    ["analyst", "pilot", "unknown"], tool_calls_total 11 with a tool named
    `session.start`. None of those are facts about agents working.
    `session.id`, `agent.name` and `tool.name` are correct to EMIT — they are
    join keys — but the consumer must not read a hook's evaluation as the
    activity it evaluated. ADR-018.
    """
    print("--- barony observation plane: not agent activity (v1.1) ---")
    records, rep = ingest_otel.load_file(BARON)
    activity, baron = ingest_otel.partition_guard_records(records)
    check("every row in the fixture partitions as baron evidence",
          len(baron) == 11 and activity == [], str(len(activity)))

    m = ingest_otel.compute_metrics(records, [rep])
    agg = m["aggregate"]
    check("NO session is fabricated from baron rows",
          m["sessions"] == [], str(m["sessions"]))
    for key in ("session_count", "session_duration_total_s",
                "session_duration_p50_s", "distinct_agent_identities",
                "distinct_models", "llm_calls_total", "tool_calls_total",
                "tool_calls_by_name", "human_turns_total"):
        check(f"{key}: not measurable from baron evidence alone",
              agg[key]["confidence"] == "not measurable",
              f"{key} = {agg[key]}")
    note = agg["session_count"].get("note") or ""
    check("the absence note says WHY, and does not claim the file was "
          "unparseable",
          "observation-plane" in note and "guard_decisions" in note, note)

    # The evidence is excluded, not discarded.
    check("the baron rows are still counted on their own axis, all 11 of them",
          agg["baron_events_by_kind"]["confidence"] == "measured"
          and sum(agg["baron_events_by_kind"]["value"].values()) == 11,
          str(agg["baron_events_by_kind"]["value"]))


def test_baron_guard_metrics():
    """UNIT 2 — guard_decisions / baron_events_by_kind, both measured."""
    print("--- barony observation plane: counts (v1.1) ---")
    check("INGESTER_VERSION bumped to 1.1",
          ingest_otel.INGESTER_VERSION == "1.1",
          ingest_otel.INGESTER_VERSION)

    m = ingest([BARON])
    agg = m["aggregate"]
    gd = agg["guard_decisions"]
    check("guard_decisions counts match the generated scenarios "
          "(4 allow, 3 deny, 1 override, 1 error)",
          gd["value"] == {"allow": 4, "deny": 3, "error": 1, "ok": 0,
                          "override": 1}, str(gd["value"]))
    check("guard_decisions is MEASURED (a direct count, never inferred)",
          gd["confidence"] == "measured", str(gd["confidence"]))
    check("guard_decisions carries the source file",
          gd.get("source") == ["baron_events.jsonl"], str(gd.get("source")))
    check("note keeps deny and error separate",
          "fail-closed" in (gd.get("note") or ""), str(gd.get("note")))
    check("note refuses to invite a fidelity reading",
          "not a fidelity score" in (gd.get("note") or ""),
          str(gd.get("note")))
    check("the evidence kinds are NOT counted as decisions — a PostToolUse "
          "observation adjudicated nothing",
          sum(gd["value"].values()) == 9, str(gd["value"]))

    bk = agg["baron_events_by_kind"]
    check("baron_events_by_kind accounts for every partitioned row",
          bk["value"] == {"guard.decision": 8, "guard.override": 1,
                          "session.start": 1, "tool.post": 1},
          str(bk["value"]))

    # NOT SHIPPED, on purpose: an aggregate over `baron.enforcement`. The
    # merged producer derives it from the rules artifact's static `detection`
    # field, which DECISIONS-FOR-REVIEW D1 measured mislabelling in both
    # directions. This fixture contains both mislabelled rows, so the day the
    # producer is corrected these assertions flip and this test is the place
    # that says why. ADR-018 §5.
    raw = [json.loads(x) for x in BARON.read_text().splitlines()]
    escape = [x for x in raw
              if x["attributes"].get("baron.capability.verb") == "write_path"]
    check("today: a STRUCTURAL refusal (path escapes the repo root) is "
          "labelled `enforced` though no capability adjudicated it — the "
          "over-count in D1",
          len(escape) == 1
          and escape[0]["attributes"]["baron.enforcement"] == "enforced",
          str([x["attributes"].get("baron.enforcement") for x in escape]))
    check("no aggregate is published over baron.enforcement while that is "
          "true",
          "guard_enforcement_class" not in agg, str(sorted(agg)))

    # Honesty: absent => not measurable, with the attribute named.
    m2 = ingest([FLAT])
    gd2 = m2["aggregate"]["guard_decisions"]
    check("no baron rows => NOT MEASURABLE with the attribute named",
          gd2["value"] == "not measurable"
          and "baron.outcome" in gd2["note"], str(gd2))

    # merge_telemetry must actually surface them (TELEMETRY_KEYS is an
    # allowlist, not a passthrough — a new key is invisible until listed).
    merged = merge_telemetry.merge({"metrics": {}}, m)
    tele = merged["metrics"]["telemetry"]
    check("merge_telemetry folds the guard metrics under metrics.telemetry.*",
          tele.get("guard_decisions", {}).get("value") == gd["value"]
          and tele.get("baron_events_by_kind", {}).get("value") == bk["value"],
          str(sorted(tele)))
    check("folded entry is source-tagged otel:<file>",
          tele["guard_decisions"].get("source") == "otel:baron_events.jsonl",
          str(tele["guard_decisions"].get("source")))
    md = merge_telemetry.render_markdown(m, merged)
    check("guard rows render in the markdown table",
          "`guard_decisions`" in md and "allow=4" in md, md[:300])


PRE_V11_FIXTURES = ("otlp_two_sessions.json", "flat_spans.jsonl",
                    "missing_attrs.jsonl")
NEW_AGG_KEYS = {"guard_decisions", "baron_events_by_kind"}


def test_additivity_lock():
    """The v1.1 change must be STRICTLY additive to the pre-1.1 fixtures.

    golden_pre_baron_metrics.json was generated from ingest_otel.py BEFORE
    this change. Every pre-existing key must still serialise byte-identically;
    only the two new aggregate keys may appear.

    BOUND, stated so it is not over-read: this half of the lock only exercises
    exports CONTAINING NO BARON ROWS, so it can never catch contamination —
    which is the whole defect. `test_no_contamination_from_paired_export`
    below is the half that can.
    """
    print("--- additivity lock (pre-1.1 fixtures unchanged) ---")
    golden = json.loads(GOLDEN.read_text())
    for name in PRE_V11_FIXTURES:
        recs, rep = ingest_otel.load_file(FIXTURES / name)
        m = ingest_otel.compute_metrics(recs, [rep])
        m.pop("generated", None)
        m.pop("telemetry_metrics_version", None)
        # The golden stores basenames: the raw value is this checkout's
        # absolute path (see gen_golden_pre_baron_metrics.py).
        for entry in m["ingest"]["files"]:
            entry["path"] = Path(entry["path"]).name
        added = set(m["aggregate"]) - set(golden[name]["aggregate"])
        check(f"{name}: only the two new aggregate keys added",
              added == NEW_AGG_KEYS, str(sorted(added)))
        for k in NEW_AGG_KEYS:
            m["aggregate"].pop(k, None)
        before = json.dumps(golden[name], indent=2, sort_keys=True)
        after = json.dumps(m, indent=2, sort_keys=True)
        check(f"{name}: pre-existing output byte-identical", before == after,
              "output drifted — this change is no longer additive")


def test_no_contamination_from_paired_export():
    """Adding a baron export ALONGSIDE a real one must move no activity metric.

    This is the lock that can actually fail. It pairs each pre-1.1 fixture
    with `baron_events.jsonl` and compares against that fixture ingested
    alone. A fixture with no baron rows cannot exhibit the failure, so the
    additivity lock above proves nothing about it.

    Verified to fail by reverting the fix — a test that cannot fail is not
    evidence. With `partition_guard_records` made a no-op, THIS test fails 34
    checks: 10 on flat_spans.jsonl (the per-session breakdown plus 9 activity
    metrics), 11 on otlp_two_sessions.json, 7 on missing_attrs.jsonl, and all
    6 of the named checks below. ADR-018 §4 records the before/after values.

    `source` is the one field allowed to move, and only by gaining the baron
    filename: it lists the files INGESTED, not the records that contributed.
    That is a pre-existing coarseness of the ingester (provenance is
    file-level, not record-level), not something v1.1 introduced — so the test
    pins the exact permitted delta rather than ignoring the field.
    """
    print("--- no contamination when a baron export is paired in ---")
    baron_recs, baron_rep = ingest_otel.load_file(BARON)
    for name in PRE_V11_FIXTURES:
        recs, rep = ingest_otel.load_file(FIXTURES / name)
        alone = ingest_otel.compute_metrics(recs, [rep])
        paired = ingest_otel.compute_metrics(recs + baron_recs,
                                             [rep, baron_rep])
        check(f"{name}: the per-session breakdown is byte-identical",
              json.dumps(alone["sessions"], sort_keys=True)
              == json.dumps(paired["sessions"], sort_keys=True),
              "a baron row joined, split or extended a session")
        for key in alone["aggregate"]:
            if key in NEW_AGG_KEYS:
                continue
            a = dict(alone["aggregate"][key])
            b = dict(paired["aggregate"][key])
            a_src, b_src = a.pop("source", None), b.pop("source", None)
            check(f"{name}/{key}: value, confidence and note unchanged",
                  json.dumps(a, sort_keys=True)
                  == json.dumps(b, sort_keys=True),
                  f"alone={a} paired={b}")
            expect_src = (sorted(set(a_src) | {BARON.name})
                          if a_src is not None else None)
            check(f"{name}/{key}: source grew by the baron file and nothing "
                  "else", b_src == expect_src, f"{a_src} -> {b_src}")

    # The values an unpartitioned ingester actually got wrong, named so a
    # regression is legible rather than a diff of two JSON blobs.
    flat, flat_rep = ingest_otel.load_file(FLAT)
    paired = ingest_otel.compute_metrics(flat + baron_recs,
                                         [flat_rep, baron_rep])
    agg = paired["aggregate"]
    check("session_count stays 1 (unpartitioned: 2 — a session that never "
          "happened)",
          agg["session_count"]["value"] == 1, str(agg["session_count"]))
    check("session_duration_p50_s stays 600.0 (unpartitioned: 300.455 — "
          "halved by the hook processes' own wall-clock)",
          agg["session_duration_p50_s"]["value"] == 600.0,
          str(agg["session_duration_p50_s"]))
    check("tool_calls_total stays 1 (unpartitioned: 12 — guard EVALUATING a "
          "call is not the call)",
          agg["tool_calls_total"]["value"] == 1,
          str(agg["tool_calls_total"]))
    check("tool_calls_by_name gains no tool named `session.start`",
          agg["tool_calls_by_name"]["value"] == {"run_sql": 1},
          str(agg["tool_calls_by_name"]["value"]))
    check("distinct_agent_identities stays ['researcher'] (unpartitioned "
          "added 'analyst', 'pilot' and a literal 'unknown' — personas guard "
          "EVALUATED, not agents observed working)",
          agg["distinct_agent_identities"]["value"] == ["researcher"],
          str(agg["distinct_agent_identities"]["value"]))
    check("human_turns_total stays MEASURED (unpartitioned downgraded it to "
          "`inferred`: the fabricated session had no user-prompt events)",
          agg["human_turns_total"]["confidence"] == "measured",
          str(agg["human_turns_total"]))


def main() -> int:
    print("=== multi-agent-audit telemetry-mode tests ===")
    for p in (OTLP, FLAT, MISSING, BARON, GOLDEN):
        if not p.exists():
            print(f"fixture missing: {p}", file=sys.stderr)
            return 1
    test_otlp_fixture()
    test_flat_fixture()
    test_missing_attrs_fixture()
    test_combined()
    test_cli()
    test_merge()
    test_baron_wire_shape()
    test_baron_rows_are_not_agent_activity()
    test_baron_guard_metrics()
    test_additivity_lock()
    test_no_contamination_from_paired_export()
    print(f"\n=== Summary: {PASS} pass, {FAIL} fail ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
