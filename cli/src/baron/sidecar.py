"""``baron sidecar run`` — one persona, one deployable work loop (ADR-026).

A **sidecar** packages a persona as a deployable unit: the emitted runtime kit
(``agents/<slug>/runtime/``) plus a work loop, coordinating through the collab
repo as shared state. This module is the loop's mechanical half — the
generalisation of the hand-written ``fleet-runner`` launchd job the pattern came
from. One cycle:

1. **sync** — ``git pull --ff-only`` every working copy the manifest describes
   (:func:`baron.session.start` with ``sync=True``);
2. **sweep** — open ``_handoff/`` items addressed to this persona (or ``all``)
   and backlog lines carrying its routing label. Nothing addressed and nothing
   labelled = **idle**: the cycle exits without waking the runtime (the
   fleet-runner's cheap guard — never pay for a model call with no work);
3. **invoke** — run the project-supplied runtime command once, with the work
   brief on stdin (and at ``$BARON_SIDECAR_BRIEF``);
4. **land** — ``baron session end`` bookkeeping (index, scoped commit of the
   coordination surfaces) and a plain ``git push`` of the collab repo.

**The boundary is ADR-007 and it is load-bearing here.** Steps 1, 2 and 4 are
baron's; step 3 is a command *the project supplies* (``--cmd`` /
``$BARON_SIDECAR_CMD``, defaulted in the emitted ``agents/<slug>/sidecar.sh``,
which lives in the project's repo). baron syncs, sweeps, commits and pushes; it
never defaults to a model binary and does not own the agent loop.

The loop form follows ``persona.yaml``'s ``runtime.trigger`` (ADR-026 §6 Q2):
``interactive`` is one-shot by hand (``--watch`` is refused — that loop is the
human's session), ``event`` is one-shot spawned by the wake
(``baron notify`` → ``baron-notify.yml``, ADR-010), ``cron`` is scheduler-driven
and may ``--watch``. A watching sidecar re-reads git as truth every cycle — it
holds no state between them, which is what keeps audit-by-diff true (ADR-026 §4).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from . import identity as identity_mod, session as session_mod, status as status_mod
from .gitutil import GitError, current_branch, git, has_remote, is_git_repo
from .handoff import Handoff

#: ``runtime.trigger`` values (persona.schema.md).
TRIGGERS = ("interactive", "event", "cron")
DEFAULT_TRIGGER = "interactive"

#: Triggers whose sidecar may run long (``--watch``). An interactive persona's
#: loop is the human session, so watching one is a configuration error, not a
#: deployment.
WATCHABLE = ("event", "cron")

DEFAULT_WATCH_INTERVAL = 900  # seconds; a cron sidecar's self-paced fallback

#: Placeholder a runtime command may use to receive the brief as a file path
#: instead of on stdin (``--cmd "runner --prompt-file {brief_file}"``).
BRIEF_TOKEN = "{brief_file}"


class SidecarError(RuntimeError):
    """A sidecar cycle could not be run (bad persona, bad trigger, no manifest)."""


# --- persona / work discovery ----------------------------------------------------------


def _persona_spec(collab: Path, manifest: dict, persona: str) -> Path | None:
    root = status_mod._resolve_root(collab, manifest)
    for entry in manifest.get("personas", []) or []:
        if isinstance(entry, dict) and str(entry.get("slug")) == persona:
            spec = entry.get("spec")
            if spec:
                path = root / str(spec)
                return path if path.is_file() else None
    return None


def persona_data(collab: Path, manifest: dict, persona: str) -> dict:
    """The persona's canonical spec, or ``{}`` when the manifest doesn't list it."""
    spec = _persona_spec(collab, manifest, persona)
    if spec is None:
        return {}
    try:
        data = yaml.safe_load(spec.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SidecarError(f"{spec}: unparseable persona spec ({exc})")
    return data if isinstance(data, dict) else {}


def resolve_trigger(data: dict, override: str | None = None) -> str:
    """``runtime.trigger`` (ADR-026 §6 Q2), overridable per invocation."""
    if override is not None:
        if override not in TRIGGERS:
            raise SidecarError(
                f"unknown trigger {override!r} — pick from {', '.join(TRIGGERS)}"
            )
        return override
    trigger = ((data.get("runtime") or {}) if isinstance(data.get("runtime"), dict) else {}).get(
        "trigger"
    )
    return str(trigger) if trigger in TRIGGERS else DEFAULT_TRIGGER


def routing_label(data: dict, persona: str) -> str:
    label = (data.get("identity") or {}).get("routing_label")
    return str(label) if label else f"agent-{persona}"


def backlog_items(collab: Path, manifest: dict, label: str) -> tuple[list[str], str | None]:
    """(unchecked backlog lines carrying ``label``, note).

    Only a ``source: file`` backlog is swept mechanically — a tracker-backed one
    is the runtime's to read (baron does not call forge APIs to plan work), and
    the note says so. Parked items are skipped when ``backlog.park_label`` is
    declared (ADR-009 §3.2).
    """
    backlog = manifest.get("backlog") or {}
    if not isinstance(backlog, dict):
        return [], None
    source = str(backlog.get("source") or "")
    location = str(backlog.get("location") or "")
    if source != "file":
        return [], (
            f"backlog source {source!r} is not a file — the runtime reads it "
            "(the sweep only covers _handoff/ here)"
            if source
            else None
        )
    if not location:
        return [], "manifest backlog.source is 'file' but declares no location"
    path = status_mod._resolve_root(collab, manifest) / location
    if not path.is_file():
        return [], f"backlog file {location} not found"
    park = backlog.get("park_label")
    park_marker = f"<!-- {park} -->" if park else None
    items: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("- [ ]") or label not in line:
            continue
        if park_marker and park_marker in line:
            continue
        items.append(line)
    return items, None


# --- the work brief --------------------------------------------------------------------


def render_brief(
    collab: Path,
    persona: str,
    data: dict,
    handoffs: list[Handoff],
    backlog: list[str],
    trigger: str,
) -> str:
    """The unit-of-work brief handed to the runtime.

    It is a *pointer*, not a persona: the persona lives in the runtime kit the
    runtime already loads (``agents/<slug>/runtime/``), and the canonical spec is
    the yaml. The brief names the cycle's work in session-ritual order —
    review feedback resolves BEFORE new backlog work (ADR-008), which is the one
    ordering a sidecar must not get wrong.
    """
    prefix = (data.get("identity") or {}).get("commit_prefix") or f"{persona}:"
    lines = [
        f"You are {data.get('persona') or persona} ({persona}) running one sidecar cycle "
        f"for this project (trigger: {trigger}).",
        "",
        f"Collab repo: {collab.as_posix()} (already synced for you this cycle).",
        f"Canonical spec: agents/{persona}/persona.yaml. Runtime kit: agents/{persona}/runtime/.",
        "Rules: CONVENTIONS.md and COORDINATION.md in the collab repo — read them before acting.",
        "",
        "Do ONE unit of work this cycle, in this order:",
        "",
        "1. Act on LIVE review feedback on your open PRs first — a verdict whose head SHA "
        "matches the PR's current head. A stale verdict is void, and a review-state label "
        "is never the evidence (CONVENTIONS.md § A label is not evidence).",
    ]
    if handoffs:
        lines.append("2. Then work these open handoffs addressed to you:")
        for h in sorted(handoffs, key=lambda h: h.created):
            age = f"{h.age_days}d" if h.age_days is not None else "?"
            lines.append(
                f"   - _handoff/{h.path.name} (from {h.from_}, priority {h.priority}, age {age})"
            )
    else:
        lines.append("2. No open handoffs are addressed to you.")
    if backlog:
        lines.append("3. Then the backlog items carrying your routing label:")
        lines += [f"   {item}" for item in backlog]
    else:
        lines.append("3. No backlog items carry your routing label.")
    lines += [
        "",
        f"Commit as `{prefix} <type> | <description>`, staging only intended files "
        "(never `git add -A`). Close any handoff you finish (`baron handoff close`). "
        "Stay inside your capabilities — the deny list in your spec is not advisory.",
        "",
        "When the unit of work is done, stop. baron commits the coordination surfaces "
        "and pushes after you exit; the next cycle re-reads git as truth.",
    ]
    return "\n".join(lines) + "\n"


# --- the cycle -------------------------------------------------------------------------


@dataclass
class CycleReport:
    collab: Path
    persona: str
    trigger: str
    dry_run: bool
    synced: list[session_mod.SyncResult] = field(default_factory=list)
    handoffs: list[str] = field(default_factory=list)
    backlog: list[str] = field(default_factory=list)
    idle: bool = False
    invoked: bool = False
    exit_code: int | None = None
    committed: bool = False
    committed_paths: list[str] = field(default_factory=list)
    pushed: bool = False
    push_detail: str = ""
    brief: str = ""
    notes: list[str] = field(default_factory=list)
    identity: identity_mod.Identity | None = None

    @property
    def ok(self) -> bool:
        return self.exit_code in (None, 0)

    def to_dict(self) -> dict[str, object]:
        return {
            "collab": self.collab.as_posix(),
            "persona": self.persona,
            "trigger": self.trigger,
            "dry_run": self.dry_run,
            "synced": [s.to_dict() for s in self.synced],
            "handoffs": self.handoffs,
            "backlog": self.backlog,
            "idle": self.idle,
            "invoked": self.invoked,
            "exit_code": self.exit_code,
            "committed": self.committed,
            "committed_paths": self.committed_paths,
            "pushed": self.pushed,
            "push_detail": self.push_detail,
            "notes": self.notes,
            # Never carries a credential value — only the variable NAME and whether
            # it is set (ADR-027 §3.5).
            "identity": self.identity.to_dict() if self.identity else None,
        }


def _workdir(collab: Path, manifest: dict, persona: str) -> Path:
    """Where the runtime is invoked: this persona's worktree if one exists, else
    the code repo, else the collab repo. The kit's relative paths assume exactly
    this layout (see the kit README)."""
    root = status_mod._resolve_root(collab, manifest)
    workspace = manifest.get("workspace") or {}
    worktrees_root = workspace.get("worktrees_root")
    if worktrees_root:
        candidate = (root / str(worktrees_root) / persona).resolve()
        if (candidate / ".git").exists():
            return candidate
    for repo in manifest.get("repos", []) or []:
        if isinstance(repo, dict) and repo.get("role") == "code" and repo.get("path"):
            candidate = (root / str(repo["path"])).resolve()
            if candidate.is_dir():
                return candidate
    return collab


def _invoke(cmd: str, brief: str, *, cwd: Path, collab: Path, persona: str,
            timeout: int | None) -> tuple[int, str | None]:
    """Run the project's runtime command once. Returns (exit_code, note)."""
    try:
        argv = shlex.split(cmd)
    except ValueError as exc:
        raise SidecarError(f"--cmd is not parseable as a command line: {exc}")
    if not argv:
        raise SidecarError("--cmd is empty")
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", prefix=f"baron-brief-{persona}-", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(brief)
        brief_path = Path(fh.name)
    argv = [a.replace(BRIEF_TOKEN, brief_path.as_posix()) for a in argv]
    env = dict(os.environ)
    env.update(
        {
            "BARON_SIDECAR_PERSONA": persona,
            "BARON_SIDECAR_COLLAB": collab.as_posix(),
            "BARON_SIDECAR_BRIEF": brief_path.as_posix(),
        }
    )
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), input=brief, text=True, env=env, timeout=timeout
        )
        return proc.returncode, None
    except FileNotFoundError:
        raise SidecarError(f"runtime command not found: {argv[0]}")
    except subprocess.TimeoutExpired:
        return 124, f"runtime command timed out after {timeout}s — outcome not landed"
    finally:
        brief_path.unlink(missing_ok=True)


