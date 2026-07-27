"""Drift guard for the vendored templates (ADR-006).

The canonical emit-time templates live in the skill
(``skills/barony/assets/collab-repo/`` + the four canon references in
``skills/barony/references/``); ``baron init`` reads the VENDORED copy under
``cli/src/baron/data/templates/`` so a pip-installed baron needs no repo
checkout. The two trees must stay byte-identical — when this file fails, run

    python cli/scripts/sync_templates.py

and commit the result.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baron.scaffold import ARCHETYPE_TEMPLATES, CANON_REFERENCES
from baron.templates import read_template

from conftest import REPO_ROOT

CANONICAL = REPO_ROOT / "skills" / "barony" / "assets" / "collab-repo"
REFERENCES = REPO_ROOT / "skills" / "barony" / "references"
VENDORED = REPO_ROOT / "cli" / "src" / "baron" / "data" / "templates"

RESYNC = "vendored templates drifted — run `python cli/scripts/sync_templates.py` and commit"

pytestmark = pytest.mark.skipif(
    not CANONICAL.is_dir(), reason="canonical skill tree absent (installed wheel?)"
)


def _tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_collab_repo_tree_byte_identical() -> None:
    canonical = _tree(CANONICAL)
    vendored = _tree(VENDORED / "collab-repo")
    missing = sorted(set(canonical) - set(vendored))
    extra = sorted(set(vendored) - set(canonical))
    assert not missing and not extra, f"{RESYNC}\nmissing={missing}\nextra={extra}"
    differing = [rel for rel, blob in canonical.items() if vendored[rel] != blob]
    assert not differing, f"{RESYNC}\ndiffering={sorted(differing)}"


def test_canon_references_byte_identical() -> None:
    for name in CANON_REFERENCES:
        canonical = (REFERENCES / name).read_bytes()
        vendored = (VENDORED / "references" / name).read_bytes()
        assert canonical == vendored, f"{RESYNC}\ndiffering=references/{name}"
    extra = sorted(
        p.name for p in (VENDORED / "references").iterdir() if p.name not in CANON_REFERENCES
    )
    assert not extra, f"{RESYNC}\nextra references vendored: {extra}"


def test_every_archetype_template_is_packaged() -> None:
    for archetype, rel in sorted(ARCHETYPE_TEMPLATES.items()):
        text = read_template(rel)
        assert "capabilities" in text, f"{archetype}: {rel} is not a persona template"
