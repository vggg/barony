"""P2.3 — spec↔runtime drift acceptance.

Reproduces the pilot failure directly: a collab repo declaring more personas than
the machine has registered agents. The pilot's manifest declared eight personas
against a six-agent Claude registry; the two unregistered ones silently ran as
some other agent.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from baron import drift
from baron.cli import app
from baron.validate import validate_path

runner = CliRunner()


def _manifest(personas: list[str], adapters: dict | None = None) -> dict:
    data = {
        "project": {"name": "pilot", "description": "d"},
        "paths": {"strategy": "relative", "root": "."},
        "repos": [{"id": "collab", "path": ".", "role": "collab"}],
        "backlog": {"source": "file", "location": "backlog.md"},
        "personas": [{"slug": s, "spec": f"agents/{s}/persona.yaml"} for s in personas],
    }
    if adapters is not None:
        data["adapters"] = adapters
    return data


def _registry(root: Path, subdir: str, slugs: list[str], suffix: str = ".md") -> Path:
    d = root / subdir
    d.mkdir(parents=True, exist_ok=True)
    for s in slugs:
        (d / f"{s}{suffix}").write_text("agent\n", encoding="utf-8")
    return d


def test_unregistered_persona_is_an_error(tmp_path: Path) -> None:
    """The pilot case: declared in the canon, absent from the registry."""
    collab, home = tmp_path / "collab", tmp_path / "home"
    collab.mkdir()
    home.mkdir()
    _registry(collab, ".claude/agents", ["dev", "librarian"])

    findings = drift.check(
        collab,
        _manifest(["dev", "librarian", "terrence", "carson"], {"claude": {"tier": "auto"}}),
        home=home,
    )
    errors = [f for f in findings if f.severity == "error"]
    assert {f.check for f in errors} == {"runtime-drift"}
    missing = sorted(s for s in ("terrence", "carson") if any(s in f.message for f in errors))
    assert missing == ["carson", "terrence"], [f.message for f in errors]
    # The message has to say what goes WRONG, not just that a file is absent.
    assert "wrong identity" in errors[0].message


def test_no_registry_anywhere_is_a_warning_not_an_error(tmp_path: Path) -> None:
    """CI has no ~/.claude/agents. This must never turn a green build red."""
    collab, home = tmp_path / "collab", tmp_path / "home"
    collab.mkdir()
    home.mkdir()

    findings = drift.check(
        collab, _manifest(["dev", "terrence"], {"claude": {"tier": "auto"}}), home=home
    )
    assert [f.severity for f in findings] == ["warning"]
    assert findings[0].check == "runtime-drift-unverifiable"
    assert not [f for f in findings if f.severity == "error"]


def test_undeclared_runtime_is_never_checked(tmp_path: Path) -> None:
    """A stray registry on the laptop must not fail a project that declares no
    runtime — baron does not guess which runtime a project hydrates on."""
    collab, home = tmp_path / "collab", tmp_path / "home"
    collab.mkdir()
    home.mkdir()
    _registry(home, ".claude/agents", ["someone-elses-agent"])

    assert drift.check(collab, _manifest(["dev"]), home=home) == []
    assert drift.check(collab, _manifest(["dev"], {"generic": {}}), home=home) == []


def test_user_level_only_registration_warns_about_shared_scope(tmp_path: Path) -> None:
    """~/.claude/agents is shared across every project on the machine, so a
    same-named agent from another project would satisfy the check."""
    collab, home = tmp_path / "collab", tmp_path / "home"
    collab.mkdir()
    home.mkdir()
    _registry(home, ".claude/agents", ["dev"])

    findings = drift.check(collab, _manifest(["dev"], {"claude": {"tier": "auto"}}), home=home)
    assert [f.severity for f in findings] == ["warning"]
    assert "shared across every project" in findings[0].message


def test_project_level_registration_is_silent(tmp_path: Path) -> None:
    collab, home = tmp_path / "collab", tmp_path / "home"
    collab.mkdir()
    home.mkdir()
    _registry(collab, ".claude/agents", ["dev"])
    _registry(home, ".claude/agents", ["dev"])

    assert drift.check(collab, _manifest(["dev"], {"claude": {"tier": "auto"}}), home=home) == []


def test_code_repo_registry_is_searched(tmp_path: Path) -> None:
    """Claude subagents usually live in the CODE repo, not the collab repo."""
    collab, code, home = tmp_path / "collab", tmp_path / "code", tmp_path / "home"
    collab.mkdir()
    code.mkdir()
    home.mkdir()
    _registry(code, ".claude/agents", ["dev"])
    manifest = _manifest(["dev"], {"claude": {"tier": "auto"}})
    manifest["repos"].append({"id": "code", "path": "../code", "role": "code"})

    assert drift.check(collab, manifest, home=home) == []


def test_code_puppy_uses_its_own_registry_shape(tmp_path: Path) -> None:
    """.code_puppy (underscore) + .json — the adapter flags the separator as a footgun."""
    collab, home = tmp_path / "collab", tmp_path / "home"
    collab.mkdir()
    home.mkdir()
    _registry(collab, ".code_puppy/agents", ["dev"], suffix=".json")

    manifest = _manifest(["dev", "ghost"], {"code-puppy": {}})
    findings = drift.check(collab, manifest, home=home)
    errors = [f for f in findings if f.severity == "error"]
    assert len(errors) == 1 and "ghost" in errors[0].message


def test_wired_into_validate_and_opt_out_works(tmp_path: Path) -> None:
    """End-to-end through `baron validate`, including the CLI surface.

    NOTE the persona slug: the CLI path resolves ``Path.home()`` for real, so a
    common slug like ``dev`` would be satisfied by the DEVELOPER's own
    ``~/.claude/agents/dev.md`` and the test would pass for the wrong reason (it
    did, on the first run). The slug here cannot plausibly exist on any machine.
    """
    slug = "baron-drift-fixture-persona"
    collab = tmp_path / "collab"
    (collab / "agents").mkdir(parents=True)
    (collab / "manifest.yaml").write_text(
        yaml.safe_dump(_manifest([slug], {"claude": {"tier": "auto"}})), encoding="utf-8"
    )
    _registry(collab, ".claude/agents", [])  # registry exists; the persona is not in it

    findings, _files, _skipped = validate_path(collab, home=tmp_path / "home")
    assert [f.check for f in findings if f.severity == "error"] == ["runtime-drift"]

    # Opt-out leaves the rest of validate untouched.
    off, _f, _s = validate_path(collab, runtime_drift=False, home=tmp_path / "home")
    assert not [f for f in off if f.check.startswith("runtime-drift")]

    assert runner.invoke(app, ["validate", str(collab), "--no-runtime-drift"]).exit_code == 0
    assert runner.invoke(app, ["validate", str(collab)]).exit_code == 1