def _push(collab: Path, ident: identity_mod.Identity | None = None) -> tuple[bool, str]:
    """Plain ``git push`` of the collab repo. No force, no retry (ADR-010's
    discipline): a rejected push means someone else moved, which is a decision,
    not a race to win.

    Pushes under the persona's own forge credential when one resolves (ADR-027) —
    otherwise ambient, exactly as before.
    """
    if not is_git_repo(collab):
        return False, "not a git working copy"
    if not has_remote(collab):
        return False, "no origin remote"
    branch = current_branch(collab)
    if branch is None:
        return False, "detached HEAD"
    config = identity_mod.credential_config(ident) if ident else None
    proc = git(collab, "push", "origin", branch, check=False, config=config)
    if proc.returncode == 0:
        detail = (proc.stderr.strip() or proc.stdout.strip() or "pushed").splitlines()[-1]
        return True, detail
    first = (proc.stderr.strip() or proc.stdout.strip() or "").splitlines()
    return False, f"push rejected: {first[0] if first else 'unknown error'}"


def run_cycle(
    collab: Path,
    persona: str,
    *,
    cmd: str | None = None,
    trigger: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    push: bool = True,
    timeout: int | None = None,
    require_identity: bool = False,
) -> CycleReport:
    """One sidecar cycle: sync → sweep → invoke → land. See the module docstring.

    The whole cycle runs **as the persona** (ADR-027): its git authorship and, when a
    credential resolves, its own forge token are applied to the process environment
    for the duration, so baron's commits, the runtime subprocess, and any `gh` that
    subprocess spawns all attribute to the same actor.
    """
    try:
        manifest = status_mod.load_manifest(collab)
    except (FileNotFoundError, ValueError) as exc:
        raise SidecarError(str(exc))
    data = persona_data(collab, manifest, persona)
    if not data:
        raise SidecarError(
            f"persona {persona!r} is not listed in {collab.as_posix()}/manifest.yaml "
            "(or its spec is missing) — a sidecar deploys a declared persona"
        )
    resolved_trigger = resolve_trigger(data, trigger)
    ident = identity_mod.resolve(data, persona)
    if require_identity:
        ident = replace(ident, required=True)
    if not dry_run:
        try:
            identity_mod.require(ident)
        except identity_mod.IdentityError as exc:
            raise SidecarError(str(exc)) from exc
    with identity_mod.acting_as(ident):
        report = _cycle_body(
            collab, persona, manifest, data, ident, resolved_trigger,
            cmd=cmd, dry_run=dry_run, force=force, push=push, timeout=timeout,
        )
    return report


