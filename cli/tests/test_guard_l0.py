"""L0 (ADR-034 §4.1, OD-1) — the enforcement configuration is out of reach of
the party it governs.

The hole these tests close is **G5**: the hook re-reads ``--persona-file`` on
every invocation and ``.claude/settings.json`` was an ordinary path, so a
persona holding ``write_code`` could **grant itself a denied verb**, or
**unwire the hook entirely**, in one edit — and the very next tool call was
adjudicated against the document it had just written. Every other enforcement
layer was conditional on that not happening.

Two properties are asserted throughout, and they are the whole point:

* **Structural, not adjudicated.** No capability verb unlocks any of these. The
  most-capable persona in the fixtures is refused identically to the least, and
  ``edit_other_personas`` — the one verb that used to reach another persona's
  spec dir — does not reach a capability document any more. Because nothing was
  adjudicated, ``Decision.adjudicated`` stays False and the event reads
  ``unevaluated`` (ADR-018 §2), exactly like the step-0 path escape.
* **End-to-end through the real hook.** The self-grant and unwire tests drive a
  real subprocess over the documented stdin contract, not the evaluator alone.

Honest bound, restated here because a file this emphatic invites the wrong
inference: ``~/.claude/settings.json`` lives outside the repo root, so guard's
cwd-anchored comparison cannot see it and an agent with a shell can still
unwire itself there. L0 is a fence around the policy documents in the repo, not
a sandbox (ADR-034 §6).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from test_guard import (  # the fixtures and the real-subprocess harness
    DEV_PERSONA,
    hook,
    personas,  # noqa: F401 — pytest fixture, imported for use
    run_guard,
)

from baron import guard

#: A persona holding EVERY write-ish verb in the vocabulary, including
#: `edit_other_personas`. If L0 held only for weak personas it would not be
#: structural, so this is the fixture most of the file argues against.
OMNIPOTENT_PERSONA = """\
persona: Omni
slug: omni
archetype: dev
identity:
  git_name: Omni
  git_email: omni@example.invalid
  commit_prefix: "omni:"
  routing_label: agent-omni
capabilities:
  allow:
    - read_code
    - read_collab
    - write_code
    - write_path: [findings, _handoff, wiki, agents]
    - open_pr
    - run_tests
    - merge_pr
    - push_main
    - force_push
    - edit_other_personas
  deny: []
scope:
  summary: holds everything
  focus: [prove L0 is not a capability check]
