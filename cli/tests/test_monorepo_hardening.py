"""The seven gaps the 2026-08-14 fleet-coordination dogfood found in ADR-025.

Standing up a real coordination monorepo — `baron init --layout monorepo` at
~/Workspace/fleet-coordination, then `add-project barony` — surfaced two defects
that made the topology unusable and five that made it unpleasant. Each test below
is named for the symptom the dogfood actually saw, because the symptoms are the
regression risk: the code paths are easy to re-break and the failures are quiet.

The two critical ones share a property worth stating: both fail SILENTLY UPWARD.
A self-aliased code repo reports green, and an absent notify block is
indistinguishable from a deliberate fail-closed one. Neither announces itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from baron import gitutil, monorepo, scaffold as scaffold_mod
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


def _manifest(project: Path) -> dict:
    return yaml.safe_load((project / "manifest.yaml").read_text(encoding="utf-8"))


def _code_path(project: Path) -> str | None:
    repos = _manifest(project).get("repos") or []
    code = [r for r in repos if r.get("role") == "code"]
    return code[0]["path"] if code else None


# --- gap 1 (CRITICAL): the self-aliasing code repo ---------------------------------------


def test_url_code_repo_is_rebased_for_the_monorepo_nesting_level(
    tmp_path: Path, fixed_clock: object
) -> None:
    """THE dogfood bug. `--code-repo <url>` names no local path, so baron assumes
    the conventional sibling clone — and the sibling of a monorepo SUBDIR is one
    more level up than the sibling of a standalone collab repo.

    Emitting `../barony` from `<root>/barony/` resolved back to the subdir itself:
    the code repo aliased the coordination repo, every path existed, and `baron
    status` reported the code repo GREEN with nothing cloned. A false green ends
    the investigation, which is why this is worse than a red.
    """
    root = _init_mono(tmp_path)
    result = runner.invoke(
        app,
        ["add-project", "barony", "--root", str(root),
         "--code-repo", "git@github.com:vggg/barony.git"],
    )
    assert result.exit_code == 0, result.output

    project = root / "barony"
    assert _code_path(project) == "../../barony"
    # The claim that matters is not the string but where it LANDS: outside the repo.
    landed = (project / "../../barony").resolve()
    assert landed != project and landed != root
    assert root not in landed.parents


def test_url_code_repo_keeps_one_level_up_outside_a_monorepo(
    tmp_path: Path, fixed_clock: object
) -> None:
    """The re-basing is monorepo-only — standalone `baron init` is unchanged."""
    dest = tmp_path / "barony-collab"
    result = runner.invoke(
        app, ["init", "barony", "--dir", str(dest),
              "--code-repo", "git@github.com:vggg/barony.git"]
    )
    assert result.exit_code == 0, result.output
    assert _code_path(dest) == "../barony"


@pytest.mark.parametrize(
    "target, expected",
    [
        ("root", "the coordination monorepo root itself"),   # the root
        ("sibling", "INSIDE"),                                # a sibling project subdir
        ("parent", "ANCESTOR"),                               # the root's own parent
    ],
)
def test_add_project_refuses_to_alias_the_coordination_repo(
    tmp_path: Path, fixed_clock: object, target: str, expected: str
) -> None:
    """Belt to the re-basing's braces: a code repo may not BE the coordination
    repo, live inside it, or contain it. Checked on the RESOLVED path, so it
    catches every spelling rather than the one the dogfood happened to hit."""
    root = _init_mono(tmp_path)
    assert runner.invoke(
        app, ["add-project", "barony", "--root", str(root)]
    ).exit_code == 0
    code_repo = {"root": root, "sibling": root / "barony", "parent": root.parent}[target]

    result = runner.invoke(
        app,
        ["add-project", "aliased", "--root", str(root), "--code-repo", str(code_repo)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    assert expected in result.output
    assert not (root / "aliased").exists(), "a refused graft must leave nothing behind"


def test_standalone_init_refuses_to_alias_its_own_collab_repo(
    tmp_path: Path, fixed_clock: object
) -> None:
    """The guard is not monorepo-specific — `repos[]` already carries `collab: .`,
    so a code repo pointing at the collab root is always a contradiction."""
    dest = tmp_path / "gardenkit-collab"
    result = runner.invoke(
        app, ["init", "gardenkit", "--dir", str(dest), "--code-repo", str(dest)]
    )
    assert result.exit_code != 0
    assert "the collab repo" in result.output


def test_a_grafted_project_with_a_url_code_repo_reports_the_missing_clone(
    tmp_path: Path, fixed_clock: object
) -> None:
    """The end-to-end claim: with the path fixed, `baron status` tells the truth.

    Before the fix this project was green. Nothing had been cloned, so the honest
    answer is red-missing — that is the whole point of the fix.
    """
    root = _init_mono(tmp_path)
    assert runner.invoke(
        app,
        ["add-project", "barony", "--root", str(root),
         "--code-repo", "git@github.com:vggg/barony.git"],
    ).exit_code == 0

    result = runner.invoke(app, ["status", "--collab", str(root)])
    assert "missing" in result.output or "not-a-repo" in result.output


# --- gap 2 (CRITICAL): the absent notify block -------------------------------------------


def test_add_project_emits_the_notify_block(tmp_path: Path, fixed_clock: object) -> None:
    """A grafted project could never be woken and the manifest gave no hint why:
    `notify` was simply absent, and absent reads the same as a deliberate
    fail-closed decision. Emit it always, even empty."""
    root = _init_mono(tmp_path)
    assert runner.invoke(app, ["add-project", "barony", "--root", str(root)]).exit_code == 0

    manifest = _manifest(root / "barony")
    assert "notify" in manifest
    assert manifest["notify"]["wake_allowed"] == []
    text = (root / "barony" / "manifest.yaml").read_text(encoding="utf-8")
    assert "wake_allowed" in text and "fail-closed" in text


def test_init_emits_the_notify_block_too(tmp_path: Path, fixed_clock: object) -> None:
    """add-project reuses init's emitters, so the fix belongs in the shared one —
    which means standalone init gains the same discoverable block."""
    dest = tmp_path / "gardenkit-collab"
    assert runner.invoke(app, ["init", "gardenkit", "--dir", str(dest)]).exit_code == 0
    assert _manifest(dest)["notify"]["wake_allowed"] == []


@pytest.mark.parametrize("cmd", ["init", "add-project"])
def test_wake_allowed_can_be_scaffolded_open(
    tmp_path: Path, fixed_clock: object, cmd: str
) -> None:
    """The empty default stays fail-closed (ADR-010 §5.5: a project that has not
    decided who may spend money does not spend money), so the way to a WORKING
    wake loop is one explicit flag rather than a hand-edit nobody knows to make."""
    if cmd == "init":
        target = tmp_path / "gardenkit-collab"
        args = ["init", "gardenkit", "--dir", str(target),
                "--personas", "dev:carson,librarian:iris", "--wake-allowed", "iris"]
    else:
        root = _init_mono(tmp_path)
        target = root / "barony"
        args = ["add-project", "barony", "--root", str(root),
                "--personas", "dev:carson,librarian:iris", "--wake-allowed", "iris"]
    assert runner.invoke(app, args).exit_code == 0
    assert _manifest(target)["notify"]["wake_allowed"] == ["iris"]


def test_wake_allowed_rejects_a_persona_the_project_does_not_have(
    tmp_path: Path, fixed_clock: object
) -> None:
    """The gate matches the handoff's `from:` slug, so a name that is not a persona
    of this project can never fire — accepting it would scaffold a dead allowlist
    that LOOKS open."""
    root = _init_mono(tmp_path)
    result = runner.invoke(
        app,
        ["add-project", "barony", "--root", str(root),
         "--personas", "dev:carson,librarian:iris", "--wake-allowed", "nobody"],
    )
    assert result.exit_code != 0
    assert "not a persona of this project" in result.output
    assert not (root / "barony").exists()


def test_a_scaffolded_wake_allowlist_actually_opens_the_gate(
    tmp_path: Path, fixed_clock: object
) -> None:
    """The loop the dogfood could not close: scaffold the allowlist, and the CLI's
    own gate admits that persona instead of suppressing the wake."""
    root = _init_mono(tmp_path)
    assert runner.invoke(
        app,
        ["add-project", "barony", "--root", str(root),
         "--personas", "dev:carson,librarian:iris", "--wake-allowed", "iris"],
    ).exit_code == 0

    from baron import notify as notify_mod

    project = root / "barony"
    assert notify_mod._wake_allowed(project, "iris") is True
    assert notify_mod._wake_allowed(project, "carson") is False


# --- gap 3: the unscoped dirty check ------------------------------------------------------


def test_dirty_count_is_scoped_to_the_directory_it_is_asked_about(
    tmp_path: Path, fixed_clock: object
) -> None:
    """`git status --porcelain` reports the whole work tree no matter which subdir
    you run it from. In a monorepo that made ONE uncommitted file dirty every
    project — the dogfood saw `_meta` flagged for an edit to `barony/manifest.yaml`."""
    root = _init_mono(tmp_path)
    assert runner.invoke(app, ["add-project", "barony", "--root", str(root)]).exit_code == 0
    assert run_git(root, "status", "--porcelain").strip() == ""

    (root / "barony" / "manifest.yaml").write_text(
        (root / "barony" / "manifest.yaml").read_text(encoding="utf-8") + "# touched\n",
        encoding="utf-8",
    )
    assert gitutil.dirty_count(root / "barony") == 1
    assert gitutil.dirty_count(root / "_meta") == 0
    assert gitutil.dirty_count(root) == 1  # the root still sees everything under it


def test_portfolio_status_blames_only_the_dirty_project(
    tmp_path: Path, fixed_clock: object
) -> None:
    root = _init_mono(tmp_path)
    assert runner.invoke(app, ["add-project", "barony", "--root", str(root)]).exit_code == 0
    (root / "barony" / "backlog.md").write_text("dirty\n", encoding="utf-8")

    report = monorepo.collect_status(root)
    dirty = {
        name: [f for f in findings if f.check == "dirty"]
        for name, findings in report.per_project.items()
    }
    assert dirty["barony"] and not dirty["_meta"]


# --- gap 4: the lost archetype provenance -------------------------------------------------


def test_reviewer_and_merger_record_their_own_archetype(
    tmp_path: Path, fixed_clock: object
) -> None:
    """The templates hard-coded `archetype: dev` for both, so a scaffolded roster
    read back as indistinguishable devs — the one field that records which
    archetype a persona came from, thrown away at hydration time.

    They remain dev-SHAPED (same hydration mechanics, narrower capabilities);
    dev-shaped is not the same claim as `dev`.
    """
    root = _init_mono(tmp_path)
    assert runner.invoke(
        app,
        ["add-project", "barony", "--root", str(root),
         "--personas", "dev:carson,reviewer:tess,merger:mo,librarian:iris"],
    ).exit_code == 0

    def archetype(slug: str) -> str:
        spec = yaml.safe_load(
            (root / "barony" / "agents" / slug / "persona.yaml").read_text(encoding="utf-8")
        )
        return spec["archetype"]

    assert archetype("carson") == "dev"
    assert archetype("tess") == "reviewer"
    assert archetype("mo") == "merger"
    assert archetype("iris") == "librarian"


def test_the_new_archetypes_validate_clean(tmp_path: Path, fixed_clock: object) -> None:
    """`reviewer`/`merger` must be in the schema enum, or every scaffold that uses
    them now emits a warning about its own output."""
    from baron import schemas

    assert {"reviewer", "merger"} <= set(schemas.ARCHETYPES)
    dest = tmp_path / "barony-collab"
    assert runner.invoke(
        app,
        ["init", "barony", "--dir", str(dest),
         "--personas", "reviewer:tess,merger:mo,librarian:iris"],
    ).exit_code == 0
    result = runner.invoke(app, ["validate", str(dest)])
    assert result.exit_code == 0, result.output
    assert "archetype" not in result.output


def test_the_derived_context_file_carries_the_real_archetype(
    tmp_path: Path, fixed_clock: object
) -> None:
    """Provenance is only preserved if it survives into the hydrated kit too."""
    dest = tmp_path / "barony-collab"
    assert runner.invoke(
        app, ["init", "barony", "--dir", str(dest), "--personas", "reviewer:tess"]
    ).exit_code == 0
    kit = (dest / "agents" / "tess" / "runtime" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "archetype: reviewer" in kit


# --- gap 5: the inert nested .github/ -----------------------------------------------------


def test_a_nested_github_dir_is_reported_inert(tmp_path: Path, fixed_clock: object) -> None:
    """GitHub resolves workflows from the REPOSITORY root only. A `.github/` in a
    project subdir fires never while looking exactly like working CI to anyone
    reading that subdir — the failure mode is believing you have a lock guard."""
    root = _init_mono(tmp_path)
    assert runner.invoke(app, ["add-project", "barony", "--root", str(root)]).exit_code == 0
    (root / "barony" / ".github" / "workflows").mkdir(parents=True)
    (root / "barony" / ".github" / "workflows" / "lock-guard.yml").write_text("on: pr\n")

    assert monorepo.inert_github_dirs(root) == ["barony"]
    result = runner.invoke(app, ["add-project", "second", "--root", str(root)])
    assert result.exit_code == 0
    assert "barony/.github/ exists but is INERT" in result.output


def test_no_inert_warning_on_a_clean_monorepo(tmp_path: Path, fixed_clock: object) -> None:
    root = _init_mono(tmp_path)
    result = runner.invoke(app, ["add-project", "barony", "--root", str(root)])
    assert result.exit_code == 0
    assert "INERT" not in result.output
    assert monorepo.inert_github_dirs(root) == []


def test_the_roots_own_github_is_never_flagged(tmp_path: Path, fixed_clock: object) -> None:
    """The root's .github/ is the one that DOES run — flagging it would be exactly
    backwards."""
    root = _init_mono(tmp_path)
    assert (root / ".github" / "workflows").is_dir()
    assert monorepo.inert_github_dirs(root) == []


def test_an_unregistered_subdirs_inert_github_is_reported_too(
    tmp_path: Path, fixed_clock: object
) -> None:
    """Registration status has nothing to do with whether the CI runs. It doesn't."""
    root = _init_mono(tmp_path)
    stray = root / "stray"
    (stray / ".github" / "workflows").mkdir(parents=True)
    (stray / "manifest.yaml").write_text("project:\n  name: stray\n", encoding="utf-8")
    assert monorepo.inert_github_dirs(root) == ["stray"]


