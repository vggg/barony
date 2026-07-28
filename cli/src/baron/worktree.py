"""M6 tooling — ``baron worktree add|list|remove``: the branch-per-persona
worktree topology.

One shared object store (``git worktree``), one ``persona/<slug>`` branch per
persona, worktrees under the manifest's ``workspace.worktrees_root``. This is
the topology that *prevents* the per-clone stranding classes ``baron status``
detects (ADR-003 §2.7): commits land in one object store, so "committed in a
clone that never pushed" cannot silently diverge from what the other working
copies can see.

``baron status`` sweeps worktrees via the existing ``workspace.worktrees_root``
manifest field (schema v1.2) — same divergence checks as clones. Migration
from a clone-per-persona workspace: ``docs/worktree-migration.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .gitutil import (
    GitError,
    commits_not_in,
    default_branch,
    dirty_count,
    git,
    has_remote,
    is_git_repo,
)

BRANCH_PREFIX = "persona/"


class WorktreeError(RuntimeError):
    """A worktree operation could not be completed."""


@dataclass(frozen=True)
class Worktree:
    path: Path
    branch: str | None  # None = detached
    ahead: int | None
    behind: int | None
    is_main: bool  # the primary working copy (not a linked worktree)

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path.as_posix(),
            "branch": self.branch,
            "ahead": self.ahead,
            "behind": self.behind,
            "is_main": self.is_main,
        }


def persona_branch(persona: str) -> str:
    return f"{BRANCH_PREFIX}{persona}"


def _require_repo(repo: Path) -> None:
    if not is_git_repo(repo):
        raise WorktreeError(f"{repo} is not a git working copy")


def _default_upstream(repo: Path) -> tuple[str, str]:
    """(default_branch_name, comparison_ref). Prefers origin/<default>; for a
    local-only repo falls back to the local default-named branch."""
    default = default_branch(repo)
    if default is not None:
        return default, f"origin/{default}"
    for candidate in ("main", "master"):
        proc = git(repo, "show-ref", "--verify", "--quiet",
                   f"refs/heads/{candidate}", check=False)
        if proc.returncode == 0:
            return candidate, candidate
    raise WorktreeError(
        f"cannot determine the default branch of {repo} (no origin default, "
        "no local main/master)"
    )


def _branch_exists(repo: Path, branch: str) -> bool:
    proc = git(repo, "show-ref", "--verify", "--quiet",
               f"refs/heads/{branch}", check=False)
    return proc.returncode == 0


def add(repo: Path, persona: str, root: Path) -> Path:
    """Create ``<root>/<persona>`` as a worktree on branch ``persona/<persona>``
    (created from the default branch if missing)."""
    _require_repo(repo)
    branch = persona_branch(persona)
    dest = root / persona
    if dest.exists():
        raise WorktreeError(f"{dest} already exists — remove it first")
    root.mkdir(parents=True, exist_ok=True)
    try:
        if _branch_exists(repo, branch):
            git(repo, "worktree", "add", str(dest), branch)
        else:
            _, base_ref = _default_upstream(repo)
            git(repo, "worktree", "add", "-b", branch, str(dest), base_ref)
    except GitError as exc:
        raise WorktreeError(str(exc)) from exc
    return dest


def list_worktrees(repo: Path) -> list[Worktree]:
    """Every worktree of ``repo`` with its branch's ahead/behind vs the default
    branch (origin/<default> when a remote exists)."""
    _require_repo(repo)
    proc = git(repo, "worktree", "list", "--porcelain")
    try:
        _, upstream = _default_upstream(repo)
    except WorktreeError:
        upstream = None
    out: list[Worktree] = []
    first = True
    path: Path | None = None
    branch: str | None = None
    for line in proc.stdout.splitlines() + [""]:
        if line.startswith("worktree "):
            path = Path(line.split(" ", 1)[1])
        elif line.startswith("branch "):
            branch = line.split(" ", 1)[1].removeprefix("refs/heads/")
        elif not line.strip() and path is not None:
            ahead = behind = None
            if branch is not None and upstream is not None:
                try:
                    ahead = commits_not_in(repo, branch, upstream)
                    behind = commits_not_in(repo, upstream, branch)
                except GitError:
                    pass
            out.append(Worktree(path, branch, ahead, behind, is_main=first))
            first = False
            path, branch = None, None
    return out


def remove(repo: Path, persona: str, *, force: bool = False) -> Path:
    """Remove the persona's worktree. Refuses when the worktree is dirty or its
    branch carries commits not merged to the default branch, unless ``force``.
    The ``persona/<persona>`` branch itself is kept either way — removing a
    worktree never deletes history."""
    _require_repo(repo)
    branch = persona_branch(persona)
    target = next(
        (w for w in list_worktrees(repo) if not w.is_main and w.branch == branch),
        None,
    )
    if target is None:
        raise WorktreeError(f"no worktree found on branch {branch}")
    problems: list[str] = []
    if target.path.is_dir():
        dirt = dirty_count(target.path)
        if dirt:
            problems.append(f"{dirt} uncommitted path(s)")
    if target.ahead:
        problems.append(f"{target.ahead} commit(s) not merged to the default branch")
    if problems and not force:
        raise WorktreeError(
            f"refusing to remove {target.path}: " + "; ".join(problems)
            + " — push/merge first, or pass --force"
        )
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(target.path))
    try:
        git(repo, *args)
    except GitError as exc:
        raise WorktreeError(str(exc)) from exc
    return target.path


def _worktree_subcommand_available(repo: Path, sub: str) -> bool:
    """Whether ``git worktree <sub>`` exists in this git — ``repair`` landed in
    git 2.30, so an old git lists no ``repair`` in ``git worktree -h``."""
    proc = git(repo, "worktree", "-h", check=False)
    return sub in (proc.stdout + proc.stderr)


def prune(repo: Path, *, dry_run: bool = False) -> str:
    """Wrap ``git worktree prune``: drop stale administrative registrations in
    ``.git/worktrees/`` for worktree directories that no longer exist (moved or
    ``rm``'d out from under git). Non-destructive to committed work — it only
    touches admin state, never a branch or its history. ``dry_run`` passes
    ``-n`` to report what *would* be pruned without removing anything. Returns
    git's (verbose) report; empty means nothing stale."""
    _require_repo(repo)
    if not _worktree_subcommand_available(repo, "prune"):
        raise WorktreeError(
            f"this git ({repo}) has no `git worktree prune` — upgrade git"
        )
    args = ["worktree", "prune", "-v"]
    if dry_run:
        args.append("-n")
    try:
        proc = git(repo, *args)
    except GitError as exc:
        raise WorktreeError(str(exc)) from exc
    # `git worktree prune -v` writes its "Removing …" report to stderr.
    return (proc.stdout + proc.stderr).strip()


def repair(repo: Path, paths: list[Path] | None = None) -> str:
    """Wrap ``git worktree repair``: fix the administrative links (the gitdir
    pointer and each worktree's ``.git`` gitlink) after a worktree or the main
    repo was moved. With ``paths``, repair those worktrees; otherwise repair all.
    Non-destructive to committed work — it only re-points admin files, never a
    branch or its history. Returns git's report (empty when nothing needed
    fixing). Requires git >= 2.30."""
    _require_repo(repo)
    if not _worktree_subcommand_available(repo, "repair"):
        raise WorktreeError(
            f"this git ({repo}) has no `git worktree repair` (added in git 2.30)"
            " — upgrade git"
        )
    args = ["worktree", "repair"]
    if paths:
        args += [str(p) for p in paths]
    try:
        proc = git(repo, *args)
    except GitError as exc:
        raise WorktreeError(str(exc)) from exc
    # `git worktree repair` writes its progress to stderr; surface both.
    return (proc.stdout + proc.stderr).strip()


def render_table(worktrees: list[Worktree]) -> str:
    if not worktrees:
        return "no worktrees"
    rows = [("PATH", "BRANCH", "AHEAD", "BEHIND", "")]
    for w in worktrees:
        rows.append(
            (
                w.path.as_posix(),
                w.branch or "(detached)",
                "?" if w.ahead is None else str(w.ahead),
                "?" if w.behind is None else str(w.behind),
                "(main working copy)" if w.is_main else "",
            )
        )
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    return "\n".join(
        ("  ".join(r[i].ljust(widths[i]) for i in range(4)) + "  " + r[4]).rstrip()
        for r in rows
    )