def _cycle_body(
    collab: Path,
    persona: str,
    manifest: dict,
    data: dict,
    ident: identity_mod.Identity,
    resolved_trigger: str,
    *,
    cmd: str | None,
    dry_run: bool,
    force: bool,
    push: bool,
    timeout: int | None,
) -> CycleReport:
    """The cycle proper, run inside :func:`baron.identity.acting_as`."""
    report = CycleReport(
        collab=collab, persona=persona, trigger=resolved_trigger, dry_run=dry_run,
        identity=ident,
    )
    if ident.declared and not ident.resolved:
        report.notes.append(
            f"forge identity UNRESOLVED (${ident.token_env} unset) — forge actions "
            "this cycle attribute to whoever is ambiently logged in, not to "
            f"{ident.login or persona} (ADR-027; see docs/runbooks/forge-identity.md)"
        )
        if ident.required:
            report.notes.append(
                "this persona sets identity.forge.required — a non-dry-run cycle "
                "would refuse to run"
            )
    elif not ident.declared:
        report.notes.append(
            "no identity.forge declared — this persona acts on the forge under "
            "ambient credentials (ADR-027)"
        )

    # 1. sync + 2. sweep — session start does both reads in one pass.
    brief_data = session_mod.start(collab, persona=persona, sync=not dry_run)
    report.synced = brief_data.synced
    if dry_run:
        report.notes.append("dry run: repos not synced, runtime not invoked, nothing landed")
    for sync in report.synced:
        if not sync.ok:
            report.notes.append(f"sync: {sync.label} {sync.detail}")
    label = routing_label(data, persona)
    items, note = backlog_items(collab, manifest, label)
    if note:
        report.notes.append(note)
    report.handoffs = [h.path.name for h in brief_data.open_handoffs]
    report.backlog = items
    report.brief = render_brief(
        collab, persona, data, brief_data.open_handoffs, items, resolved_trigger
    )

    if not report.handoffs and not items and not force:
        report.idle = True
        report.notes.append(
            "idle: nothing addressed to this persona and nothing carries its routing "
            "label — runtime not invoked (--force overrides)"
        )
        return report

    # 3. invoke — the project-owned slot.
    if dry_run:
        return report
    if not (cmd or "").strip():
        raise SidecarError(
            "no runtime command — pass --cmd or set $BARON_SIDECAR_CMD. baron does not "
            "default to a model binary; the emitted agents/<slug>/sidecar.sh carries "
            "your project's invocation (ADR-007)"
        )
    workdir = _workdir(collab, manifest, persona)
    code, invoke_note = _invoke(
        cmd, report.brief, cwd=workdir, collab=collab, persona=persona, timeout=timeout
    )
    report.invoked = True
    report.exit_code = code
    if invoke_note:
        report.notes.append(invoke_note)
    if code != 0:
        report.notes.append(f"runtime exited {code} — landing whatever it did commit")

    # 4. land — bookkeeping the runtime is not asked to remember, then push.
    end = session_mod.end(collab, persona=persona)
    report.committed = end.committed
    report.committed_paths = end.committed_paths
    if push:
        try:
            report.pushed, report.push_detail = _push(collab, ident)
        except GitError as exc:  # pragma: no cover - git wrapper already soft-fails
            report.pushed, report.push_detail = False, str(exc)
        if not report.pushed:
            report.notes.append(f"push: {report.push_detail}")
    else:
        report.push_detail = "skipped (--no-push)"
    return report