# --- gap 6: adopting an existing collab repo ----------------------------------------------


def _standalone_collab(tmp_path: Path, name: str) -> Path:
    dest = tmp_path / f"{name}-collab"
    assert runner.invoke(app, ["init", name, "--dir", str(dest)]).exit_code == 0
    return dest


def test_adopt_registers_an_existing_collab_repo_moved_into_the_root(
    tmp_path: Path, fixed_clock: object
) -> None:
    """`add-project` scaffolds and refuses a non-empty target, so an existing
    collab repo — history, personas, ledgers and all — had no way into a monorepo
    short of hand-editing the marker. That was the dogfood's manual subtree graft."""
    root = _init_mono(tmp_path)
    existing = _standalone_collab(tmp_path, "gardenkit")
    import shutil

    shutil.rmtree(existing / ".git")
    shutil.move(str(existing), str(root / "gardenkit"))

    result = runner.invoke(app, ["adopt-project", "gardenkit", "--root", str(root)])
    assert result.exit_code == 0, result.output
    assert [p.dir for p in monorepo.load(root).projects] == ["_meta", "gardenkit"]
    assert monorepo.load(root).unregistered == []
    assert "gardenkit" in (root / "README.md").read_text(encoding="utf-8")
    assert run_git(root, "status", "--porcelain").strip() == ""


