"""ADR-029 — the `observer` archetype is read-only, and the read-only-ness is
enforced rather than described.

Two halves, matching the ADR's honest bound:

- **Scaffold**: `baron init --personas observer:<slug>` hydrates the archetype,
  records its own `archetype:` (not `dev`), validates clean, and emits the
  `observations/` zone — only when the roster actually carries an observer.
- **Guard**: the hydrated spec, fed to a real `baron guard` subprocess, blocks
  a write to every other zone plus merge/push/force-push, and allows the two
  paths the archetype exists to write. If this ever passes vacuously the
  archetype is prose, which is the thing the ADR says it must not be.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

from baron import schemas
from baron.cli import app
from baron.scaffold import ARCHETYPE_TEMPLATES

runner = CliRunner()


def _init(dest: Path, personas: str) -> None:
    result = runner.invoke(
        app, ["init", "barony", "--dir", str(dest), "--personas", personas]
    )
    assert result.exit_code == 0, result.output


# --- the archetype exists end to end --------------------------------------------------


def test_observer_is_a_shipped_archetype() -> None:
    assert "observer" in ARCHETYPE_TEMPLATES
    assert "observer" in schemas.ARCHETYPES
    assert "observations" in schemas.WRITE_PATH_SCOPES


def test_scaffolding_an_observer_validates_clean(tmp_path: Path, fixed_clock: object) -> None:
    dest = tmp_path / "collab"
    _init(dest, "observer:oscar,dev:carson,librarian:iris")
    result = runner.invoke(app, ["validate", str(dest)])
    assert result.exit_code == 0, result.output
    assert "archetype" not in result.output  # the enum must know the new value


def test_the_hydrated_observer_is_read_only(tmp_path: Path, fixed_clock: object) -> None:
    dest = tmp_path / "collab"
    _init(dest, "observer:oscar,librarian:iris")
    spec = yaml.safe_load(
        (dest / "agents" / "oscar" / "persona.yaml").read_text(encoding="utf-8")
    )
    assert spec["archetype"] == "observer"

    def scopes(items: list) -> set[str]:
        out: set[str] = set()
        for item in items:
            if isinstance(item, dict):
                out.update(item.get("write_path", []))
        return out

    allow, deny = spec["capabilities"]["allow"], spec["capabilities"]["deny"]
    plain_allow = {i for i in allow if isinstance(i, str)}
    plain_deny = {i for i in deny if isinstance(i, str)}

    # It may read everything...
    assert {"read_code", "read_collab"} <= plain_allow
    # ...and write exactly two scopes, one of which is its own zone.
    assert scopes(allow) == {"observations", "_handoff"}
    # No write verb, no delivery verb, no numbering surface.
    assert {
        "write_code",
        "open_pr",
        "merge_pr",
        "push_main",
        "force_push",
        "edit_other_personas",
    } <= plain_deny
    assert {"findings", "decisions", "wiki"} <= scopes(deny)


def test_the_observations_zone_is_emitted_only_with_an_observer(
    tmp_path: Path, fixed_clock: object
) -> None:
    with_obs = tmp_path / "with"
    _init(with_obs, "observer:oscar,librarian:iris")
    assert (with_obs / "observations" / "README.md").is_file()
    index = (with_obs / "observations" / "index.md").read_text(encoding="utf-8")
    assert "oscar" in index
    # Deliberately NOT a numbered ledger (ADR-029 §2.1) — the observer holds no
    # numbering authority, so nothing here allocates an ID.
    assert "O1" not in index
    assert "_handoff" in index

    without = tmp_path / "without"
    _init(without, "dev:carson,librarian:iris")
    assert not (without / "observations").exists()


# --- guard: the write boundary is mechanical ------------------------------------------


def _run_guard(persona: Path, tool: str, tool_input: dict, cwd: Path):
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in ("BARON_GUARD_OVERRIDE", "BARON_PERSONA_FILE", "BARON_EVENTS_SINK")
    }
    payload = {
        "session_id": "test",
        "hook_event_name": "PreToolUse",
        "cwd": str(cwd),
        "tool_name": tool,
        "tool_input": tool_input,
    }
    return subprocess.run(
        [sys.executable, "-m", "baron.cli", "guard", "--persona-file", str(persona)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


def _observer_spec(tmp_path: Path) -> tuple[Path, Path]:
    dest = tmp_path / "collab"
    _init(dest, "observer:oscar,librarian:iris")
    return dest / "agents" / "oscar" / "persona.yaml", dest


def test_guard_allows_the_observers_own_zone(tmp_path: Path, fixed_clock: object) -> None:
    spec, collab = _observer_spec(tmp_path)
    for target in ("observations/2026-08-14-first-pass.md", "_handoff/2026-08-14-to-iris.md"):
        proc = _run_guard(spec, "Write", {"file_path": str(collab / target)}, collab)
        assert proc.returncode == 0, f"{target}: {proc.stderr}"


def test_guard_blocks_every_other_zone(tmp_path: Path, fixed_clock: object) -> None:
    spec, collab = _observer_spec(tmp_path)
    for target in (
        "findings/index.md",  # no numbering authority
        "decisions/index.md",
        "wiki/log.md",
        "CONVENTIONS.md",
        "backlog.md",
    ):
        proc = _run_guard(spec, "Write", {"file_path": str(collab / target)}, collab)
        assert proc.returncode == 2, f"{target} was NOT blocked: {proc.stdout!r}"


def test_guard_blocks_another_personas_spec(tmp_path: Path, fixed_clock: object) -> None:
    spec, collab = _observer_spec(tmp_path)
    proc = _run_guard(
        spec, "Edit", {"file_path": str(collab / "agents" / "iris" / "persona.yaml")}, collab
    )
    assert proc.returncode == 2, proc.stdout
    assert "edit_other_personas" in proc.stderr


def test_guard_blocks_the_command_verbs(tmp_path: Path, fixed_clock: object) -> None:
    spec, collab = _observer_spec(tmp_path)
    for command, verb in (
        ("git push origin main", "push_main"),
        ("git push --force origin oscar/notes", "force_push"),
        ("gh pr merge 44 --squash", "merge_pr"),
    ):
        proc = _run_guard(spec, "Bash", {"command": command}, collab)
        assert proc.returncode == 2, f"{command} was NOT blocked"
        assert verb in proc.stderr
