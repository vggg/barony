"""Acceptance for the optional session-ritual primitives (ADR-007).

`baron session start|end` mechanize ONLY the git/markdown bookkeeping of the
session ritual — no agent loop, no model calls. These tests prove the composed
behaviour: the session brief, `--json` shape, `--sync` fast-forward pulls, the
index-regen + scoped coordination commit (persona-attributed), the red-status
exit, and the clean no-op paths.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from baron import handoff, session
from baron.cli import app

from conftest import clone, commit_file, init_bare, init_repo, run_git

runner = CliRunner()

_PERSONA_YAML = """\
persona: Tess
slug: tess
archetype: dev
identity:
  git_name: Tess
  git_email: tess@example.local
  commit_prefix: "tess:"
  routing_label: agent-tess
"""


def _manifest(code_rel: str | None) -> str:
    lines = [
        "project: {name: sess, description: session primitives fixture}",
        "paths: {strategy: relative, root: .}",
        "repos:",
    ]
    if code_rel:
        lines += [f"  - {{id: code, path: {code_rel}, role: code, remote: unused}}"]
    lines += [
        "  - {id: collab, path: ., role: collab}",
        "backlog: {source: file, location: backlog.md}",
        "personas:",
        "  - {slug: tess, spec: agents/tess/persona.yaml}",
    ]
    return "\n".join(lines) + "\n"


def build_collab(tmp_path: Path, *, code_rel: str | None = None) -> Path:
    """A minimal collab repo: manifest, a tess persona spec (commit_prefix), backlog."""
    collab = init_repo(tmp_path / "collab")
    (collab / "agents" / "tess").mkdir(parents=True)
    (collab / "agents" / "tess" / "persona.yaml").write_text(_PERSONA_YAML, encoding="utf-8")
    (collab / "backlog.md").write_text("# backlog\n", encoding="utf-8")
    (collab / "CONVENTIONS.md").write_text("# conventions\n", encoding="utf-8")
    (collab / "COORDINATION.md").write_text("# coordination\n", encoding="utf-8")
    (collab / "manifest.yaml").write_text(_manifest(code_rel), encoding="utf-8")
    run_git(collab, "add", "-A")
    run_git(collab, "commit", "-q", "-m", "collab: bootstrap")
    return collab


def _write_overdue_handoff(collab: Path) -> None:
    """An open handoff created long before the fixed clock — trips the SLA red."""
    (collab / "_handoff").mkdir(exist_ok=True)
    (collab / "_handoff" / "2026-06-01-overdue.md").write_text(
        "---\ncreated: 2026-06-01\nstatus: open\nfor: tess\nfrom: rex\npriority: high\n---\n\n# Overdue\n",
        encoding="utf-8",
    )
    run_git(collab, "add", "-A")
    run_git(collab, "commit", "-q", "-m", "collab: overdue handoff")


# --- start ----------------------------------------------------------------------------


def test_start_surfaces_persona_open_handoff_and_brief(
    tmp_path: Path, fixed_clock: object
) -> None:
    collab = build_collab(tmp_path)
    handoff.create(collab, for_="tess", from_="rex", title="For tess")
    handoff.create(collab, for_="iris", from_="rex", title="For iris")
    handoff.create(collab, for_="all", from_="rex", title="For everyone")

    brief = session.start(collab, persona="tess")
    names = {h.path.name for h in brief.open_handoffs}
    assert "2026-07-22-1200-rex-for-tess.md" in names
    assert "2026-07-22-1200-rex-for-everyone.md" in names  # `all` is addressed to tess too
    assert "2026-07-22-1200-rex-for-iris.md" not in names  # someone else's

    text = session.render_brief(brief)
    assert "session brief" in text
    assert "2026-07-22-1200-rex-for-tess.md" in text
    assert "file — backlog.md" in text  # backlog source + location from the manifest
    assert "CONVENTIONS.md (found)" in text and "COORDINATION.md (found)" in text
    # honesty note: no agent, orchestration is the runtime's job.
    assert "do NOT run an agent" in text and "ADR-007" in text


def test_start_json_shape(tmp_path: Path, fixed_clock: object) -> None:
    collab = build_collab(tmp_path)
    handoff.create(collab, for_="tess", from_="rex", title="Ping")

    result = runner.invoke(
        app, ["session", "start", "--collab", str(collab), "--persona", "tess", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["collab"].endswith("/collab")
    assert payload["persona"] == "tess"
    assert payload["synced"] == []  # no --sync -> read-only
    assert payload["backlog"] == {"source": "file", "location": "backlog.md"}
    assert payload["conventions"] == {"CONVENTIONS.md": True, "COORDINATION.md": True}
    assert any(h["for"] == "tess" for h in payload["open_handoffs"])


def test_start_sync_fast_forward_pulls(tmp_path: Path, fixed_clock: object) -> None:
    origin = init_bare(tmp_path / "origin.git")
    seed = clone(origin, tmp_path / "seed")
    commit_file(seed, "src/app.py", "print('v1')\n", "seed: initial")
    run_git(seed, "push", "-q", "origin", "main")
    code = clone(origin, tmp_path / "code")  # the working copy the manifest names
    # origin gains a commit the code working copy has not pulled.
    drive_by = clone(origin, tmp_path / "drive-by")
    commit_file(drive_by, "src/new.py", "print('v2')\n", "cloud: new file")
    run_git(drive_by, "push", "-q", "origin", "main")

    collab = build_collab(tmp_path, code_rel="../code")
    assert not (code / "src" / "new.py").exists()  # behind before sync

    brief = session.start(collab, persona="tess", sync=True)
    code_sync = next(s for s in brief.synced if s.label == "repo:code")
    assert code_sync.ok, code_sync.detail
    assert (code / "src" / "new.py").exists()  # fast-forwarded
    # the local-only collab repo has no origin -> skipped, never forced.
    collab_sync = next(s for s in brief.synced if s.label == "repo:collab")
    assert collab_sync.ok and "no origin" in collab_sync.detail


def test_start_clean_is_read_only_noop(tmp_path: Path, fixed_clock: object) -> None:
    collab = build_collab(tmp_path)
    before = run_git(collab, "rev-parse", "HEAD")
    result = runner.invoke(app, ["session", "start", "--collab", str(collab)])
    assert result.exit_code == 0, result.output
    assert "open handoffs: none" in result.output
    # read-only: no commit, no sync mutation.
    assert run_git(collab, "rev-parse", "HEAD") == before
    assert run_git(collab, "status", "--porcelain") == ""


# --- end ------------------------------------------------------------------------------


def test_end_regenerates_index_and_commits_with_persona_prefix(
    tmp_path: Path, fixed_clock: object
) -> None:
    collab = build_collab(tmp_path)
    # A dirty coordination artifact (uncommitted) that `end` must stage + commit.
    (collab / "wiki").mkdir()
    (collab / "wiki" / "log.md").write_text("# log\n", encoding="utf-8")

    report = session.end(collab, persona="tess")
    assert report.committed
    assert report.commit_prefix == "tess:"
    assert (collab / "_handoff" / "README.md").is_file()  # index regenerated
    assert "wiki/log.md" in report.committed_paths

    subject = run_git(collab, "log", "-1", "--format=%s").strip()
    assert subject.startswith("tess: session | end")
    # staged by path, never `git add -A`: nothing else lingered.
    assert run_git(collab, "status", "--porcelain") == ""

    # default attribution is baron: when no persona resolves.
    (collab / "wiki" / "log.md").write_text("# log v2\n", encoding="utf-8")
    session.end(collab)
    assert run_git(collab, "log", "-1", "--format=%s").strip().startswith("baron: session | end")


def test_end_exits_one_on_red_status(tmp_path: Path, fixed_clock: object) -> None:
    collab = build_collab(tmp_path)
    _write_overdue_handoff(collab)  # open past the 14d SLA -> red

    result = runner.invoke(app, ["session", "end", "--collab", str(collab), "--persona", "tess"])
    assert result.exit_code == 1, result.output
    assert "handoff-overdue" in result.output


def test_end_clean_is_noop(tmp_path: Path, fixed_clock: object) -> None:
    collab = build_collab(tmp_path)
    # First end settles the index (creates + commits _handoff/README.md).
    session.end(collab, persona="tess")
    assert run_git(collab, "status", "--porcelain") == ""

    # Second end: index regenerates identically, nothing outstanding, status green.
    report = session.end(collab, persona="tess")
    assert not report.committed
    assert report.committed_paths == []
    assert report.reds == 0

    result = runner.invoke(app, ["session", "end", "--collab", str(collab)])
    assert result.exit_code == 0, result.output
    assert "nothing outstanding" in result.output


def test_end_json_shape(tmp_path: Path, fixed_clock: object) -> None:
    collab = build_collab(tmp_path)
    result = runner.invoke(app, ["session", "end", "--collab", str(collab), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["commit_prefix"] == "baron:"
    assert payload["readme"].endswith("_handoff/README.md")
    assert "findings" in payload["status"] and "summary" in payload["status"]
    assert {r["kind"] for r in payload["ledgers"]} <= {"finding", "decision"}
