"""``baron init`` acceptance: canonical layout, self-validation via the real
schemas, persona hydration, runtime kits, git init, and the non-empty-dir refusal."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from baron import ledger
from baron.cli import app
from baron.scaffold import Persona, parse_personas
from baron.validate import validate_path

from conftest import init_repo, run_git

runner = CliRunner()

PERSONAS = "dev:carson,dev:terrence,librarian:iris"


def _init(tmp_path: Path, *extra: str, personas: str = PERSONAS):
    dest = tmp_path / "gardenkit-collab"
    result = runner.invoke(
        app,
        ["init", "gardenkit", "--dir", str(dest), "--personas", personas, *extra],
    )
    return result, dest


def test_layout_manifest_and_self_validation(tmp_path: Path, fixed_clock: object) -> None:
    result, dest = _init(tmp_path)
    assert result.exit_code == 0, result.output

    for rel in (
        "CONVENTIONS.md",
        "COORDINATION.md",
        "README.md",
        "manifest.yaml",
        "backlog.md",
        "canon/START.md",
        "canon/ORCHESTRATE.md",
        "canon/PARTICIPATE.md",
        "canon/capability-vocab.v1.md",
        "canon/capability-rules.md",
        "canon/persona.schema.md",
        "canon/manifest.schema.md",
        "adapters/claude/HYDRATE.md",
        "adapters/code-puppy/HYDRATE.md",
        "adapters/pydantic-ai/HYDRATE.md",
        "adapters/generic/HYDRATE.md",
        "agents/carson/persona.yaml",
        "agents/terrence/persona.yaml",
        "agents/iris/persona.yaml",
        "_handoff/README.md",
        "_handoff/2026-07-22-bootstrap-to-iris-genesis.md",
        "findings/README.md",
        "findings/index.md",
        "decisions/README.md",
        "decisions/index.md",
        "wiki/README.md",
        "wiki/index.md",
        "wiki/log.md",
        ".github/workflows/lock-guard.yml",
    ):
        assert (dest / rel).is_file(), f"missing {rel}"

    # The scaffold passes the real schemas with zero findings.
    findings, files, _skipped = validate_path(dest)
    assert [f.to_dict() for f in findings] == []
    assert len(files) == 4  # manifest + 3 personas

    # No template docs leaked an unfilled token (validate only covers yaml).
    for rel in ("CONVENTIONS.md", "COORDINATION.md", "_handoff/README.md", "wiki/index.md"):
        assert "{{" not in (dest / rel).read_text(encoding="utf-8"), rel

    # Persona hydration: identity domain, slug, librarian rename (archetype kept).
    carson = (dest / "agents/carson/persona.yaml").read_text(encoding="utf-8")
    assert "slug: carson" in carson and "carson@gardenkit.local" in carson
    iris = (dest / "agents/iris/persona.yaml").read_text(encoding="utf-8")
    assert "persona: Iris" in iris and "archetype: librarian" in iris
    assert "routing_label: agent-iris" in iris

    # Genesis handoff is open, dated by the injectable clock, addressed to the librarian.
    genesis = (dest / "_handoff/2026-07-22-bootstrap-to-iris-genesis.md").read_text(
        encoding="utf-8"
    )
    assert "status: open" in genesis and "for: iris" in genesis

    # Next-steps block printed.
    assert "next steps:" in result.output
    assert "baron validate ." in result.output


def test_git_initialized_with_clean_first_commit(tmp_path: Path, fixed_clock: object) -> None:
    result, dest = _init(tmp_path)
    assert result.exit_code == 0, result.output
    assert (dest / ".git").is_dir()
    assert run_git(dest, "branch", "--show-current").strip() == "main"
    assert "baron: init | scaffold gardenkit" in run_git(dest, "log", "-1", "--format=%s")
    assert run_git(dest, "status", "--porcelain").strip() == ""  # everything committed


def test_no_git_flag(tmp_path: Path, fixed_clock: object) -> None:
    result, dest = _init(tmp_path, "--no-git")
    assert result.exit_code == 0, result.output
    assert not (dest / ".git").exists()


def test_reinit_refuses_non_empty_dir(tmp_path: Path, fixed_clock: object) -> None:
    result, dest = _init(tmp_path)
    assert result.exit_code == 0, result.output
    again = runner.invoke(
        app, ["init", "gardenkit", "--dir", str(dest), "--personas", PERSONAS]
    )
    assert again.exit_code == 1
    assert "not empty" in again.output
    # An existing-but-empty dir is fine.
    empty = tmp_path / "empty"
    empty.mkdir()
    ok = runner.invoke(
        app, ["init", "gardenkit", "--dir", str(empty), "--personas", PERSONAS, "--no-git"]
    )
    assert ok.exit_code == 0, ok.output


def test_persona_spec_errors_are_usage_errors(tmp_path: Path) -> None:
    for personas in ("dev", "wizard:carson", "dev:carson,dev:carson", "dev:Carson"):
        result, _ = _init(tmp_path / personas.replace(":", "_"), personas=personas)
        assert result.exit_code == 2, (personas, result.output)


def test_librarian_added_when_missing() -> None:
    roster = parse_personas("dev:carson")
    assert roster == [Persona("dev", "carson"), Persona("librarian", "librarian")]
    with pytest.raises(Exception, match="librarian"):
        parse_personas("dev:librarian")


def test_runtime_kits_per_runtime(tmp_path: Path, fixed_clock: object) -> None:
    # claude (default): Tier-2 CLAUDE.md + the guard hook settings.
    _, dest = _init(tmp_path / "claude")
    settings = json.loads(
        (dest / "agents/carson/runtime/.claude/settings.json").read_text(encoding="utf-8")
    )
    command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert command.startswith("baron guard --persona-file")
    assert "agents/carson/persona.yaml" in command
    claude_md = (dest / "agents/carson/runtime/CLAUDE.md").read_text(encoding="utf-8")
    assert "Never merge a pull request." in claude_md
    assert "INSTRUCTED" in claude_md  # honest tier note

    # generic + code-puppy: Tier-1 AGENTS.md.
    for rt in ("generic", "code-puppy"):
        _, dest = _init(tmp_path / rt, "--runtime", rt)
        agents_md = (dest / "agents/carson/runtime/AGENTS.md").read_text(encoding="utf-8")
        assert "instruction-only" in agents_md

    # pydantic-ai: the emitted bootstrap (emission needs no extra installed).
    _, dest = _init(tmp_path / "pai", "--runtime", "pydantic-ai")
    setup = (dest / "agents/carson/runtime/agent_setup.py").read_text(encoding="utf-8")
    assert "build_agent" in setup and "agents/carson/persona.yaml" in setup

    result, _ = _init(tmp_path / "bad", "--runtime", "emacs")
    assert result.exit_code == 2


def test_code_repo_recorded_and_ledger_usable(tmp_path: Path, fixed_clock: object) -> None:
    code = init_repo(tmp_path / "gardenkit")
    (code / "README.md").write_text("code\n", encoding="utf-8")
    run_git(code, "add", "README.md")
    run_git(code, "commit", "-q", "-m", "init")

    result, dest = _init(tmp_path, "--code-repo", str(code))
    assert result.exit_code == 0, result.output
    manifest = (dest / "manifest.yaml").read_text(encoding="utf-8")
    assert "role: code" in manifest and "path: ../gardenkit" in manifest
    assert "worktrees_root: ../gardenkit-worktrees" in manifest
    # With a code repo, the claude kit's guard hook points across the sibling layout.
    command = json.loads(
        (dest / "agents/carson/runtime/.claude/settings.json").read_text(encoding="utf-8")
    )["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "../gardenkit-collab/agents/carson/persona.yaml" in command

    # The generated index headers work with the real ledger allocator.
    n = ledger.add_entry(
        dest, "finding", title="First finding", author="Carson", push=False
    )
    assert n == 1
    assert "### F1 — First finding (2026-07-22, Carson)" in (
        dest / "findings/index.md"
    ).read_text(encoding="utf-8")
