"""ADR-025 — the coordination monorepo: `baron init --layout monorepo`,
`baron add-project`, and the portfolio-wide reads.

The load-bearing claims, in order:
- monorepo init emits a ROOT (marker, README, one shared .github/) plus a project SUBDIR;
- add-project grafts a valid subdir into an existing root and refuses on anything else;
- portfolio status/health/validate aggregate across the registered subdirs;
- single-project behaviour is unchanged — the default layout is still one collab repo,
  and every command run INSIDE a subdir behaves exactly as it does in a standalone repo;
- the wake carries the project so the root's gate can route into it.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from baron import monorepo
from baron.cli import app

from conftest import run_git

runner = CliRunner()


def _init_mono(tmp_path: Path, *extra: str) -> Path:
    root = tmp_path / "fleet-coordination"
    result = runner.invoke(
        app,
        ["init", "fleet-coordination", "--dir", str(root), "--layout", "monorepo", *extra],
    )
    assert result.exit_code == 0, result.output
    return root


# --- init --layout monorepo -------------------------------------------------------------


def test_init_monorepo_emits_root_plus_first_project_subdir(
    tmp_path: Path, fixed_clock: object
) -> None:
    root = _init_mono(tmp_path)

    # The root: marker, README, and the CI seam owned once.
    assert (root / monorepo.MARKER).is_file()
    assert (root / "README.md").is_file()
    for wf in ("baron-notify.yml", "lock-guard.yml", "strip-stale-verdict.yml"):
        assert (root / ".github" / "workflows" / wf).is_file()
    # The root is NOT itself a project.
    assert not (root / "manifest.yaml").exists()

    # The first project is the portfolio project, as a full collab-repo scaffold.
    meta = root / monorepo.META_DIR
    for rel in (
        "manifest.yaml", "CONVENTIONS.md", "COORDINATION.md", "backlog.md",
        "_handoff", "decisions/index.md", "findings/index.md", "wiki/log.md",
        "agents/librarian/persona.yaml", "canon/START.md", "adapters/claude/HYDRATE.md",
    ):
        assert (meta / rel).exists(), rel
    # ...but CI and git stay at the root.
    assert not (meta / ".github").exists()
    assert not (meta / ".git").exists()
    assert (root / ".git").is_dir()


def test_init_monorepo_marker_registers_the_first_project(
    tmp_path: Path, fixed_clock: object
) -> None:
    root = _init_mono(tmp_path)
    data = yaml.safe_load((root / monorepo.MARKER).read_text(encoding="utf-8"))
    assert data["layout"] == "monorepo"
    assert data["projects"] == [{"dir": "_meta", "name": "meta"}]

    repo = monorepo.load(root)
    assert [p.dir for p in repo.projects] == ["_meta"]
    assert repo.unregistered == []
    assert monorepo.is_root(root)
    assert not monorepo.is_root(root / "_meta")


def test_meta_subdir_keeps_a_hostname_safe_project_name(
    tmp_path: Path, fixed_clock: object
) -> None:
    """The subdir is `_meta`; the PROJECT is `meta`, because the project name becomes
    the git identity domain <slug>@<project>.local (ADR-025 §7 Q3)."""
    root = _init_mono(tmp_path)
    persona = yaml.safe_load(
        (root / "_meta" / "agents" / "librarian" / "persona.yaml").read_text(encoding="utf-8")
    )
    assert persona["identity"]["git_email"] == "librarian@meta.local"
    manifest = yaml.safe_load((root / "_meta" / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["project"]["name"] == "meta"


def test_init_monorepo_commits_once_at_the_root(tmp_path: Path, fixed_clock: object) -> None:
    root = _init_mono(tmp_path)
    assert run_git(root, "status", "--porcelain").strip() == ""
    tracked = run_git(root, "ls-files").split()
    assert "_meta/manifest.yaml" in tracked
    assert ".baron-monorepo.yaml" in tracked


def test_default_layout_is_still_one_collab_repo(tmp_path: Path, fixed_clock: object) -> None:
    """Per-project-repo remains the DEFAULT (ADR-025 §7 Q4) — unchanged, git and all."""
    dest = tmp_path / "gardenkit-collab"
    result = runner.invoke(app, ["init", "gardenkit", "--dir", str(dest)])
    assert result.exit_code == 0, result.output
    assert (dest / "manifest.yaml").is_file()
    assert (dest / ".git").is_dir()
    assert (dest / ".github" / "workflows" / "baron-notify.yml").is_file()
    assert not (dest / monorepo.MARKER).exists()


def test_unknown_layout_is_a_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["init", "x", "--dir", str(tmp_path / "x"), "--layout", "polyrepo"]
    )
    assert result.exit_code == 2
    assert "--layout" in result.output


# --- add-project ------------------------------------------------------------------------


def test_add_project_grafts_a_valid_subdir(tmp_path: Path, fixed_clock: object) -> None:
    root = _init_mono(tmp_path)
    code = tmp_path / "barony-code"
    code.mkdir()
    result = runner.invoke(
        app,
        [
            "add-project", "barony", "--root", str(root),
            "--code-repo", str(code), "--personas", "dev:carson,librarian:iris",
        ],
    )
    assert result.exit_code == 0, result.output

    project = root / "barony"
    for rel in (
        "manifest.yaml", "agents/carson/persona.yaml", "agents/iris/persona.yaml",
        "_handoff", "decisions/index.md", "findings/index.md", "wiki/log.md",
    ):
        assert (project / rel).exists(), rel
    assert not (project / ".github").exists()

    manifest = yaml.safe_load((project / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["project"]["name"] == "barony"
    # The code repo is per-project and resolved from the SUBDIR.
    code_repo = next(r for r in manifest["repos"] if r["role"] == "code")
    assert code_repo["path"] == "../../barony-code"
    # ...so the worktrees root stays a sibling of the MONOREPO, not a stray dir inside it.
    assert manifest["workspace"]["worktrees_root"] == "../../barony-worktrees"

    assert [p.dir for p in monorepo.load(root).projects] == ["_meta", "barony"]
    assert "barony" in (root / "README.md").read_text(encoding="utf-8")
    assert run_git(root, "status", "--porcelain").strip() == ""


def test_add_project_refuses_outside_a_monorepo(tmp_path: Path, fixed_clock: object) -> None:
    dest = tmp_path / "gardenkit-collab"
    assert runner.invoke(app, ["init", "gardenkit", "--dir", str(dest)]).exit_code == 0
    result = runner.invoke(app, ["add-project", "barony", "--root", str(dest)])
    assert result.exit_code == 2
    assert "not a coordination-monorepo root" in result.output


def test_add_project_refuses_a_duplicate_and_a_path(tmp_path: Path, fixed_clock: object) -> None:
    root = _init_mono(tmp_path)
    dup = runner.invoke(app, ["add-project", "_meta", "--root", str(root)])
    assert dup.exit_code == 2 and "already registered" in dup.output
    traversal = runner.invoke(app, ["add-project", "../escape", "--root", str(root)])
    assert traversal.exit_code == 2 and "plain directory name" in traversal.output


def test_add_project_runtime_kit_points_back_through_the_monorepo(
    tmp_path: Path, fixed_clock: object
) -> None:
    """A kit installed in a sibling code clone must reach <monorepo>/<project>."""
    root = _init_mono(tmp_path)
    code = tmp_path / "barony-code"
    code.mkdir()
    assert runner.invoke(
        app, ["add-project", "barony", "--root", str(root), "--code-repo", str(code)]
    ).exit_code == 0
    kit = (root / "barony" / "agents" / "dev" / "runtime" / "CLAUDE.md").read_text(
        encoding="utf-8"
    )
    assert "../fleet-coordination/barony/agents/dev/persona.yaml" in kit


# --- portfolio-wide reads ---------------------------------------------------------------


def test_status_at_the_root_aggregates_every_project(
    tmp_path: Path, fixed_clock: object
) -> None:
    root = _init_mono(tmp_path)
    assert runner.invoke(app, ["add-project", "barony", "--root", str(root)]).exit_code == 0

    result = runner.invoke(app, ["status", "--collab", str(root), "--json"])
    payload = json.loads(result.output)
    assert payload["layout"] == "monorepo"
    assert set(payload["projects"]) == {"_meta", "barony"}
    assert payload["summary"]["projects"] == 2

    human = runner.invoke(app, ["status", "--collab", str(root)])
    assert "portfolio: 2 project(s)" in human.output
    assert "portfolio total:" in human.output


def test_portfolio_status_surfaces_a_red_from_one_project(
    tmp_path: Path, fixed_clock: object
) -> None:
    root = _init_mono(tmp_path)
    assert runner.invoke(app, ["add-project", "barony", "--root", str(root)]).exit_code == 0
    # An overdue open handoff in ONE project must red the portfolio.
    stale = root / "barony" / "_handoff" / "2026-01-01-someone-to-dev-stale.md"
    stale.write_text(
        "---\ncreated: 2026-01-01\nstatus: open\nfor: dev\nfrom: someone\n---\n\nold\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["status", "--collab", str(root), "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["projects"]["barony"]["summary"]["red"] == 1
    assert payload["projects"]["_meta"]["summary"]["red"] == 0
    assert payload["summary"]["red"] == 1


def test_status_inside_a_subdir_is_single_project(tmp_path: Path, fixed_clock: object) -> None:
    root = _init_mono(tmp_path)
    result = runner.invoke(app, ["status", "--collab", str(root / "_meta"), "--json"])
    payload = json.loads(result.output)
    assert "layout" not in payload  # the plain single-project shape, unchanged
    assert payload["collab"].endswith("_meta")


def test_health_at_the_root_rolls_up_per_project(tmp_path: Path, fixed_clock: object) -> None:
    root = _init_mono(tmp_path)
    assert runner.invoke(app, ["add-project", "barony", "--root", str(root)]).exit_code == 0
    result = runner.invoke(app, ["health", "--collab", str(root), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["layout"] == "monorepo"
    assert set(payload["projects"]) == {"_meta", "barony"}
    assert payload["summary"] == {
        "projects": 2, "verdicts": 0,
        "mutation_kill": {"killed": 0, "run": 0, "rate": None},
        "claim_drift": 0, "reviewer_escapes": 0, "stalls": 0,
    }
    human = runner.invoke(app, ["health", "--collab", str(root)])
    assert "portfolio health" in human.output


def test_validate_at_the_root_covers_every_project(tmp_path: Path, fixed_clock: object) -> None:
    root = _init_mono(tmp_path)
    assert runner.invoke(app, ["add-project", "barony", "--root", str(root)]).exit_code == 0
    result = runner.invoke(
        app, ["validate", str(root), "--json", "--no-runtime-drift"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["layout"] == "monorepo"
    assert payload["projects"] == ["_meta", "barony"]
    checked = " ".join(payload["files_checked"])
    assert "_meta/manifest.yaml" in checked and "barony/manifest.yaml" in checked
    assert payload["summary"]["errors"] == 0


def test_validate_warns_on_an_unregistered_project_subdir(
    tmp_path: Path, fixed_clock: object
) -> None:
    """A manifest-carrying subdir the marker does not list is skipped by portfolio
    reads — say so rather than let it vanish."""
    root = _init_mono(tmp_path)
    stray = root / "orphan"
    stray.mkdir()
    (stray / "manifest.yaml").write_text(
        (root / "_meta" / "manifest.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert monorepo.load(root).unregistered == ["orphan"]

    result = runner.invoke(app, ["validate", str(root), "--json", "--no-runtime-drift"])
    checks = [f["check"] for f in json.loads(result.output)["findings"]]
    assert "unregistered-project" in checks
    # ...and it stays out of the portfolio reads.
    status = json.loads(
        runner.invoke(app, ["status", "--collab", str(root), "--json"]).output
    )
    assert "orphan" not in status["projects"]
    assert status["unregistered"] == ["orphan"]


# --- dispatch routing (ADR-025 §7 Q2) ----------------------------------------------------


def test_project_of_locates_the_subdir_and_the_root(tmp_path: Path, fixed_clock: object) -> None:
    root = _init_mono(tmp_path)
    assert runner.invoke(app, ["add-project", "barony", "--root", str(root)]).exit_code == 0

    located = monorepo.project_of(root / "barony")
    assert located is not None
    found_root, ref = located
    assert found_root == root.resolve() and ref.dir == "barony"
    # Deeper inside the project still resolves to the project.
    assert monorepo.project_of(root / "barony" / "_handoff")[1].dir == "barony"
    # The root itself is not a project.
    assert monorepo.project_of(root) is None


def test_notify_payload_carries_the_project(tmp_path: Path, fixed_clock: object) -> None:
    """The wake must name the subdir; the gate cds there before resolving anything."""
    from baron import notify as notify_mod

    root = _init_mono(tmp_path)
    assert runner.invoke(app, ["add-project", "barony", "--root", str(root)]).exit_code == 0
    project = root / "barony"
    manifest = project / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "notify:\n  wake_allowed:\n    - iris\n",
        encoding="utf-8",
    )
    run_git(root, "add", "--", "barony/manifest.yaml")
    run_git(root, "commit", "-q", "-m", "test: allow iris to wake")

    seen: dict[str, object] = {}

    class FakeForge:
        def dispatch_event(self, repo: Path, *, event_type: str, payload: dict) -> None:
            seen["repo"] = repo
            seen["payload"] = payload

    # The git side belongs to the ROOT — give it an origin + default branch there.
    origin = tmp_path / "origin.git"
    run_git(root, "init", "--bare", "-q", str(origin))
    run_git(root, "remote", "add", "origin", str(origin))
    run_git(root, "push", "-q", "-u", "origin", "main")

    result = notify_mod.notify(
        project, persona="dev", title="wake up", from_="iris", forge=FakeForge()
    )
    assert result.woke, result.suppressed
    assert result.project == "barony"
    assert seen["payload"]["project"] == "barony"
    assert seen["payload"]["persona"] == "dev"
    assert seen["repo"] == root.resolve()  # the dispatch targets the monorepo's remote


def test_notify_outside_a_monorepo_carries_no_project(
    tmp_path: Path, fixed_clock: object
) -> None:
    """Single-project behaviour is byte-for-byte unchanged: no `project` key at all."""
    from baron import notify as notify_mod

    dest = tmp_path / "gardenkit-collab"
    assert runner.invoke(app, ["init", "gardenkit", "--dir", str(dest)]).exit_code == 0
    manifest = dest / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "notify:\n  wake_allowed:\n    - iris\n",
        encoding="utf-8",
    )
    run_git(dest, "add", "--", "manifest.yaml")
    run_git(dest, "commit", "-q", "-m", "test: allow iris to wake")
    origin = tmp_path / "origin.git"
    run_git(dest, "init", "--bare", "-q", str(origin))
    run_git(dest, "remote", "add", "origin", str(origin))
    run_git(dest, "push", "-q", "-u", "origin", "main")

    seen: dict[str, object] = {}

    class FakeForge:
        def dispatch_event(self, repo: Path, *, event_type: str, payload: dict) -> None:
            seen["payload"] = payload

    result = notify_mod.notify(
        dest, persona="dev", title="wake up", from_="iris", forge=FakeForge()
    )
    assert result.woke, result.suppressed
    assert result.project is None
    assert "project" not in seen["payload"]


def test_root_notify_workflow_routes_by_project(tmp_path: Path, fixed_clock: object) -> None:
    root = _init_mono(tmp_path)
    wf = (root / ".github" / "workflows" / "baron-notify.yml").read_text(encoding="utf-8")
    # Routing: the gate validates the payload project against the registry, then cds.
    assert "client_payload.project" in wf
    assert ".baron-monorepo.yaml" in wf
    assert 'cd "$PROJECT"' in wf
    # Authorization still comes from the COMMITTED handoff, never the payload (§5.5).
    assert "from:" in wf and "wake_allowed" in wf
    # Concurrency is keyed per project so two fleets' wakes never queue behind each other.
    assert "baron-notify-${{ github.event.client_payload.project }}" in wf
