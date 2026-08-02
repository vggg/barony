"""P2.3 — spec↔runtime drift acceptance.

The signal is PARTIAL registration (see baron/drift.py). Every test injects
``home``: the CLI path resolves ``Path.home()`` for real, and an earlier cut of
this suite passed because the DEVELOPER's own ``~/.claude/agents/dev.md``
satisfied a fixture named ``dev``.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from baron import drift
from baron.cli import app
from baron.validate import validate_path

runner = CliRunner()


def _manifest(personas: list[str], adapters: dict | None = None, **extra) -> dict:
    data = {
        "project": {"name": "pilot", "description": "d"},
        "paths": {"strategy": "relative", "root": "."},
        "repos": [{"id": "collab", "path": ".", "role": "collab"}],
        "backlog": {"source": "file", "location": "backlog.md"},
        "personas": [{"slug": s, "spec": f"agents/{s}/persona.yaml"} for s in personas],
    }
    if adapters is not None:
        data["adapters"] = adapters
    data.update(extra)
    return data


def _registry(root: Path, subdir: str, slugs: list[str], suffix: str = ".md") -> Path:
    d = root / subdir
    d.mkdir(parents=True, exist_ok=True)
    for s in slugs:
        (d / f"{s}{suffix}").write_text(f"---\nname: {s}\n---\nagent\n", encoding="utf-8")
    return d


def _dirs(tmp_path: Path) -> tuple[Path, Path]:
    collab, home = tmp_path / "collab", tmp_path / "home"
    collab.mkdir()
    home.mkdir()
    return collab, home


CLAUDE = {"claude": {"tier": "auto"}}


def test_partial_registration_flags_the_gaps(tmp_path: Path) -> None:
    """The pilot shape: 6 of 8 registered, 2 declared-only."""
    collab, home = _dirs(tmp_path)
    _registry(collab, ".claude/agents", ["dev", "librarian", "analyst", "sage"])

    findings = drift.check(
        collab,
        _manifest(["dev", "librarian", "analyst", "sage", "terrence", "carson"], CLAUDE),
        home=home,
    )
    errors = [f for f in findings if f.severity == "error"]
    assert sorted(s for s in ("terrence", "carson") if any(s in f.message for f in errors)) == [
        "carson",
        "terrence",
    ]
    assert len(errors) == 2
    assert "wrong identity" in errors[0].message
    assert "4/6" in errors[0].message  # the evidence that hydration DOES happen here


def test_zero_registered_is_silent(tmp_path: Path) -> None:
    """Tier-2, Tier-1, or not-yet-hydrated. A registry may exist for other
    projects; that alone is not evidence THIS project hydrates agents."""
    collab, home = _dirs(tmp_path)
    _registry(home, ".claude/agents", ["someone-elses-agent"])

    assert drift.check(collab, _manifest(["dev", "terrence"], CLAUDE), home=home) == []


def test_fresh_scaffold_is_silent_even_with_a_user_registry(tmp_path: Path) -> None:
    """B1 regression: `baron init` prints `baron validate .` as the next step, so
    a fresh scaffold must not fail it. Every Claude Code machine has
    ~/.claude/agents, so registry PRESENCE could never have been the signal."""
    collab, home = _dirs(tmp_path)
    _registry(home, ".claude/agents", ["dev", "unrelated-a", "unrelated-b"])

    findings = drift.check(collab, _manifest(["carson", "terrence", "iris"], CLAUDE), home=home)
    assert [f for f in findings if f.severity == "error"] == []


def test_explicit_tier_2_is_never_checked(tmp_path: Path) -> None:
    """HYDRATE.md at Tier 2: 'do NOT emit a dead subagent file'. A correctly
    configured Tier-2 project must not be reported as drift."""
    collab, home = _dirs(tmp_path)
    _registry(collab, ".claude/agents", ["dev"])

    manifest = _manifest(["dev", "terrence"], {"claude": {"tier": 2}})
    assert drift.check(collab, manifest, home=home) == []
    # ...but tier 3 with the same layout IS drift.
    manifest3 = _manifest(["dev", "terrence"], {"claude": {"tier": 3}})
    assert [f.severity for f in drift.check(collab, manifest3, home=home)] == ["error"]


def test_undeclared_and_registryless_runtimes_are_skipped(tmp_path: Path) -> None:
    collab, home = _dirs(tmp_path)
    _registry(collab, ".claude/agents", ["dev"])
    two = ["dev", "ghost"]
    assert drift.check(collab, _manifest(two), home=home) == []  # no adapters block
    assert drift.check(collab, _manifest(two, {"generic": {}}), home=home) == []
    assert drift.check(collab, _manifest(two, {"pydantic-ai": {}}), home=home) == []


def test_frontmatter_name_counts_as_registration(tmp_path: Path) -> None:
    """Claude keys a subagent on frontmatter `name:`, not the filename."""
    collab, home = _dirs(tmp_path)
    d = collab / ".claude/agents"
    d.mkdir(parents=True)
    (d / "dev.md").write_text("---\nname: dev\n---\n", encoding="utf-8")
    (d / "renamed-file.md").write_text("---\nname: terrence\n---\n", encoding="utf-8")

    assert drift.check(collab, _manifest(["dev", "terrence"], CLAUDE), home=home) == []


def test_manifest_paths_root_is_honoured(tmp_path: Path) -> None:
    """repos[].path resolves against paths.root, not the manifest's directory."""
    workspace = tmp_path / "ws"
    collab = workspace / "collab"
    code = workspace / "code"
    collab.mkdir(parents=True)
    code.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    _registry(code, ".claude/agents", ["dev"])

    manifest = _manifest(["dev", "ghost"], CLAUDE, paths={"strategy": "relative", "root": ".."})
    manifest["repos"] = [
        {"id": "collab", "path": "collab", "role": "collab"},
        {"id": "code", "path": "code", "role": "code"},
    ]
    errors = [f for f in drift.check(collab, manifest, home=home) if f.severity == "error"]
    assert len(errors) == 1 and "ghost" in errors[0].message