session_ritual: [sync_repos]
"""


@pytest.fixture
def omni(tmp_path: Path) -> Path:
    path = tmp_path / "omni-persona.yaml"
    path.write_text(OMNIPOTENT_PERSONA, encoding="utf-8")
    return path


def _persona(text: str) -> guard.GuardPersona:
    """Parse a persona document the way the hook does."""
    import yaml

    data = yaml.safe_load(text)
    allow, allow_scopes = guard._split_items(data["capabilities"].get("allow"))
    deny, deny_scopes = guard._split_items(data["capabilities"].get("deny"))
    return guard.GuardPersona(
        slug=str(data["slug"]),
        allow=frozenset(allow),
        deny=frozenset(deny),
        allow_scopes=allow_scopes,
        deny_scopes=deny_scopes,
    )


def _write(target: Path, cwd: Path, persona_text: str = OMNIPOTENT_PERSONA):
    return guard.evaluate_write(
        "Write", {"file_path": str(target)}, cwd, _persona(persona_text)
    )


# --- the two attacks, end to end through the real hook --------------------------------


def test_a_persona_cannot_self_grant_a_denied_verb(
    personas: dict[str, Path], tmp_path: Path  # noqa: F811
) -> None:
    """FM4's shape, mechanised: rewrite your own spec, then use the new verb.

    `dara` denies `merge_pr`. Before ADR-034 the first call below succeeded —
    `agents/dara/persona.yaml` was "its own surface" — and the SECOND call was
    then adjudicated against the rewritten document.
    """
    own_spec = tmp_path / "agents" / "dara" / "persona.yaml"
    proc = run_guard(
        personas["dev"], hook("Write", {"file_path": str(own_spec)}, tmp_path)
    )
    assert proc.returncode == 2, proc.stderr
    assert "capability document" in proc.stderr
    # And the verb it was trying to buy is still denied.
    proc = run_guard(
        personas["dev"], hook("Bash", {"command": "gh pr merge 12 --squash"}, tmp_path)
    )
    assert proc.returncode == 2, proc.stderr
    assert "merge_pr" in proc.stderr


def test_a_persona_cannot_unwire_or_delete_the_hook(
    personas: dict[str, Path], tmp_path: Path  # noqa: F811
) -> None:
    """The other half of G5: remove the guard instead of out-voting it.

    Both the project's settings.json and the copy inside the persona's own
    emitted runtime kit are refused — the second is the one a persona would
    actually reach for, and an anchored-at-root rule would have missed it.
    """
    for target in (
        tmp_path / ".claude" / "settings.json",
        tmp_path / ".claude" / "settings.local.json",
        tmp_path / "agents" / "dara" / "runtime" / ".claude" / "settings.json",
        tmp_path / "agents" / "dara" / "sidecar.sh",
    ):
        proc = run_guard(
            personas["dev"], hook("Write", {"file_path": str(target)}, tmp_path)
        )
        assert proc.returncode == 2, f"{target} was writable: {proc.stderr}"
        assert "ADR-034 L0" in proc.stderr


# --- structural: no verb unlocks it ---------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".baron-waivers.yaml",
        ".baron-rules.yaml",
        ".barony/allowed_signers",
        "agents/omni/persona.yaml",
        "agents/someone-else/persona.yaml",
        "agents/omni/AGENT.md",
        "agents/omni/runtime/.claude/settings.json",
    ],
)
def test_every_fenced_path_is_refused_for_the_most_capable_persona(
    relative: str, tmp_path: Path
) -> None:
    decision = _write(tmp_path / relative, tmp_path)
    assert not decision.allowed, f"{relative} was writable by an all-verbs persona"
    # The refusal is NOT an adjudication: nothing about this persona decided it,
    # and a differently-capable one would have got the same answer.
    assert decision.adjudicated is False, relative


@pytest.mark.parametrize(
    "relative",
    [
        # A NON-acting slug on purpose. `omni`'s own copies of these are refused
        # twice over — once by the trailing match, once by the own-spec-dir rule
        # — so a regression in `_trailing_match` alone stays invisible there.
        # Under someone else's slug the trailing match is the ONLY thing left:
        # the own-spec-dir rule does not apply, and step 2 would hand these to a
        # holder of `edit_other_personas` as ordinary files.
        "agents/someone-else/runtime/.claude/settings.json",
        "agents/someone-else/runtime/.claude/settings.local.json",
        "agents/someone-else/runtime/.baron-waivers.yaml",
        "agents/someone-else/runtime/.baron-rules.yaml",
        "agents/someone-else/runtime/.barony/allowed_signers",
    ],
)
def test_trailing_match_fences_another_personas_emitted_kit(
    relative: str, tmp_path: Path
) -> None:
    """Pin the trailing match on its own, unmasked by the own-spec-dir rule.

    An emitted runtime kit under ANOTHER persona's dir is the case that only
    `_trailing_match` catches — and it is the one that matters, because that
    copy is live hook wiring, and the acting persona here holds
    `edit_other_personas`, which reaches everything else under that dir.
    """
    decision = _write(tmp_path / relative, tmp_path)
    assert not decision.allowed, f"{relative} was writable by an all-verbs persona"
    assert decision.adjudicated is False, relative
    assert "ADR-034 L0" in decision.reason
    # Not the own-spec-dir refusal wearing a different hat.
    assert "own spec dir" not in decision.reason, relative
    # Control: the same dir, an ordinary file, IS reachable with the verb — so
    # the assertions above are about the trailing match and nothing broader.
    sibling = _write(tmp_path / "agents/someone-else/runtime/README.md", tmp_path)
    assert sibling.allowed, sibling.reason


def test_the_fence_does_not_depend_on_the_persona(tmp_path: Path) -> None:
    """Same path, opposite personas, identical verdict — that is 'structural'."""
    target = tmp_path / "agents" / "dara" / "persona.yaml"
    strong = _write(target, tmp_path, OMNIPOTENT_PERSONA)
    weak = _write(target, tmp_path, DEV_PERSONA)
    assert not strong.allowed and not weak.allowed
    assert strong.reason == weak.reason
    assert strong.adjudicated is weak.adjudicated is False


def test_edit_other_personas_no_longer_reaches_a_capability_document(
    tmp_path: Path,
) -> None:
    """The verb still exists and still governs — just not the grant itself."""
    assert _persona(OMNIPOTENT_PERSONA).grants("edit_other_personas")
    denied = _write(tmp_path / "agents" / "other" / "persona.yaml", tmp_path)
    assert not denied.allowed and "capability document" in denied.reason
    # ... while an ordinary file under another persona's dir is still allowed
    # to a holder of the verb. L0 narrowed the verb's reach, it did not void it.
    allowed = _write(tmp_path / "agents" / "other" / "NOTES.md", tmp_path)
    assert allowed.allowed, allowed.reason


def test_a_handoff_component_does_not_unlock_a_fenced_path(tmp_path: Path) -> None:
    """Why L0 sits ABOVE the universal-write allow, not merely above step 2.

    `_handoff` is matched as a COMPONENT anywhere in the path. Had L0 been
    placed where ADR-034 §4.1 first drafted it — after step 1 — this path would
    have been allowed by the universal-write zone before any fence was consulted.
    """
    decision = _write(tmp_path / "_handoff" / ".claude" / "settings.json", tmp_path)
    assert not decision.allowed, decision.reason


# --- what L0 deliberately does NOT fence ----------------------------------------------


def test_ordinary_work_is_untouched(tmp_path: Path) -> None:
    """The fence is narrow. Source, findings and handoffs stay writable."""
    for relative in (
        "src/app.py",
        "findings/2026-08-14-thing.md",
        "_handoff/tasks/2026-08-14-note.md",
        "wiki/status.md",
        "agents/README.md",  # not inside any persona's dir
        ".claude/agents/reviewer.md",  # a subagent file, not the settings doc
    ):
        decision = _write(tmp_path / relative, tmp_path)
        assert decision.allowed, f"{relative} was fenced: {decision.reason}"


def test_the_home_settings_file_is_out_of_reach_and_said_so(tmp_path: Path) -> None:
    """ADR-034 §6, asserted rather than merely written down.

    `~/.claude/settings.json` is outside the repo root. It is refused here, but
    by the STEP-0 path escape (it is above cwd), not by L0 — and on a real
    session where the runtime's cwd is the home directory's descendant, nothing
    in baron sees it at all. The bound is stated, not fixed.
    """
    outside = tmp_path.parent / "elsewhere" / ".claude" / "settings.json"
    decision = _write(outside, tmp_path)
    assert not decision.allowed
    assert "escapes the collab/persona root" in decision.reason