def watch(
    collab: Path,
    persona: str,
    *,
    interval: int = DEFAULT_WATCH_INTERVAL,
    max_cycles: int | None = None,
    on_cycle=None,
    sleep=time.sleep,
    **kwargs,
) -> list[CycleReport]:
    """Run cycles forever (or ``max_cycles`` times), sleeping ``interval`` between.

    Long-running but **stateless per task** (ADR-026 §4): every cycle re-reads git
    as truth and keeps nothing from the last one, so the audit-by-diff guarantee
    survives the process living longer than one unit of work.
    """
    data = persona_data(collab, status_mod.load_manifest(collab), persona)
    resolved = resolve_trigger(data, kwargs.get("trigger"))
    if resolved not in WATCHABLE:
        raise SidecarError(
            f"--watch is refused for a {resolved!r} persona — that loop is the human's "
            f"session. Watchable triggers: {', '.join(WATCHABLE)} (persona.yaml "
            "runtime.trigger, or --trigger to override)"
        )
    reports: list[CycleReport] = []
    count = 0
    while max_cycles is None or count < max_cycles:
        report = run_cycle(collab, persona, **kwargs)
        reports.append(report)
        if on_cycle is not None:
            on_cycle(report)
        count += 1
        if max_cycles is not None and count >= max_cycles:
            break
        sleep(interval)
    return reports


