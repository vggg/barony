"""Drift guard: the embedded capability vocabulary must match the prose spec."""

from __future__ import annotations

import re

from baron.schemas import CAPABILITY_VERBS, PARAMETRIC_VERBS, RITUAL_TOKENS

from conftest import REPO_ROOT

VOCAB_MD = (
    REPO_ROOT
    / "skills/barony/references/capability-vocab.v1.md"
)
PERSONA_SCHEMA_MD = REPO_ROOT / "skills/barony/references/persona.schema.md"

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


def parse_spec_ritual_tokens() -> list[str]:
    """Ritual tokens from persona.schema.md's session-ritual table."""
    tokens: list[str] = []
    in_section = False
    for line in PERSONA_SCHEMA_MD.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_section = line.strip().startswith("## Session-ritual tokens")
            continue
        if in_section:
            m = _VERB_ROW_RE.match(line)
            if m:
                tokens.append(m.group(1))
    return tokens


def test_ritual_tokens_match_the_canon() -> None:
    """THE JOIN between baron's constant and the canon — without it the two ends
    of the ritual contract are never compared.

    tests/bi_runtime_accept.py checks the ADAPTERS against the canon table, and
    test_every_ritual_token_renders_on_every_runtime checks the CODE RENDERERS
    against RITUAL_TOKENS. Those two meet only if RITUAL_TOKENS and the canon
    table are themselves equal — and until this test existed they were not
    compared anywhere. Adding a token to RITUAL_TOKENS plus both code renderers,
    without touching the canon, left all three prose adapters uncovered with every
    suite green. Caught in review of the change that claimed the gap was closed.
    """
    spec_tokens = parse_spec_ritual_tokens()
    assert spec_tokens, f"no ritual tokens parsed from {PERSONA_SCHEMA_MD} — format changed?"
    assert set(spec_tokens) == set(RITUAL_TOKENS), (
        "ritual-token drift between baron.schemas.RITUAL_TOKENS and "
        f"{PERSONA_SCHEMA_MD} — the adapters are gated against the CANON, so a token "
        "that exists only in baron reaches no prose adapter and nothing complains"
    )


def test_every_ritual_token_renders_on_every_runtime() -> None:
    """A ritual token with no prose on some runtime silently disappears there.

    Both code renderers fall back to echoing the raw token, so a missing entry is
    not a crash — it is the rule quietly vanishing from that runtime's persona body. This
    is the gap that shipped `check_review_feedback` to three runtimes and not the
    fourth; the vocabulary is the contract, so every renderer must cover it.

    SCOPE — this guards the two CODE renderers. The three prose adapters are
    guarded separately by tests/bi_runtime_accept.py check (d), and the two halves
    are joined by test_ritual_tokens_match_the_canon below: without that join,
    RITUAL_TOKENS and the canon could diverge and each suite would still pass."""
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
