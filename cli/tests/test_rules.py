"""The capability-rules artifact: packaged, versioned, and actually consumed.

Deliverable contract (ADR-004 addendum §4.1): the verb→enforcement rule table
lives in ``baron/data/capability-rules.v1.yaml`` (package data), guard loads
its policy from it, and the artifact's verb set exactly matches the frozen
10-verb vocabulary embedded in ``baron.schemas``.
"""

from __future__ import annotations

from dataclasses import replace
from importlib.resources import files
from pathlib import Path

import yaml

from baron import guard, rules
from baron.schemas import CAPABILITY_VERBS


def test_artifact_is_packaged_and_versioned() -> None:
    resource = files("baron").joinpath(rules.RULES_RESOURCE)
    raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
    assert raw["rules_version"] == rules.SUPPORTED_RULES_VERSION == 1
    loaded = rules.load_rules()
    assert loaded.rules_version == 1
    assert loaded.ambiguity_policy == "conservative-deny"


def test_open_pr_and_run_tests_stay_unparsed_deferred() -> None:
    """`open_pr`/`run_tests` denial parsing is DEFERRED, not forgotten.

    ADR-004 §2.2, the artifact's own notes, and docs/BACKLOG.md § "Guard coverage
    growth" all say the same thing on the same trigger rule: these two verbs stay
    instruction-only until there is OBSERVED NEED (capability vocabulary design
    rule 4). Re-checked 2026-08-09 during the 2026-08-08 evaluation close-out —
    no observed-need evidence exists in the repo or in that evaluation, so the
    deferral holds and `rules_version` stays 1.

    This test is the tripwire: adding detection for either verb must be a
    deliberate act that bumps `rules_version` (so every consumer notices) rather
    than a quiet edit to the artifact.
    """
    loaded = rules.load_rules()
    for verb in ("open_pr", "run_tests"):
        entry = loaded.verbs[verb]
        assert entry["detection"] == "none", (
            f"{verb} gained detection — that is a policy change: bump "
            "rules_version in capability-rules.v1.yaml, update ADR-004 §2.2 and "
            "docs/BACKLOG.md, and record the observed need that triggered it"
        )
        assert "NOT parsed" in entry["notes"]
    assert loaded.rules_version == rules.SUPPORTED_RULES_VERSION == 1


def test_rules_verb_set_matches_frozen_vocabulary() -> None:
    loaded = rules.load_rules()
    assert set(loaded.verbs) == set(CAPABILITY_VERBS), (
        "capability-rules.v1.yaml verbs drifted from the frozen 10-verb vocabulary"
    )
    assert len(loaded.verbs) == 10
    # Every rule-referenced verb resolves inside the table (loader-enforced,
    # asserted here as the contract).
    for verb in (
        loaded.push_force_verb,
        loaded.push_all_branches_verb,
        loaded.push_default_branch_verb,
        loaded.merge_on_default_branch_verb,
        loaded.gh_pr_merge_verb,
    ):
        assert verb in loaded.verbs


def test_guard_consumes_the_packaged_rules(monkeypatch, tmp_path: Path) -> None:
    """Guard decisions must come from the artifact, not from hardcoded copies.

    Proven by swapping the loaded rules for a mutated copy (gh pr merge mapped
    to a different verb) and watching the decision follow the data.
    """
    persona = guard.GuardPersona(
        slug="probe",
        allow=frozenset({"read_code", "merge_pr"}),
        deny=frozenset({"push_main", "force_push"}),
        allow_scopes=(),
        deny_scopes=(),
    )
    # Baseline: packaged rules map `gh pr merge` -> merge_pr, which is granted.
    decision = guard.evaluate_bash("gh pr merge 12 --squash", tmp_path, persona)
    assert decision.allowed, decision.reason

    mutated = replace(rules.load_rules(), gh_pr_merge_verb="push_main")
    monkeypatch.setattr(guard, "_rules", lambda: mutated)
    decision = guard.evaluate_bash("gh pr merge 12 --squash", tmp_path, persona)
    assert not decision.allowed
    assert "push_main" in decision.verbs


def test_broken_artifact_fails_closed(monkeypatch, tmp_path: Path) -> None:
    persona_file = tmp_path / "persona.yaml"
    persona_file.write_text(
        "persona: Probe\nslug: probe\n"
        "capabilities:\n  allow: [read_code]\n  deny: [push_main]\n",
        encoding="utf-8",
    )

    def boom() -> rules.CapabilityRules:
        raise rules.RulesError("artifact unreadable (test)")

    monkeypatch.setattr(guard, "load_rules", boom)
    payload = (
        '{"tool_name": "Bash", "tool_input": {"command": "git push origin main"}, '
        f'"cwd": "{tmp_path.as_posix()}"}}'
    )
    code, stderr = guard.process(payload, persona_file=persona_file)
    assert code == 2
    assert "fail closed" in stderr
    assert "artifact unreadable (test)" in stderr


def test_unsupported_rules_version_is_refused() -> None:
    try:
        rules._parse({"rules_version": 99})
    except rules.RulesError as exc:
        assert "99" in str(exc)
    else:  # pragma: no cover - the assertion above must fire
        raise AssertionError("rules_version 99 was accepted")
