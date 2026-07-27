"""Drift guard: the embedded capability vocabulary must match the prose spec."""

from __future__ import annotations

import re

from baron.schemas import CAPABILITY_VERBS, PARAMETRIC_VERBS

from conftest import REPO_ROOT

VOCAB_MD = (
    REPO_ROOT
    / "skills/barony/references/capability-vocab.v1.md"
)

# Verb table rows look like: | `read_code` | Read the code repo | whole-tool | - |
_VERB_ROW_RE = re.compile(r"^\|\s*`([a-z_]+)`\s*\|")


def parse_spec_verbs() -> list[str]:
    verbs: list[str] = []
    in_verbs_section = False
    for line in VOCAB_MD.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_verbs_section = line.strip() == "## The v1 verbs"
            continue
        if in_verbs_section:
            m = _VERB_ROW_RE.match(line)
            if m:
                verbs.append(m.group(1))
    return verbs


def test_embedded_vocabulary_matches_frozen_spec() -> None:
    spec_verbs = parse_spec_verbs()
    assert spec_verbs, f"no verbs parsed from {VOCAB_MD} — spec format changed?"
    assert set(spec_verbs) == set(CAPABILITY_VERBS), (
        "capability vocabulary drift between baron.schemas.CAPABILITY_VERBS and "
        f"{VOCAB_MD}"
    )
    assert len(spec_verbs) == len(CAPABILITY_VERBS) == 10  # v1 is FROZEN at 10 verbs


def test_parametric_verbs_are_in_vocabulary() -> None:
    assert PARAMETRIC_VERBS <= set(CAPABILITY_VERBS)