def render_cycle(report: CycleReport) -> str:
    lines = [
        f"sidecar cycle — {report.persona} · trigger {report.trigger} · "
        f"{report.collab.as_posix()}" + (" · DRY RUN" if report.dry_run else "")
    ]
    if report.identity is not None:
        lines.append(f"acting as: {identity_mod.describe(report.identity)}")
    if report.synced:
        for s in report.synced:
            lines.append(f"  {'ok ' if s.ok else 'ERR'} sync {s.label}: {s.detail}")
    lines.append(
        f"swept: {len(report.handoffs)} handoff(s), {len(report.backlog)} backlog item(s)"
    )
    for name in report.handoffs:
        lines.append(f"  _handoff/{name}")
    for item in report.backlog:
        lines.append(f"  {item}")
    if report.idle:
        lines.append("idle — runtime not invoked")
    elif report.dry_run:
        lines.append("would invoke the runtime with this brief:")
        lines.append("")
        lines.append(report.brief.rstrip("\n"))
    else:
        lines.append(f"runtime: exit {report.exit_code}")
        if report.committed:
            lines.append(f"commit: {len(report.committed_paths)} coordination path(s)")
        else:
            lines.append("commit: nothing outstanding")
        lines.append(f"push: {report.push_detail or 'skipped'}")
    for note in report.notes:
        lines.append(f"note: {note}")
    lines.append("")
    lines.append(
        "baron syncs, sweeps, commits and pushes; the runtime owns the model loop (ADR-007)."
    )
    return "\n".join(lines)
