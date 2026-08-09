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

    # The mutation goes through the rule LIST (ADR-016): rules are data, and
    # `gh_pr_merge_verb` is now a derived accessor over it. Pre-ADR-016 this
    # read `replace(loaded, gh_pr_merge_verb=...)`; the assertions below are
    # unchanged, only the handle on the datum moved.
    loaded = rules.load_rules()
    mutated = replace(
        loaded,
        command_rules=tuple(
            replace(rule, verb="push_main") if rule.id == rules.RULE_GH_PR_MERGE else rule
            for rule in loaded.command_rules
        ),
    )
    assert mutated.gh_pr_merge_verb == "push_main"
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


# --- ADR-016: the rule-list representation --------------------------------------------

#: The exact values every legacy accessor returned BEFORE the ADR-016 refactor,
#: transcribed by hand from the pre-refactor `CapabilityRules` construction.
#: Pinned as literals on purpose: re-deriving them from the artifact would test
#: the loader against itself and prove nothing about behaviour preservation.
PRE_REFACTOR_ACCESSORS: dict[str, object] = {
    "git_global_value_options": (
        "-C",
        "-c",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--exec-path",
    ),
    "push_value_options": ("--repo", "--receive-pack", "--exec", "-o", "--push-option"),
    "push_force_flags": ("--force", "-f", "--force-if-includes"),
    "push_force_flag_prefixes": ("--force-with-lease",),
    "push_force_verb": "force_push",
    "push_plus_refspec_prefix": "+",
    "push_all_branch_flags": ("--all", "--branches", "--mirror"),
    "push_all_branches_verb": "push_main",
    "push_default_branch_fallbacks": ("main", "master", "HEAD"),
    "push_default_branch_verb": "push_main",
    "merge_on_default_branch_verb": "push_main",
    "gh_pr_merge_subcommand": ("pr", "merge"),
    "gh_pr_merge_verb": "merge_pr",
    "universal_write_components": ("_handoff",),
    "spec_dir_component": "agents",
}


def test_legacy_accessors_are_behaviour_preserving() -> None:
    """Every pre-ADR-016 field name still resolves to the same value and type.

    This is the whole safety argument for the refactor: guard.py and
    runtimes/pydantic_ai.py were not touched, so if these hold, they cannot
    have changed behaviour.
    """
    loaded = rules.load_rules()
    for name, expected in PRE_REFACTOR_ACCESSORS.items():
        actual = getattr(loaded, name)
        assert actual == expected, f"{name}: {actual!r} != {expected!r}"
        assert type(actual) is type(expected), f"{name} changed type"


def test_capability_rules_is_still_frozen() -> None:
    loaded = rules.load_rules()
    for attr, value in (("rules_version", 2), ("command_rules", ())):
        try:
            setattr(loaded, attr, value)
        except Exception as exc:  # FrozenInstanceError is a subclass of AttributeError
            assert type(exc).__name__ == "FrozenInstanceError", exc
        else:  # pragma: no cover - the assertion above must fire
            raise AssertionError(f"CapabilityRules.{attr} was mutable")
    # Derived accessors are read-only too (no setter on the property).
    try:
        loaded.push_force_verb = "merge_pr"
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("a derived accessor was settable")


def test_rule_list_covers_every_builtin_rule_with_a_known_matcher() -> None:
    loaded = rules.load_rules()
    ids = {rule.id for rule in loaded.rules}
    assert ids == {
        rules.RULE_PUSH_FORCE_FLAGS,
        rules.RULE_PUSH_PLUS_REFSPEC,
        rules.RULE_PUSH_ALL_BRANCHES,
        rules.RULE_PUSH_DEFAULT_BRANCH,
        rules.RULE_MERGE_ON_DEFAULT_BRANCH,
        rules.RULE_GH_PR_MERGE,
        rules.RULE_UNIVERSAL_WRITE,
        rules.RULE_SPEC_DIR,
    }
    for rule in loaded.command_rules:
        assert rule.matcher in rules.COMMAND_MATCHERS
        assert rule.verb in loaded.verbs
        assert rule.source == rules.SOURCE_BUILTIN
        assert rule.kind == "command"
    for rule in loaded.path_rules:
        assert rule.matcher in rules.PATH_MATCHERS
        assert rule.source == rules.SOURCE_BUILTIN
        assert rule.kind == "path"
    # `rule()` is the public handle the CLI joins on.
    assert loaded.rule(rules.RULE_GH_PR_MERGE).verb == "merge_pr"
    try:
        loaded.rule("nope")
    except rules.RulesError as exc:
        assert "nope" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an unknown rule id resolved")


