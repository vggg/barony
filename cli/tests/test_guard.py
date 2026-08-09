"""M4 acceptance: ``baron guard`` as a Claude Code PreToolUse hook.

Feeds synthetic hook JSON (the documented stdin shape:
https://code.claude.com/docs/en/hooks — tool_name / tool_input / cwd) to a
real subprocess of the CLI and asserts the documented output contract:
exit 0 = no objection (normal permission flow), exit 2 = block with the
reason on stderr. Also covers the fail-closed error paths and the
BARON_GUARD_OVERRIDE escape hatch (allow + tracked log line).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import commit_file, clone, init_bare, run_git

DEV_PERSONA = """\
persona: Dara
slug: dara
archetype: dev
identity:
  git_name: Dara
  git_email: dara@example.invalid
  commit_prefix: "dara:"
  routing_label: agent-dara
capabilities:
  allow:
    - read_code
    - read_collab
    - write_code
    - write_path: [findings, _handoff]
    - open_pr
    - run_tests
  deny:
    - write_path: [wiki]
    - merge_pr
    - push_main
    - force_push
    - edit_other_personas
scope:
  summary: dev persona
  focus: [implement tickets]
session_ritual: [sync_repos]
"""

MERGER_PERSONA = """\
persona: Mona
slug: mona
archetype: dev
identity:
  git_name: Mona
  git_email: mona@example.invalid
  commit_prefix: "mona:"
  routing_label: agent-mona
capabilities:
  allow:
    - read_code
    - read_collab
    - merge_pr
    - push_main
    - force_push
  deny:
    - write_code
scope:
  summary: merge gate
  focus: [verify preconditions and merge]
session_ritual: [sync_repos]
"""

REVIEWER_PERSONA = """\
persona: Vera
slug: vera
archetype: dev
identity:
  git_name: Vera
  git_email: vera@example.invalid
  commit_prefix: "vera:"
  routing_label: agent-vera
capabilities:
  allow:
    - read_code
    - read_collab
    - write_path: [findings, _handoff]
  deny:
    - write_code
    - write_path: [wiki]
    - merge_pr
    - push_main
    - force_push
    - edit_other_personas
scope:
  summary: read-only reviewer
  focus: [review]
