"""``baron init`` acceptance: canonical layout, self-validation via the real
schemas, persona hydration, runtime kits, git init, and the non-empty-dir refusal."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from baron import ledger
from baron.cli import app
from baron.scaffold import Persona, parse_personas
from baron.validate import validate_path

from conftest import init_repo, run_git

runner = CliRunner()

PERSONAS = "dev:carson,dev:terrence,librarian:iris"


def pretooluse_block(command: str) -> list:
    """The generated PreToolUse block EXACTLY as v1.10.0 emitted it.

    Frozen deliberately (ADR-012 §5): this block already exists, byte for byte,
    in every repo `baron init` has ever generated. ADR-012 adds sibling hook
    blocks around it; if that edit perturbs this one — matcher, command string,
    the 15s timeout, or even key order — downstream repos silently diverge from
    what baron now generates and nothing else would catch it.
    """
    return [
        {
            "matcher": "Bash|Edit|Write|NotebookEdit",
            "hooks": [{"type": "command", "command": command, "timeout": 15}],
        }
    ]


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
        ".github/workflows/strip-stale-verdict.yml",
        ".github/workflows/baron-notify.yml",
    ):
        assert (dest / rel).is_file(), f"missing {rel}"

    # The scaffold passes the real SCHEMAS with zero findings.
    # runtime_drift=False: a fresh scaffold has declared personas and no
    # registered runtime agents by design (Tier-3 hydration is conversational,
    # ADR-006 §3), and the drift check reads the DEVELOPER's real
    # ~/.claude/agents — so leaving it on would make this assertion depend on
    # the machine it runs on. Drift has its own suite: tests/test_drift.py.
    findings, files, _skipped = validate_path(dest, runtime_drift=False)
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
    raw = (dest / "agents/carson/runtime/.claude/settings.json").read_text(
        encoding="utf-8"
    )
    settings = json.loads(raw)
    command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert command.startswith("baron guard --persona-file")
    assert "agents/carson/persona.yaml" in command

    # ENFORCEMENT block: byte-frozen, including key order (ADR-012 §5).
    assert settings["hooks"]["PreToolUse"] == pretooluse_block(command)
    assert json.dumps(settings["hooks"]["PreToolUse"], indent=2) == json.dumps(
        pretooluse_block(command), indent=2
    )
    assert raw.index('"PreToolUse"') < raw.index('"PostToolUse"')

    # EVIDENCE blocks (ADR-012): same one command, dispatched inside baron on
    # hook_event_name. Session events carry no tool name, so no matcher.
    hooks = settings["hooks"]
    assert set(hooks) == {
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "SessionStart",
        "SessionEnd",
    }
    for event in ("PostToolUse", "PostToolUseFailure"):
        assert hooks[event] == [
            {
                "matcher": "Bash|Edit|Write|NotebookEdit",
                "hooks": [{"type": "command", "command": command, "timeout": 5}],
            }
        ], event
    for event in ("SessionStart", "SessionEnd"):
        assert hooks[event] == [
            {"hooks": [{"type": "command", "command": command, "timeout": 5}]}
        ], event
        assert "matcher" not in hooks[event][0]
    # Stop is handled by `baron guard` but deliberately NOT wired: it fires every
    # turn, and its only distinctive power is blocking, which ADR-012 §3 refuses.
    assert "Stop" not in hooks
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


def test_dev_ritual_sweeps_review_feedback_before_backlog(
    tmp_path: Path, fixed_clock: object
) -> None:
    """ADR-008: dev personas clear LIVE review verdicts before claiming new work.

    The token is a known ritual token (so validate raises no warning), it is ordered
    ahead of ``check_backlog``, and every runtime kit renders it as a real step."""
    _, dest = _init(tmp_path / "claude")

    ritual = yaml.safe_load(
        (dest / "agents/carson/persona.yaml").read_text(encoding="utf-8")
    )["session_ritual"]
    assert "check_review_feedback" in ritual
    assert ritual.index("check_review_feedback") < ritual.index("check_backlog")

    # runtime_drift=False: this asserts SCHEMA acceptance of the new ritual token.
    # Leaving drift on would read the developer's real ~/.claude/agents.
    findings, _files, _skipped = validate_path(dest, runtime_drift=False)
    assert not [
        f for f in findings if "check_review_feedback" in f.message
    ], "the new ritual token must be in the known vocabulary"

    # The Tier-2 kit renders the token as prose naming the SHA test, not the token name.
    claude_md = (dest / "agents/carson/runtime/CLAUDE.md").read_text(encoding="utf-8")
    assert "check_review_feedback" not in claude_md
    assert "head SHA" in claude_md and "label" in claude_md

    # Tier-1 kits carry it too — the rule is runtime-neutral.
    _, generic = _init(tmp_path / "generic", "--runtime", "generic")
    agents_md = (generic / "agents/carson/runtime/AGENTS.md").read_text(encoding="utf-8")
    assert "head SHA" in agents_md


def test_strip_stale_verdict_workflow(tmp_path: Path, fixed_clock: object) -> None:
    """ADR-008: the mechanical half of 'a label is not evidence'."""
    _, dest = _init(tmp_path)
    wf_text = (dest / ".github/workflows/strip-stale-verdict.yml").read_text(
        encoding="utf-8"
    )
    wf = yaml.safe_load(wf_text)

    # Fires on every push to an open PR — that is the moment a verdict goes stale.
    # (PyYAML parses a bare `on:` key as the boolean True.)
    assert wf[True]["pull_request"]["types"] == ["synchronize"]
    assert wf["permissions"]["pull-requests"] == "write"

    step = wf["jobs"]["strip"]["steps"][0]
    labels = step["env"]["VERDICT_LABELS"].split()
    assert "reviewed-approved" in labels and "changes-requested" in labels

    # Owner gates are NOT reviewer verdicts and must survive a push. Check by PREFIX,
    # not membership: an exact-match assertion passes vacuously against a longer
    # variant like `needs-human-review`, which is precisely the collision that would
    # auto-strip something only the owner may lift.
    owner_gates = ("needs-human", "hold", "contract-change")
    assert not [
        lab for lab in labels if lab.startswith(owner_gates)
    ], f"owner gate (or a name confusable with one) in the strip list: {labels}"

    # Whole-line, fixed-string matching — see the comment in the workflow.
    assert "grep -qxF" in step["run"]
    # The honest-limitation note travels with the file (the lock-guard precedent).
    assert "HONEST LIMITATION" in wf_text


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
    hooks = json.loads(
        (dest / "agents/carson/runtime/.claude/settings.json").read_text(encoding="utf-8")
    )["hooks"]
    command = hooks["PreToolUse"][0]["hooks"][0]["command"]
    assert "../gardenkit-collab/agents/carson/persona.yaml" in command
    assert hooks["PreToolUse"] == pretooluse_block(command)
    # ADR-012: every hook block resolves the SAME relative persona path — a
    # sibling layout that only rewrote the enforcement hook would leave the
    # evidence hooks pointing at a persona file that does not exist.
    for blocks in hooks.values():
        for block in blocks:
            for entry in block["hooks"]:
                assert entry["command"] == command

    # The generated index headers work with the real ledger allocator.
    n = ledger.add_entry(
        dest, "finding", title="First finding", author="Carson", push=False
    )
    assert n == 1
    assert "### F1 — First finding (2026-07-22, Carson)" in (
        dest / "findings/index.md"
    ).read_text(encoding="utf-8")
