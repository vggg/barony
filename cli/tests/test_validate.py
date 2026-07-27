"""M1 acceptance: baron validate against real fixtures and synthetic breakage."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from baron.cli import app
from baron.validate import validate_file, validate_path

from conftest import REPO_ROOT

runner = CliRunner()

TESS = REPO_ROOT / "tests/examples/tess/persona.yaml"
REX = REPO_ROOT / "tests/examples/rex/persona.yaml"
MANIFEST_EXAMPLE = (
    REPO_ROOT / "skills/barony/assets/collab-repo/manifest.example.yaml"
)


def errors(findings: list) -> list:
    return [f for f in findings if f.severity == "error"]


def test_tess_and_rex_fixtures_validate_clean() -> None:
    for fixture in (TESS, REX):
        found = validate_file(fixture)
        assert errors(found) == [], [f.message for f in found]


def test_manifest_example_validates_clean() -> None:
    found = validate_file(MANIFEST_EXAMPLE)
    assert errors(found) == [], [f.message for f in found]


def test_fixture_placeholder_is_exempt_but_inline_copy_is_not(tmp_path: Path) -> None:
    # tess carries {{IDENTITY_DOMAIN}}; outside an exempt path that must be an error.
    copy = tmp_path / "persona.yaml"
    copy.write_text(TESS.read_text(encoding="utf-8"), encoding="utf-8")
    found = validate_file(copy)
    assert any(f.check == "placeholder" for f in errors(found))


def test_bad_verb_missing_field_and_overlap_flagged(tmp_path: Path) -> None:
    bad = tmp_path / "persona.yaml"
    bad.write_text(
        """\
persona: Mal
slug: mal
archetype: dev
identity:
  git_name: Mal
  git_email: mal@example.com
  commit_prefix: "mal:"
  routing_label: agent-mal
capabilities:
  allow:
    - read_code
    - gh_pr_create
    - write_path: [findings]
  deny:
    - read_code
    - write_path: [findings, wiki]
scope:
  summary: broken on purpose
  focus: []
session_ritual:
  - sync_repos
""",
        encoding="utf-8",
    )
    found = validate_file(bad)
    checks = {f.check for f in errors(found)}
    assert "verb" in checks  # gh_pr_create is tool-level, not vocabulary
    assert "overlap" in checks  # read_code + write_path[findings] on both sides
    assert "empty" in checks  # scope.focus must not be empty


def test_unknown_field_is_warning_not_error(tmp_path: Path) -> None:
    text = TESS.read_text(encoding="utf-8").replace("{{IDENTITY_DOMAIN}}", "example.com")
    copy = tmp_path / "persona.yaml"
    copy.write_text(text + "\nfavourite_colour: mauve\n", encoding="utf-8")
    found = validate_file(copy)
    assert errors(found) == []
    assert any(f.check == "unknown-field" and f.severity == "warning" for f in found)


def test_discovery_skips_templates_but_validates_fixtures() -> None:
    findings, files, skipped = validate_path(REPO_ROOT / "tests" / "examples")
    assert TESS in files and REX in files
    assert errors(findings) == []
    findings2, files2, skipped2 = validate_path(
        REPO_ROOT / "skills/barony/assets"
    )
    assert files2 == []  # everything under assets/collab-repo/ is a template
    assert skipped2, "template persona.yaml files should be reported as skipped"


def test_cli_exit_codes_and_json(tmp_path: Path) -> None:
    ok = runner.invoke(app, ["validate", str(TESS), "--json"])
    assert ok.exit_code == 0, ok.output
    payload = json.loads(ok.output)
    assert payload["summary"]["errors"] == 0

    broken = tmp_path / "manifest.yaml"
    broken.write_text("project:\n  name: x\n", encoding="utf-8")
    bad = runner.invoke(app, ["validate", str(broken), "--json"])
    assert bad.exit_code == 1
    payload = json.loads(bad.output)
    assert payload["summary"]["errors"] > 0
    assert any(f["check"] == "missing-field" for f in payload["findings"])
