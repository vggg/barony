"""The coordination monorepo (ADR-025) — projects as subdirs of one collab repo.

``baron init`` emits **one collab repo per project** (ADR-006). That default buys
multi-tenant isolation and independent lifecycle, so it stays the default. For a
single owner running a portfolio of fleets it buys mostly repo sprawl and — the real
cost — no cross-project view. ADR-025 adds the other topology:

    fleet-coordination/          # ONE collab monorepo (git), root marker below
      .baron-monorepo.yaml       #   the marker + the project registry
      .github/workflows/         #   the CI seam, owned ONCE at the root
      _meta/                     #   the portfolio project (no code repo)
        manifest.yaml agents/ _handoff/ decisions/ findings/ wiki/
      barony/                    #   a project — code repo: vggg/barony
        manifest.yaml agents/ ...

Each subdir is an ordinary Barony project — same manifest, same personas, same
ledgers — so every single-project command keeps working when run *inside* a subdir.
What this module adds is the root: detection, the registry, and the portfolio-wide
reads (``baron status`` / ``baron health`` walk the subdirs and aggregate).

Design calls this module makes that ADR-025 left open (recorded here, not hidden):

- **The marker is a file, not a manifest.** The root is not itself a project (the
  portfolio project is the ``_meta`` subdir, per §2), so it carries no
  ``manifest.yaml``; ``.baron-monorepo.yaml`` is what makes a directory a monorepo
  root. Detection is exact — never "a directory that happens to contain projects".
- **Subdir name and project name are separate.** They are equal for every project
  added by name; the exception is the portfolio project, whose subdir is ``_meta``
  (leading underscore, sorts first, reads as meta) while its project name is
  ``meta`` — because the project name becomes the git identity domain
  ``<slug>@<project>.local`` and a leading underscore has no business in a hostname.
- **The registry is declared AND discovered.** ``projects:`` in the marker is the
  ordered truth; a subdir holding a ``manifest.yaml`` that is not listed is reported
  as ``unregistered`` rather than silently included or silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import clock, health as health_mod, status as status_mod
from .scaffold import Persona, ScaffoldError, scaffold

#: The file whose presence makes a directory a coordination-monorepo root.
MARKER = ".baron-monorepo.yaml"

#: Subdir + project name of the portfolio project (ADR-025 §2: the portfolio is a
#: project that coordinates projects).
META_DIR = "_meta"
META_PROJECT = "meta"


class MonorepoError(RuntimeError):
    """The operation is not valid for this directory (or would corrupt the root)."""


@dataclass(frozen=True)
class ProjectRef:
    dir: str  # subdir name under the root
    name: str  # project name (the manifest's project.name / identity domain)

    def path(self, root: Path) -> Path:
        return root / self.dir


@dataclass
class Monorepo:
    root: Path
    projects: list[ProjectRef] = field(default_factory=list)
    #: subdirs holding a manifest.yaml that the marker does not list
    unregistered: list[str] = field(default_factory=list)


# --- detection -------------------------------------------------------------------------


def is_root(path: Path) -> bool:
    """True when ``path`` is a coordination-monorepo root."""
    return (path / MARKER).is_file()


def find_root(start: Path) -> Path | None:
    """The nearest monorepo root at or above ``start`` (None when there is none)."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if is_root(candidate):
            return candidate
    return None


def project_of(collab: Path) -> tuple[Path, ProjectRef] | None:
    """(root, project) when ``collab`` is a project subdir of a monorepo, else None.

    Used by the commands that must know *which* project they are acting for — the
    dispatch payload (ADR-025 §7 Q2) above all. A monorepo root itself is not a
    project, so this returns None there.
    """
    resolved = collab.resolve()
    root = find_root(resolved)
    if root is None or root == resolved:
        return None
    try:
        rel = resolved.relative_to(root)
    except ValueError:  # pragma: no cover - find_root guarantees containment
        return None
    subdir = rel.parts[0]
    for project in load(root).projects:
        if project.dir == subdir:
            return root, project
    return None


# --- the registry ----------------------------------------------------------------------


def _discover(root: Path) -> list[str]:
    return sorted(
        child.name
        for child in root.iterdir()
        if child.is_dir()
        and not child.name.startswith(".")
        and (child / "manifest.yaml").is_file()
    )


