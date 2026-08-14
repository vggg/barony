"""baron — command-line surface (typer app).

The markdown/git substrate is the database (ADR-003): every command below reads
and writes the same human-legible collab-repo files the personas do.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

from . import (
    clock,
    decision as decision_mod,
    export as export_mod,
    doctor as doctor_mod,
    guard as guard_mod,
    handoff as handoff_mod,
    health as health_mod,
    indexer,
    ledger,
    lock as lock_mod,
    monorepo as monorepo_mod,
    notify as notify_mod,
    rules as rules_mod,
    runtimes,
    scaffold as scaffold_mod,
    session as session_mod,
    sidecar as sidecar_mod,
    status as status_mod,
    validate as validate_mod,
    verdict as verdict_mod,
    waivers as waivers_mod,
    worktree as worktree_mod,
)
from .forge import ForgeError, ForgeUnavailable
from .schemas import CAPABILITY_VERBS

app = typer.Typer(
    name="baron",
    help=(
        "Disciplined reader/writer over a Barony collab repo. "
        "The markdown/git substrate is the database — baron never adds another store."
    ),
    no_args_is_help=True,
    add_completion=False,
)

_COLLAB_OPT = typer.Option(
    Path("."),
    "--collab",
    help="Path to the collab repo root (default: current directory).",
)


def _echo_json(payload: object) -> None:
    typer.echo(json.dumps(payload, indent=2, default=str))


def _version_callback(value: bool) -> None:
    if value:
        from . import __version__

        typer.echo(f"barony {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(  # noqa: ARG001 - consumed by the eager callback
        False,
        "--version",
        "-V",
        help="Show the installed Barony version and exit.",
        is_eager=True,
        callback=_version_callback,
    ),
) -> None:
    """Barony's CLI. Run `baron <command> --help` for any command."""


# --- init -----------------------------------------------------------------------------


@app.command()
def init(
    project_name: str = typer.Argument(
        ..., help="Project name (also the git identity domain: <slug>@<project>.local)."
    ),
    dir_: Optional[Path] = typer.Option(
        None, "--dir", help="Target directory for the collab repo (default: ./<project-name>)."
    ),
    code_repo: Optional[str] = typer.Option(
        None,
        "--code-repo",
        help="Existing code repo — a local path or a git URL — recorded in manifest.yaml.",
    ),
    personas: str = typer.Option(
        "dev:dev,librarian:librarian",
        "--personas",
        help=(
            "Comma-separated archetype:slug pairs (e.g. dev:carson,dev:terrence,"
            "librarian:iris). Archetypes: "
            + ", ".join(sorted(scaffold_mod.ARCHETYPE_TEMPLATES))
            + ". A librarian is added automatically if missing."
        ),
    ),
    runtime: str = typer.Option(
        "claude",
        "--runtime",
        help="Runtime kit to emit per persona: " + " | ".join(scaffold_mod.RUNTIMES) + ".",
    ),
    layout: str = typer.Option(
        "repo",
        "--layout",
        help=(
            "repo (default): one collab repo for this project — keeps per-project "
            "isolation. monorepo: a coordination monorepo whose projects are subdirs "
            "(ADR-025); grow it with `baron add-project`."
        ),
    ),
    first_project: str = typer.Option(
        monorepo_mod.META_DIR,
        "--first-project",
        help=(
            "--layout monorepo only: the first project subdir (default: _meta, the "
            "portfolio project — no code repo, its work items are cross-project decisions)."
        ),
    ),
    no_git: bool = typer.Option(False, "--no-git", help="Skip git init + first commit."),
) -> None:
    """Scaffold a new collab repo — the deterministic subset of canon/ORCHESTRATE.md.

    Emits the canonical layout (CONVENTIONS/COORDINATION, manifest.yaml, canon/ +
    adapters/ from the packaged templates, hydrated agents/<slug>/persona.yaml,
    genesis handoff, ledger index headers, wiki stub, and the lock-guard +
    strip-stale-verdict CI templates) plus a per-persona runtime kit, validates its
    own output, and git-commits. NOTE: strip-stale-verdict.yml also belongs in the
    CODE repo, where most reviewed PRs live — see its header.
    Persona scope prose, AGENT.md manuals, and Tier-3 hydration stay on the
    conversational path (canon/ORCHESTRATE.md).

    `--layout monorepo` emits the other topology instead (ADR-025): a coordination
    monorepo root — marker, README and the shared .github/ seam — with the first
    project (`_meta` by default) as a subdir. Per-project-repo stays the default;
    the monorepo trades multi-tenant isolation for one clone with a portfolio view.
    """
    try:
        roster = scaffold_mod.parse_personas(personas)
        if runtime not in scaffold_mod.RUNTIMES:
            raise scaffold_mod.ScaffoldError(
                f"unknown runtime {runtime!r} — pick from "
                + ", ".join(scaffold_mod.RUNTIMES)
            )
        if layout not in ("repo", "monorepo"):
            raise scaffold_mod.ScaffoldError(
                f"unknown --layout {layout!r} — pick from repo, monorepo"
            )
    except scaffold_mod.ScaffoldError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2)
    dest = dir_ if dir_ is not None else Path(project_name)
    if layout == "monorepo":
        _init_monorepo(
            project_name,
            dest,
            first_project=first_project,
            code_repo=code_repo,
            roster=roster,
            runtime=runtime,
            do_git=not no_git,
        )
        return
    try:
        report = scaffold_mod.scaffold(
            project_name,
            dest,
            code_repo=code_repo,
            personas=roster,
            runtime=runtime,
            do_git=not no_git,
        )
    except scaffold_mod.ScaffoldError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)

    root = report.root
    typer.echo(f"scaffolded {project_name} at {root.as_posix()} ({len(report.created)} files)")
    typer.echo(
        "personas: " + ", ".join(f"{p.slug} ({p.archetype})" for p in report.personas)
        + f" · runtime kit: {report.runtime}"
    )
    if report.git_committed:
        typer.echo("git: initialized on branch main, first commit made")
    elif report.git_initialized:
        typer.echo("git: initialized (first commit NOT made — see notes)")
    elif not no_git:
        typer.echo("git: NOT initialized — see notes")
    for note in report.notes:
        typer.echo(f"note: {note}")
    typer.echo(
        "\nnext steps:\n"
        f"  1. cd {dest.as_posix()}\n"
        "  2. baron validate .        # canonical specs — expect 0 errors\n"
        "  3. baron status            # divergence/staleness report (green when fresh)\n"
        "  4. INSTALL each persona's runtime kit where its runtime starts —\n"
        "     copy agents/<slug>/runtime/ into that working copy (see its README).\n"
        "     Generating the kit is not installing it: the badminton-analyzer\n"
        "     incident merged 15 PRs under a persona denied merge_pr because the\n"
        "     guard hook was generated and never copied.\n"
        "  5. baron doctor --dir <that working copy>   # proves the wiring; exit 1\n"
        "     if the hook, executable, persona, or rules are missing (ADR-017)\n"
        "  6. open your runtime there — canon/START.md routes you\n"
        "  7. every session: sync repos, read CONVENTIONS.md + COORDINATION.md,\n"
        "     check _handoff/ (COORDINATION.md § Session-start checklist)\n"
        "\nedit next: agents/<slug>/persona.yaml scope blocks (init fills a generic\n"
        "placeholder scope), manifest.yaml description, and backlog.md."
    )


# --- ADR-025: the coordination monorepo -------------------------------------------------


def _commit_monorepo(root: Path, paths: list[str], message: str) -> tuple[bool, Optional[str]]:
    """git-init (if needed) + commit ``paths`` at the monorepo root. (committed, note).

    The monorepo root is the git repo — the project subdirs are not — so both
    `init --layout monorepo` and `add-project` commit here rather than in the subdir.
    """
    import shutil

    from . import gitutil

    if shutil.which("git") is None:
        return False, "git not found — nothing committed; run `git init -b main` later"
    try:
        if not gitutil.is_git_repo(root):
            gitutil.git(root, "init", "-q", "-b", "main")
        gitutil.git(root, "add", "--", *paths)
        gitutil.git(root, "commit", "-q", "-m", message)
    except gitutil.GitError as exc:
        return False, f"git step incomplete ({exc}) — the files are all written"
    return True, None


