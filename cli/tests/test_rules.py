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

import pytest
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


#: The enforcement claim baron makes for each frozen verb, stated OUTRIGHT.
#: verb -> (class, detection, enforcement, label)
#:
#: Written as literals on purpose. The round-2 test derived its expectation from
#: `detection` — the very field under test — so it could only ever restate the
#: document back to itself: a document claiming `detection: command` for
#: `read_code` satisfied it while `baron rules list` printed `enforced` for a
#: verb nothing checks. A table of literals cannot be satisfied that way. If a
#: row here changes, someone is changing what baron CLAIMS to enforce, and the
#: diff says so in review.
EXPECTED_CLAIMS: dict[str, tuple[str, str, str, str]] = {
    "read_code": ("whole-tool", "none", rules.ENFORCEMENT_ADAPTER_DEPENDENT, "instructed"),
    "read_collab": ("whole-tool", "none", rules.ENFORCEMENT_ADAPTER_DEPENDENT, "instructed"),
    "write_code": ("whole-tool", "file-op", rules.ENFORCEMENT_GUARD, "enforced"),
    "write_path": ("sub-tool", "file-op", rules.ENFORCEMENT_GUARD, "enforced"),
    "open_pr": ("sub-tool", "none", rules.ENFORCEMENT_INSTRUCTED, "instructed"),
    "run_tests": ("sub-tool", "none", rules.ENFORCEMENT_INSTRUCTED, "instructed"),
    "merge_pr": ("sub-tool", "command", rules.ENFORCEMENT_GUARD, "enforced"),
    "push_main": ("sub-tool", "command", rules.ENFORCEMENT_GUARD, "enforced"),
    "force_push": ("sub-tool", "command", rules.ENFORCEMENT_GUARD, "enforced"),
    "edit_other_personas": ("sub-tool", "file-op", rules.ENFORCEMENT_GUARD, "enforced"),
}


def test_enforcement_claims_are_pinned_to_a_literal_table() -> None:
    """What baron claims to enforce is pinned, not re-derived from the document."""
    loaded = rules.load_rules()
    assert set(EXPECTED_CLAIMS) == set(CAPABILITY_VERBS)
    for verb, (klass, detection, enforcement, label) in EXPECTED_CLAIMS.items():
        entry = loaded.verbs[verb]
        assert entry["class"] == klass, verb
        assert entry["detection"] == detection, verb
        assert loaded.enforcement(verb) == enforcement, verb
        assert loaded.label(verb) == label, verb


def test_every_enforced_verb_is_backed_by_a_real_check() -> None:
    """`enforced` requires a rule (or the file-op chain) behind it — no exceptions.

    The independent half of the pinning above: it does not ask what the document
    SAYS, it asks whether something in the parsed rule set could actually fire.
    """
    loaded = rules.load_rules()
    for verb in CAPABILITY_VERBS:
        bound = [r for r in loaded.rules if r.verb == verb]
        chain = verb in rules.FILE_OP_CHAIN_VERBS
        if loaded.label(verb) == "enforced":
            assert bound or chain, f"{verb}: labelled enforced with nothing behind it"
        else:
            assert not bound, f"{verb}: a rule binds it but it is not labelled enforced"


def test_detection_consistency_is_parser_enforced_not_test_enforced() -> None:
    """The check above must live in the PARSER, so document input reaches it.

    Round 2 asserted verb/rule consistency in this file only, against
    `load_rules()`. That left every *document* free to violate it — which is the
    input that matters, since `--file` accepts one. This test pins the check's
    presence in `rules.py`; the REFUSED_DOCUMENTS cases exercise it.
    """
    assert hasattr(rules, "_check_detection_consistency")
    source = Path(rules.__file__).read_text(encoding="utf-8")
    assert "_check_detection_consistency(verbs, command_rules, path_rules)" in source


def test_adapter_dependent_verbs_are_qualified_not_claimed() -> None:
    """A verb no shipped enforcer checks must carry the caveat, not a claim."""
    loaded = rules.load_rules()
    adapter_dependent = [
        v for v in loaded.verbs if loaded.enforcement(v) == rules.ENFORCEMENT_ADAPTER_DEPENDENT
    ]
    # These are the whole-tool/no-detection verbs; if this set ever empties or
    # grows, the caveat text in rules.LABEL_CAVEAT needs re-measuring.
    assert adapter_dependent == ["read_code", "read_collab"]
    for verb in adapter_dependent:
        assert loaded.label(verb) == "instructed"
        assert loaded.caveat(verb) == rules.LABEL_CAVEAT
    for verb in ("force_push", "open_pr", "write_code"):
        assert loaded.caveat(verb) == ""
    assert "read_code" in rules.LABEL_CAVEAT
    assert "pydantic-ai" in rules.LABEL_CAVEAT
    # ADR-020: the caveat is built FROM the per-adapter measurements, so it
    # cannot drift from them, and it states the bound rather than the result
    # alone (baron emits no mechanism ≠ the runtime cannot enforce it).
    for adapter, why in rules.READ_VERB_MEASUREMENTS.items():
        assert adapter in rules.LABEL_CAVEAT
        assert why in rules.LABEL_CAVEAT
    assert "baron emits no mechanism" in rules.LABEL_CAVEAT


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