def test_adopt_reads_the_project_name_from_the_adopted_manifest(
    tmp_path: Path, fixed_clock: object
) -> None:
    """The adopted repo's manifest is its own truth — baron reads it, never
    rewrites it, so the subdir name and the project name may legitimately differ."""
    root = _init_mono(tmp_path)
    existing = _standalone_collab(tmp_path, "gardenkit")
    import shutil

    shutil.rmtree(existing / ".git")
    shutil.move(str(existing), str(root / "garden"))

    assert runner.invoke(app, ["adopt-project", "garden", "--root", str(root)]).exit_code == 0
    ref = next(p for p in monorepo.load(root).projects if p.dir == "garden")
    assert ref.name == "gardenkit"


def test_adopt_refuses_a_contradicting_project_name(
    tmp_path: Path, fixed_clock: object
) -> None:
    root = _init_mono(tmp_path)
    existing = _standalone_collab(tmp_path, "gardenkit")
    import shutil

    shutil.rmtree(existing / ".git")
    shutil.move(str(existing), str(root / "garden"))

    result = runner.invoke(
        app, ["adopt-project", "garden", "--root", str(root), "--project-name", "other"]
    )
    assert result.exit_code == 2
    assert "contradicts" in result.output


def test_adopt_refuses_a_still_nested_git_repo(tmp_path: Path, fixed_clock: object) -> None:
    """A subdir that is still its own repo is invisible to the root's git — the
    monorepo would register a project whose files it cannot track."""
    root = _init_mono(tmp_path)
    existing = _standalone_collab(tmp_path, "gardenkit")
    import shutil

    shutil.move(str(existing), str(root / "gardenkit"))
    result = runner.invoke(app, ["adopt-project", "gardenkit", "--root", str(root)])
    assert result.exit_code == 2
    assert "still its own git repo" in result.output
    assert "git subtree add" in result.output


