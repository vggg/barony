#!/usr/bin/env python3
"""Guard the published fleet snapshot: shape, honesty, and — above all — leaks.

The coordination repo this snapshot is projected from is PRIVATE. The projection
in `build_data.py` sanitises, but a sanitiser is only as good as its test, and a
regenerated snapshot is committed straight into a public repo. This is the gate
that fails the build rather than letting a leak land.

Run directly (`python3 dashboard/check_snapshot.py`) or via CI. Stdlib only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parent / "data" / "fleet.json"

# Anything matching these must never appear in the published file. Absolute
# local paths leak the machine layout; the collab repo name leaks the private
# surface; a token pattern would be a genuine credential leak.
FORBIDDEN = [
    (r"/Users/", "absolute macOS home path"),
    (r"/home/[a-z]", "absolute Linux home path"),
    (r"/private/(?:tmp|var)/", "absolute private tmp path"),
    (r"\bfleet-coordination\b", "private coordination repo name"),
    (r"\bObsidian\b", "private vault reference"),
    (r"gh[pousr]_[A-Za-z0-9]{16,}", "GitHub token"),
    (r"ghs_[A-Za-z0-9]{16,}", "GitHub token"),
    (r"\bsk-[A-Za-z0-9]{20,}", "API key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
    (r"\.baron/events", "event-plane path"),
]

REQUIRED_TOP = [
    "schema", "generated_at", "generator", "portfolio", "kpis",
    "projects_detail", "agents", "identity", "health", "merge_queue",
    "observer", "owner_actions", "honesty",
]


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


def main() -> int:
    if not SNAPSHOT.exists():
        print(f"FAIL: no snapshot at {SNAPSHOT}. Run dashboard/build-data.sh.")
        return 1

    raw = SNAPSHOT.read_text(encoding="utf-8")
    errors = 0

    print("dashboard snapshot guard")
    print(f"  file: dashboard/data/fleet.json ({len(raw)} bytes)")

    # ---- 1. leaks
    for pattern, label in FORBIDDEN:
        hits = re.findall(pattern, raw)
        if hits:
            fail(f"leak — {label}: {len(hits)} occurrence(s) matching /{pattern}/")
            errors += 1
    if not errors:
        print(f"  ok    no leaks ({len(FORBIDDEN)} patterns checked)")

    # ---- 2. shape
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"not valid JSON: {e}")
        return 1

    missing = [k for k in REQUIRED_TOP if k not in d]
    if missing:
        fail(f"missing top-level keys: {', '.join(missing)}")
        errors += 1
    else:
        print(f"  ok    shape ({len(REQUIRED_TOP)} required keys present)")

    if d.get("schema") != "barony.dashboard/v1":
        fail(f"unexpected schema: {d.get('schema')!r}")
        errors += 1

    # ---- 3. honesty: an unmeasured metric must not render as a number
    for m in d.get("health", {}).get("metrics", []):
        if not m.get("measured"):
            if m.get("value") not in (None, 0):
                fail(f"metric {m.get('key')!r} is unmeasured but carries value {m.get('value')!r}")
                errors += 1
            if not m.get("note"):
                fail(f"metric {m.get('key')!r} is unmeasured but states no caveat")
                errors += 1
        if not m.get("basis"):
            fail(f"metric {m.get('key')!r} has no stated basis")
            errors += 1
    else:
        if not errors:
            print(f"  ok    honesty ({len(d.get('health', {}).get('metrics', []))} metrics carry a basis)")

    # A single verdict must be labelled as such — never presented as a trend.
    verdicts = d.get("kpis", {}).get("verdicts", 0)
    cov = d.get("health", {}).get("coverage", {})
    if verdicts <= 1 and not cov.get("note"):
        fail("verdict coverage is sparse but no coverage note is stated")
        errors += 1

    # ---- 4. freshness: a snapshot read from unrefreshed clones must say so.
    # This is the guard on the failure that produced ~21 phantom reds once
    # already: branches merged and deleted on origin, still red locally.
    fresh = d.get("generator", {}).get("refresh")
    if fresh is None:
        fail("generator.refresh is absent — snapshot predates the fetch-first build")
        errors += 1
    else:
        stale = (not fresh.get("attempted")) or fresh.get("fetch_failures")
        if stale and not fresh.get("note"):
            fail("working copies were not fully refreshed but no caveat is recorded")
            errors += 1
        if stale and not any(
            a.get("kind") == "freshness" for a in d.get("owner_actions", [])
        ):
            fail("refresh was incomplete but no owner action surfaces it")
            errors += 1
        if not errors:
            state = "refreshed" if not stale else "STALE (declared)"
            print(f"  ok    freshness recorded — {state}")

    # ---- 5. inactive capabilities must be labelled, not silently empty
    obs = d.get("observer", {})
    if not obs.get("active") and not obs.get("note"):
        fail("observer is inactive but the snapshot gives no explanation")
        errors += 1
    sign = d.get("identity", {}).get("signing", {})
    if sign.get("state") != "implemented" and not sign.get("note"):
        fail("commit signing is not implemented but the snapshot gives no explanation")
        errors += 1
    if not errors:
        print("  ok    inactive capabilities are labelled")

    print()
    if errors:
        print(f"SNAPSHOT GUARD FAILED — {errors} problem(s). Do not publish.")
        return 1
    print("SNAPSHOT GUARD PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
