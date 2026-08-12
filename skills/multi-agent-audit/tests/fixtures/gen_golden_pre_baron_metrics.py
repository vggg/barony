#!/usr/bin/env python3
"""
gen_golden_pre_baron_metrics.py — PROVENANCE for
`golden_pre_baron_metrics.json`, the additivity lock's baseline.

The golden must be the output of the ingester *as it was before* the v1.1
barony partition, or the lock is circular: regenerating it from the current
script would make any drift self-approving. So this does not import the
working-tree module. It extracts `ingest_otel.py` from a git ref (default
`harden/ops-plane`, the branch v1.1 was cut from), loads that, and asserts the
loaded module reports `INGESTER_VERSION == "1.0"` before writing anything.

    python3 skills/multi-agent-audit/tests/fixtures/\\
        gen_golden_pre_baron_metrics.py [<git-ref>]

Stdlib only, like everything else in this skill.

`ingest.files[].path` is normalised to the BASENAME. The raw value is the
absolute path the ingester was handed, which differs per checkout; committing
it would make the lock fail on every machine but the one that generated it.
`test_additivity_lock` applies the same normalisation before comparing.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[3]
REL = "skills/multi-agent-audit/scripts/ingest_otel.py"
DEST = HERE / "golden_pre_baron_metrics.json"
PRE_V11_FIXTURES = ("otlp_two_sessions.json", "flat_spans.jsonl",
                    "missing_attrs.jsonl")


def load_pre_v11(ref: str):
    proc = subprocess.run(["git", "-C", str(REPO), "show", f"{ref}:{REL}"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"cannot read {REL} at {ref}: {proc.stderr.strip()}",
              file=sys.stderr)
        return None
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "ingest_otel_pre_v11.py"
        path.write_text(proc.stdout)
        spec = importlib.util.spec_from_file_location("ingest_otel_pre_v11",
                                                      path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def main(argv: list[str]) -> int:
    ref = argv[1] if len(argv) > 1 else "harden/ops-plane"
    base = load_pre_v11(ref)
    if base is None:
        return 1
    if base.INGESTER_VERSION != "1.0":
        print(f"{ref} reports INGESTER_VERSION={base.INGESTER_VERSION!r}, not "
              "'1.0' — that ref already has the v1.1 partition, so a golden "
              "built from it would approve its own drift. Pick the ref v1.1 "
              "was cut from.", file=sys.stderr)
        return 1

    out = {}
    for name in PRE_V11_FIXTURES:
        recs, rep = base.load_file(HERE / name)
        metrics = base.compute_metrics(recs, [rep])
        metrics.pop("generated", None)            # wall clock
        metrics.pop("telemetry_metrics_version", None)  # bumped by v1.1
        for entry in metrics["ingest"]["files"]:
            entry["path"] = pathlib.Path(entry["path"]).name
        out[name] = metrics
    DEST.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"wrote {DEST} from ingester {base.INGESTER_VERSION} at {ref}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
