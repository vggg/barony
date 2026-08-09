"""CLI-surface smoke tests: help text, subcommand wiring, index exit codes, forge."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from baron.cli import app
from baron.forge import ForgeError, ForgeUnavailable, GitHubForge, get_forge

from conftest import init_repo, run_git

runner = CliRunner()


@pytest.mark.parametrize(
    "args",
    [
        ["--help"],
        ["validate", "--help"],
        ["status", "--help"],
        ["finding", "new", "--help"],
        ["decision", "new", "--help"],
        ["handoff", "create", "--help"],
        ["handoff", "close", "--help"],
        ["handoff", "list", "--help"],
        ["index", "--help"],
    ],
)
def test_help_surfaces(args: list[str]) -> None:
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "--help" in result.output or "Usage" in result.output


def test_index_command_flags_duplicates(tmp_path: Path, fixed_clock: object) -> None:
    collab = init_repo(tmp_path / "collab")
    (collab / "findings").mkdir()
    (collab / "findings" / "index.md").write_text(
        "### F7 — a (2026-07-01, X)\n\n### F7 — b (2026-07-02, Y)\n", encoding="utf-8"
    )
    run_git(collab, "add", "-A")
    run_git(collab, "commit", "-q", "-m", "x")
    result = runner.invoke(app, ["index", "--collab", str(collab)])
    assert result.exit_code == 1
    assert "duplicate" in result.output
    assert (collab / "_handoff" / "README.md").is_file()


def test_get_forge_github_builtin() -> None:
    forge = get_forge("github")
    assert isinstance(forge, GitHubForge)
    assert isinstance(forge.available(), bool)


def test_get_forge_unknown_mentions_plugin_group() -> None:
    with pytest.raises(ForgeError, match="baron.forges"):
        get_forge("gitlab")  # backlog: ships as a plugin, see docs/BACKLOG.md


def test_github_forge_unavailable_without_gh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))  # no gh here
    forge = GitHubForge()
    assert forge.available() is False
    with pytest.raises(ForgeUnavailable, match="gh"):
        forge.list_open_prs(tmp_path)


def test_version_flag_matches_pyproject():
    """`baron --version` prints the packaged version, and it matches
    pyproject.toml. Regression: __version__ silently sat at 0.4.0 while the
    package shipped 0.5.1, and there was no --version flag at all (found the
    minute barony 0.5.1 hit PyPI)."""
    import re
    from pathlib import Path

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("barony ")
    printed = result.output.split()[1].strip()

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    declared = re.search(r'^version = "([^"]+)"', pyproject.read_text(), re.M).group(1)
    assert printed == declared, f"--version {printed} != pyproject {declared}"


# --- `baron rules` — the capability-rules diagnostic surface (ADR-016) ----------------


def _rules_persona(tmp_path: Path) -> Path:
    """A persona holding nothing dangerous — denies force_push/push_main/merge_pr."""
    persona_file = tmp_path / "persona.yaml"
    persona_file.write_text(
        "persona: Probe\nslug: probe\n"
        "capabilities:\n"
        "  allow: [read_code, write_code, open_pr]\n"
        "  deny: [push_main, force_push, merge_pr, edit_other_personas]\n",
        encoding="utf-8",
    )
    return persona_file


def _packaged_artifact_text() -> str:
    from importlib.resources import files as _files

    from baron import rules as rules_mod

    return _files("baron").joinpath(rules_mod.RULES_RESOURCE).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "args",
    [
        ["rules", "--help"],
        ["rules", "list", "--help"],
        ["rules", "validate", "--help"],
        ["rules", "diff", "--help"],
        ["rules", "explain", "--help"],
    ],
)
def test_rules_help_surfaces(args: list[str]) -> None:
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output


def test_rules_list_json_emits_exactly_the_frozen_verbs() -> None:
    import json

    from baron.schemas import CAPABILITY_VERBS

    result = runner.invoke(app, ["rules", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["rules_version"] == 1
    assert payload["vocabulary"] == "capability-vocab.v1"
    printed = [row["verb"] for row in payload["verbs"]]
    assert printed == list(CAPABILITY_VERBS)
    assert len(printed) == 10
    labels = {row["verb"]: row["label"] for row in payload["verbs"]}
    assert labels["force_push"] == "enforced"
    assert labels["open_pr"] == "instructed"
    assert labels["run_tests"] == "instructed"
    by_verb = {row["verb"]: row for row in payload["verbs"]}
    assert "git.push.force_flags" in by_verb["force_push"]["rules"]


def test_rules_list_json_qualifies_the_label_in_the_payload() -> None:
    """The caveat must be IN the document, not only in the human table.

    Machine consumers are the ones most likely to trust `label` unread; a
    footer printed by the text renderer does not reach them.
    """
    import json

    from baron import rules as rules_mod

    result = runner.invoke(app, ["rules", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["label_caveat"] == rules_mod.LABEL_CAVEAT

    by_verb = {row["verb"]: row for row in payload["verbs"]}
    for verb in ("read_code", "read_collab"):
        row = by_verb[verb]
        assert row["enforcement"] == "adapter-dependent"
        # The honest label: nothing baron ships enforces these.
        assert row["label"] == "instructed"
        assert row["caveat"] == rules_mod.LABEL_CAVEAT
    # Verbs that need no qualifying do not carry a stray one.
    assert "caveat" not in by_verb["force_push"]
    assert "caveat" not in by_verb["open_pr"]
    # And no row anywhere claims enforcement without guard detection.
    for row in payload["verbs"]:
        if row["label"] == "enforced":
            assert row["detection"] != "none", row


def test_rules_list_table_names_the_honesty_caveat() -> None:
    result = runner.invoke(app, ["rules", "list"])
    assert result.exit_code == 0, result.output
    assert "force_push" in result.output
    assert "adapter-dependent" in result.output
    assert "no adapter baron ships does" in result.output


def test_rules_validate_passes_on_the_shipped_artifact() -> None:
    result = runner.invoke(app, ["rules", "validate"])
    assert result.exit_code == 0, result.output
    assert "valid" in result.output
    assert "capability-vocab.v1" in result.output


def test_rules_validate_refuses_an_unsupported_rules_version(tmp_path: Path) -> None:
    """The negotiation invariant, at the CLI boundary: a consumer must refuse
    rules it does not understand rather than silently mis-enforce them."""
    fixture = tmp_path / "rules-v99.yaml"
    fixture.write_text(
        _packaged_artifact_text().replace("rules_version: 1", "rules_version: 99"),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["rules", "validate", "--file", str(fixture)])
    assert result.exit_code == 2, result.output
    assert "99" in result.output
    assert "refusing to mis-enforce" in result.output


def test_rules_validate_reports_a_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["rules", "validate", "--file", str(tmp_path / "nope.yaml")]
    )
    assert result.exit_code == 2, result.output
    assert "cannot read rules file" in result.output


#: A rule this baron does not implement, spliced into the packaged artifact.
#: NOT a substitution of an existing value — that is the shape every other
#: fixture here has, and it is why this hole survived a round: `validate`
#: printed "valid" and `diff` printed "identical to the packaged artifact"
#: while quietly discarding the rule.
_ADDED_RULE_YAML = (
    "        evil_new_rule:\n"
    "          verb: force_push\n"
    "          matcher: totally_bogus_matcher\n"
    '          flags: ["--sneaky"]\n'
)


def _artifact_with_an_added_rule(tmp_path: Path) -> Path:
    fixture = tmp_path / "added-rule.yaml"
    text = _packaged_artifact_text()
    doctored = text.replace("        plus_refspec:", _ADDED_RULE_YAML + "        plus_refspec:", 1)
    assert doctored != text, "fixture substitution did not apply"
    fixture.write_text(doctored, encoding="utf-8")
    return fixture


def test_rules_validate_refuses_a_document_that_adds_a_rule(tmp_path: Path) -> None:
    fixture = _artifact_with_an_added_rule(tmp_path)
    result = runner.invoke(app, ["rules", "validate", "--file", str(fixture)])
    assert result.exit_code == 2, result.output
    assert "evil_new_rule" in result.output
    assert "valid" not in result.output


def test_rules_diff_refuses_a_document_that_adds_a_rule(tmp_path: Path) -> None:
    """The regression that matters: `diff` must never call a document with
    unrecognised content "identical to the packaged artifact"."""
    fixture = _artifact_with_an_added_rule(tmp_path)
    result = runner.invoke(app, ["rules", "diff", "--file", str(fixture)])
    assert result.exit_code == 2, result.output
    assert "evil_new_rule" in result.output
    assert "identical" not in result.output


def test_rules_validate_refuses_an_unknown_matcher(tmp_path: Path) -> None:
    """The closed-matcher refusal, reachable from DOCUMENT input.

    Before round 2 the matcher was hardcoded in the parser, so this check could
    only ever fire against a developer edit to the builtin table — the ADR
    claimed a validation that no user input could trigger.
    """
    fixture = tmp_path / "bad-matcher.yaml"
    fixture.write_text(
        _packaged_artifact_text().replace(
            "matcher: flag_present", "matcher: totally_bogus_matcher", 1
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["rules", "validate", "--file", str(fixture)])
    assert result.exit_code == 2, result.output
    assert "unknown matcher" in result.output


def test_rules_diff_reports_an_added_verb(tmp_path: Path) -> None:
    """An added VERB is reportable (unlike an added rule, which is refused):
    the frozen-vocabulary check is a policy check, not a parse refusal."""
    import json

    fixture = tmp_path / "extra-verb.yaml"
    fixture.write_text(
        _packaged_artifact_text().replace(
            "verbs:\n", "verbs:\n  wild_verb:\n    class: sub-tool\n    detection: none\n", 1
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["rules", "diff", "--file", str(fixture), "--json"])
    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["verbs_added"] == ["wild_verb"]
    assert payload["rules_added"] == []

    # ...and `validate` fails the frozen-vocabulary check (exit 1, not a refusal).
    result = runner.invoke(app, ["rules", "validate", "--file", str(fixture)])
    assert result.exit_code == 1, result.output
    assert "FAIL" in result.output
    assert "wild_verb" in result.output


def test_rules_diff_identical_and_changed(tmp_path: Path) -> None:
    import json

    artifact = _packaged_artifact_text()
    same = tmp_path / "same.yaml"
    same.write_text(artifact, encoding="utf-8")
    result = runner.invoke(app, ["rules", "diff", "--file", str(same)])
    assert result.exit_code == 0, result.output
    assert "identical" in result.output

    changed = tmp_path / "changed.yaml"
    changed.write_text(
        artifact.replace('flags: ["--all", "--branches", "--mirror"]', 'flags: ["--all"]'),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["rules", "diff", "--file", str(changed), "--json"])
    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["identical"] is False
    assert payload["rules_changed"] == ["git.push.all_branches"]
    assert payload["rules_added"] == []
    assert payload["verbs_added"] == []


def test_rules_explain_force_push_is_denied_and_labelled_enforced(tmp_path: Path) -> None:
    persona_file = _rules_persona(tmp_path)
    result = runner.invoke(
        app,
        [
            "rules",
            "explain",
            "git push --force origin main",
            "--persona-file",
            str(persona_file),
            "--cwd",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1, result.output  # would be DENIED
    assert "force_push" in result.output
    assert "enforced" in result.output
    assert "git.push.force_flags" in result.output
    assert "DENY" in result.output


def test_rules_explain_matches_guard_evaluate_bash_exactly(tmp_path: Path) -> None:
    """The anti-drift pin: `rules explain` must be a dry run of the real
    decision, never a second implementation of it."""
    import json

    from baron import guard as guard_mod

    persona_file = _rules_persona(tmp_path)
    command = "git push --force origin main"
    result = runner.invoke(
        app,
        [
            "rules",
            "explain",
            command,
            "--persona-file",
            str(persona_file),
            "--cwd",
            str(tmp_path),
            "--json",
        ],
    )
    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)

    decision = guard_mod.evaluate_bash(
        command, tmp_path.resolve(), guard_mod.load_persona(persona_file)
    )
    assert payload["allowed"] is decision.allowed
    assert [row["verb"] for row in payload["verbs"]] == list(decision.verbs)
    assert payload["reason"] == decision.reason


def test_rules_explain_allows_an_ordinary_command(tmp_path: Path) -> None:
    persona_file = _rules_persona(tmp_path)
    result = runner.invoke(
        app,
        [
            "rules",
            "explain",
            "pytest -q",
            "--persona-file",
            str(persona_file),
            "--cwd",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "ALLOW" in result.output
    assert "guard maps no capability verb" in result.output


def test_rules_explain_write_mode_matches_guard_evaluate_write(tmp_path: Path) -> None:
    import json

    from baron import guard as guard_mod

    persona_file = _rules_persona(tmp_path)
    target = str(tmp_path / "agents" / "other" / "persona.yaml")
    result = runner.invoke(
        app,
        [
            "rules",
            "explain",
            target,
            "--write",
            "--persona-file",
            str(persona_file),
            "--cwd",
            str(tmp_path),
            "--json",
        ],
    )
    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "write"
    assert [row["verb"] for row in payload["verbs"]] == ["edit_other_personas"]
    assert payload["verbs"][0]["candidate_rules"] == ["file_ops.spec_dir"]

    decision = guard_mod.evaluate_write(
        "Write",
        {"file_path": target},
        tmp_path.resolve(),
        guard_mod.load_persona(persona_file),
    )
    assert payload["allowed"] is decision.allowed
    assert payload["reason"] == decision.reason


def test_rules_explain_reports_a_bad_persona_file(tmp_path: Path) -> None:
    bad = tmp_path / "persona.yaml"
    bad.write_text("persona: Probe\n", encoding="utf-8")  # no capabilities block
    result = runner.invoke(
        app, ["rules", "explain", "git push", "--persona-file", str(bad)]
    )
    assert result.exit_code == 2, result.output
    assert "no capabilities block" in result.output