def _init_monorepo(
    name: str,
    dest: Path,
    *,
    first_project: str,
    code_repo: Optional[str],
    roster: list,
    runtime: str,
    do_git: bool,
) -> None:
    """`baron init --layout monorepo`: root + first project subdir (ADR-025)."""
    root = dest.resolve()
    try:
        created = monorepo_mod.create_root(
            root, name, date=clock.today().isoformat()
        )
        project_name = (
            monorepo_mod.META_PROJECT
            if first_project == monorepo_mod.META_DIR
            else first_project
        )
        ref, project_files = monorepo_mod.add_project(
            root,
            first_project,
            project_name=project_name,
            # The portfolio project has no code repo by definition (ADR-025 §2).
            code_repo=None if first_project == monorepo_mod.META_DIR else code_repo,
            personas=roster,
            runtime=runtime,
        )
    except (monorepo_mod.MonorepoError, scaffold_mod.ScaffoldError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    created = sorted(set(created) | set(project_files))

    typer.echo(
        f"scaffolded coordination monorepo {name} at {root.as_posix()} "
        f"({len(created)} files)"
    )
    typer.echo(f"first project: {ref.dir}/ (project name {ref.name})")
    typer.echo(
        "personas: " + ", ".join(f"{p.slug} ({p.archetype})" for p in roster)
        + f" · runtime kit: {runtime}"
    )
    if do_git:
        committed, note = _commit_monorepo(
            root,
            created,
            f"baron: init | scaffold {name} coordination monorepo "
            f"(layout monorepo, first project {ref.dir})",
        )
        typer.echo(
            "git: initialized on branch main, first commit made"
            if committed
            else "git: NOT fully initialized — see note"
        )
        if note:
            typer.echo(f"note: {note}")
    if first_project == monorepo_mod.META_DIR and code_repo:
        typer.echo(
            f"note: --code-repo ignored for the {monorepo_mod.META_DIR} project "
            "(the portfolio project has no code repo) — pass it to `baron add-project`"
        )
    typer.echo(
        "\nnext steps:\n"
        f"  1. cd {dest.as_posix()}\n"
        "  2. baron add-project <name> --code-repo <path-or-url>   # graft each fleet in\n"
        "  3. baron validate .        # every project's specs at once — expect 0 errors\n"
        "  4. baron status            # portfolio-wide divergence/staleness\n"
        f"  5. cd {first_project}/ and install the runtime kits as usual (agents/<slug>/runtime/)\n"
        "\nnote: CI lives once, at the root — `.github/workflows/baron-notify.yml` routes\n"
        "each wake into the project subdir named by the dispatch payload."
    )


@app.command("add-project")
def add_project(
    name: str = typer.Argument(
        ..., help="Project subdir to graft into the monorepo (also the project name)."
    ),
    root_: Path = typer.Option(
        Path("."), "--root", help="Coordination-monorepo root (default: current directory)."
    ),
    project_name: Optional[str] = typer.Option(
        None,
        "--project-name",
        help="Project name if it must differ from the subdir (it becomes the git "
        "identity domain <slug>@<project>.local).",
    ),
    code_repo: Optional[str] = typer.Option(
        None,
        "--code-repo",
        help="Existing code repo — a local path or a git URL — recorded in this "
        "project's manifest.yaml. Code repos stay separate and per-project.",
    ),
    personas: str = typer.Option(
        "dev:dev,librarian:librarian",
        "--personas",
        help=(
            "Comma-separated archetype:slug pairs. Archetypes: "
            + ", ".join(sorted(scaffold_mod.ARCHETYPE_TEMPLATES))
            + ". A librarian is added automatically if missing."
        ),
    ),
    runtime: str = typer.Option(
        "claude",
        "--runtime",
        help="Runtime kit to emit per persona: " + " | ".join(scaffold_mod.RUNTIMES) + ".",
    ),
    no_git: bool = typer.Option(False, "--no-git", help="Write the files; do not commit."),
) -> None:
    """Graft a new project subdir into an existing coordination monorepo (ADR-025).

    Emits `<root>/<name>/` with its own manifest.yaml, agents/, _handoff/, decisions/,
    findings/ and wiki/ — the same scaffold `baron init` writes — then registers it in
    the root's `.baron-monorepo.yaml`. CI and git stay at the root: the subdir gets no
    `.github/` of its own and no repo of its own.

    Refuses cleanly when --root is not a monorepo root; use
    `baron init <name> --layout monorepo` to create one.
    """
    root = root_.resolve()
    try:
        roster = scaffold_mod.parse_personas(personas)
        if runtime not in scaffold_mod.RUNTIMES:
            raise scaffold_mod.ScaffoldError(
                f"unknown runtime {runtime!r} — pick from " + ", ".join(scaffold_mod.RUNTIMES)
            )
    except scaffold_mod.ScaffoldError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2)
    try:
        ref, created = monorepo_mod.add_project(
            root,
            name,
            project_name=project_name,
            code_repo=code_repo,
            personas=roster,
            runtime=runtime,
        )
    except monorepo_mod.MonorepoError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2)
    except scaffold_mod.ScaffoldError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"grafted {ref.dir}/ into {root.as_posix()} ({len(created)} files)")
    typer.echo(
        "personas: " + ", ".join(f"{p.slug} ({p.archetype})" for p in roster)
        + f" · runtime kit: {runtime}"
    )
    if not no_git:
        committed, note = _commit_monorepo(
            root,
            created,
            f"baron: init | add project {ref.dir} to the coordination monorepo",
        )
        typer.echo("git: committed at the monorepo root" if committed else "git: NOT committed")
        if note:
            typer.echo(f"note: {note}")
    typer.echo(
        "\nnext steps:\n"
        f"  1. baron validate {ref.dir}       # this project's specs — expect 0 errors\n"
        "  2. baron status                  # portfolio-wide, from the root\n"
        f"  3. install {ref.dir}/agents/<slug>/runtime/ where each runtime starts\n"
        "     (generating a kit is not installing it — see `baron init`'s note)\n"
        f"  4. edit {ref.dir}/manifest.yaml description and the persona scope blocks"
    )


# --- M1: validate ---------------------------------------------------------------------


