"""``baron session start|end`` — thin, OPTIONAL session-ritual bookkeeping.

These primitives mechanize ONLY the git/markdown *bookkeeping* steps of the
session ritual (sync working copies, surface open handoffs / convention pointers
/ the backlog location on open; regenerate the handoff index, commit outstanding
coordination artifacts, run a divergence check on close). They do NOT run an
agent, make model calls, or own an orchestration loop — that boundary is
[ADR-007](../../../docs/adr/ADR-007-session-boundary.md): Barony is the
coordination/governance layer; execution belongs to the runtime.

Everything here COMPOSES existing baron functions — nothing is reinvented:
:mod:`baron.status` (manifest topology, divergence check), :mod:`baron.handoff`
(open-handoff listing + the ``prefix=`` close attribution mechanism, reused for
the end-commit prefix), :mod:`baron.indexer` (the ``baron index`` logic), and
:mod:`baron.gitutil` (the ``git`` subprocess wrapper). They are opt-in: nothing
in baron requires them, and interactive sessions plus every existing command work
unchanged. They are NOT new capability verbs — the frozen 10-verb vocabulary is
untouched; these are composable *commands*, not permissions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from . import clock, indexer, status as status_mod
from .gitutil import git, has_remote, is_git_repo
from .handoff import Handoff, iter_handoffs

#: Collab-repo coordination surfaces `session end` may commit (never `git add -A`).
COORDINATION_PATHS = ("_handoff", "findings", "decisions", "wiki")

#: Convention/coordination docs surfaced in the session brief.
CONVENTION_DOCS = ("CONVENTIONS.md", "COORDINATION.md")

#: The one-line honesty note both commands print (text mode). Mirrors --help.
BOUNDARY_NOTE = (
    "these mechanize the git/markdown bookkeeping of the session ritual; they do "
    "NOT run an agent — orchestration is the runtime's job (ADR-007)."
)


class SessionError(RuntimeError):
    """A session primitive could not complete (e.g. no manifest)."""


# --- start ----------------------------------------------------------------------------


@dataclass
class SyncResult:
    label: str
    path: Path
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "path": self.path.as_posix(),
            "ok": self.ok,
            "detail": self.detail,
        }


@dataclass
class SessionBrief:
    collab: Path
    persona: str | None
    synced: list[SyncResult]
    open_handoffs: list[Handoff]
    conventions: dict[str, bool]
    backlog_source: str | None
    backlog_location: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "collab": self.collab.as_posix(),
            "persona": self.persona,
            "synced": [s.to_dict() for s in self.synced],
            "open_handoffs": [h.to_dict() for h in self.open_handoffs],
            "conventions": self.conventions,
            "backlog": {"source": self.backlog_source, "location": self.backlog_location},
        }


def _pull_ff_only(label: str, path: Path) -> SyncResult:
    """`git pull --ff-only` one working copy — never merges, never forces.

    Repos with no ``origin`` are skipped (the ritual's "skip repos that have no
    origin yet"); a non-fast-forward is reported, not forced (honest: it needs a
    human/agent decision).
    """
    if not is_git_repo(path):
        return SyncResult(label, path, ok=True, detail="skipped (not a git working copy)")
    if not has_remote(path):
        return SyncResult(label, path, ok=True, detail="skipped (no origin remote)")
    proc = git(path, "pull", "--ff-only", check=False)
    detail = (proc.stdout.strip() or proc.stderr.strip() or "").splitlines()
    first = detail[0] if detail else ""
    if proc.returncode == 0:
        return SyncResult(label, path, ok=True, detail=first or "up to date")
    return SyncResult(label, path, ok=False, detail=f"pull --ff-only failed: {first}")


def start(
    collab: Path,
    *,
    persona: str | None = None,
    sync: bool = False,
) -> SessionBrief:
    """Session-open bookkeeping: read-mostly (only the optional ``sync`` mutates).

    Composes: :func:`baron.status.load_manifest` /
    :func:`baron.status._targets` (topology), :func:`_pull_ff_only` over
    :mod:`baron.gitutil` (optional sync), :func:`baron.handoff.iter_handoffs`
    (open handoffs for the persona, else all).
    """
    manifest = status_mod.load_manifest(collab)

    synced: list[SyncResult] = []
    if sync:
        for label, path in status_mod._targets(collab, manifest):
            synced.append(_pull_ff_only(label, path))

    open_handoffs = [h for h in iter_handoffs(collab) if h.status == "open"]
    if persona:
        open_handoffs = [h for h in open_handoffs if h.for_ in (persona, "all")]

    conventions = {name: (collab / name).is_file() for name in CONVENTION_DOCS}

    backlog = manifest.get("backlog") or {}
    backlog_source = str(backlog["source"]) if isinstance(backlog, dict) and backlog.get("source") else None
    backlog_location = (
        str(backlog["location"]) if isinstance(backlog, dict) and backlog.get("location") else None
    )

    return SessionBrief(
        collab=collab,
        persona=persona,
        synced=synced,
        open_handoffs=open_handoffs,
        conventions=conventions,
        backlog_source=backlog_source,
        backlog_location=backlog_location,
    )


def render_brief(brief: SessionBrief) -> str:
    lines: list[str] = []
    who = f" · persona: {brief.persona}" if brief.persona else " · all personas"
    lines.append(f"session brief — {brief.collab.as_posix()}{who}")

    if not brief.synced:
        lines.append("sync: off (pass --sync to `git pull --ff-only` the manifest working copies)")
    else:
        lines.append("sync:")
        for s in brief.synced:
            flag = "ok " if s.ok else "ERR"
            lines.append(f"  {flag} {s.label} {s.path.as_posix()}: {s.detail}")

    if brief.open_handoffs:
        scope = f"for {brief.persona} / all" if brief.persona else "all addressees"
        lines.append(f"open handoffs ({len(brief.open_handoffs)}, {scope}):")
        for h in sorted(brief.open_handoffs, key=lambda h: h.created):
            age = f"{h.age_days}d" if h.age_days is not None else "?"
            lines.append(
                f"  {h.path.name}  for={h.for_} from={h.from_} priority={h.priority} age={age}"
            )
    else:
        lines.append("open handoffs: none")

    conv = ", ".join(
        f"{name} ({'found' if present else 'MISSING'})"
        for name, present in brief.conventions.items()
    )
    lines.append(f"conventions: {conv}")

    if brief.backlog_location:
        src = f"{brief.backlog_source} — " if brief.backlog_source else ""
        lines.append(f"backlog: {src}{brief.backlog_location}")
    else:
        lines.append("backlog: (not declared in manifest)")

    lines.append("")
    lines.append(BOUNDARY_NOTE)
    return "\n".join(lines)


# --- end ------------------------------------------------------------------------------


@dataclass
class EndReport:
    collab: Path
    persona: str | None
    readme: Path
    ledgers: list[indexer.LedgerReport]
    commit_prefix: str
    committed: bool
    committed_paths: list[str]
    status_findings: list[status_mod.StatusFinding]

    @property
    def reds(self) -> int:
        return sum(1 for f in self.status_findings if f.severity == status_mod.RED)

    def to_dict(self) -> dict[str, object]:
        return {
            "collab": self.collab.as_posix(),
            "persona": self.persona,
            "readme": self.readme.as_posix(),
            "ledgers": [r.to_dict() for r in self.ledgers],
            "commit_prefix": self.commit_prefix,
            "committed": self.committed,
            "committed_paths": self.committed_paths,
            "status": {
                "findings": [f.to_dict() for f in self.status_findings],
                "summary": {
                    "red": self.reds,
                    "warn": len(self.status_findings) - self.reds,
                },
            },
        }


def resolve_commit_prefix(collab: Path, manifest: dict, persona: str | None) -> str:
    """The persona's ``identity.commit_prefix`` from its manifest-listed spec,
    else ``baron:`` — the same default the handoff-close attribution uses.

    Reuses the ``prefix=`` mechanism :func:`baron.handoff.close` already takes,
    so an end-commit is attributed exactly like a persona-closed handoff.
    """
    if not persona:
        return "baron:"
    root = status_mod._resolve_root(collab, manifest)
    for entry in manifest.get("personas", []) or []:
        if not isinstance(entry, dict) or str(entry.get("slug")) != persona:
            continue
        spec = entry.get("spec")
        if not spec:
            break
        spec_path = root / str(spec)
        if not spec_path.is_file():
            break
        try:
            data = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            break
        prefix = (data.get("identity") or {}).get("commit_prefix")
        if isinstance(prefix, str) and prefix.strip():
            return prefix.strip()
        break
    return "baron:"


def _staged_coordination_paths(collab: Path, existing: list[str]) -> list[str]:
    """Paths staged under the coordination dirs (scoped ``git diff --cached``)."""
    proc = git(collab, "diff", "--cached", "--name-only", "--", *existing, check=False)
    return [p for p in proc.stdout.splitlines() if p.strip()]


def end(collab: Path, *, persona: str | None = None) -> EndReport:
    """Session-close bookkeeping.

    Composes: :func:`baron.indexer.update_readme` + :func:`baron.indexer.check_ledger`
    (the ``baron index`` logic), a scoped ``git add`` + commit of dirty
    coordination artifacts (prefix via :func:`resolve_commit_prefix`, NEVER
    ``git add -A``), and :func:`baron.status.collect` (the divergence check).
    """
    manifest = status_mod.load_manifest(collab)

    # 1. Regenerate the handoff index (same as `baron index`).
    readme = indexer.update_readme(collab)
    ledgers = [
        r for k in indexer.KINDS if (r := indexer.check_ledger(collab, k)) is not None
    ]

    # 2. Commit outstanding coordination artifacts — staged by path, never -A.
    prefix = resolve_commit_prefix(collab, manifest, persona)
    committed = False
    committed_paths: list[str] = []
    existing = [d for d in COORDINATION_PATHS if (collab / d).exists()]
    if existing and is_git_repo(collab):
        git(collab, "add", "--", *existing)
        committed_paths = _staged_coordination_paths(collab, existing)
        if committed_paths:
            git(
                collab,
                "commit",
                "-m",
                f"{prefix} session | end (coordination artifacts)",
                "--",
                *existing,
            )
            committed = True

    # 3. Close with a divergence check (same as `baron status`).
    status_findings = status_mod.collect(collab)

    return EndReport(
        collab=collab,
        persona=persona,
        readme=readme,
        ledgers=ledgers,
        commit_prefix=prefix,
        committed=committed,
        committed_paths=committed_paths,
        status_findings=status_findings,
    )


def render_end(report: EndReport) -> str:
    lines: list[str] = []
    who = f" · persona: {report.persona}" if report.persona else ""
    lines.append(f"session end — {report.collab.as_posix()}{who}")
    lines.append(f"index: wrote {report.readme.as_posix()}")
    for r in report.ledgers:
        if r.duplicates:
            lines.append(f"  ERROR   {r.kind}s: duplicate IDs {r.duplicates}")
        elif r.gaps or r.out_of_order:
            note = []
            if r.gaps:
                note.append(f"gaps at {r.gaps}")
            if r.out_of_order:
                note.append(f"out-of-order at {r.out_of_order}")
            lines.append(f"  warning {r.kind}s: {'; '.join(note)} (report-only)")
        else:
            lines.append(f"  ok      {r.kind}s: numbering clean")
    if report.committed:
        lines.append(
            f"commit: `{report.commit_prefix} session | end` "
            f"({len(report.committed_paths)} coordination path(s))"
        )
    else:
        lines.append("commit: nothing outstanding in _handoff/ findings/ decisions/ wiki/")
    lines.append("status:")
    lines.append(status_mod.render_table(report.status_findings))
    lines.append("")
    lines.append(BOUNDARY_NOTE)
    return "\n".join(lines)