session_ritual: [sync_repos]
"""


@pytest.fixture
def personas(tmp_path: Path) -> dict[str, Path]:
    out = {}
    for name, text in (
        ("dev", DEV_PERSONA),
        ("merger", MERGER_PERSONA),
        ("reviewer", REVIEWER_PERSONA),
    ):
        path = tmp_path / f"{name}-persona.yaml"
        path.write_text(text, encoding="utf-8")
        out[name] = path
    return out


def run_guard(
    persona: Path | None,
    payload: object,
    *,
    override: str | None = None,
    env_persona: Path | None = None,
    events_sink: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        k: v
        for k, v in os.environ.items()
        # BARON_EVENTS_* are filtered so a developer who exports a sink cannot
        # change what these tests observe (ADR-013: the default is silent).
        if k
        not in (
            "BARON_GUARD_OVERRIDE",
            "BARON_PERSONA_FILE",
            "BARON_EVENTS_SINK",
            "BARON_EVENTS_DEBUG",
        )
    }
    if override is not None:
        env["BARON_GUARD_OVERRIDE"] = override
    if events_sink is not None:
        env["BARON_EVENTS_SINK"] = events_sink
    if env_persona is not None:
        env["BARON_PERSONA_FILE"] = str(env_persona)
    args = [sys.executable, "-m", "baron.cli", "guard"]
    if persona is not None:
        args += ["--persona-file", str(persona)]
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        args, input=stdin, capture_output=True, text=True, env=env
    )


def hook(tool: str, tool_input: dict, cwd: Path) -> dict:
    # The documented PreToolUse stdin shape (subset baron consumes).
    return {
        "session_id": "test",
        "hook_event_name": "PreToolUse",
        "cwd": str(cwd),
        "tool_name": tool,
        "tool_input": tool_input,
    }


# --- Bash: push / force / merge -------------------------------------------------------


def test_denied_push_main_blocks(personas: dict[str, Path], tmp_path: Path) -> None:
    proc = run_guard(
        personas["dev"], hook("Bash", {"command": "git push origin main"}, tmp_path)
    )
    assert proc.returncode == 2, proc.stderr
    assert "push_main" in proc.stderr
    assert proc.stdout == ""


def test_feature_branch_push_passes(personas: dict[str, Path], tmp_path: Path) -> None:
    proc = run_guard(
        personas["dev"],
        hook("Bash", {"command": "git push origin dara/42-fix"}, tmp_path),
    )
    assert proc.returncode == 0, proc.stderr


def test_force_push_maps_to_force_push_verb(
    personas: dict[str, Path], tmp_path: Path
) -> None:
    proc = run_guard(
        personas["dev"],
        hook("Bash", {"command": "git push --force origin dara/42-fix"}, tmp_path),
    )
    assert proc.returncode == 2
    assert "force_push" in proc.stderr
    # -f and --force-with-lease are the same verb
    for flag in ("-f", "--force-with-lease"):
        proc = run_guard(
            personas["dev"],
            hook("Bash", {"command": f"git push {flag} origin dara/42-fix"}, tmp_path),
        )
        assert proc.returncode == 2, flag
        assert "force_push" in proc.stderr


def test_persona_with_verbs_always_passes(
    personas: dict[str, Path], tmp_path: Path
) -> None:
    for command in (
        "git push origin main",
        "git push -f origin main",
        "git push",  # even the ambiguous form passes when the verb is granted
        "gh pr merge 12 --squash",
    ):
        proc = run_guard(
            personas["merger"], hook("Bash", {"command": command}, tmp_path)
        )
        assert proc.returncode == 0, (command, proc.stderr)


def test_bare_push_is_conservatively_push_main(
    personas: dict[str, Path], tmp_path: Path
) -> None:
    # cwd is not a git repo: target branch undeterminable -> inferred push_main.
    proc = run_guard(personas["dev"], hook("Bash", {"command": "git push"}, tmp_path))
    assert proc.returncode == 2
    assert "push_main" in proc.stderr
    assert "conservatively" in proc.stderr


def test_bare_push_resolves_upstream_when_cwd_is_a_repo(
    personas: dict[str, Path], tmp_path: Path
) -> None:
    origin = init_bare(tmp_path / "origin.git")
    repo = clone(origin, tmp_path / "repo")
    commit_file(repo, "a.txt", "a\n", "seed: a")
    run_git(repo, "push", "-q", "-u", "origin", "main")
    run_git(repo, "checkout", "-q", "-b", "dara/topic")
    commit_file(repo, "b.txt", "b\n", "dara: b")
    run_git(repo, "push", "-q", "-u", "origin", "dara/topic")
    # Bare push from a feature branch with a feature upstream: not push_main.
    proc = run_guard(personas["dev"], hook("Bash", {"command": "git push"}, repo))
    assert proc.returncode == 0, proc.stderr
    # HEAD:main refspec from the same branch IS push_main.
    proc = run_guard(
        personas["dev"], hook("Bash", {"command": "git push origin HEAD:main"}, repo)
    )
    assert proc.returncode == 2
    assert "push_main" in proc.stderr


def test_git_merge_on_default_branch_blocks(
    personas: dict[str, Path], tmp_path: Path
) -> None:
    origin = init_bare(tmp_path / "origin.git")
    repo = clone(origin, tmp_path / "repo")
    commit_file(repo, "a.txt", "a\n", "seed: a")
    run_git(repo, "push", "-q", "-u", "origin", "main")
    run_git(repo, "branch", "-q", "topic")
    proc = run_guard(
        personas["dev"], hook("Bash", {"command": "git merge topic"}, repo)
    )
    assert proc.returncode == 2
    assert "push_main" in proc.stderr
    # On a feature branch the same command passes (merging main INTO the branch).
    run_git(repo, "checkout", "-q", "topic")
    proc = run_guard(
        personas["dev"], hook("Bash", {"command": "git merge main"}, repo)
    )
    assert proc.returncode == 0, proc.stderr


def test_gh_pr_merge_maps_to_merge_pr(
    personas: dict[str, Path], tmp_path: Path
) -> None:
    proc = run_guard(
        personas["dev"], hook("Bash", {"command": "gh pr merge 12 --squash"}, tmp_path)
    )
    assert proc.returncode == 2
    assert "merge_pr" in proc.stderr


def test_compound_command_is_checked_per_segment(
    personas: dict[str, Path], tmp_path: Path
) -> None:
    proc = run_guard(
        personas["dev"],
        hook(
            "Bash",
            {"command": "git add -A && git commit -m x && git push origin main"},
            tmp_path,
        ),
    )
    assert proc.returncode == 2
    assert "push_main" in proc.stderr


def test_non_git_commands_pass(personas: dict[str, Path], tmp_path: Path) -> None:
    for command in ("ls -la", "pytest -q", "echo done", "git status", "git diff"):
        proc = run_guard(personas["dev"], hook("Bash", {"command": command}, tmp_path))
        assert proc.returncode == 0, (command, proc.stderr)


# --- Edit / Write / NotebookEdit ------------------------------------------------------


def test_write_path_persona_scoping(personas: dict[str, Path], tmp_path: Path) -> None:
    collab = tmp_path / "collab"
    collab.mkdir()
    # Inside a declared scope: allowed.
    proc = run_guard(
        personas["reviewer"],
        hook("Edit", {"file_path": str(collab / "findings" / "index.md")}, collab),
    )
    assert proc.returncode == 0, proc.stderr
    # Outside every declared scope (source dir): blocked.
    proc = run_guard(
        personas["reviewer"],
        hook("Edit", {"file_path": str(collab / "src" / "app.py")}, collab),
    )
    assert proc.returncode == 2
    assert "write_path" in proc.stderr
    # Universal zone: _handoff/ is always writable.
    proc = run_guard(
        personas["reviewer"],
        hook("Write", {"file_path": str(collab / "_handoff" / "2026-07-23-x.md")}, collab),
    )
    assert proc.returncode == 0, proc.stderr
    # NotebookEdit is governed the same way.
    proc = run_guard(
        personas["reviewer"],
        hook("NotebookEdit", {"notebook_path": str(collab / "nb" / "x.ipynb")}, collab),
    )
    assert proc.returncode == 2


def test_write_code_persona_source_writes_pass_but_denied_scope_blocks(
    personas: dict[str, Path], tmp_path: Path
) -> None:
    proc = run_guard(
        personas["dev"],
        hook("Write", {"file_path": str(tmp_path / "src" / "app.py")}, tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    proc = run_guard(
        personas["dev"],
        hook("Edit", {"file_path": str(tmp_path / "wiki" / "status.md")}, tmp_path),
    )
    assert proc.returncode == 2
    assert "wiki" in proc.stderr


def test_out_of_root_write_is_denied_even_with_write_code(
    personas: dict[str, Path], tmp_path: Path
) -> None:
    """FIX 2 defense-in-depth: a target that normalizes ABOVE the collab/persona
    root is denied by the guard itself (not left to the FS jail), even for a
    write_code persona — a Shell `>` redirect escapes both jail and scoping."""
    collab = tmp_path / "collab"
    collab.mkdir()
    # `..` escaping the root: refused
    proc = run_guard(
        personas["dev"],
        hook("Write", {"file_path": str(collab / "findings" / ".." / ".." / "etc" / "x")}, collab),
    )
    assert proc.returncode == 2, proc.stderr
    assert "escapes" in proc.stderr
    # a relative payload with `..` collapsing above root, same verdict
    proc = run_guard(
        personas["dev"],
        hook("Write", {"file_path": "findings/../../outside.md"}, collab),
    )
    assert proc.returncode == 2
    assert "escapes" in proc.stderr
    # sanity: an in-root findings write for the same persona still passes
    proc = run_guard(
        personas["dev"],
        hook("Write", {"file_path": str(collab / "findings" / "ok.md")}, collab),
    )
    assert proc.returncode == 0, proc.stderr


def test_edit_other_personas_gate(personas: dict[str, Path], tmp_path: Path) -> None:
    other = tmp_path / "agents" / "mona" / "persona.yaml"
    own = tmp_path / "agents" / "dara" / "persona.yaml"
    proc = run_guard(personas["dev"], hook("Edit", {"file_path": str(other)}, tmp_path))
    assert proc.returncode == 2
    assert "edit_other_personas" in proc.stderr
    proc = run_guard(personas["dev"], hook("Edit", {"file_path": str(own)}, tmp_path))
    assert proc.returncode == 0, proc.stderr


# --- unknown tools, override, fail-closed ---------------------------------------------


def test_unknown_tools_pass(personas: dict[str, Path], tmp_path: Path) -> None:
    proc = run_guard(
        personas["reviewer"], hook("WebFetch", {"url": "https://example.com"}, tmp_path)
    )
    assert proc.returncode == 0, proc.stderr


def test_override_allows_and_logs(personas: dict[str, Path], tmp_path: Path) -> None:
    cwd = tmp_path / "work"
    cwd.mkdir()
    proc = run_guard(
        personas["dev"],
        hook("Bash", {"command": "git push origin main"}, cwd),
        override="hotfix F51, owner approved in chat",
    )
    assert proc.returncode == 0, proc.stderr
    log = cwd / ".baron" / "guard-override.log"
    assert log.is_file()
    line = log.read_text(encoding="utf-8").strip()
    assert "git push origin main" in line
    assert "hotfix F51, owner approved in chat" in line
    assert "Bash" in line


def test_malformed_stdin_denies(personas: dict[str, Path]) -> None:
    proc = run_guard(personas["dev"], "this is not json {")
    assert proc.returncode == 2
    assert "fail closed" in proc.stderr


def test_missing_persona_file_denies_with_actionable_stderr(tmp_path: Path) -> None:
    proc = run_guard(
        None, hook("Bash", {"command": "git push origin main"}, tmp_path)
    )
    assert proc.returncode == 2
    assert "BARON_PERSONA_FILE" in proc.stderr


def test_unreadable_persona_file_denies(tmp_path: Path) -> None:
    proc = run_guard(
        tmp_path / "missing.yaml",
        hook("Bash", {"command": "git push origin main"}, tmp_path),
    )
    assert proc.returncode == 2
    assert "persona file not found" in proc.stderr


def test_env_persona_file_is_honored(
    personas: dict[str, Path], tmp_path: Path
) -> None:
    proc = run_guard(
        None,
        hook("Bash", {"command": "git push origin main"}, tmp_path),
        env_persona=personas["dev"],
    )
    assert proc.returncode == 2
    assert "push_main" in proc.stderr


# --- ADR-013: observation events on the verdict path ----------------------------------
#
# These assert the event stream, never the verdict. Every verdict test above runs
# unmodified and must stay that way: emission is additive and consequence-free.


def _rows(root: Path) -> list[dict]:
    """Every JSONL row the disk sink wrote under ``root``, in file order."""
    out: list[dict] = []
    for path in sorted((root / ".baron" / "events").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            out.append(json.loads(line))
    return out


def test_denied_call_emits_one_deny_event(
    personas: dict[str, Path], tmp_path: Path
) -> None:
    proc = run_guard(
        personas["dev"],
        hook("Bash", {"command": "git push origin main"}, tmp_path),
        events_sink="disk",
    )
    assert proc.returncode == 2, proc.stderr

    rows = _rows(tmp_path)
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["span_name"] == "guard.decision"
    attrs = row["attributes"]
    assert attrs["baron.outcome"] == "deny"
    assert attrs["baron.capability.verb"] == "push_main"
    assert attrs["baron.enforcement"] == "enforced"
    assert attrs["baron.actor"] == "dara"
    assert attrs["agent.name"] == "dara"
    assert attrs["tool.name"] == "Bash"
    assert attrs["session.id"] == "test"
    assert attrs["baron.subject"] == "git push origin main"
    assert attrs["events.version"] == 1
    assert (tmp_path / ".baron/events/.gitignore").read_text(encoding="utf-8") == "*\n"


def test_allowed_call_emits_one_allow_event(
    personas: dict[str, Path], tmp_path: Path
) -> None:
    proc = run_guard(
        personas["dev"],
        hook("Bash", {"command": "git push origin dara/42-fix"}, tmp_path),
        events_sink="disk",
    )
    assert proc.returncode == 0, proc.stderr

    rows = _rows(tmp_path)
    assert len(rows) == 1, rows
    assert rows[0]["span_name"] == "guard.decision"
    assert rows[0]["attributes"]["baron.outcome"] == "allow"


def test_override_emits_an_override_event_and_leaves_the_tracked_log_alone(
    personas: dict[str, Path], tmp_path: Path
) -> None:
    """The tab-separated TRACKED override log stays byte-for-byte what it was."""
    cwd = tmp_path / "work"
    cwd.mkdir()
    proc = run_guard(
        personas["dev"],
        hook("Bash", {"command": "git push origin main"}, cwd),
        override="hotfix F51, owner approved in chat",
        events_sink="disk",
    )
    assert proc.returncode == 0, proc.stderr

    line = (cwd / ".baron" / "guard-override.log").read_text(encoding="utf-8")
    fields = line.rstrip("\n").split("\t")
    assert len(fields) == 4
    assert fields[1:] == [
        "Bash",
        "git push origin main",
        "hotfix F51, owner approved in chat",
    ]

    rows = _rows(cwd)
    assert len(rows) == 1, rows
    assert rows[0]["span_name"] == "guard.override"
    assert rows[0]["attributes"]["baron.outcome"] == "override"


def test_fail_closed_path_emits_an_error_event(tmp_path: Path) -> None:
    """A fail-closed deny is still observed — with the honest "not-applicable"
    enforcement label, because no verb was ever mapped."""
    proc = run_guard(
        tmp_path / "missing.yaml",
        hook("Bash", {"command": "git push origin main"}, tmp_path),
        events_sink="disk",
    )
    assert proc.returncode == 2
    assert "persona file not found" in proc.stderr

    rows = _rows(tmp_path)
    assert len(rows) == 1, rows
    attrs = rows[0]["attributes"]
    assert rows[0]["span_name"] == "guard.decision"
    assert attrs["baron.outcome"] == "error"
    assert attrs["baron.enforcement"] == "not-applicable"
    assert attrs["baron.actor"] == "unknown"
    assert "persona file not found" in str(attrs["baron.error"])


def test_with_the_sink_unset_the_baron_tree_is_untouched(
    personas: dict[str, Path], tmp_path: Path
) -> None:
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    proc = run_guard(
        personas["dev"], hook("Bash", {"command": "git push origin main"}, tmp_path)
    )
    assert proc.returncode == 2
    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert before == after
    assert not (tmp_path / ".baron").exists()


def test_sink_failure_does_not_change_guard_exit_code(
    personas: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard is fail-CLOSED; evidence emission is fail-OPEN (ADR-013 §4).

    A sink that raises must not brick a session — and must not silently flip a
    deny into an allow either. Both exit codes are pinned.
    """
    from baron import events as events_mod
    from baron import guard as guard_mod

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("sink is on fire")

    monkeypatch.setattr(events_mod, "emit", explode)
    monkeypatch.delenv("BARON_GUARD_OVERRIDE", raising=False)

    deny = guard_mod.process(
        json.dumps(hook("Bash", {"command": "git push origin main"}, tmp_path)),
        personas["dev"],
    )
    assert deny[0] == 2
    assert "push_main" in deny[1]

    allow = guard_mod.process(
        json.dumps(hook("Bash", {"command": "git push origin dara/42-fix"}, tmp_path)),
        personas["dev"],
    )
    assert allow == (0, "")