@app.command()
def validate(
    path: Path = typer.Argument(
        Path("."),
        help="A persona.yaml/manifest.yaml file, or a directory to search recursively.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
    runtime_drift: bool = typer.Option(
        True,
        "--runtime-drift/--no-runtime-drift",
        help="Also check declared personas against the runtime's agent registry (P2.3).",
    ),
) -> None:
    """Validate persona.yaml / manifest.yaml against the canonical v1 schemas.

    Checks: YAML parse, missing/unknown fields, types, capability verbs against
    the FROZEN v1 vocabulary, allow/deny overlap, unfilled {{PLACEHOLDER}}
    tokens. Emit-time templates (paths containing assets/collab-repo/ or
    legacy/) are skipped during directory discovery — they legitimately carry
    placeholders; fixture paths (tests/examples/) are exempt from the
    placeholder check only. Exit 0 = no errors (warnings allowed); exit 1 = errors.

    SPEC-RUNTIME DRIFT (P2.3): when a directory holding manifest.yaml is
    validated, the personas it declares are compared against the agents actually
    registered for each runtime the manifest declares in `adapters`. The signal is
    PARTIAL registration: if some personas are registered and others are not, the
    project demonstrably hydrates agents here and the gaps are ERRORS — work
    routed to a missing persona runs as some other agent (wrong identity, wrong
    commit prefix, wrong capabilities), which is how a cron ran under the wrong
    persona on the pilot. All-or-nothing is silent: zero registered is the correct
    state for Tier-1/Tier-2 projects and for a fresh scaffold. An explicit
    `adapters.claude.tier: 2` is never checked. `--no-runtime-drift` skips it.

    Directory validation already recurses, so pointing it at a coordination-monorepo
    root (ADR-025) validates every project's specs in one pass; the report then names
    the projects covered, and any subdir carrying a manifest.yaml without being
    registered in `.baron-monorepo.yaml` is reported as a warning (portfolio reads
    would skip it silently otherwise).
    """
    if not path.exists():
        typer.echo(f"error: {path} does not exist", err=True)
        raise typer.Exit(2)
    findings, files, skipped = validate_mod.validate_path(
        path, runtime_drift=runtime_drift
    )
    projects: list[str] = []
    if path.is_dir() and monorepo_mod.is_root(path.resolve()):
        repo = monorepo_mod.load(path.resolve())
        projects = [p.dir for p in repo.projects]
        for unregistered in repo.unregistered:
            findings.append(
                validate_mod.Finding(
                    file=f"{unregistered}/manifest.yaml",
                    kind="manifest",
                    severity="warning",
                    check="unregistered-project",
                    message=(
                        f"{unregistered}/ holds a manifest.yaml but is not listed in "
                        f"{monorepo_mod.MARKER} — portfolio status/health skip it"
                    ),
                )
            )
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    if json_out:
        payload: dict = {
            "files_checked": [f.as_posix() for f in files],
            "templates_skipped": [f.as_posix() for f in skipped],
            "findings": [f.to_dict() for f in findings],
            "summary": {"errors": len(errors), "warnings": len(warnings)},
        }
        if projects:
            payload["layout"] = "monorepo"
            payload["projects"] = projects
        _echo_json(payload)
    else:
        for f in findings:
            typer.echo(f"{f.severity.upper():7s} {f.file}: [{f.check}] {f.message}")
        if skipped:
            typer.echo(f"skipped {len(skipped)} template file(s) (assets/collab-repo, legacy)")
        if projects:
            typer.echo(
                f"coordination monorepo: {len(projects)} project(s) — " + ", ".join(projects)
            )
        typer.echo(
            f"{len(files)} file(s) checked: {len(errors)} error(s), {len(warnings)} warning(s)"
        )
    raise typer.Exit(1 if errors else 0)


# --- M2: status -----------------------------------------------------------------------


@app.command()
def status(
    collab: Path = _COLLAB_OPT,
    fetch: bool = typer.Option(
        False, "--fetch", help="git fetch each working copy first (needed to see remote-side divergence)."
    ),
    sla: int = typer.Option(14, "--sla", help="Open-handoff SLA in days."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Divergence & staleness report across the project's working copies.

    Reads manifest.yaml (repos + optional workspace.clones / workspace.worktrees_root)
    and reports: ahead/behind origin default branch, uncommitted dirt, unmerged
    local branches with age, open handoffs past SLA, ledger staleness vs
    code-repo activity (heuristic), and a stale wiki/status.md. Exit 0 = green
    (warnings allowed); exit 1 = at least one red finding (CI-usable).

    Run at a coordination-monorepo root (ADR-025) it goes PORTFOLIO-WIDE: every
    registered project subdir is walked and the findings are reported per project
    with a portfolio total. Inside a single project — monorepo subdir or standalone
    collab repo alike — behaviour is unchanged.
    """
    collab_root = collab.resolve()
    if monorepo_mod.is_root(collab_root):
        try:
            portfolio = monorepo_mod.collect_status(collab_root, fetch=fetch, sla_days=sla)
        except monorepo_mod.MonorepoError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(2)
        if json_out:
            payload = portfolio.to_dict()
            payload["generated"] = clock.today().isoformat()
            payload["sla_days"] = sla
            _echo_json(payload)
        else:
            typer.echo(monorepo_mod.render_status(portfolio))
        raise typer.Exit(1 if portfolio.reds else 0)
    try:
        findings = status_mod.collect(collab.resolve(), fetch=fetch, sla_days=sla)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2)
    reds = [f for f in findings if f.severity == status_mod.RED]
    if json_out:
        _echo_json(
            {
                "generated": clock.today().isoformat(),
                "collab": collab.resolve().as_posix(),
                "sla_days": sla,
                "findings": [f.to_dict() for f in findings],
                "summary": {"red": len(reds), "warn": len(findings) - len(reds)},
            }
        )
    else:
        typer.echo(status_mod.render_table(findings))
    raise typer.Exit(1 if reds else 0)


# --- M3: ledgers ----------------------------------------------------------------------

finding_app = typer.Typer(help="Findings ledger (findings/index.md).", no_args_is_help=True)
decision_app = typer.Typer(help="Decisions ledger (decisions/index.md).", no_args_is_help=True)
app.add_typer(finding_app, name="finding")
app.add_typer(decision_app, name="decision")


def _ledger_new(
    kind: str,
    collab: Path,
    title: str,
    author: str,
    body_file: Optional[Path],
    no_push: bool,
    retries: int,
) -> None:
    body: str | None = None
    if body_file is not None:
        if not body_file.is_file():
            typer.echo(f"error: --body-file {body_file} not found", err=True)
            raise typer.Exit(2)
        body = body_file.read_text(encoding="utf-8")
    try:
        n = ledger.add_entry(
            collab.resolve(),
            kind,
            title=title,
            author=author,
            body=body,
            push=not no_push,
            retries=retries,
        )
    except (ledger.LedgerError,) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    prefix = ledger.KINDS[kind].prefix
    pushed = "committed (not pushed)" if no_push else "committed and pushed"
    typer.echo(f"{prefix}{n} — {title} ({pushed})")


@finding_app.command("new")
def finding_new(
    title: str = typer.Option(..., "--title", help="Finding title (goes in the heading)."),
    author: str = typer.Option(
        ...,
        "--author",
        help="Ledger attribution (the proposer named in the entry heading). "
        "Separate from the git author that signs the commit — a librarian can "
        "allocate --author <reviewer> while committing under its own identity.",
    ),
    body_file: Optional[Path] = typer.Option(
        None, "--body-file", help="File whose content becomes the entry body (default: a stub)."
    ),
    collab: Path = _COLLAB_OPT,
    no_push: bool = typer.Option(False, "--no-push", help="Commit locally only (offline)."),
    retries: int = typer.Option(
        3, "--retries", help="Push-rejection retries (fetch+rebase+renumber)."
    ),
) -> None:
    """Allocate the next F-number and append a house-style entry.

    Allocation is race-safe by push-retry: on push rejection baron rolls back,
    rebases onto origin, re-parses the index, renumbers, and retries (bounded).
    """
    _ledger_new("finding", collab, title, author, body_file, no_push, retries)


@decision_app.command("reconcile")
def decision_reconcile(
    number: int = typer.Argument(..., help="Decision number, e.g. 57 for D57."),
    park: list[str] = typer.Option(
        [], "--park",
        help="Backlog item this decision supersedes (issue number, or an id for a file backlog). Repeatable.",
    ),
    collab: Path = _COLLAB_OPT,
    no_commit: bool = typer.Option(False, "--no-commit", help="Write the block but do not commit."),
) -> None:
    """Record what a ratified decision must reconcile (ADR-009 — `park` only).

    A decision is durable only when it reaches the surfaces personas pull WORK
    from. Recording it in decisions/ is the obvious half; parking the items it
    supersedes is the half that stops an agent picking up the now-wrong work.

    baron does NOT infer what a decision contradicts — the items are declared
    input. It records them, and `baron decision check` verifies discharge.
    """
    requested = [decision_mod.Park(p) for p in park]
    try:
        try:
            manifest = status_mod.load_manifest(collab)
        except Exception:
            manifest = {}
        unresolved = decision_mod.unresolved_parks(collab, manifest, requested)
        merged = decision_mod.reconcile(
            collab, number, parks=requested, commit=not no_commit,
        )
    except decision_mod.DecisionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"D{number}: {len(merged)} park obligation(s) recorded")
    for p in merged:
        typer.echo(f"  park {p.issue}")
    for p in unresolved:
        typer.echo(
            f"WARNING: `{p.issue}` matches nothing in the backlog. `check` will report "
            f"it unverifiable forever, since absence is not treated as proof. Record "
            f"the id exactly as the backlog writes it (e.g. GH-214, not 214).",
            err=True,
        )
    typer.echo("\nrun `baron decision check` to verify discharge; recording is not reconciling.")


@decision_app.command("check")
def decision_check(
    number: Optional[int] = typer.Argument(None, help="Only this decision (default: all)."),
    collab: Path = _COLLAB_OPT,
    fetch: bool = typer.Option(False, "--fetch", help="Query the forge for issue-tracker backlogs."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Verify every recorded park obligation is discharged.

    Three states, never two: discharged / outstanding / unverifiable. An
    unreachable forge is never scored as either (ADR-009 §4). Exit 0 = nothing
    outstanding, 1 = outstanding.
    """
    try:
        manifest = status_mod.load_manifest(collab)
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2)
    forge = repo = None
    if fetch:
        try:
            from .forge import get_forge

            # get_forge takes a forge NAME (default "github"); passing the manifest
            # raised TypeError: unhashable type: 'dict' — and it escaped the except
            # below, so the ONLY path that verifies a github_issues backlog crashed.
            forge = get_forge(str(manifest.get("forge", "github")))
            repo = collab
        except (ForgeError, ForgeUnavailable, TypeError, KeyError) as exc:
            typer.echo(
                f"note: forge unavailable ({exc.__class__.__name__}: {exc}) — "
                f"forge-backed checks report unverifiable"
            )
    try:
        findings = decision_mod.check(collab, manifest, only=number, forge=forge, repo=repo)
    except decision_mod.DecisionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)

    if json_out:
        _echo_json({"findings": [f.__dict__ for f in findings]})
    else:
        for f in findings:
            typer.echo(f"{f.state.upper():13s} D{f.decision} park {f.target}: {f.message}")
        outstanding = sum(1 for f in findings if f.state == decision_mod.OUTSTANDING)
        unver = sum(1 for f in findings if f.state == decision_mod.UNVERIFIABLE)
        typer.echo(
            f"{len(findings)} obligation(s): {outstanding} outstanding, {unver} unverifiable"
        )
    # Green only on all-DISCHARGED: unverifiable is amber, and amber is not green.
    raise typer.Exit(0 if decision_mod.is_green(findings) else 1)


@decision_app.command("new")
def decision_new(
    title: str = typer.Option(..., "--title", help="Decision title (goes in the heading)."),
    author: str = typer.Option(
        ...,
        "--author",
        help="Ledger attribution (the proposer named in the entry heading). "
        "Separate from the git author that signs the commit — a librarian can "
        "allocate --author <reviewer> while committing under its own identity.",
    ),
    body_file: Optional[Path] = typer.Option(
        None, "--body-file", help="File whose content becomes the entry body (default: a stub)."
    ),
    collab: Path = _COLLAB_OPT,
    no_push: bool = typer.Option(False, "--no-push", help="Commit locally only (offline)."),
    retries: int = typer.Option(
        3, "--retries", help="Push-rejection retries (fetch+rebase+renumber)."
    ),
) -> None:
    """Allocate the next D-number and append a house-style entry (same race-safe
    push-retry allocation as `baron finding new`)."""
    _ledger_new("decision", collab, title, author, body_file, no_push, retries)


# --- M3: handoffs ---------------------------------------------------------------------

handoff_app = typer.Typer(
    help="_handoff/ lifecycle: create -> close -> archive (never delete).",
    no_args_is_help=True,
)
app.add_typer(handoff_app, name="handoff")


@handoff_app.command("create")
def handoff_create(
    for_: str = typer.Option(..., "--for", help="Addressee persona (or `all`)."),
    from_: str = typer.Option(..., "--from", help="Sending persona."),
    title: str = typer.Option(..., "--title", help="Handoff title (also drives the filename slug)."),
    priority: str = typer.Option("medium", "--priority", help="low | medium | high."),
    body_file: Optional[Path] = typer.Option(
        None,
        "--body-file",
        help="File whose content becomes the handoff body under the frontmatter "
        "(default: just the title heading).",
    ),
    collab: Path = _COLLAB_OPT,
    no_commit: bool = typer.Option(False, "--no-commit", help="Write the file without committing."),
) -> None:
    """Write _handoff/YYYY-MM-DD-<slug>.md with standard frontmatter (status: open)."""
    if priority not in handoff_mod.PRIORITIES:
        typer.echo(f"error: --priority must be one of {handoff_mod.PRIORITIES}", err=True)
        raise typer.Exit(2)
    body: Optional[str] = None
    if body_file is not None:
        if not body_file.is_file():
            typer.echo(f"error: --body-file {body_file} not found", err=True)
            raise typer.Exit(2)
        body = body_file.read_text(encoding="utf-8")
    try:
        path = handoff_mod.create(
            collab.resolve(),
            for_=for_,
            from_=from_,
            title=title,
            priority=priority,
            body=body,
            commit=not no_commit,
        )
    except handoff_mod.HandoffError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(path.as_posix())


@handoff_app.command("close")
def handoff_close(
    file: Path = typer.Argument(..., help="The handoff file (path, or bare filename in _handoff/)."),
    note: Optional[str] = typer.Option(None, "--note", help="Closing note (added as a blockquote)."),
    as_: Optional[str] = typer.Option(
        None,
        "--as",
        help="Closing persona slug — attributes the close commit as `<slug>:` "
        "instead of the default `baron:`.",
    ),
    collab: Path = _COLLAB_OPT,
    no_commit: bool = typer.Option(False, "--no-commit", help="Move without git (no history-preserving mv)."),
) -> None:
    """Flip status to done (+ closed: date, optional note) and git-mv the file
    to _handoff/archive/YYYY/ — archive, never delete."""
    prefix = f"{as_.strip().lower()}:" if as_ and as_.strip() else "baron:"
    try:
        dest = handoff_mod.close(
            collab.resolve(), file, note=note, prefix=prefix, commit=not no_commit
        )
    except handoff_mod.HandoffError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(dest.as_posix())


@handoff_app.command("list")
def handoff_list(
    collab: Path = _COLLAB_OPT,
    open_only: bool = typer.Option(False, "--open", help="Only handoffs with status: open."),
    archived: bool = typer.Option(False, "--archived", help="Include archived handoffs."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """List handoffs with status, addressee, sender, and age."""
    items = handoff_mod.iter_handoffs(collab.resolve(), include_archived=archived)
    if open_only:
        items = [h for h in items if h.status == "open"]
    if json_out:
        _echo_json([h.to_dict() for h in items])
        return
    if not items:
        typer.echo("no handoffs")
        return
    for h in items:
        age = f"{h.age_days}d" if h.age_days is not None else "?"
        typer.echo(
            f"{h.status:6s} {h.path.name}  for={h.for_} from={h.from_} "
            f"priority={h.priority} age={age}"
        )


# --- M3: index ------------------------------------------------------------------------


@app.command()
def index(
    collab: Path = _COLLAB_OPT,
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Regenerate the BARON INDEX block in _handoff/README.md and verify ledger
    numbering (duplicates = error; gaps / out-of-order = report-only warnings —
    baron never renumbers history)."""
    root = collab.resolve()
    readme = indexer.update_readme(root)
    reports = [r for k in indexer.KINDS if (r := indexer.check_ledger(root, k)) is not None]
    duplicates = any(r.duplicates for r in reports)
    if json_out:
        _echo_json(
            {
                "readme": readme.as_posix(),
                "ledgers": [r.to_dict() for r in reports],
            }
        )
    else:
        typer.echo(f"wrote {readme.as_posix()}")
        for r in reports:
            if r.duplicates:
                typer.echo(f"ERROR   {r.kind}s: duplicate IDs {r.duplicates}")
            if r.gaps:
                typer.echo(f"warning {r.kind}s: numbering gaps at {r.gaps} (report-only)")
            if r.out_of_order:
                typer.echo(f"warning {r.kind}s: out-of-order headings at {r.out_of_order} (report-only)")
            if not (r.duplicates or r.gaps or r.out_of_order):
                typer.echo(f"ok      {r.kind}s: numbering duplicate-free and monotonic")
    raise typer.Exit(1 if duplicates else 0)


# --- P3.4 (partial): export -------------------------------------------------------------


@app.command()
def export(
    collab: Path = _COLLAB_OPT,
    kind: Optional[list[str]] = typer.Option(
        None,
        "--kind",
        help=(
            "Restrict to one or more kinds (repeatable): "
            + " | ".join(export_mod.KIND_ORDER)
            + ". Default: all four."
        ),
    ),
    adr_dir: str = typer.Option(
        export_mod.ADR_DIR, "--adr-dir", help="ADR directory, relative to the collab repo."
    ),
    archived: bool = typer.Option(
        True,
        "--archived/--no-archived",
        help="Include archived handoffs (default ON — the export is the history, not the queue).",
    ),
    allow_dirty: bool = typer.Option(
        False,
        "--allow-dirty",
        help=(
            "Also emit records from MODIFIED tracked sources, stamped `meta.dirty` "
            "(their citation resolves but returns the committed text, not what was "
            "parsed). Untracked sources are still skipped — they have no commit to cite."
        ),
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Export ADRs, decisions, findings and handoffs as citable records.

    One flat record per artifact — `{id, kind, title, path, commit_sha, status,
    body, links}` plus an open `meta` bag — walked from the same markdown the
    personas write. Every record names the commit whose bytes were parsed, so
    `git show <commit_sha>:<path>` reproduces the source exactly; that is the
    citation requirement AGENT-TASKS.md 3.4 puts on any knowledge substrate.

    A source that is untracked or has uncommitted edits is **skipped and named**
    (`skipped[]`), never emitted with a SHA that does not match its content.
    `--allow-dirty` relaxes that for modified tracked sources only, stamping
    `meta.dirty` on the affected records; an untracked source is skipped
    regardless, because `commit_sha` is never empty.

    This is a plain read — no knowledge backend, no plugin seam, no network
    ([ADR-015](../docs/adr/ADR-015-baron-export.md)). `baron export --json | jq
    '.records[] | select(.kind=="decision")'` is the whole intended workflow
    today. Exit 0; exit 2 if the collab path is not a git repo with history.
    """
    try:
        result = export_mod.collect(
            collab,
            kinds=set(kind) if kind else None,
            include_archived=archived,
            allow_dirty=allow_dirty,
            adr_dir=adr_dir,
        )
    except export_mod.ExportError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2)
    if json_out:
        _echo_json(result.to_dict())
        for s in result.skipped:
            typer.echo(
                f"warning: skipped {s.path} ({s.reason}) — {s.records} record(s) not citable",
                err=True,
            )
    else:
        typer.echo(export_mod.render_table(result))
    raise typer.Exit(0)


# --- M4: guard ------------------------------------------------------------------------


@app.command()
def guard(
    persona_file: Optional[Path] = typer.Option(
        None,
        "--persona-file",
        envvar=guard_mod.PERSONA_ENV,
        help="The acting persona's persona.yaml (or set BARON_PERSONA_FILE).",
    ),
) -> None:
    """Claude Code hook: capability enforcement (PreToolUse) + evidence capture.

    Reads the hook JSON from stdin (hook_event_name/session_id/cwd on every
    event, plus tool_name/tool_input on tool events, per
    https://code.claude.com/docs/en/hooks) and dispatches on hook_event_name.

    PreToolUse (or no hook_event_name) is the ENFORCEMENT path: the call is
    mapped to the frozen v1 capability verbs and guard either stays silent
    (exit 0 — normal permission flow) or blocks (exit 2, reason on stderr, fed
    to the model). Fail-closed on internal errors; BARON_GUARD_OVERRIDE=<reason>
    allows AND appends to the tracked .baron/guard-override.log.

    SessionStart / SessionEnd / Stop / PostToolUse / PostToolUseFailure are
    EVIDENCE ONLY — they emit one event and always exit 0 (ADR-012). Any other
    hook event exits 0 and does nothing. Only PreToolUse can ever block.

    Wire-up: see the Claude adapter's HYDRATE.md steps 3c (enforcement) and 3d
    (evidence).
    """
    code, stderr_text = guard_mod.process(sys.stdin.read(), persona_file)
    if stderr_text:
        typer.echo(stderr_text, err=True)
    raise typer.Exit(code)


# --- rules: inspect the capability-rules artifact (ADR-016) ---------------------------

rules_app = typer.Typer(
    help=(
        "Inspect the capability-rules artifact — the verb→enforcement table "
        "`baron guard` and the runtime adapters share "
        "(baron/data/capability-rules.v1.yaml). Read-only and diagnostic: "
        "baron loads PACKAGED rules only, so nothing here activates a rules "
        "file (ADR-016 §5)."
    ),
    no_args_is_help=True,
)
app.add_typer(rules_app, name="rules")


def _load_rules_or_exit(file: Optional[Path]) -> rules_mod.CapabilityRules:
    """The packaged artifact, or a candidate document named by ``--file``."""
    try:
        if file is None:
            return rules_mod.load_rules()
        return rules_mod.parse_file(file)
    except rules_mod.RulesError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2)


#: Longest verb-entry value rendered inline as `was -> now`. Anything longer
#: gets the two-line block form below.
_INLINE_VALUE_LIMIT = 60


def _oneline(text: str) -> str:
    """Collapse a verb-entry value onto one line (`notes` is a YAML block)."""
    return " ".join(text.split())


def _echo_value_change(key: str, was: str, now: str, flag: str) -> None:
    """Render one changed verb-entry field, never eliding the difference.

    Values are printed in FULL. An earlier draft truncated to a fixed prefix,
    which rendered two different `notes` blocks as an identical-looking pair —
    a diff that hides the diff is worse than no diff at all.
    """
    was, now = _oneline(was), _oneline(now)
    if len(was) <= _INLINE_VALUE_LIMIT and len(now) <= _INLINE_VALUE_LIMIT:
        typer.echo(f"    {key}: {was} -> {now}{flag}")
        return
    typer.echo(f"    {key}:{flag}")
    typer.echo(f"      base:      {was}")
    typer.echo(f"      candidate: {now}")


def _rules_for_verb(loaded: rules_mod.CapabilityRules, verb: str) -> list[str]:
    """Ids of the rules that can imply ``verb`` (rule ids, sorted by table order)."""
    return [rule.id for rule in loaded.rules if rule.verb == verb]


def _verb_rows(loaded: rules_mod.CapabilityRules) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for verb in CAPABILITY_VERBS:
        entry = loaded.verbs.get(verb, {})
        row: dict[str, object] = {
            "verb": verb,
            "class": entry.get("class", ""),
            "detection": entry.get("detection", "none"),
            "enforcement": loaded.enforcement(verb),
            "label": loaded.label(verb),
            "rules": _rules_for_verb(loaded, verb),
            "notes": entry.get("notes", "").strip(),
        }
        # The qualifier travels WITH the row, not just in a human-readable
        # footer: machine consumers are the ones most likely to trust `label`
        # unread. Absent when the label needs no qualifying.
        caveat = loaded.caveat(verb)
        if caveat:
            row["caveat"] = caveat
        rows.append(row)
    return rows


@rules_app.command("list")
def rules_list(
    file: Optional[Path] = typer.Option(
        None, "--file", help="Read this rules document instead of the packaged artifact."
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """List the verb table: class, detection modality, and the honest label.

    `enforcement` is three-state on purpose (ADR-002 honesty rule):
    `guard` = guard mechanically checks it; `adapter-dependent` = guard does
    NOT parse for it and neither does any adapter baron ships, though a runtime
    with a tool allow-list could; `instructed` = nothing checks it, the denial
    is prose in the persona body.

    `label` says `enforced` ONLY for `guard`. `adapter-dependent` labels
    `instructed` because nothing baron ships enforces it — see the `caveat`
    field (JSON) or the footer (table).
    """
    loaded = _load_rules_or_exit(file)
    rows = _verb_rows(loaded)
    qualified = [row for row in rows if row.get("caveat")]
    if json_out:
        payload: dict[str, object] = {
            "rules_version": loaded.rules_version,
            "vocabulary": loaded.vocabulary,
            "ambiguity_policy": loaded.ambiguity_policy,
            # Document-level too, so a consumer reading only the envelope still
            # sees what `label` does and does not promise.
            "label_caveat": rules_mod.LABEL_CAVEAT,
            "verbs": rows,
        }
        _echo_json(payload)
        return
    typer.echo(
        f"capability-rules v{loaded.rules_version} "
        f"({loaded.vocabulary}, ambiguity: {loaded.ambiguity_policy})"
    )
    typer.echo(f"{'VERB':<21}{'CLASS':<12}{'DETECTION':<11}{'ENFORCEMENT':<19}LABEL")
    for row in rows:
        typer.echo(
            f"{row['verb']:<21}{row['class']:<12}{row['detection']:<11}"
            f"{row['enforcement']:<19}{row['label']}"
        )
        rule_ids = row["rules"]
        if rule_ids:
            typer.echo(f"{'':<21}rules: {', '.join(rule_ids)}")  # type: ignore[arg-type]
    if qualified:
        verbs = ", ".join(str(row["verb"]) for row in qualified)
        # The claim, then its evidence one adapter per line. The JSON payload
        # carries both in a single `label_caveat` string (ADR-020 §5).
        typer.echo(f"\nnote ({verbs}): {rules_mod.LABEL_CAVEAT_SUMMARY}")
        for adapter, why in rules_mod.READ_VERB_MEASUREMENTS.items():
            typer.echo(f"  measured — {adapter}: {why}")


@rules_app.command("validate")
def rules_validate(
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        help=(
            "Validate this candidate rules document instead of the packaged "
            "artifact. Validating a file does NOT activate it — baron loads "
            "packaged rules only (ADR-016 §5)."
        ),
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Parse a rules artifact and report the negotiation + integrity checks.

    Exit 0 clean, 1 if a check fails, 2 if the document is refused outright —
    the same refusal guard turns into a fail-closed DENY. A document is refused
    when it is unreadable, not YAML, names an unsupported
    `rules_version`/`vocabulary`, carries a key or a rule this baron does not
    implement, names an unknown matcher (or one other than the matcher guard
    implements for that rule), or omits a built-in rule. Unrecognised content is
    never dropped silently.
    """
    loaded = _load_rules_or_exit(file)
    origin = file.as_posix() if file is not None else f"packaged {rules_mod.RULES_RESOURCE}"

    checks: list[dict[str, object]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})

    # The first two and the last are parser-enforced — a mismatch never reaches
    # here, it exits 2 above. They are reported so `validate` shows WHAT was
    # negotiated, not just that nothing blew up.
    check(
        "rules_version",
        True,
        f"{loaded.rules_version} == supported {rules_mod.SUPPORTED_RULES_VERSION} "
        "(exact match, parser-enforced; negotiation is not a range)",
    )
    check(
        "vocabulary",
        True,
        f"{loaded.vocabulary} == supported {rules_mod.SUPPORTED_VOCABULARY} "
        "(parser-enforced)",
    )
    missing = sorted(set(CAPABILITY_VERBS) - set(loaded.verbs))
    extra = sorted(set(loaded.verbs) - set(CAPABILITY_VERBS))
    check(
        "frozen vocabulary",
        not missing and not extra,
        f"{len(loaded.verbs)} verbs; missing={missing or 'none'} extra={extra or 'none'}",
    )
    unbound = sorted(
        {rule.verb for rule in loaded.rules if rule.verb and rule.verb not in loaded.verbs}
    )
    check(
        "rule verbs resolve",
        not unbound,
        f"{len(loaded.rules)} rules "
        f"({len(loaded.command_rules)} command + {len(loaded.path_rules)} path); "
        f"unbound={unbound or 'none'}",
    )
    check(
        "ambiguity policy",
        loaded.ambiguity_policy == "conservative-deny",
        loaded.ambiguity_policy or "(unset)",
    )
    check(
        "matchers known",
        True,
        f"{len(loaded.command_rules)} command rules name a matcher in the closed "
        "set AND the one guard implements (parser-enforced, from the document); "
        "path-rule matchers are structural, not document-supplied",
    )
    # RE-DERIVED here, not asserted. The parser refuses an inconsistent document
    # before it reaches this code (rules._check_detection_consistency), so this
    # can only fail against a CONSTRUCTED CapabilityRules — but a check whose
    # text claims coverage must compute the thing it claims. The round-2 version
    # of the check below was hardcoded True and printed `ok` over a document
    # containing `detection: banana`; that is the exact failure mode ADR-002 and
    # ADR-008 exist to prevent, so nothing here is hardcoded that can be counted.
    misdescribed: list[str] = []
    for verb, entry in loaded.verbs.items():
        modality = entry.get("detection", rules_mod.DETECTION_NONE)
        bound = [rule for rule in loaded.rules if rule.verb == verb]
        chain = verb in rules_mod.FILE_OP_CHAIN_VERBS
        claims = modality != rules_mod.DETECTION_NONE
        implemented = bool(bound) or (chain and modality == rules_mod.DETECTION_FILE_OP)
        if claims != implemented:
            misdescribed.append(f"{verb} (detection={modality}, rules={len(bound)})")
    check(
        "detection matches implementation",
        not misdescribed,
        (
            f"{len(loaded.verbs)} verbs; every `enforced` label is backed by a "
            "rule or the file-op precedence chain (parser-enforced, re-derived "
            "here)"
        )
        if not misdescribed
        else "misdescribed: " + ", ".join(misdescribed),
    )
    check(
        "no unrecognised content",
        True,
        "every key, rule slot and enumerated value (class, detection, matcher) "
        "in the document is one this baron implements (parser-enforced: unknown "
        "content is refused, never ignored)",
    )

    failed = [c for c in checks if not c["ok"]]
    if json_out:
        _echo_json(
            {
                "source": origin,
                "ok": not failed,
                "checks": checks,
                "label_caveat": rules_mod.LABEL_CAVEAT,
            }
        )
    else:
        typer.echo(f"source: {origin}")
        for c in checks:
            status = "ok    " if c["ok"] else "FAIL  "
            typer.echo(f"{status}  {c['check']}: {c['detail']}")
        typer.echo("valid" if not failed else f"{len(failed)} check(s) failed")
    raise typer.Exit(1 if failed else 0)


@rules_app.command("diff")
def rules_diff(
    file: Path = typer.Option(
        ...,
        "--file",
        help="Candidate rules document to compare against the packaged artifact.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Diff a candidate rules document against the packaged artifact.

    Joins on rule id. Exit 0 if identical, 1 if they differ, 2 if either side
    is refused. A candidate carrying a rule or key this baron does not
    implement is REFUSED (exit 2), not reported as an addition — so `identical`
    can never be printed over content that was quietly dropped.

    A clean diff is NOT an adoption path: baron still loads only the packaged
    artifact (ADR-016 §5).
    """
    base = _load_rules_or_exit(None)
    other = _load_rules_or_exit(file)

    base_rules = {rule.id: rule for rule in base.rules}
    other_rules = {rule.id: rule for rule in other.rules}
    delta = rules_mod.diff_rules(base, other)
    header = delta["header"]
    added = delta["rules_added"]
    removed = delta["rules_removed"]
    changed = delta["rules_changed"]
    verbs_added = delta["verbs_added"]
    verbs_removed = delta["verbs_removed"]
    verbs_changed = delta["verbs_changed"]

    payload = {
        "base": f"packaged {rules_mod.RULES_RESOURCE}",
        "candidate": file.as_posix(),
        **delta,
    }
    differs = any(delta.values())
    if json_out:
        _echo_json({**payload, "identical": not differs})
    elif not differs:
        typer.echo("identical to the packaged artifact")
    else:
        for line in header:
            typer.echo(f"~ {line}")
        for rid in added:
            typer.echo(f"+ rule {rid} ({other_rules[rid].verb})")
        for rid in removed:
            typer.echo(f"- rule {rid} ({base_rules[rid].verb})")
        for rid in changed:
            typer.echo(f"~ rule {rid}")
            typer.echo(f"    base:      {base_rules[rid]}")
            typer.echo(f"    candidate: {other_rules[rid]}")
        for verb in verbs_added:
            typer.echo(f"+ verb {verb}  (NOT in the frozen vocabulary)")
        for verb in verbs_removed:
            typer.echo(f"- verb {verb}")
        for verb in verbs_changed:  # type: ignore[union-attr]
            typer.echo(f"~ verb {verb}")
            base_entry = base.verbs[verb]
            other_entry = other.verbs[verb]
            for key in sorted(set(base_entry) | set(other_entry)):
                was, now = base_entry.get(key, "(absent)"), other_entry.get(key, "(absent)")
                if was == now:
                    continue
                # `class` and `detection` change what baron CLAIMS to enforce;
                # spell the consequence out rather than leaving a reviewer to
                # re-derive it from the routing rules.
                was_claim = (base.enforcement(verb), base.label(verb))
                now_claim = (other.enforcement(verb), other.label(verb))
                flag = (
                    f"  [{was_claim[0]}/{was_claim[1]} -> {now_claim[0]}/{now_claim[1]}]"
                    if key in ("class", "detection") and was_claim != now_claim
                    else ""
                )
                _echo_value_change(key, was, now, flag)
    raise typer.Exit(1 if differs else 0)


@rules_app.command("explain")
def rules_explain(
    target: str = typer.Argument(
        ..., help="A shell command (default), or a file path with --write."
    ),
    persona_file: Path = typer.Option(
        ...,
        "--persona-file",
        envvar=guard_mod.PERSONA_ENV,
        help="The acting persona's persona.yaml (or set BARON_PERSONA_FILE).",
    ),
    write: bool = typer.Option(
        False,
        "--write",
        help="Treat TARGET as a write-tool path (Edit/Write/NotebookEdit) instead "
        "of a shell command.",
    ),
    tool: str = typer.Option(
        "Write", "--tool", help="Write tool name to attribute the call to (with --write)."
    ),
    cwd: Path = typer.Option(
        Path("."),
        "--cwd",
        help="Directory the call would run in — branch resolution reads it.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Show what `baron guard` would decide for one call, and why.

    Runs the SAME evaluators the PreToolUse hook runs
    (`guard.evaluate_bash` / `guard.evaluate_write`) — this is a dry run of the
    real decision, not a reimplementation, so the two cannot drift.

    Exit 0 = the call would pass, 1 = it would be DENIED, 2 = guard could not
    evaluate it (which the hook turns into a fail-closed deny).

    Honest limit: `candidate_rules` lists the rules that CAN imply each verb,
    not the single rule instance that matched — guard reports the concrete
    inference in `reason` instead (e.g. "force flag `--force`"), and
    re-deriving it here would mean a second parser that could drift from the
    first.
    """
    loaded = _load_rules_or_exit(None)
    try:
        persona = guard_mod.load_persona(persona_file)
        where = cwd.resolve()
        if write:
            decision = guard_mod.evaluate_write(tool, {"file_path": target}, where, persona)
        else:
            decision = guard_mod.evaluate_bash(target, where, persona)
    except guard_mod.GuardError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2)

    verbs = []
    for verb in decision.verbs:
        entry: dict[str, object] = {
            "verb": verb,
            "enforcement": loaded.enforcement(verb),
            "label": loaded.label(verb),
            "candidate_rules": _rules_for_verb(loaded, verb),
        }
        caveat = loaded.caveat(verb)
        if caveat:
            entry["caveat"] = caveat
        verbs.append(entry)
    if json_out:
        _echo_json(
            {
                "target": target,
                "mode": "write" if write else "bash",
                "tool": tool if write else "Bash",
                "cwd": where.as_posix(),
                "persona": {
                    "slug": persona.slug,
                    "file": persona_file.as_posix(),
                },
                "allowed": decision.allowed,
                "verbs": verbs,
                "reason": decision.reason,
            }
        )
    else:
        typer.echo(f"target : {target}")
        typer.echo(f"persona: {persona.slug or persona_file.name} ({persona_file})")
        typer.echo(f"verdict: {'ALLOW' if decision.allowed else 'DENY'}")
        if not verbs:
            typer.echo("verbs  : (none — guard maps no capability verb to this call)")
        else:
            typer.echo("verbs  :")
        for entry in verbs:
            rule_ids = ", ".join(entry["candidate_rules"]) or "—"  # type: ignore[arg-type]
            typer.echo(
                f"  {entry['verb']:<21}{entry['label']:<11}"
                f"({entry['enforcement']}; candidate rules: {rule_ids})"
            )
        if decision.reason:
            typer.echo("reason :")
            for line in decision.reason.splitlines():
                typer.echo(f"  {line}")
    raise typer.Exit(0 if decision.allowed else 1)
# --- doctor: guard wiring self-test -----------------------------------------------------


@app.command()
def doctor(
    dir_: Path = typer.Option(
        Path("."),
        "--dir",
        help="Project directory the runtime starts in (the one holding .claude/settings.json).",
    ),
    persona_file: Optional[Path] = typer.Option(
        None,
        "--persona-file",
        help="Check this persona instead of the one the hook command names.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Self-test the `baron guard` WIRING — and fail loudly when it is missing.

    The badminton-analyzer incident merged 15 PRs under a persona whose
    `merge_pr` denial was believed enforced; the hook had never been installed,
    so the denial had silently degraded to persona text. This command is that
    silence's remedy: it checks that the hook's executable resolves, that a
    PreToolUse hook in `.claude/settings.json` invokes `baron guard` with a
    matcher covering every governed tool, that the named persona and the
    capability-rules artifact load, that a synthetic denial fed to THAT
    EXECUTABLE really exits 2, that malformed stdin fails closed (ADR-004 §2.3),
    and that BARON_GUARD_OVERRIDE is not sitting exported. Exit 1 on any FAIL.

    Honesty boundary: doctor verifies WIRING, not invocation. It proves the
    install CAN enforce; it cannot observe whether Claude Code actually ran the
    hook on a real tool call. A green doctor means "correctly wired", never
    "enforcement happened". Two further bounds, both printed: the denial probes
    spawn the hook's own command (`uv run`-style prefixes included) and fall back
    to the in-process guard module only when no resolvable executable is named —
    saying so when they do; and a bare executable name resolves against DOCTOR's
    PATH, not the runtime's. Project-level settings only — a hook wired in
    ~/.claude/settings.json is invisible here.
    """
    if not dir_.is_dir():
        typer.echo(f"error: {dir_} is not a directory", err=True)
        raise typer.Exit(2)
    report = doctor_mod.run(dir_, persona_file=persona_file)
    if json_out:
        _echo_json(report.to_dict())
    else:
        typer.echo(doctor_mod.render(report))
    raise typer.Exit(0 if report.ok else 1)


# --- runtime hydrators ----------------------------------------------------------------

hydrate_app = typer.Typer(
    help="Hydrate a persona.yaml onto a specific runtime (adapters/<runtime>/HYDRATE.md).",
    no_args_is_help=True,
)
app.add_typer(hydrate_app, name="hydrate")


@hydrate_app.command("pydantic-ai")
def hydrate_pydantic_ai(
    persona_file: Path = typer.Option(
        ..., "--persona-file", help="The persona's persona.yaml."
    ),
    out: Path = typer.Option(
        Path("agent_setup.py"),
        "--out",
        help="Where to write the ready-to-edit bootstrap script.",
    ),
    collab: Path = _COLLAB_OPT,
) -> None:
    """Emit a ready-to-edit pydantic-ai bootstrap script for one persona.

    The script imports baron.runtimes.pydantic_ai.build_agent and carries a
    model placeholder ("test" — offline — until you pick a real model).
    Emission needs only baron; RUNNING the script needs the optional extra
    (pip install 'barony[pydantic-ai]', pinned to the verified
    pydantic-ai-harness range).
    """
    if not persona_file.is_file():
        typer.echo(f"error: persona file not found: {persona_file}", err=True)
        raise typer.Exit(2)
    script = runtimes.render_pydantic_ai_bootstrap(persona_file, collab_root=collab)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(script, encoding="utf-8")
    typer.echo(out.as_posix())
    typer.echo(
        "note: running it requires the extra — pip install 'barony[pydantic-ai]'"
    )


# --- M5: lock -------------------------------------------------------------------------

lock_app = typer.Typer(
    help="PR-as-lock (ADR-002 §3): the open PR is the lock; labels are the query surface.",
    no_args_is_help=True,
)
app.add_typer(lock_app, name="lock")

_REPO_OPT = typer.Option(
    Path("."),
    "--repo",
    help="The repo the lock applies to (default: current directory).",
)


@lock_app.command("claim")
def lock_claim(
    path: str = typer.Argument(..., help="Repo-relative path (or glob) to lock."),
    reason: Optional[str] = typer.Option(None, "--reason", help="Why the lock is held."),
    repo: Path = _REPO_OPT,
) -> None:
    """Claim a lock: lock/<slug> branch + empty commit + draft PR labeled lock:<path>.

    Refuses (showing the holder) if an open lock PR for the same path exists."""
    try:
        url = lock_mod.claim(repo.resolve(), path, reason=reason)
    except (lock_mod.LockError, ForgeUnavailable, ForgeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"locked {path} — {url}")


@lock_app.command("release")
def lock_release(
    path: str = typer.Argument(..., help="The locked path to release."),
    repo: Path = _REPO_OPT,
) -> None:
    """Release a lock: close its lock PR and delete the lock/<slug> branch."""
    try:
        number = lock_mod.release(repo.resolve(), path)
    except (lock_mod.LockError, ForgeUnavailable, ForgeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"released {path} (closed PR #{number})")


@lock_app.command("list")
def lock_list(
    repo: Path = _REPO_OPT,
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """List open locks (every open PR carrying a lock:* label)."""
    try:
        locks = lock_mod.list_locks(repo.resolve())
    except (ForgeUnavailable, ForgeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    if json_out:
        _echo_json([l.to_dict() for l in locks])
    else:
        typer.echo(lock_mod.render_table(locks))


# --- M6 tooling: worktrees ------------------------------------------------------------

worktree_app = typer.Typer(
    help="Branch-per-persona worktree topology (one shared object store).",
    no_args_is_help=True,
)
app.add_typer(worktree_app, name="worktree")

_WT_REPO_OPT = typer.Option(
    None,
    "--repo",
    help="The code repo (default: manifest repos[role=code] via --collab, else cwd).",
)
_WT_ROOT_OPT = typer.Option(
    None,
    "--root",
    help="Worktrees root (default: manifest workspace.worktrees_root via --collab).",
)


def _worktree_context(
    collab: Path, repo_opt: Optional[Path], root_opt: Optional[Path], *, need_root: bool
) -> tuple[Path, Optional[Path]]:
    """Resolve (code_repo, worktrees_root) from options, falling back to the
    manifest (workspace.worktrees_root, repos[role=code])."""
    repo = repo_opt
    root = root_opt
    if repo is None or (root is None and need_root):
        try:
            manifest = status_mod.load_manifest(collab.resolve())
        except (FileNotFoundError, ValueError) as exc:
            if repo is None:
                repo = Path(".")
            if root is None and need_root:
                typer.echo(
                    f"error: --root not given and manifest unavailable ({exc})", err=True
                )
                raise typer.Exit(2)
            manifest = None
        if manifest is not None:
            manifest_root = status_mod._resolve_root(collab.resolve(), manifest)
            if repo is None:
                for entry in manifest.get("repos", []) or []:
                    if isinstance(entry, dict) and entry.get("role") == "code":
                        repo = (manifest_root / str(entry.get("path", "."))).resolve()
                        break
                else:
                    repo = Path(".")
            if root is None:
                worktrees_root = (manifest.get("workspace") or {}).get("worktrees_root")
                if worktrees_root:
                    root = (manifest_root / str(worktrees_root)).resolve()
                elif need_root:
                    typer.echo(
                        "error: no --root and the manifest has no "
                        "workspace.worktrees_root", err=True,
                    )
                    raise typer.Exit(2)
    assert repo is not None
    return repo.resolve(), root


@worktree_app.command("add")
def worktree_add(
    persona: str = typer.Argument(..., help="Persona slug (branch persona/<slug>)."),
    root: Optional[Path] = _WT_ROOT_OPT,
    repo: Optional[Path] = _WT_REPO_OPT,
    collab: Path = _COLLAB_OPT,
) -> None:
    """Create <root>/<persona> as a git worktree on branch persona/<persona>
    (created from the default branch if missing)."""
    code_repo, wt_root = _worktree_context(collab, repo, root, need_root=True)
    assert wt_root is not None
    try:
        dest = worktree_mod.add(code_repo, persona, wt_root)
    except worktree_mod.WorktreeError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(dest.as_posix())


@worktree_app.command("list")
def worktree_list(
    repo: Optional[Path] = _WT_REPO_OPT,
    collab: Path = _COLLAB_OPT,
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """List worktrees with each branch's ahead/behind vs the default branch."""
    code_repo, _ = _worktree_context(collab, repo, None, need_root=False)
    try:
        worktrees = worktree_mod.list_worktrees(code_repo)
    except worktree_mod.WorktreeError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    if json_out:
        _echo_json([w.to_dict() for w in worktrees])
    else:
        typer.echo(worktree_mod.render_table(worktrees))


@worktree_app.command("remove")
def worktree_remove(
    persona: str = typer.Argument(..., help="Persona slug whose worktree to remove."),
    repo: Optional[Path] = _WT_REPO_OPT,
    collab: Path = _COLLAB_OPT,
    force: bool = typer.Option(
        False, "--force", help="Remove even if dirty or holding unmerged commits."
    ),
) -> None:
    """Remove a persona worktree. Refuses when dirty or unmerged unless --force;
    the persona/<slug> branch is kept either way."""
    code_repo, _ = _worktree_context(collab, repo, None, need_root=False)
    try:
        removed = worktree_mod.remove(code_repo, persona, force=force)
    except worktree_mod.WorktreeError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"removed {removed.as_posix()} (branch persona/{persona} kept)")


@worktree_app.command("prune")
def worktree_prune(
    repo: Optional[Path] = _WT_REPO_OPT,
    collab: Path = _COLLAB_OPT,
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report what would be pruned (git worktree prune -n); change nothing."
    ),
) -> None:
    """Prune stale worktree registrations (`git worktree prune`).

    Clears the administrative entries git leaves in `.git/worktrees/` when a
    worktree directory is moved or deleted outside baron. Non-destructive: it
    only touches admin state — no branch or commit is affected."""
    code_repo, _ = _worktree_context(collab, repo, None, need_root=False)
    try:
        report = worktree_mod.prune(code_repo, dry_run=dry_run)
    except worktree_mod.WorktreeError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    if report:
        typer.echo(report)
        if dry_run:
            typer.echo("(dry run — nothing removed; rerun without --dry-run to prune)")
    else:
        typer.echo("nothing to prune (no stale worktree registrations)")


@worktree_app.command("repair")
def worktree_repair(
    paths: Optional[list[Path]] = typer.Argument(
        None, help="Worktree paths to repair (default: repair all worktrees)."
    ),
    repo: Optional[Path] = _WT_REPO_OPT,
    collab: Path = _COLLAB_OPT,
) -> None:
    """Repair worktree admin links after a move (`git worktree repair`).

    Fixes the gitdir pointer and each worktree's `.git` gitlink after a worktree
    or the main repo was moved on disk. Non-destructive: it only re-points admin
    files — no branch or commit is affected. Requires git >= 2.30."""
    code_repo, _ = _worktree_context(collab, repo, None, need_root=False)
    try:
        report = worktree_mod.repair(code_repo, paths or None)
    except worktree_mod.WorktreeError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(report if report else "nothing to repair (worktree links intact)")


# --- waivers --------------------------------------------------------------------------

waiver_app = typer.Typer(
    help="Status waivers (.baron-waivers.yaml): park a red deliberately, with expiry.",
    no_args_is_help=True,
)
app.add_typer(waiver_app, name="waiver")


@waiver_app.command("add")
def waiver_add(
    pattern: str = typer.Argument(
        ..., help="fnmatch pattern on the `baron status` SUBJECT column."
    ),
    reason: str = typer.Option(..., "--reason", help="Why the red is deliberate."),
    handoff: str = typer.Option(
        ..., "--handoff", help="Collab-relative handoff path documenting the park."
    ),
    expires: str = typer.Option(..., "--expires", help="YYYY-MM-DD expiry."),
    collab: Path = _COLLAB_OPT,
) -> None:
    """Add a waiver: matching red findings show as warn until the expiry."""
    try:
        path = waivers_mod.add(
            collab.resolve(), pattern, reason=reason, handoff=handoff, expires=expires
        )
    except waivers_mod.WaiverError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(path.as_posix())


@waiver_app.command("list")
def waiver_list(
    collab: Path = _COLLAB_OPT,
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """List waivers (active and expired) with their expiry state."""
    entries, problems = waivers_mod.load(collab.resolve())
    today = clock.today()
    if json_out:
        _echo_json(
            {
                "waivers": [
                    {**w.to_dict(), "expired": w.expired(today)} for w in entries
                ],
                "problems": problems,
            }
        )
        return
    if not entries and not problems:
        typer.echo("no waivers")
        return
    for w in entries:
        state = "EXPIRED" if w.expired(today) else "active"
        typer.echo(
            f"{state:7s} {w.subject}  expires={w.expires.isoformat()} "
            f"reason={w.reason} handoff={w.handoff}"
        )
    for problem in problems:
        typer.echo(f"problem {problem}")


# --- session ritual primitives (optional; ADR-007) ------------------------------------

session_app = typer.Typer(
    help=(
        "Optional session-ritual bookkeeping (ADR-007). start|end mechanize the "
        "git/markdown bookkeeping of the session ritual; they do NOT run an agent "
        "— orchestration is the runtime's job. Opt-in and composable; not new "
        "capability verbs (the frozen 10 stay frozen)."
    ),
    no_args_is_help=True,
)
app.add_typer(session_app, name="session")


@session_app.command("start")
def session_start(
    collab: Path = _COLLAB_OPT,
    persona: Optional[str] = typer.Option(
        None, "--persona", help="Scope the brief to this persona slug (else all personas)."
    ),
    sync: bool = typer.Option(
        False,
        "--sync",
        help="`git pull --ff-only` each manifest working copy first (a git mutation; "
        "default off). Never merges or force-pulls; non-fast-forwards are reported.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Session-open bookkeeping: sync (optional), then surface the brief.

    Read-mostly (only ``--sync`` mutates): surfaces OPEN handoffs for the persona
    (else all), a pointer to CONVENTIONS.md/COORDINATION.md, and the manifest
    backlog location. These mechanize the git/markdown bookkeeping of the session
    ritual; they do NOT run an agent — orchestration is the runtime's job
    (ADR-007). Opt-in and composable; not a new capability verb.
    """
    try:
        brief = session_mod.start(collab.resolve(), persona=persona, sync=sync)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2)
    if json_out:
        _echo_json(brief.to_dict())
    else:
        typer.echo(session_mod.render_brief(brief))
    raise typer.Exit(0)


@session_app.command("end")
def session_end(
    collab: Path = _COLLAB_OPT,
    persona: Optional[str] = typer.Option(
        None,
        "--persona",
        help="Attribute the coordination commit with this persona's commit_prefix "
        "(else `baron:`).",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Session-close bookkeeping: regenerate the index, commit dirty coordination
    artifacts, end with a divergence check.

    Regenerates the handoff index (``baron index`` logic); commits any dirty
    ``_handoff/ findings/ decisions/ wiki/`` paths (staged by path — NEVER
    ``git add -A``) with the persona's ``commit_prefix`` (else ``baron:``); then
    prints a ``baron status`` summary. Skips the commit cleanly when nothing is
    outstanding. Exit 0 green / 1 if status finds red (CI-usable). These
    mechanize the git/markdown bookkeeping of the session ritual; they do NOT run
    an agent — orchestration is the runtime's job (ADR-007).
    """
    try:
        report = session_mod.end(collab.resolve(), persona=persona)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2)
    if json_out:
        _echo_json(report.to_dict())
    else:
        typer.echo(session_mod.render_end(report))
    raise typer.Exit(1 if report.reds else 0)


@app.command("notify")
def notify_cmd(
    persona: str = typer.Argument(..., help="Persona to notify (the handoff's `for:`)."),
    title: str = typer.Option(..., "--title", help="Handoff title (drives the filename slug)."),
    from_: Optional[str] = typer.Option(
        None, "--from", help="Sending persona. Required unless --no-wake."
    ),
    body_file: Optional[Path] = typer.Option(
        None, "--body-file", help="File whose content becomes the handoff body."
    ),
    in_reply_to: Optional[str] = typer.Option(
        None, "--in-reply-to", help="Parent handoff stem; carries the wake_depth chain (ADR-010 §5.1)."
    ),
    max_depth: int = typer.Option(
        notify_mod.DEFAULT_MAX_DEPTH, "--max-depth", help="Refuse to wake past this hop count."
    ),
    no_wake: bool = typer.Option(
        False, "--no-wake", help="Deliver the handoff only; fire no repository_dispatch."
    ),
    collab: Path = _COLLAB_OPT,
) -> None:
    """Deliver a _handoff/ to <persona>, then (unless --no-wake) fire a repository_dispatch
    so a project-owned workflow spawns them. Delivery never depends on the wake (ADR-010)."""
    wake = not no_wake
    if wake and not from_:
        typer.echo(
            "error: --from is required unless --no-wake "
            "(it keys manifest.notify.wake_allowed and wake_origin)",
            err=True,
        )
        raise typer.Exit(2)
    body: Optional[str] = None
    if body_file is not None:
        if not body_file.is_file():
            typer.echo(f"error: --body-file {body_file} not found", err=True)
            raise typer.Exit(2)
        body = body_file.read_text(encoding="utf-8")
    forge = None
    if wake:
        try:
            from .forge import get_forge

            forge = get_forge("github")
        except Exception:
            forge = None
    try:
        result = notify_mod.notify(
            collab.resolve(),
            persona=persona,
            title=title,
            from_=from_ or "baron",
            body=body,
            in_reply_to=in_reply_to,
            max_depth=max_depth,
            wake=wake,
            forge=forge,
        )
    except notify_mod.NotifyError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(result.handoff.as_posix())
    if result.woke:
        routed = f" -> project {result.project}" if result.project else ""
        typer.echo(
            f"woke {persona}{routed}: repository_dispatch fired "
            f"(wake_depth {result.wake_depth})."
        )
    else:
        typer.echo(f"delivered; no wake — {result.suppressed}")


sidecar_app = typer.Typer(
    help="Per-persona deployable work loop (ADR-026 persona sidecar).",
    no_args_is_help=True,
)
app.add_typer(sidecar_app, name="sidecar")


@sidecar_app.command("run")
def sidecar_run(
    persona: str = typer.Argument(..., help="Persona slug to run a cycle for."),
    collab: Path = _COLLAB_OPT,
    cmd: Optional[str] = typer.Option(
        None,
        "--cmd",
        envvar="BARON_SIDECAR_CMD",
        help="The runtime invocation (project-owned). Brief on stdin, also at "
        "$BARON_SIDECAR_BRIEF; `{brief_file}` in the command is replaced with that path.",
    ),
    trigger: Optional[str] = typer.Option(
        None, "--trigger", help="Override persona.yaml runtime.trigger (interactive|event|cron)."
    ),
    watch: bool = typer.Option(
        False, "--watch", help="Long-running: keep cycling (event/cron triggers only)."
    ),
    interval: int = typer.Option(
        sidecar_mod.DEFAULT_WATCH_INTERVAL, "--interval", help="Seconds between --watch cycles."
    ),
    max_cycles: Optional[int] = typer.Option(
        None, "--max-cycles", help="Stop --watch after this many cycles (default: never)."
    ),
    timeout: Optional[int] = typer.Option(
        None, "--timeout", help="Kill the runtime command after this many seconds."
    ),
    force: bool = typer.Option(
        False, "--force", help="Invoke the runtime even when the sweep finds no work."
    ),
    no_push: bool = typer.Option(False, "--no-push", help="Commit outcomes but do not push."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Plan + brief only: no sync, no runtime, nothing landed."
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """One sidecar cycle for <persona>: sync the collab repo, sweep _handoff/ (review
    feedback before new work) and the labelled backlog, invoke the runtime once, then
    commit and push the outcome.

    The runtime invocation is yours (--cmd / $BARON_SIDECAR_CMD, defaulted in the
    emitted `agents/<slug>/sidecar.sh`): baron syncs, sweeps, commits and pushes; it
    does not own the agent loop (ADR-007). Exit 0 green, 1 if the runtime failed.
    """
    kwargs = dict(
        cmd=cmd,
        trigger=trigger,
        dry_run=dry_run,
        force=force,
        push=not no_push,
        timeout=timeout,
    )

    def emit(report: sidecar_mod.CycleReport) -> None:
        if json_out:
            _echo_json(report.to_dict())
        else:
            typer.echo(sidecar_mod.render_cycle(report))

    try:
        if watch:
            reports = sidecar_mod.watch(
                collab.resolve(),
                persona,
                interval=interval,
                max_cycles=max_cycles,
                on_cycle=emit,
                **kwargs,
            )
            raise typer.Exit(0 if all(r.ok for r in reports) else 1)
        report = sidecar_mod.run_cycle(collab.resolve(), persona, **kwargs)
    except sidecar_mod.SidecarError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2)
    emit(report)
    raise typer.Exit(0 if report.ok else 1)


verdict_app = typer.Typer(
    help="Reviewer/merger verdicts on the observation plane (ADR-024 fleet-health)."
)
app.add_typer(verdict_app, name="verdict")


@verdict_app.command("record")
def verdict_record(
    pr: int = typer.Option(..., "--pr", help="PR number reviewed."),
    head: str = typer.Option(..., "--head", help="Head SHA the verdict is bound to."),
    from_: str = typer.Option(..., "--from", help="Reviewing persona."),
    verdict_: str = typer.Option(..., "--verdict", help="approved | changes | needs-human | ..."),
    mutations_run: int = typer.Option(0, "--mutations-run", help="Mutation-check tally: run."),
    mutations_killed: int = typer.Option(0, "--mutations-killed", help="Mutation-check tally: killed."),
    drift: int = typer.Option(0, "--drift", help="Claim-vs-code drift instances found this verdict."),
    drift_understating: int = typer.Option(0, "--drift-understating", help="Of those, how many pointed the safe/understating way."),
    escape: bool = typer.Option(False, "--escape", help="Caught a defect a PRIOR review of an earlier head passed (a reviewer miss)."),
    altitude: Optional[int] = typer.Option(None, "--altitude", help="Round number if this is a recurring bug chased across heads."),
    note: str = typer.Option("", "--note", help="<=80 char note."),
    collab: Path = _COLLAB_OPT,
) -> None:
    """Emit a review.verdict event. Default sink is null (D4) — set BARON_EVENTS_SINK=disk to record."""
    verdict_mod.record(
        collab.resolve(), author=from_, pr=pr, head=head, verdict=verdict_,
        mutations_run=mutations_run, mutations_killed=mutations_killed,
        drift_instances=drift, drift_understating=drift_understating,
        escape=escape, altitude=altitude, note=note,
    )
    typer.echo(f"recorded review.verdict for PR #{pr}@{head}")


@app.command("health")
def health_cmd(
    since: Optional[str] = typer.Option(None, "--since", help="ISO date prefix; drop verdicts before it."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
    collab: Path = _COLLAB_OPT,
) -> None:
    """Fleet-health rollup: reviewer-quality metrics from the plane + baron status stalls (ADR-024).

    Read-only. Measures what was emitted, not what happened — a fleet that records no
    verdicts shows a clean board, so the report states its coverage.

    At a coordination-monorepo root (ADR-025) this is portfolio-wide: one report per
    project subdir plus a rolled-up total. The honest bound rolls up with it."""
    collab_root = collab.resolve()
    if monorepo_mod.is_root(collab_root):
        try:
            portfolio = monorepo_mod.collect_health(collab_root, since=since)
        except monorepo_mod.MonorepoError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(2)
        if json_out:
            _echo_json(portfolio.to_dict())
        else:
            typer.echo(monorepo_mod.render_health(portfolio))
        return
    rep = health_mod.collect(collab_root, since=since)
    if json_out:
        _echo_json(rep.to_dict())
    else:
        typer.echo(health_mod.render(rep))


def main() -> None:  # pragma: no cover - console-script convenience
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