@pytest.mark.parametrize(
    "setup, expected",
    [
        ("absent", "does not exist"),
        ("no-manifest", "no manifest.yaml"),
        ("duplicate", "already registered"),
        ("traversal", "plain directory name"),
    ],
)
def test_adopt_refuses_cleanly(
    tmp_path: Path, fixed_clock: object, setup: str, expected: str
) -> None:
    root = _init_mono(tmp_path)
    name = "gardenkit"
    if setup == "no-manifest":
        (root / name).mkdir()
    elif setup == "duplicate":
        name = "_meta"
    elif setup == "traversal":
        name = "../escape"
    result = runner.invoke(app, ["adopt-project", name, "--root", str(root)])
    assert result.exit_code == 2
    assert expected in result.output


def test_adopt_refuses_outside_a_monorepo(tmp_path: Path, fixed_clock: object) -> None:
    dest = _standalone_collab(tmp_path, "gardenkit")
    result = runner.invoke(app, ["adopt-project", "anything", "--root", str(dest)])
    assert result.exit_code == 2
    assert "not a coordination-monorepo root" in result.output


def test_adopt_flags_the_adopted_repos_inert_github(
    tmp_path: Path, fixed_clock: object
) -> None:
    """The single most likely thing an adopted standalone collab repo brings with
    it is a `.github/` that stops running the moment it is adopted."""
    root = _init_mono(tmp_path)
    existing = _standalone_collab(tmp_path, "gardenkit")
    import shutil

    shutil.rmtree(existing / ".git")
    shutil.move(str(existing), str(root / "gardenkit"))
    assert (root / "gardenkit" / ".github").is_dir()

    result = runner.invoke(app, ["adopt-project", "gardenkit", "--root", str(root)])
    assert result.exit_code == 0
    assert "gardenkit/.github/ exists but is INERT" in result.output
    # Reported, not deleted: removing another repo's CI is not a side effect of
    # registering it.
    assert (root / "gardenkit" / ".github").is_dir()


def test_an_adopted_project_joins_the_portfolio_reads(
    tmp_path: Path, fixed_clock: object
) -> None:
    """Adoption is only real if `baron status` covers it afterwards."""
    root = _init_mono(tmp_path)
    existing = _standalone_collab(tmp_path, "gardenkit")
    import shutil

    shutil.rmtree(existing / ".git")
    shutil.move(str(existing), str(root / "gardenkit"))
    assert runner.invoke(app, ["adopt-project", "gardenkit", "--root", str(root)]).exit_code == 0

    report = monorepo.collect_status(root)
    assert set(report.per_project) == {"_meta", "gardenkit"}


# --- the shared emitter stays shared ------------------------------------------------------


def test_scaffold_rejects_wake_allowed_for_an_unknown_slug_directly() -> None:
    """Guard the library surface too — `add-project` is not the only caller."""
    with pytest.raises(scaffold_mod.ScaffoldError, match="not a persona of this project"):
        scaffold_mod.scaffold(
            "x",
            Path("/nonexistent-should-not-be-reached"),
            personas=[scaffold_mod.Persona("dev", "carson")],
            wake_allowed=["ghost"],
        )
