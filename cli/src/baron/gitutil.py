"""Thin subprocess wrapper over git.

Deliberately not gitpython (ADR-003 dependency policy): baron shells out to the
same `git` the personas use, with captured output and explicit error checking.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    """A git invocation failed."""


def git(
    repo: Path | str, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run ``git -C <repo> <args>`` with captured text output.

    Raises :class:`GitError` on non-zero exit when ``check`` is true.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise GitError(f"git {' '.join(args)} failed in {repo}: {detail}")
    return proc


def is_git_repo(path: Path) -> bool:
    if not path.is_dir():
        return False
    proc = git(path, "rev-parse", "--is-inside-work-tree", check=False)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def has_remote(repo: Path, name: str = "origin") -> bool:
    proc = git(repo, "remote", check=False)
    return name in proc.stdout.split()


def fetch(repo: Path, remote: str = "origin") -> bool:
    """Fetch (with --prune); returns False instead of raising on failure."""
    return git(repo, "fetch", "--prune", remote, check=False).returncode == 0


def default_branch(repo: Path, remote: str = "origin") -> str | None:
    """The remote's default branch name, or None if undeterminable offline."""
    proc = git(
        repo, "symbolic-ref", "--quiet", f"refs/remotes/{remote}/HEAD", check=False
    )
    if proc.returncode == 0 and proc.stdout.strip():
        # refs/remotes/origin/main -> main
        return proc.stdout.strip().split(f"refs/remotes/{remote}/", 1)[-1]
    for candidate in ("main", "master"):
        verify = git(
            repo,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/remotes/{remote}/{candidate}",
            check=False,
        )
        if verify.returncode == 0:
            return candidate
    return None


def ahead_behind(repo: Path, upstream: str) -> tuple[int, int]:
    """(ahead, behind) of HEAD relative to ``upstream`` (e.g. origin/main)."""
    proc = git(repo, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
    behind_s, ahead_s = proc.stdout.split()
    return int(ahead_s), int(behind_s)


def dirty_count(repo: Path) -> int:
    """Number of uncommitted (staged/unstaged/untracked) paths UNDER ``repo``.

    Scoped with the ``-- .`` pathspec, not left repo-wide. For a repo root the two
    are identical; for a directory *inside* a work tree they are not, and in a
    coordination monorepo (ADR-025) every project collab path is such a directory.
    Unscoped, the 2026-08-14 dogfood reported `_meta` dirty because a sibling
    project's `manifest.yaml` was uncommitted — one edit, N projects blamed, and
    the report stops distinguishing which project actually needs a commit.
    """
    proc = git(repo, "status", "--porcelain", "--", ".")
    return len([line for line in proc.stdout.splitlines() if line.strip()])


def local_branches(repo: Path) -> list[tuple[str, int]]:
    """[(branch_name, last_commit_unix_ts)] for every local branch."""
    proc = git(
        repo,
        "for-each-ref",
        "refs/heads",
        "--format=%(refname:short)%09%(committerdate:unix)",
    )
    out: list[tuple[str, int]] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        name, _, ts = line.partition("\t")
        out.append((name, int(ts or 0)))
    return out


def commits_not_in(repo: Path, branch: str, upstream: str) -> int:
    """Count of commits on ``branch`` not reachable from ``upstream``."""
    proc = git(repo, "rev-list", "--count", f"{upstream}..{branch}")
    return int(proc.stdout.strip() or 0)


def last_commit_date(repo: Path, *paths: str) -> str | None:
    """ISO date (%cs) of the newest commit touching ``paths`` (or any, if none given)."""
    args = ["log", "-1", "--format=%cs"]
    if paths:
        args += ["--", *paths]
    proc = git(repo, *args, check=False)
    out = proc.stdout.strip()
    return out or None


def current_branch(repo: Path) -> str | None:
    """The checked-out branch name, or None if detached HEAD."""
    proc = git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    name = proc.stdout.strip()
    return name if (proc.returncode == 0 and name and name != "HEAD") else None