def test_enforcement_label_is_derived_never_hardcoded() -> None:
    """capability-rules.v1.yaml sets ``detection: none`` for open_pr / run_tests.
    Labelling those "enforced" is the overclaiming ADR-002/ADR-008 forbid."""
    from baron import guard as guard_mod

    assert guard_mod._enforcement(("push_main",)) == "enforced"
    assert guard_mod._enforcement(("write_path",)) == "enforced"
    assert guard_mod._enforcement(("open_pr",)) == "instructed"
    assert guard_mod._enforcement(("run_tests",)) == "instructed"
    assert guard_mod._enforcement(()) == "not-applicable"
    # A mixed call is enforced if ANY mapped verb is mechanically detected.
    assert guard_mod._enforcement(("open_pr", "push_main")) == "enforced"


def test_every_verb_in_the_rules_artifact_gets_the_label_its_detection_implies() -> None:
    """Drift guard: a new detection value must not silently become "instructed"."""
    from baron import guard as guard_mod
    from baron.rules import load_rules

    verbs = load_rules().verbs
    detections = {entry.get("detection", "none") for entry in verbs.values()}
    assert detections <= {"none", "command", "file-op"}, detections
    for verb, entry in verbs.items():
        expected = (
            "enforced"
            if entry.get("detection") in ("command", "file-op")
            else "instructed"
        )
        assert guard_mod._enforcement((verb,)) == expected, verb