def test_spec_dir_verb_matches_the_literal_guard_uses() -> None:
    """`guard.evaluate_write` names the spec-dir verb literally; the artifact
    does not carry it. Assert the pair agrees so it cannot drift silently."""
    source = Path(guard.__file__).read_text(encoding="utf-8")
    assert f'grants("{rules.SPEC_DIR_VERB}")' in source
    assert rules.load_rules().rule(rules.RULE_SPEC_DIR).verb == rules.SPEC_DIR_VERB


def test_duplicate_rule_ids_are_refused() -> None:
    loaded = rules.load_rules()
    first = loaded.command_rules[0]
    try:
        replace(loaded, command_rules=(first, first))
    except rules.RulesError as exc:
        assert "duplicate rule id" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("duplicate rule ids were accepted")


def test_enforcement_labels_are_honest() -> None:
    """Three states, not two — a whole-tool verb guard does not parse is
    enforced by the ADAPTER (tool omission), which is not guard's claim."""
    loaded = rules.load_rules()
    assert loaded.enforcement("force_push") == rules.ENFORCEMENT_GUARD
    assert loaded.label("force_push") == "enforced"
    assert loaded.enforcement("read_code") == rules.ENFORCEMENT_TOOL_OMISSION
    assert loaded.enforcement("open_pr") == rules.ENFORCEMENT_INSTRUCTED
    assert loaded.label("open_pr") == "instructed"
    assert loaded.label("run_tests") == "instructed"


# --- version / vocabulary negotiation --------------------------------------------------


def _artifact_text() -> str:
    return files("baron").joinpath(rules.RULES_RESOURCE).read_text(encoding="utf-8")


def test_parse_text_accepts_the_shipped_artifact() -> None:
    parsed = rules.parse_text(_artifact_text(), origin="packaged")
    assert parsed == rules.load_rules()


def test_parse_text_refuses_an_unknown_vocabulary() -> None:
    doctored = _artifact_text().replace(
        "vocabulary: capability-vocab.v1", "vocabulary: capability-vocab.v9"
    )
    try:
        rules.parse_text(doctored, origin="doctored")
    except rules.RulesError as exc:
        assert "capability-vocab.v9" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an unknown vocabulary was accepted")


def test_parse_file_refuses_unparseable_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "rules.yaml"
    bad.write_text("rules_version: [1\n", encoding="utf-8")
    try:
        rules.parse_file(bad)
    except rules.RulesError as exc:
        assert "not valid YAML" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("broken YAML was accepted")


def test_parse_file_reports_a_missing_file(tmp_path: Path) -> None:
    try:
        rules.parse_file(tmp_path / "absent.yaml")
    except rules.RulesError as exc:
        assert "cannot read rules file" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a missing rules file was accepted")


def test_guard_reads_packaged_data_only() -> None:
    """Honesty pin (ADR-016 §5): baron does NOT read a project rules file yet.

    `load_rules()` takes no path (so its process-global cache stays correct)
    and guard never reaches for the file-parsing entry points. If a
    `.baron/rules.yaml` loader lands without its own ADR and precedence story,
    this is what should fail first.
    """
    import inspect

    assert list(inspect.signature(rules.load_rules).parameters) == []
    guard_src = Path(guard.__file__).read_text(encoding="utf-8")
    assert "parse_file" not in guard_src
    assert "parse_text" not in guard_src
