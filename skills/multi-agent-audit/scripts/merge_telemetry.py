#!/usr/bin/env python3
"""
merge_telemetry.py — Fold ingest_otel.py telemetry metrics into a
multi-agent-audit snapshot so the report can cite MEASURED telemetry
values alongside git-derived ones, with a source tag distinguishing them.

Design choice (smaller diff than extending render_report.py): this script
writes a NEW merged snapshot; render_report.py needs no changes —
- unknown snapshot fields are ignored by the renderer and trend reader
  (schema is permissive by design, see references/confidence-and-trends.md);
- every metric this script adds lives under `metrics.telemetry.*` (plus a
  few clearly-suffixed `metrics.autonomy.*_otel` keys), shaped exactly like
  existing metric entries ({"value", "confidence", "note", "source"}), so
  the renderer's caveats section automatically surfaces any
  `not measurable` telemetry rows.

Honesty rules enforced here:
- NEVER overwrites a git-derived value. Telemetry values are ADDED under
  new keys; the git-derived `metrics.autonomy.intervention_tax` (usually
  `inferred`) is left untouched. The auditor cites both, labeled by source.
- Refuses to write in place — shipped snapshots are frozen (only the
  `addenda:` field of a shipped snapshot may ever be edited, and not by
  this script). Output must be a different path.
- Source tags: every added entry carries `"source": "otel:<file>[;<file>]"`.
  Git-derived entries carry no such tag (or their own command provenance),
  which is the report's source column distinction.

Usage:
  python3 merge_telemetry.py --snapshot <snapshot.json> \
      --telemetry <telemetry-metrics.json> --output <merged.json> \
      [--markdown]

  --markdown additionally prints a ready-to-paste "Telemetry-derived
  metrics" markdown table (with a Source column) to stdout.

Read-only on inputs. Writes only --output. Stdlib only; Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Aggregate keys from ingest_otel.py copied under metrics.telemetry.*
TELEMETRY_KEYS = [
    "session_count",
    "session_duration_total_s",
    "session_duration_p50_s",
    "tool_calls_total",
    "tool_errors_total",
    "tool_error_rate",
    "tool_calls_by_name",
    "llm_calls_total",
    "input_tokens_total",
    "output_tokens_total",
    "cache_read_tokens_total",
    "cache_creation_tokens_total",
    "cost_usd_total",
    "human_turns_total",
    "human_turns_per_session_mean",
    "human_turns_per_task",
    "distinct_models",
    "distinct_agent_identities",
    # v1.1 — barony observation-plane evidence (ADR-013 rows, ADR-021
    # partitioning). This list is an explicit ALLOWLIST, not a passthrough: a
    # new ingester aggregate key is invisible to the report until named here.
    "guard_decisions",
    "baron_events_by_kind",
]

# Intervention-tax INPUTS promoted (added, never replacing) into
# metrics.autonomy under clearly-suffixed keys.
AUTONOMY_PROMOTIONS = [
    ("human_turns_per_session_mean", "human_turns_per_session_otel"),
    ("human_turns_per_task", "human_turns_per_task_otel"),
]


def source_tag(telemetry: dict) -> str:
    files = [Path(f.get("path", "?")).name
             for f in (telemetry.get("ingest") or {}).get("files") or []]
    return "otel:" + ";".join(files) if files else "otel:?"


def tag_entry(entry: dict, tag: str) -> dict:
    out = dict(entry)
    out["source"] = tag  # normalize ingest's list-form source to one tag
    return out


def merge(snapshot: dict, telemetry: dict) -> dict:
    merged = json.loads(json.dumps(snapshot))  # deep copy; inputs untouched
    tag = source_tag(telemetry)
    agg = telemetry.get("aggregate") or {}

    metrics = merged.setdefault("metrics", {})
    tele_block = {}
    for key in TELEMETRY_KEYS:
        if key in agg:
            tele_block[key] = tag_entry(agg[key], tag)
    metrics["telemetry"] = tele_block

    autonomy = metrics.setdefault("autonomy", {})
    for src_key, dst_key in AUTONOMY_PROMOTIONS:
        entry = agg.get(src_key)
        if not entry:
            continue
        if dst_key in autonomy:
            print(f"warning: {dst_key} already present in snapshot; "
                  "left untouched (telemetry copy remains under "
                  "metrics.telemetry)", file=sys.stderr)
            continue
        autonomy[dst_key] = tag_entry(entry, tag)

    merged["telemetry_provenance"] = {
        "ingester_version": telemetry.get("telemetry_metrics_version"),
        "generated": telemetry.get("generated"),
        "source_files": (telemetry.get("ingest") or {}).get("files"),
        "session_count": len(telemetry.get("sessions") or []),
        "note": ("Telemetry values are ADDITIVE. Git-derived metrics are "
                 "never overwritten; where both exist the report cites "
                 "both with their source tags. Traces show ACTUAL "
                 "behavior only — the INTENDED lens still comes from the "
                 "project's declared docs (dual-lens rule)."),
    }
    return merged


def fmt_value(v):
    if isinstance(v, dict):
        return "; ".join(f"{k}={val}" for k, val in v.items()) or "(none)"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) or "(none)"
    if isinstance(v, float):
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return s if s else "0"
    return str(v)


def render_markdown(telemetry: dict, merged: dict) -> str:
    tag = source_tag(telemetry)
    lines = [
        "### Telemetry-derived metrics (OTel export)",
        "",
        f"Source: `{tag}` — file-based OTel export ingested by "
        "`ingest_otel.py` (no live endpoints queried).",
        "",
        "| Metric | Value | Confidence | Source |",
        "|---|---|---|---|",
    ]
    tele = (merged.get("metrics") or {}).get("telemetry") or {}
    for key in TELEMETRY_KEYS:
        entry = tele.get(key)
        if not entry:
            continue
        conf = entry.get("confidence", "?")
        note = entry.get("note")
        val = fmt_value(entry.get("value"))
        if note and conf != "measured":
            val = f"{val} — {note}"
        elif conf == "not measurable" and note:
            val = note
        lines.append(f"| `{key}` | {val} | {conf} | {tag} |")
    lines += [
        "",
        "_Git-derived rows elsewhere in this report keep their own "
        "provenance; the `otel:` tag marks values measured from the "
        "trace export. Telemetry shows ACTUAL behavior only — INTENDED "
        "still comes from the declared docs._",
    ]
    return "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser(
        description="Merge ingest_otel.py metrics into an audit snapshot.")
    ap.add_argument("--snapshot", required=True, type=Path)
    ap.add_argument("--telemetry", required=True, type=Path,
                    help="metrics JSON produced by ingest_otel.py")
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--markdown", action="store_true",
                    help="also print a ready-to-paste markdown table")
    args = ap.parse_args(argv[1:])

    for p in (args.snapshot, args.telemetry):
        if not p.exists():
            print(f"error: input not found: {p}", file=sys.stderr)
            return 1
    if args.output.resolve() == args.snapshot.resolve():
        print("error: refusing to overwrite the snapshot in place — "
              "shipped snapshots are frozen; write the merged snapshot "
              "to a new path", file=sys.stderr)
        return 1

    try:
        snapshot = json.loads(args.snapshot.read_text())
        telemetry = json.loads(args.telemetry.read_text())
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON input — {e}", file=sys.stderr)
        return 1

    merged = merge(snapshot, telemetry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(merged, indent=2) + "\n")
    print(f"wrote {args.output}", file=sys.stderr)

    if args.markdown:
        print(render_markdown(telemetry, merged))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