#: Every substitution below turns the SHIPPED artifact into a document the
#: parser must refuse. Reachability is the point: before ADR-016's round-2 fix
#: the closed-matcher check could only fire against a developer edit to the
#: builtin table, and an added rule was silently discarded.
#: Verb entries quoted verbatim from the artifact, so a value-level fixture
#: patches the ENTRY rather than a same-looking string in the header comment.
#: `test_verb_entry_fixtures_are_anchored_to_the_artifact` pins them.
_READ_CODE_ENTRY = "  read_code:\n    class: whole-tool\n    detection: none\n"
_MERGE_PR_ENTRY = "  merge_pr:\n    class: sub-tool\n    detection: command\n"


def test_verb_entry_fixtures_are_anchored_to_the_artifact() -> None:
    """The value-level fixtures below are worthless if their anchor drifts.

    A substitution that no longer matches would make its case silently test the
    unmodified artifact — and `test_unrecognised_document_content_is_refused`
    would still pass, for the wrong reason.
    """
    text = _artifact_text()
    for anchor in (_READ_CODE_ENTRY, _MERGE_PR_ENTRY):
        assert text.count(anchor) == 1, f"anchor not unique in the artifact: {anchor!r}"


REFUSED_DOCUMENTS: dict[str, tuple[str, str, str]] = {
    # name: (find, replace, expected fragment of the refusal)
    "added rule": (
        "        plus_refspec:",
        "        evil_new_rule:\n"
        "          verb: force_push\n"
        "          matcher: flag_present\n"
        '          flags: ["--sneaky"]\n'
        "        plus_refspec:",
        "evil_new_rule",
    ),
    "unknown matcher": (
        "matcher: flag_present",
        "matcher: totally_bogus_matcher",
        "unknown matcher",
    ),
    "matcher guard does not implement for that rule": (
        "matcher: flag_present",
        "matcher: subcommand_present",
        "guard implements",
    ),
    "unknown top-level key": (
        "rules_version: 1",
        "rules_version: 1\nsneaky: true",
        "'sneaky'",
    ),
    "unknown verb-entry key": (
        "    class: whole-tool",
        "    class: whole-tool\n    enforced: true",
        "'enforced'",
    ),
    "unknown file_ops key": (
        '  spec_dir_component: "agents"',
        '  spec_dir_component: "agents"\n  evil_scope: ["/"]',
        "'evil_scope'",
    ),
    "unknown command program": (
        "  gh:\n",
        "  kubectl:\n    rules: {}\n  gh:\n",
        "'kubectl'",
    ),
    "removed built-in rule": (
        "        plus_refspec:\n"
        "          verb: force_push\n"
        "          matcher: refspec_prefix\n"
        '          prefix: "+"\n',
        "",
        "omits built-in rule",
    ),
    "rule missing a required parameter": (
        '          flags: ["--all", "--branches", "--mirror"]\n',
        "",
        "missing required key",
    ),
    # --- VALUE-level refusals (round-3) ------------------------------------
    # Every fixture above targets a KEY or a RULE SLOT. None targeted a VALUE,
    # which is how `detection: banana` and `class: banana` validated clean at
    # exit 0 while silently re-routing what baron claims to enforce. Note these
    # substitute the verb ENTRY, not the bare string: the artifact's header
    # comment also contains "detection: none", and a fixture that patches the
    # comment tests nothing (it passed, and looked like a pass, in round 3).
    "unknown detection value": (
        _READ_CODE_ENTRY,
        _READ_CODE_ENTRY.replace("detection: none", "detection: banana"),
        "not a detection this baron implements",
    ),
    "unknown class value": (
        _READ_CODE_ENTRY,
        _READ_CODE_ENTRY.replace("class: whole-tool", "class: banana"),
        "not a class this baron implements",
    ),
    "detection claiming a check nothing performs": (
        _READ_CODE_ENTRY,
        _READ_CODE_ENTRY.replace("detection: none", "detection: command"),
        "no command rule binds it",
    ),
    "detection file-op with nothing behind it": (
        _READ_CODE_ENTRY,
        _READ_CODE_ENTRY.replace("detection: none", "detection: file-op"),
        "no path rule binds it",
    ),
    "verb whose rule exists but under-declares detection": (
        _MERGE_PR_ENTRY,
        _MERGE_PR_ENTRY.replace("detection: command", "detection: none"),
        "misdescribes the enforcement it documents",
    ),
    "verb entry missing detection": (
        _READ_CODE_ENTRY,
        "  read_code:\n    class: whole-tool\n",
        "missing required key 'detection'",
    ),
    "verb entry missing class": (
        _READ_CODE_ENTRY,
        "  read_code:\n    detection: none\n",
        "missing required key 'class'",
    ),
}


