#!/usr/bin/env python3
"""Build the showcase-safe fleet snapshot the dashboard renders.

The coordination collab repo is PRIVATE and stays private. This script is the
one-way projection: it runs the read-only `baron` reporters against that private
repo, drops everything local or sensitive, and writes a curated JSON document
into the PUBLIC repo under `dashboard/data/fleet.json`.

Nothing here is hand-authored — rerun it and the snapshot regenerates. The
dashboard has no server and no build step: it fetches this committed file.

What is deliberately NOT emitted:
  * absolute local paths (reduced to their last two components)
  * the event-plane directory, the collab root, any `$HOME`-rooted string
  * handoff / finding / decision BODIES and filenames (counts only)

What is emitted is either already public (PR numbers, branch names, titles on
`vggg/barony`) or synthetic (the `*@barony.local` persona git identities).

Before reading anything, the build REFRESHES every working copy the fleet
describes (`git fetch origin --prune`, plus a fast-forward pull of the default
branch when that is safe). `baron status` reads LOCAL git only, so a clone that
was never pulled reports branches deleted on origin as live stalls — the
snapshot then publishes stale reds as if they were current. Refreshing first
makes the snapshot a statement about ORIGIN, not about whatever this laptop
happened to have on disk. When a fetch fails (offline, no credentials), that is
recorded in `generator.refresh` and surfaced in `honesty` rather than silently
passed off as fresh.

Usage:
    dashboard/build-data.sh                    # the normal path
    python3 dashboard/build_data.py --collab ~/Workspace/fleet-coordination
    dashboard/build-data.sh --no-refresh       # read the clones exactly as-is

Stdlib only, matching `tests/` — no dependency install to reproduce a snapshot.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "barony.dashboard/v1"

# Metrics whose denominator is genuinely empty are reported as null with an
# explicit basis, never as a flattering 0% or 100%. ADR-024's honest bound.
UNMEASURED = "no observations recorded — not a clean result"


# ---------------------------------------------------------------- sanitising

_ABS_PATH = re.compile(r"(/(?:Users|home|var|private|tmp|opt)/[\w./@ +-]+)")


def _shorten_path(match: re.Match[str]) -> str:
    """Reduce an absolute path to its final two components.

    `/Users/someone/Workspace/agent-project-bootstrap` -> `Workspace/agent-project-bootstrap`.
    Enough to identify which working copy a finding is about, with no home
    directory, no username, and no machine layout.
    """
    parts = [p for p in match.group(1).rstrip("/").split("/") if p]
    return "/".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else "")


def scrub(value):
    """Recursively strip absolute local paths out of any JSON-ish structure."""
    if isinstance(value, str):
        cleaned = _ABS_PATH.sub(_shorten_path, value)
        home = os.path.expanduser("~")
        return cleaned.replace(home, "~")
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    return value


# ------------------------------------------------------------------ helpers


def run_json(cmd: list[str], *, allow_fail: bool = True) -> dict | list | None:
    """Run a command and parse its stdout as JSON.

    `baron status` exits 1 when it finds a red finding — that is a report, not a
    failure, so a non-zero exit with parseable JSON is accepted.
    """
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = proc.stdout.strip()
    if not out:
        if allow_fail:
            print(f"  ! no output from: {' '.join(cmd[:3])}...", file=sys.stderr)
            return None
        raise SystemExit(f"command produced no output: {' '.join(cmd)}")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        if allow_fail:
            print(f"  ! unparseable output from: {' '.join(cmd[:3])}...", file=sys.stderr)
            return None
        raise


def parse_yaml_persona(path: Path) -> dict:
    """Extract the fields the dashboard needs from a persona.yaml.

    A deliberately small hand-rolled reader rather than a PyYAML dependency:
    this script must run from a bare clone with nothing installed. It only
    understands the shape `baron init` emits — `identity:` scalars and the
    `capabilities.allow` / `capabilities.deny` sequences.
    """
    text = path.read_text(encoding="utf-8")
    out: dict = {"allow": [], "deny": []}

    for key in ("persona", "slug", "archetype"):
        m = re.search(rf"^{key}:\s*(.+?)\s*$", text, re.M)
        if m:
            out[key] = m.group(1).strip().strip('"\'')

    ident = re.search(r"^identity:\n((?:[ \t]+.*\n)+)", text, re.M)
    if ident:
        for key in ("git_name", "git_email", "commit_prefix", "routing_label"):
            m = re.search(rf"^\s+{key}:\s*(.+?)\s*$", ident.group(1), re.M)
            if m:
                out[key] = m.group(1).strip().strip('"\'')

    caps = re.search(r"^capabilities:\n((?:[ \t]+.*\n|\n)+)", text, re.M)
    if caps:
        bucket = None
        for line in caps.group(1).splitlines():
            if re.match(r"^\s{2,4}allow:\s*$", line):
                bucket = "allow"
                continue
            if re.match(r"^\s{2,4}deny:\s*$", line):
                bucket = "deny"
                continue
            item = re.match(r"^\s{4,}-\s*(.+?)\s*(?:#.*)?$", line)
            if item and bucket:
                out[bucket].append(item.group(1).strip())
    return out


def days_since(iso: str) -> int | None:
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - then).days


# ---------------------------------------------------- freshness (fetch first)

# `baron status` reads LOCAL git only: unmerged-branch and behind findings are
# computed against whatever remote-tracking refs this clone last saw. A shared
# clone that is never pulled (every session working in its own worktree) will
# therefore report branches long since merged AND DELETED on origin as live
# stalls, and the published snapshot turns that into a wall of red that has
# nothing to do with the fleet. Refreshing before reading is what makes the
# snapshot a statement about origin.
#
# Deliberately conservative: fetch --prune always, and a fast-forward-only merge
# ONLY when the working copy is clean and sitting on its default branch. Never a
# rebase, never a merge commit, never a checkout — a snapshot build must not be
# able to lose work.


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _redact_remote(message: str) -> str:
    """Strip remote URLs out of a git error before it can reach the snapshot.

    A fetch failure quotes the remote it could not reach, and for the private
    coordination repo that URL is itself the thing this projection exists to
    keep out of the public file. `scrub()` handles paths, not URLs.
    """
    message = re.sub(r"\b[\w.+-]+@[\w.-]+:[^\s'\"]+", "<remote>", message)
    message = re.sub(r"\bhttps?://[^\s'\"]+", "<remote>", message)
    message = re.sub(r"(?i)\b(host):\s*\S+", r"\1: <remote>", message)
    return re.sub(r"'\s*<remote>\s*'", "<remote>", message)


def _yaml_block(text: str, key: str) -> str:
    """The indented body of a top-level `key:` block, or ''."""
    m = re.search(rf"^{key}:\s*$\n((?:[ \t]+.*\n|\n)*)", text, re.M)
    return m.group(1) if m else ""


def _yaml_scalar(block: str, key: str) -> str | None:
    m = re.search(rf"^\s+{key}:\s*(.+?)\s*$", block, re.M)
    if not m:
        return None
    value = m.group(1).strip().strip("\"'")
    return value.split(" #", 1)[0].strip() or None


def _yaml_items(block: str) -> list[dict]:
    """Split an indented sequence body into per-item key/value dicts."""
    items: list[dict] = []
    for line in block.splitlines():
        if re.match(r"^\s*#", line) or not line.strip():
            continue
        start = re.match(r"^\s*-\s*(.*)$", line)
        if start:
            items.append({})
            line = start.group(1)
            if not line.strip():
                continue
        if not items:
            continue
        kv = re.match(r"^\s*([\w_]+):\s*(.*?)\s*$", line)
        if kv:
            items[-1][kv.group(1)] = kv.group(2).strip().strip("\"'")
    return items


def manifest_targets(collab: Path, projects: list[dict]) -> list[tuple[str, str, Path]]:
    """(project, label, path) for every working copy the manifests describe.

    Mirrors `baron status`'s own target resolution — repos[].path, the optional
    workspace.clones[] and workspace.worktrees_root — with a small hand reader,
    for the same reason `parse_yaml_persona` exists: this script is stdlib only
    and must run from a bare clone with nothing installed.
    """
    targets: list[tuple[str, str, Path]] = []
    for proj in projects:
        manifest = collab / proj["dir"] / "manifest.yaml"
        if not manifest.is_file():
            continue
        text = manifest.read_text(encoding="utf-8")
        root = (collab / proj["dir"] / (_yaml_scalar(_yaml_block(text, "paths"), "root") or ".")).resolve()

        for repo in _yaml_items(_yaml_block(text, "repos")):
            if repo.get("path"):
                label = f"repo:{repo.get('id', '?')}"
                targets.append((proj["name"], label, (root / repo["path"]).resolve()))

        workspace = _yaml_block(text, "workspace")
        clones_block = re.search(r"^\s+clones:\s*$\n((?:\s+-.*\n|\s{4,}.*\n)*)", workspace, re.M)
        if clones_block:
            for clone in _yaml_items(clones_block.group(1)):
                if clone.get("path"):
                    label = f"clone:{clone.get('persona', '?')}"
                    targets.append((proj["name"], label, (root / clone["path"]).resolve()))

        worktrees_root = _yaml_scalar(workspace, "worktrees_root")
        if worktrees_root:
            wt_root = (root / worktrees_root).resolve()
            if wt_root.is_dir():
                for child in sorted(wt_root.iterdir()):
                    if (child / ".git").exists():
                        targets.append((proj["name"], f"worktree:{child.name}", child))
    return targets


def discover_projects(collab: Path) -> list[dict]:
    """The registered projects, read WITHOUT running baron.

    The refresh has to happen before `baron status`, so it cannot learn the
    topology from status's own output. It reads the ADR-025 monorepo marker
    directly, and falls back to the single-project layout.
    """
    marker = collab / ".baron-monorepo.yaml"
    if marker.is_file():
        dirs = re.findall(r"^\s+-\s+dir:\s*(.+?)\s*$", marker.read_text(encoding="utf-8"), re.M)
        if dirs:
            return [{"dir": d.strip().strip("\"'"), "name": d.strip().strip("\"'")} for d in dirs]
    return [{"dir": ".", "name": collab.name}]


def refresh_working_copies(collab: Path, projects: list[dict], *, enabled: bool) -> dict:
    """Fetch --prune (and fast-forward where safe) every working copy, first.

    Returns a report that goes into the snapshot verbatim: a build that could
    not reach origin says so, rather than publishing yesterday's refs as today's
    truth. NOTE: only labels are recorded — never paths, which would leak the
    private layout past the sanitiser.
    """
    report: dict = {"attempted": enabled, "targets": [], "fetch_failures": 0, "note": None}
    if not enabled:
        report["note"] = (
            "--no-refresh: working copies were read exactly as found on disk, so "
            "branch and behind findings may reflect stale remote-tracking refs."
        )
        print("→ refresh SKIPPED (--no-refresh) — findings may be stale")
        return report

    targets = manifest_targets(collab, projects)
    print(f"→ refreshing {len(targets)} working copy/copies against origin (fetch --prune)")

    fetched_stores: dict[str, bool] = {}
    for project, label, path in targets:
        entry = {
            "project": project,
            "target": label,
            "fetched": False,
            "pulled": None,
            "note": None,
        }
        report["targets"].append(entry)

        if not path.is_dir() or _git(path, "rev-parse", "--is-inside-work-tree").returncode != 0:
            entry["note"] = "not a git working copy — nothing to refresh"
            continue
        if "origin" not in _git(path, "remote").stdout.split():
            entry["note"] = "no origin remote — local-only working copy"
            continue

        # Worktrees share one object store with their main clone: fetch it once.
        store = _git(path, "rev-parse", "--git-common-dir").stdout.strip() or str(path)
        store = str((path / store).resolve()) if not store.startswith("/") else store
        if store in fetched_stores:
            entry["fetched"] = fetched_stores[store]
            entry["note"] = "object store already fetched via another working copy"
        else:
            proc = _git(path, "fetch", "origin", "--prune", "--prune-tags", "--tags")
            ok = proc.returncode == 0
            fetched_stores[store] = ok
            entry["fetched"] = ok
            if not ok:
                report["fetch_failures"] += 1
                first = (proc.stderr.strip().splitlines() or ["unknown error"])[-1]
                entry["note"] = (
                    "fetch failed — findings for this copy may be stale: "
                    + _redact_remote(first)
                )
                print(f"  ! fetch failed for {project}/{label}", file=sys.stderr)
                continue

        # Fast-forward only, and only where it cannot lose anything.
        head = _git(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        ref = _git(path, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD").stdout.strip()
        default = ref.rsplit("/", 1)[-1] if ref else ("main" if _git(
            path, "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"
        ).returncode == 0 else None)

        if default is None:
            entry["pulled"] = "skipped — origin default branch undeterminable"
        elif head != default:
            entry["pulled"] = f"skipped — on {head}, not {default} (a build never checks out)"
        elif _git(path, "status", "--porcelain").stdout.strip():
            entry["pulled"] = "skipped — uncommitted changes present"
        else:
            merge = _git(path, "merge", "--ff-only", f"origin/{default}")
            if merge.returncode != 0:
                entry["pulled"] = "skipped — not a fast-forward (local commits diverge)"
            else:
                entry["pulled"] = (
                    "already current" if "Already up to date" in merge.stdout
                    else f"fast-forwarded to origin/{default}"
                )

    moved = [t for t in report["targets"] if t["pulled"] and t["pulled"].startswith("fast-forwarded")]
    ok_stores = sum(1 for v in fetched_stores.values() if v)
    print(f"  {ok_stores}/{len(fetched_stores)} object store(s) fetched · {len(moved)} fast-forwarded · "
          f"{report['fetch_failures']} failure(s)")
    if report["fetch_failures"]:
        report["note"] = (
            f"{report['fetch_failures']} working copy/copies could not reach origin; their "
            "branch and behind findings below are computed from stale remote-tracking refs."
        )
    return report


# -------------------------------------------------------------- collectors


def collect_agents(collab: Path, projects: list[dict]) -> list[dict]:
    agents = []
    for proj in projects:
        agents_dir = collab / proj["dir"] / "agents"
        if not agents_dir.is_dir():
            continue
        for persona_file in sorted(agents_dir.glob("*/persona.yaml")):
            p = parse_yaml_persona(persona_file)
            allow, deny = p.get("allow", []), p.get("deny", [])
            agents.append(
                {
                    "project": proj["name"],
                    "slug": p.get("slug", persona_file.parent.name),
                    "persona": p.get("persona", persona_file.parent.name.title()),
                    "archetype": p.get("archetype", "unknown"),
                    "routing_label": p.get("routing_label"),
                    "git_name": p.get("git_name"),
                    "git_email": p.get("git_email"),
                    "commit_prefix": p.get("commit_prefix"),
                    "allow": allow,
                    "deny": deny,
                    "holds_merge_pr": "merge_pr" in allow,
                    "can_write_code": "write_code" in allow,
                }
            )
    return agents


def collect_merge_queue(repo: str) -> tuple[list[dict], str]:
    """Open PRs on the PUBLIC repo — already public information."""
    if not shutil.which("gh"):
        return [], "gh CLI not available — merge queue not collected"
    fields = "number,title,author,headRefName,isDraft,createdAt,mergeable,labels,statusCheckRollup,url"
    data = run_json(["gh", "pr", "list", "--repo", repo, "--state", "open", "--limit", "50", "--json", fields])
    if data is None:
        return [], "gh returned no data — merge queue not collected"

    queue = []
    for pr in data:
        rollup = pr.get("statusCheckRollup") or []
        conclusions = {c.get("conclusion") for c in rollup if c.get("conclusion")}
        if not rollup:
            checks = "none"
        elif conclusions <= {"SUCCESS", "NEUTRAL", "SKIPPED"}:
            checks = "passing"
        elif conclusions & {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}:
            checks = "failing"
        else:
            checks = "pending"
        queue.append(
            {
                "number": pr["number"],
                "title": pr["title"],
                "author": (pr.get("author") or {}).get("login"),
                "branch": pr.get("headRefName"),
                "draft": pr.get("isDraft", False),
                "created_at": pr.get("createdAt"),
                "age_days": days_since(pr.get("createdAt", "")),
                "mergeable": pr.get("mergeable"),
                "checks": checks,
                "labels": [l.get("name") for l in (pr.get("labels") or [])],
                "url": pr.get("url"),
            }
        )
    queue.sort(key=lambda p: p["number"], reverse=True)
    return queue, "ok"


def collect_records(collab: Path, projects: list[dict], baron: list[str]) -> dict:
    """Per-project record counts.

    `baron export` is single-project: run at a monorepo ROOT it walks no
    subdirs and reports zero records, so this loops the registered projects
    itself. Counts only — record bodies never leave the private repo.
    """
    records = {}
    for proj in projects:
        data = run_json(baron + ["export", "--collab", str(collab / proj["dir"]), "--json"])
        summary = (data or {}).get("summary", {})
        records[proj["name"]] = {
            "total": summary.get("records", 0),
            "by_kind": summary.get("by_kind", {}),
        }
    return records


def count_open_handoffs(collab: Path, projects: list[dict]) -> dict:
    """Open handoff COUNTS — filenames and bodies stay private."""
    counts = {}
    for proj in projects:
        d = collab / proj["dir"] / "_handoff"
        n = 0
        if d.is_dir():
            n = len([f for f in d.glob("*.md") if f.name.upper() != "README.MD"])
        counts[proj["name"]] = n
    return counts


# ------------------------------------------------------------------- build


def build(collab: Path, repo: str, baron: list[str], *, refresh: bool = True) -> dict:
    print(f"→ reading portfolio at {collab.name}/ (private, never published)")

    # Fetch BEFORE reading. `baron status` reads local git; without this the
    # snapshot republishes whatever refs this clone last happened to see.
    freshness = refresh_working_copies(collab, discover_projects(collab), enabled=refresh)

    status = run_json(baron + ["status", "--collab", str(collab), "--json"])
    health = run_json(baron + ["health", "--collab", str(collab), "--json"])
    if status is None or health is None:
        raise SystemExit("baron status/health produced no usable JSON — is --collab a collab repo?")

    layout = status.get("layout", "single")
    if layout == "monorepo":
        projects = [{"dir": d, "name": d} for d in status.get("projects", {})]
    else:
        projects = [{"dir": ".", "name": collab.name}]

    print(f"→ {len(projects)} project(s): {', '.join(p['name'] for p in projects)}")

    records = collect_records(collab, projects, baron)
    handoffs = count_open_handoffs(collab, projects)
    agents = collect_agents(collab, projects)
    print(f"→ {len(agents)} registered persona(s)")

    queue, queue_note = collect_merge_queue(repo)
    print(f"→ merge queue: {len(queue)} open PR(s) ({queue_note})")

    # ---- projects panel
    proj_rows = []
    for proj in projects:
        node = status.get("projects", {}).get(proj["dir"], {})
        findings = scrub(node.get("findings", []))
        summary = node.get("summary", {"red": 0, "warn": 0})
        proj_rows.append(
            {
                "name": proj["name"],
                "red": summary.get("red", 0),
                "warn": summary.get("warn", 0),
                "state": "red" if summary.get("red") else ("warn" if summary.get("warn") else "green"),
                "findings": findings,
                "records": records.get(proj["name"], {"total": 0, "by_kind": {}}),
                "open_handoffs": handoffs.get(proj["name"], 0),
                "agents": len([a for a in agents if a["project"] == proj["name"]]),
            }
        )

    # ---- health, with the honest coverage bound carried through
    hsum = health.get("summary", {})
    hprojects = []
    plane_shared = False
    plane_measured = False
    for proj in projects:
        node = health.get("projects", {}).get(proj["dir"], {})
        plane = node.get("plane", {})
        plane_shared = plane_shared or bool(plane.get("shared"))
        plane_measured = plane_measured or bool(plane.get("measured"))
        hprojects.append(
            {
                "name": proj["name"],
                "verdicts": node.get("verdicts", 0),
                "mutation_kill": node.get("mutation_kill", {}),
                "claim_drift": node.get("claim_drift", {}),
                "reviewer_escapes": node.get("reviewer_escapes", 0),
                "stalls": len(node.get("stalls", [])),
                "stall_list": scrub(node.get("stalls", [])),
                "plane_measured": bool(plane.get("measured")),
            }
        )

    verdicts = hsum.get("verdicts", 0)
    mk = hsum.get("mutation_kill", {}) or {}
    metrics = [
        {
            "key": "mutation_kill",
            "label": "Mutation kill rate",
            "value": mk.get("rate"),
            "unit": "ratio",
            "n": mk.get("run", 0),
            "basis": f"{mk.get('killed', 0)} killed / {mk.get('run', 0)} run",
            "measured": bool(mk.get("run")),
            "note": None if mk.get("run") else UNMEASURED,
        },
        {
            "key": "reviewer_escapes",
            "label": "Reviewer escapes",
            "value": hsum.get("reviewer_escapes", 0),
            "unit": "count",
            "n": verdicts,
            "basis": f"across {verdicts} recorded verdict(s)",
            "measured": verdicts > 0,
            "note": None if verdicts else UNMEASURED,
        },
        {
            "key": "claim_drift",
            "label": "Claim drift",
            "value": hsum.get("claim_drift", 0),
            "unit": "count",
            "n": verdicts,
            "basis": f"across {verdicts} recorded verdict(s)",
            "measured": verdicts > 0,
            "note": None if verdicts else UNMEASURED,
        },
        {
            "key": "verdict_coverage",
            "label": "Verdict coverage",
            "value": verdicts,
            "unit": "count",
            "n": verdicts,
            "basis": f"{verdicts} verdict(s) on the event plane",
            "measured": verdicts > 0,
            "note": "single observation — indicative only, not a trend" if verdicts == 1 else None,
        },
        {
            "key": "stalls",
            "label": "Stalls",
            "value": hsum.get("stalls", 0),
            "unit": "count",
            "n": hsum.get("stalls", 0),
            "basis": "unmerged branches + behind working copies",
            "measured": True,
            "note": None,
        },
    ]

    coverage_note = (
        "The event plane is SHARED at the monorepo root, so verdicts roll up to the "
        "portfolio but cannot be attributed to a single project — per-project verdict "
        "counts read 0 while the rollup reads {}. This is a real coverage limit, not a "
        "clean board.".format(verdicts)
        if plane_shared and not plane_measured
        else "Per-project event planes are attributed."
    )

    # ---- owner action queue, derived from the panels above
    owner_actions = []
    for pr in queue:
        if pr["draft"]:
            continue
        # A conflicting PR is NOT ready for the gate however green its checks
        # are — CI ran against a head that will not merge as-is.
        if pr["mergeable"] == "CONFLICTING":
            owner_actions.append(
                {
                    "severity": "warn",
                    "kind": "conflict",
                    "summary": f"PR #{pr['number']} conflicts with main — needs a rebase before the gate",
                    "detail": pr["title"],
                    "url": pr["url"],
                }
            )
        elif pr["checks"] == "passing" and pr["mergeable"] == "MERGEABLE":
            owner_actions.append(
                {
                    "severity": "action",
                    "kind": "merge-gate",
                    "summary": f"PR #{pr['number']} is green and awaiting the merge gate",
                    "detail": pr["title"],
                    "url": pr["url"],
                }
            )
    stale = [p for p in proj_rows for f in p["findings"] if f.get("check") == "unmerged-branch"]
    if stale:
        owner_actions.append(
            {
                "severity": "warn",
                "kind": "stalls",
                "summary": f"{hsum.get('stalls', 0)} stalled branch/working-copy findings",
                "detail": "Unmerged local branches and working copies behind origin/main.",
                "url": None,
            }
        )
    if not freshness.get("attempted") or freshness.get("fetch_failures"):
        owner_actions.append(
            {
                "severity": "warn",
                "kind": "freshness",
                "summary": "Snapshot was not fully refreshed against origin",
                "detail": freshness.get("note") or "Working copies were not fetched before reading.",
                "url": None,
            }
        )
    if not plane_measured:
        owner_actions.append(
            {
                "severity": "warn",
                "kind": "coverage",
                "summary": "Fleet-health coverage is unattributed",
                "detail": coverage_note,
                "url": None,
            }
        )

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": {
            "tool": "dashboard/build-data.sh",
            "baron_version": baron_version(baron),
            "source": "private coordination monorepo — curated projection, not a mirror",
            "refresh": freshness,
        },
        "portfolio": {
            "layout": layout,
            "projects": len(projects),
            "agents": len(agents),
            "public_repo": repo,
        },
        "kpis": {
            "projects": len(projects),
            "agents": len(agents),
            "open_prs": len(queue),
            "red_findings": sum(p["red"] for p in proj_rows),
            "warn_findings": sum(p["warn"] for p in proj_rows),
            "stalls": hsum.get("stalls", 0),
            "verdicts": verdicts,
            "open_handoffs": sum(handoffs.values()),
        },
        "projects_detail": proj_rows,
        "agents": agents,
        "identity": {
            "scheme": "persona identity block (git_name / git_email / commit_prefix / routing_label)",
            "signing": {
                "state": "not-implemented",
                "label": "Not deployed",
                "note": (
                    "Per-persona SSH signing keys are specified in ADR-027, which is now accepted "
                    "on main — but no key is enrolled for this fleet, so no agent commit is "
                    "cryptographically signed today. Identity is convention-enforced only."
                ),
            },
        },
        "health": {
            "rollup": {
                "verdicts": verdicts,
                "mutation_kill": mk,
                "claim_drift": hsum.get("claim_drift", 0),
                "reviewer_escapes": hsum.get("reviewer_escapes", 0),
                "stalls": hsum.get("stalls", 0),
            },
            "metrics": metrics,
            "coverage": {
                "measured": plane_measured,
                "plane_shared": plane_shared,
                "note": coverage_note,
            },
            "projects": hprojects,
        },
        "merge_queue": queue,
        "observer": {
            "active": False,
            "flags": [],
            "label": "Not deployed",
            "note": (
                "The observer archetype (ADR-030) is merged, but no observer is deployed "
                "against this fleet, so there are zero flags — an empty watchlist, not a clean one."
            ),
        },
        "owner_actions": owner_actions,
        "honesty": [
            "Every number here is read from the live coordination repo by `baron`; none is hand-entered.",
            freshness_note(freshness),
            "Metrics with an empty denominator render as `n/a` with their basis, never as 0% or 100%.",
            coverage_note,
            "Observer flags and commit signing are shown as NOT ACTIVE because neither is deployed in this fleet; both ADRs (027, 030) are now on main.",
        ],
    }


def freshness_note(freshness: dict) -> str:
    """One line stating, plainly, how current the underlying git data is."""
    if not freshness.get("attempted"):
        return (
            "Working copies were NOT fetched before this snapshot was taken — branch and "
            "behind findings may name branches that no longer exist on origin."
        )
    if freshness.get("fetch_failures"):
        return "Refresh was incomplete: " + str(freshness.get("note"))
    n = len(freshness.get("targets", []))
    return (
        f"Every working copy ({n}) was fetched with --prune before reading, so branch and "
        "behind findings are measured against origin as of the generation time above."
    )


def baron_version(baron: list[str]) -> str:
    proc = subprocess.run(baron + ["--version"], capture_output=True, text=True)
    line = (proc.stdout or proc.stderr).strip().splitlines()
    return line[-1].strip() if line else "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--collab",
        default=os.environ.get("BARONY_COLLAB", "~/Workspace/fleet-coordination"),
        help="Path to the PRIVATE coordination collab repo (env: BARONY_COLLAB).",
    )
    ap.add_argument("--repo", default=os.environ.get("BARONY_REPO", "vggg/barony"), help="Public repo for the merge queue.")
    ap.add_argument("--out", default=str(REPO_ROOT / "dashboard" / "data" / "fleet.json"))
    ap.add_argument("--baron", default=os.environ.get("BARON_CMD", ""), help="Override the baron command.")
    ap.add_argument(
        "--no-refresh",
        action="store_true",
        help="Do NOT fetch/fast-forward the working copies first. The snapshot then records "
             "that it may be stale — use only when deliberately reading the clones as-is.",
    )
    args = ap.parse_args()

    collab = Path(os.path.expanduser(args.collab)).resolve()
    if not collab.is_dir():
        raise SystemExit(
            f"collab repo not found: {collab}\n"
            "Pass --collab <path> or set BARONY_COLLAB. This is the PRIVATE coordination\n"
            "repo; without it there is nothing to project from."
        )

    baron = args.baron.split() if args.baron else ["uv", "run", "--project", str(REPO_ROOT / "cli"), "baron"]

    snapshot = build(collab, args.repo, baron, refresh=not args.no_refresh)

    # Belt and braces: no absolute path may survive into the published file.
    snapshot = scrub(snapshot)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"✓ wrote {out.relative_to(REPO_ROOT) if out.is_relative_to(REPO_ROOT) else out}")
    print(f"  {snapshot['kpis']['projects']} projects · {snapshot['kpis']['agents']} agents · "
          f"{snapshot['kpis']['open_prs']} open PRs · {snapshot['kpis']['verdicts']} verdict(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
