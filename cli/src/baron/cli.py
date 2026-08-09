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
    guard as guard_mod,
    handoff as handoff_mod,
    indexer,
    ledger,
    lock as lock_mod,
    rules as rules_mod,
    runtimes,
    scaffold as scaffold_mod,
    session as session_mod,
    status as status_mod,
    validate as validate_mod,
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
    """
    try:
        roster = scaffold_mod.parse_personas(personas)
        if runtime not in scaffold_mod.RUNTIMES:
            raise scaffold_mod.ScaffoldError(
                f"unknown runtime {runtime!r} — pick from "
                + ", ".join(scaffold_mod.RUNTIMES)
            )
    except scaffold_mod.ScaffoldError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2)
    dest = dir_ if dir_ is not None else Path(project_name)
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
        "  4. open your runtime at the collab root — canon/START.md routes you;\n"
        "     each persona's kit is in agents/<slug>/runtime/ (see its README)\n"
        "  5. every session: sync repos, read CONVENTIONS.md + COORDINATION.md,\n"
        "     check _handoff/ (COORDINATION.md § Session-start checklist)\n"
        "\nedit next: agents/<slug>/persona.yaml scope blocks (init fills a generic\n"
        "placeholder scope), manifest.yaml description, and backlog.md."
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
    """
    if not path.exists():
        typer.echo(f"error: {path} does not exist", err=True)
        raise typer.Exit(2)
    findings, files, skipped = validate_mod.validate_path(
        path, runtime_drift=runtime_drift
    )
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    if json_out:
        _echo_json(
            {
                "files_checked": [f.as_posix() for f in files],
                "templates_skipped": [f.as_posix() for f in skipped],
                "findings": [f.to_dict() for f in findings],
                "summary": {"errors": len(errors), "warnings": len(warnings)},
            }
        )
    else:
        for f in findings:
            typer.echo(f"{f.severity.upper():7s} {f.file}: [{f.check}] {f.message}")
        if skipped:
            typer.echo(f"skipped {len(skipped)} template file(s) (assets/collab-repo, legacy)")
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
    """
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
    """Claude Code PreToolUse hook: deterministic capability enforcement.

    Reads the hook JSON from stdin (tool_name/tool_input/cwd per
    https://code.claude.com/docs/en/hooks), maps the call to the frozen v1
    capability verbs, and either stays silent (exit 0 — normal permission flow)
    or blocks (exit 2, reason on stderr, fed to the model). Fail-closed on
    internal errors; BARON_GUARD_OVERRIDE=<reason> allows AND appends to the
    tracked .baron/guard-override.log. Wire-up: see the Claude adapter's
    HYDRATE.md (matcher Bash|Edit|Write|NotebookEdit).
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
        typer.echo(f"\nnote ({verbs}): {rules_mod.LABEL_CAVEAT}")


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
    check(
        "no unrecognised content",
        True,
        "every key and rule in the document is one this baron implements "
        "(parser-enforced: unknown content is refused, never ignored)",
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


def main() -> None:  # pragma: no cover - console-script convenience
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
