"""Drift guard: the embedded capability vocabulary must match the prose spec."""

from __future__ import annotations

import re

from baron.schemas import CAPABILITY_VERBS, PARAMETRIC_VERBS, RITUAL_TOKENS

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


def test_every_ritual_token_renders_on_every_runtime() -> None:
    """A ritual token with no prose on some runtime silently disappears there.

    Both renderers fall back to echoing the raw token, so a missing entry is not a
    crash — it is the rule quietly vanishing from that runtime's persona body. This
    is the gap that shipped `check_review_feedback` to three runtimes and not the
    fourth; the vocabulary is the contract, so every renderer must cover it.

    SCOPE — this guards the two CODE renderers only. The claude / code-puppy /
    generic adapters render ritual tokens from prose tables in their HYDRATE.md and
    NOTHING parses those, so a new token can still miss all three silently. See
    ADR-008 §2 and docs/BACKLOG.md; do not read a green run here as full coverage."""
    from baron.runtimes.pydantic_ai import _RITUAL_LINES
    from baron.scaffold import Persona, _ritual_lines

    missing = sorted(set(RITUAL_TOKENS) - set(_RITUAL_LINES))
    assert not missing, f"pydantic-ai hydrator renders no prose for: {missing}"

    persona = Persona(archetype="dev", slug="carson")
    echoed = [
        tok
        for tok in RITUAL_TOKENS
        if _ritual_lines([tok], persona, ".") == [tok]
    ]
    assert not echoed, f"baron init runtime kits render no prose for: {echoed}"