def test_user_level_only_registration_warns(tmp_path: Path) -> None:
    collab, home = _dirs(tmp_path)
    _registry(collab, ".claude/agents", ["dev"])
    _registry(home, ".claude/agents", ["terrence"])

    findings = drift.check(collab, _manifest(["dev", "terrence"], CLAUDE), home=home)
    assert [f.check for f in findings] == ["runtime-drift-scope"]
    assert "shared across every project" in findings[0].message


def test_code_puppy_registry_shape(tmp_path: Path) -> None:
    """.code_puppy (underscore) + .json — the adapter flags the separator footgun."""
    collab, home = _dirs(tmp_path)
    _registry(collab, ".code_puppy/agents", ["dev"], suffix=".json")

    findings = drift.check(collab, _manifest(["dev", "ghost"], {"code-puppy": {}}), home=home)
    errors = [f for f in findings if f.severity == "error"]
    assert len(errors) == 1 and "ghost" in errors[0].message


def test_gutting_the_check_fails_the_suite(tmp_path: Path) -> None:
    """Guard against a vacuous suite: the partial-registration fixture MUST
    produce findings, so `check` returning [] can never pass silently."""
    collab, home = _dirs(tmp_path)
    _registry(collab, ".claude/agents", ["dev"])
    assert drift.check(collab, _manifest(["dev", "ghost"], CLAUDE), home=home) != []


def test_wired_into_validate_and_opt_out(tmp_path: Path) -> None:
    slug_a, slug_b = "baron-fixture-alpha", "baron-fixture-beta"
    collab = tmp_path / "collab"
    (collab / "agents").mkdir(parents=True)
    (collab / "manifest.yaml").write_text(
        yaml.safe_dump(_manifest([slug_a, slug_b], CLAUDE)), encoding="utf-8"
    )
    _registry(collab, ".claude/agents", [slug_a])  # partial -> slug_b is drift

    findings, _f, _s = validate_path(collab, home=tmp_path / "home")
    assert [f.check for f in findings if f.severity == "error"] == ["runtime-drift"]

    off, _f, _s = validate_path(collab, runtime_drift=False, home=tmp_path / "home")
    assert not [f for f in off if f.check.startswith("runtime-drift")]

    # CLI: repo-scoped registration makes this independent of the real ~/.
    assert runner.invoke(app, ["validate", str(collab), "--no-runtime-drift"]).exit_code == 0
    assert runner.invoke(app, ["validate", str(collab)]).exit_code == 1