def load(root: Path) -> Monorepo:
    marker = root / MARKER
    if not marker.is_file():
        raise MonorepoError(
            f"{root} is not a coordination-monorepo root (no {MARKER}) — "
            "create one with `baron init <name> --layout monorepo`"
        )
    try:
        data = yaml.safe_load(marker.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise MonorepoError(f"{marker}: YAML parse error: {exc}") from exc
    if not isinstance(data, dict):
        raise MonorepoError(f"{marker}: marker is not a mapping")
    if str(data.get("layout", "")) != "monorepo":
        raise MonorepoError(f"{marker}: layout is not 'monorepo'")
    projects: list[ProjectRef] = []
    for entry in data.get("projects") or []:
        if isinstance(entry, str):
            projects.append(ProjectRef(entry, entry))
        elif isinstance(entry, dict) and entry.get("dir"):
            projects.append(
                ProjectRef(str(entry["dir"]), str(entry.get("name") or entry["dir"]))
            )
    listed = {p.dir for p in projects}
    return Monorepo(
        root=root,
        projects=projects,
        unregistered=[d for d in _discover(root) if d not in listed],
    )


def render_marker(projects: list[ProjectRef], *, date: str) -> str:
    """The marker file, rendered deterministically (comments are ours, not the user's)."""
    lines = [
        f"# {MARKER} — coordination-monorepo root marker (ADR-025).",
        "#",
        "# This directory is ONE collab repo holding many projects, each a subdir with its",
        "# own manifest.yaml, agents/, _handoff/, decisions/, findings/ and wiki/. The root",
        "# is not itself a project: the portfolio tier is the `_meta` project below.",
        "#",
        "# Graft another project in with `baron add-project <name>`; read the whole",
        "# portfolio with `baron status` / `baron health` from this directory.",
        f"# Created by `baron init --layout monorepo` on {date}.",
        "layout: monorepo",
        "version: 1",
        "projects:",
    ]
    for p in projects:
        lines.append(f"  - dir: {p.dir}")
        lines.append(f"    name: {p.name}")
    return "\n".join(lines) + "\n"


def register(root: Path, project: ProjectRef) -> None:
    """Append ``project`` to the root marker's registry (idempotent by dir name)."""
    repo = load(root)
    if any(p.dir == project.dir for p in repo.projects):
        raise MonorepoError(f"project subdir {project.dir!r} is already registered")
    projects = repo.projects + [project]
    (root / MARKER).write_text(
        render_marker(projects, date=clock.today().isoformat()), encoding="utf-8"
    )


# --- creation --------------------------------------------------------------------------


def _root_readme(name: str, projects: list[ProjectRef], date: str) -> str:
    rows = "\n".join(f"| `{p.dir}/` | {p.name} |" for p in projects)
    return (
        f"# {name} — coordination monorepo\n\n"
        f"One collab repo for a portfolio of fleets, scaffolded by `baron init "
        f"--layout monorepo` on {date} (ADR-025). Each project below is an ordinary\n"
        "Barony project living in its own subdir; only the *coordination* substrate is\n"
        "unified. Code repos stay separate and per-project — each subdir's\n"
        "`manifest.yaml` points at its own.\n\n"
        "| Subdir | Project |\n|---|---|\n" + rows + "\n\n"
        "`_meta/` is the portfolio project: no code repo, its work items are the\n"
        "cross-project decisions. The recursion is the point — the portfolio is a\n"
        "project that coordinates projects, governed by the same primitives one level up.\n\n"
        "| Do this | Run |\n|---|---|\n"
        "| Add a project | `baron add-project <name> --code-repo <path-or-url>` |\n"
        "| Read the whole portfolio | `baron status` / `baron health` (from this root) |\n"
        "| Check every spec | `baron validate .` |\n"
        "| Work in one project | `cd <project>/` — every baron command works there unchanged |\n\n"
        "CI lives once, here in `.github/workflows/`: the lock guard and the stale-verdict\n"
        "stripper are repo-wide by design, and `baron-notify.yml` routes each wake into the\n"
        "project subdir named by the dispatch payload.\n"
    )


#: Root-level workflows. Path-scoping note (ADR-025 §3): only the wake needs to know
#: which project it is for. lock-guard and strip-stale-verdict act on the PR itself —
#: its touched paths, its labels — so they are correctly repo-wide in a monorepo and
#: are emitted unchanged.
_ROOT_WORKFLOWS: tuple[tuple[str, str], ...] = (
    ("collab-repo/.github/workflows/lock-guard.yml", "lock-guard.yml"),
    ("collab-repo/.github/workflows/strip-stale-verdict.yml", "strip-stale-verdict.yml"),
    (
        "collab-repo/.github/workflows/baron-notify-monorepo.yml",
        "baron-notify.yml",
    ),
)


def create_root(root: Path, name: str, *, date: str) -> list[str]:
    """Write the root marker, README and the shared CI seam. Returns created paths."""
    from .templates import read_template

    if root.exists() and any(root.iterdir()):
        raise MonorepoError(
            f"{root} already exists and is not empty — refusing to scaffold over it"
        )
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    (root / MARKER).write_text(render_marker([], date=date), encoding="utf-8")
    created.append(MARKER)
    (root / "README.md").write_text(_root_readme(name, [], date), encoding="utf-8")
    created.append("README.md")
    for template_rel, out_name in _ROOT_WORKFLOWS:
        target = root / ".github" / "workflows" / out_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(read_template(template_rel), encoding="utf-8")
        created.append(f".github/workflows/{out_name}")
    return created


def add_project(
    root: Path,
    dir_name: str,
    *,
    project_name: str | None = None,
    code_repo: str | None = None,
    personas: list[Persona],
    runtime: str = "claude",
) -> tuple[ProjectRef, list[str]]:
    """Graft a project subdir into an existing monorepo root.

    Reuses ``baron init``'s emitters verbatim, scoped to ``<root>/<dir_name>`` and
    told it lives in a monorepo — so it skips the per-repo git init (the root owns
    the repo) and the ``.github/`` seam (the root owns CI).
    """
    repo = load(root)  # refuses cleanly when root is not a monorepo
    if "/" in dir_name or dir_name in {".", ".."} or dir_name.startswith("."):
        raise MonorepoError(
            f"project subdir {dir_name!r} must be a plain directory name under the root"
        )
    if any(p.dir == dir_name for p in repo.projects):
        raise MonorepoError(f"project {dir_name!r} is already registered in this monorepo")
    dest = root / dir_name
    if dest.exists() and any(dest.iterdir()):
        raise MonorepoError(f"{dest} already exists and is not empty — refusing to graft over it")
    name = project_name or dir_name
    report = scaffold(
        name,
        dest,
        code_repo=code_repo,
        personas=personas,
        runtime=runtime,
        do_git=False,
        in_monorepo=True,
    )
    ref = ProjectRef(dir_name, name)
    register(root, ref)
    # The root README's project table is generated, so re-render it with the new row.
    marker_date = clock.today().isoformat()
    (root / "README.md").write_text(
        _root_readme(root.name, load(root).projects, marker_date), encoding="utf-8"
    )
    created = [f"{dir_name}/{rel}" for rel in report.created] + [MARKER, "README.md"]
    return ref, created


# --- portfolio-wide reads ---------------------------------------------------------------


@dataclass
class PortfolioStatus:
    root: Path
    per_project: dict[str, list[status_mod.StatusFinding]]
    errors: dict[str, str]  # project -> why it could not be read
    unregistered: list[str]

    @property
    def reds(self) -> int:
        return sum(
            1 for fs in self.per_project.values() for f in fs if f.severity == status_mod.RED
        )

    @property
    def warns(self) -> int:
        return sum(
            1 for fs in self.per_project.values() for f in fs if f.severity != status_mod.RED
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "layout": "monorepo",
            "root": self.root.as_posix(),
            "projects": {
                name: {
                    "findings": [f.to_dict() for f in findings],
                    "summary": {
                        "red": sum(1 for f in findings if f.severity == status_mod.RED),
                        "warn": sum(1 for f in findings if f.severity != status_mod.RED),
                    },
                }
                for name, findings in self.per_project.items()
            },
            "unreadable": self.errors,
            "unregistered": self.unregistered,
            "summary": {
                "projects": len(self.per_project),
                "red": self.reds,
                "warn": self.warns,
            },
        }


def collect_status(root: Path, *, fetch: bool = False, sla_days: int = 14) -> PortfolioStatus:
    repo = load(root)
    per_project: dict[str, list[status_mod.StatusFinding]] = {}
    errors: dict[str, str] = {}
    for project in repo.projects:
        path = project.path(root)
        try:
            per_project[project.dir] = status_mod.collect(path, fetch=fetch, sla_days=sla_days)
        except (FileNotFoundError, ValueError) as exc:
            errors[project.dir] = str(exc)
    return PortfolioStatus(root, per_project, errors, repo.unregistered)


def render_status(rep: PortfolioStatus) -> str:
    lines = [
        f"=== portfolio: {len(rep.per_project)} project(s) under {rep.root.as_posix()} ==="
    ]
    for name, findings in rep.per_project.items():
        reds = sum(1 for f in findings if f.severity == status_mod.RED)
        warns = len(findings) - reds
        head = "green" if not findings else f"{reds} red, {warns} warn"
        lines.append(f"\n-- {name}/ ({head})")
        if findings:
            lines.append(
                "\n".join(
                    "   " + line for line in status_mod.render_table(findings).splitlines()
                )
            )
    for name, why in rep.errors.items():
        lines.append(f"\n-- {name}/ UNREADABLE: {why}")
    for name in rep.unregistered:
        lines.append(
            f"\nnote: {name}/ holds a manifest.yaml but is not listed in {MARKER} "
            "— portfolio reads skip it (`baron add-project` registers new projects)"
        )
    lines.append(f"\n== portfolio total: {rep.reds} red, {rep.warns} warn ==")
    return "\n".join(lines)


@dataclass
class PortfolioHealth:
    root: Path
    per_project: dict[str, health_mod.HealthReport]
    since: str | None = None

    def to_dict(self) -> dict[str, object]:
        reports = {name: rep.to_dict() for name, rep in self.per_project.items()}
        verdicts = sum(r.verdicts for r in self.per_project.values())
        run = sum(r.mutations_run for r in self.per_project.values())
        killed = sum(r.mutations_killed for r in self.per_project.values())
        return {
            "layout": "monorepo",
            "root": self.root.as_posix(),
            "since": self.since,
            "projects": reports,
            "summary": {
                "projects": len(reports),
                "verdicts": verdicts,
                "mutation_kill": {
                    "killed": killed,
                    "run": run,
                    "rate": (killed / run) if run else None,
                },
                "claim_drift": sum(r.drift_instances for r in self.per_project.values()),
                "reviewer_escapes": sum(len(r.escapes) for r in self.per_project.values()),
                "stalls": sum(len(r.stalls) for r in self.per_project.values()),
            },
        }


def collect_health(root: Path, *, since: str | None = None) -> PortfolioHealth:
    repo = load(root)
    per_project = {
        project.dir: health_mod.collect(project.path(root), since=since)
        for project in repo.projects
        if project.path(root).is_dir()
    }
    return PortfolioHealth(root, per_project, since=since)


def render_health(rep: PortfolioHealth) -> str:
    win = f"since {rep.since}" if rep.since else "all time"
    total = sum(r.verdicts for r in rep.per_project.values())
    stalls = sum(len(r.stalls) for r in rep.per_project.values())
    lines = [
        f"=== portfolio health ({win}) — {len(rep.per_project)} project(s), "
        f"{total} verdict(s), {stalls} stall(s) ===",
        "",
        "The same honest bound as single-project health (ADR-024 §5): this measures what",
        "was EMITTED. A project that records no verdicts shows a clean board.",
    ]
    for name, report in rep.per_project.items():
        lines.append("")
        lines.append(f"-- {name}/")
        lines += ["   " + line for line in health_mod.render(report).splitlines()]
    return "\n".join(lines)


__all__ = [
    "MARKER",
    "META_DIR",
    "META_PROJECT",
    "Monorepo",
    "MonorepoError",
    "PortfolioHealth",
    "PortfolioStatus",
    "ProjectRef",
    "ScaffoldError",
    "add_project",
    "collect_health",
    "collect_status",
    "create_root",
    "find_root",
    "is_root",
    "load",
    "project_of",
    "register",
    "render_health",
    "render_status",
    "render_marker",
]
