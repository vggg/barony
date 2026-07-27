#!/usr/bin/env python3
"""Vendor the canonical collab-repo templates into baron's package data.

Single source of truth (ADR-006): the emit-time templates live in the SKILL —
``skills/barony/assets/collab-repo/`` plus the four canon reference files in
``skills/barony/references/`` — because the Claude plugin reads them in place.
A pip-installed baron has no repo checkout, so ``baron init`` reads a VENDORED
copy shipped as package data:

    skills/barony/assets/collab-repo/**  ->  cli/src/baron/data/templates/collab-repo/**
    skills/barony/references/<canon 4>   ->  cli/src/baron/data/templates/references/

Drift guard: ``cli/tests/test_template_sync.py`` fails whenever the vendored
copy differs from the canonical source. Fix = run this script and commit:

    python cli/scripts/sync_templates.py

Stdlib only; paths resolve from this file, so it runs from anywhere.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "barony"
DEST = REPO_ROOT / "cli" / "src" / "baron" / "data" / "templates"

#: The canon reference files ORCHESTRATE.md §2a installs into every project.
CANON_REFERENCES = (
    "capability-vocab.v1.md",
    "capability-rules.md",
    "persona.schema.md",
    "manifest.schema.md",
)


def sync() -> int:
    source = SKILL / "assets" / "collab-repo"
    if not source.is_dir():
        print(f"error: canonical template tree not found: {source}", file=sys.stderr)
        return 1
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(source, DEST / "collab-repo")
    refs_dest = DEST / "references"
    refs_dest.mkdir(parents=True)
    for name in CANON_REFERENCES:
        ref = SKILL / "references" / name
        if not ref.is_file():
            print(f"error: canon reference missing: {ref}", file=sys.stderr)
            return 1
        shutil.copy2(ref, refs_dest / name)
    count = sum(1 for p in DEST.rglob("*") if p.is_file())
    print(f"vendored {count} template file(s) into {DEST.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(sync())