@pytest.mark.parametrize("name", sorted(REFUSED_DOCUMENTS))
def test_unrecognised_document_content_is_refused_not_ignored(name: str) -> None:
    """ADR-016 §5.4 refuse-don't-ignore, exercised from DOCUMENT input.

    Silently dropping an unrecognised rule is the worst failure mode an
    enforcement artifact has: the document says a thing is blocked and nothing
    blocks it.
    """
    find, replace, expected = REFUSED_DOCUMENTS[name]
    doctored = _artifact_text().replace(find, replace, 1)
    assert doctored != _artifact_text(), f"{name}: substitution did not apply"
    try:
        rules.parse_text(doctored, origin=name)
    except rules.RulesError as exc:
        assert expected in str(exc), f"{name}: {exc}"
    else:  # pragma: no cover - the assertion above must fire
        raise AssertionError(f"{name} was accepted")


def test_matcher_is_optional_but_authoritative() -> None:
    """A document may omit `matcher` (it then gets the one guard implements);
    if it states one, it is validated rather than trusted."""
    without = _artifact_text().replace("          matcher: flag_present\n", "", 1)
    assert without != _artifact_text()
    parsed = rules.parse_text(without, origin="no-matcher")
    # Identical to the shipped table: the omitted field defaults to guard's.
    assert parsed == rules.load_rules()
    assert parsed.rule(rules.RULE_PUSH_FORCE_FLAGS).matcher == rules.MATCHER_FLAG_PRESENT


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


# --- diff_rules: the branches no DOCUMENT can reach ------------------------------------
# `rules diff`'s added/removed branches cannot fire from a document today: the
# builtin rule set is closed and every slot is mandatory, so an extra rule is
# refused at parse time and a missing one is too (see REFUSED_DOCUMENTS). Every
# CLI diff fixture is therefore a *substitution* on the packaged artifact — which
# is exactly the hole that let an added rule go unnoticed. These exercise the
# branches directly against constructed values so the renderer is not the only
# thing standing between the loader (ADR-016 §5) and a wrong diff.


def _plus_rule(loaded: rules.CapabilityRules, rule: rules.CommandRule) -> rules.CapabilityRules:
    return replace(loaded, command_rules=(*loaded.command_rules, rule))


def test_diff_rules_detects_an_added_rule() -> None:
    base = rules.load_rules()
    extra = rules.CommandRule(
        id="gh.release_delete",
        program="gh",
        subcommand=("release", "delete"),
        matcher=rules.MATCHER_SUBCOMMAND_PRESENT,
        verb="merge_pr",
        source="project",
    )
    delta = rules.diff_rules(base, _plus_rule(base, extra))
    assert delta["rules_added"] == ["gh.release_delete"]
    assert delta["rules_removed"] == []
    assert delta["rules_changed"] == []
    assert delta["header"] == []
    # ...and the reverse direction reports it as a removal.
    reverse = rules.diff_rules(_plus_rule(base, extra), base)
    assert reverse["rules_removed"] == ["gh.release_delete"]
    assert reverse["rules_added"] == []


def test_diff_rules_detects_changed_rules_verbs_and_header() -> None:
    base = rules.load_rules()
    other = replace(
        base,
        ambiguity_policy="permissive",
        verbs={**base.verbs, "wild_verb": {"class": "sub-tool", "detection": "none"}},
        command_rules=tuple(
            replace(r, verb="push_main") if r.id == rules.RULE_GH_PR_MERGE else r
            for r in base.command_rules
        ),
    )
    delta = rules.diff_rules(base, other)
    assert delta["rules_changed"] == [rules.RULE_GH_PR_MERGE]
    assert delta["verbs_added"] == ["wild_verb"]
    assert delta["verbs_removed"] == []
    assert any("ambiguity_policy" in line for line in delta["header"])


def test_diff_rules_is_empty_for_identical_tables() -> None:
    base = rules.load_rules()
    assert not any(rules.diff_rules(base, base).values())


def test_diff_rules_joins_verb_entries_not_just_rule_ids() -> None:
    """`verbs_changed` — the round-3 hole.

    Round 2's diff joined on rule id only, so a candidate that rewrote
    `detection`, `class` or `notes` on an existing verb came back completely
    empty and `rules diff` printed "identical to the packaged artifact". Those
    are the fields that decide whether baron prints `enforced`.

    The document-reachable cases are covered by fixtures in
    `test_cli.py::test_rules_diff_reports_a_changed_verb_entry`; this pins the
    pure function, including that an unchanged verb never appears.
    """
    base = rules.load_rules()
    other = replace(
        base,
        verbs={**base.verbs, "open_pr": {**base.verbs["open_pr"], "class": "whole-tool"}},
    )
    delta = rules.diff_rules(base, other)
    assert delta["verbs_changed"] == ["open_pr"]
    assert delta["verbs_added"] == [] and delta["verbs_removed"] == []
    assert delta["rules_changed"] == []
    # Symmetric, and every other verb stays out of it.
    assert rules.diff_rules(other, base)["verbs_changed"] == ["open_pr"]
    assert len(base.verbs) > 1


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
