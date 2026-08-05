"""GitHub forge — implemented over the ``gh`` CLI via subprocess.

First real consumer: ``baron lock`` (M5, PR-as-lock per ADR-002 §3). ``gh``
is an accepted prerequisite for forge features only — its absence raises
:class:`ForgeUnavailable` with an actionable message, and no non-forge path
requires it. Branch plumbing (:meth:`create_branch`) is plain git via
subprocess — it lives behind the Forge interface so lock logic stays
forge-neutral and mockable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from ..gitutil import GitError, git
from .base import ForgeError, ForgeUnavailable


class GitHubForge:
    name = "github"

    def available(self) -> bool:
        return shutil.which("gh") is not None

    def _gh(self, repo: Path, *args: str) -> str:
        if not self.available():
            raise ForgeUnavailable(
                "GitHub CLI (`gh`) not found on PATH — install it for forge features "
                "(baron lock); everything else (validate/status/finding/decision/"
                "handoff/index/guard/worktree/waiver) works without it"
            )
        proc = subprocess.run(
            ["gh", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise ForgeError(
                f"gh {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc.stdout

    def default_branch(self, repo: Path) -> str | None:
        out = self._gh(
            repo, "repo", "view", "--json", "defaultBranchRef",
            "--jq", ".defaultBranchRef.name",
        ).strip()
        return out or None

    def open_pr(
        self,
        repo: Path,
        *,
        title: str,
        body: str,
        base: str | None = None,
        draft: bool = False,
        head: str | None = None,
        labels: list[str] | None = None,
    ) -> str:
        for label in labels or []:
            # Idempotent: --force updates an existing label instead of failing.
            self._gh(repo, "label", "create", label, "--force")
        args = ["pr", "create", "--title", title, "--body", body]
        if base:
            args += ["--base", base]
        if head:
            args += ["--head", head]
        for label in labels or []:
            args += ["--label", label]
        if draft:
            args.append("--draft")
        return self._gh(repo, *args).strip()

    def list_open_prs(self, repo: Path) -> list[dict[str, object]]:
        out = self._gh(
            repo, "pr", "list", "--state", "open",
            "--json", "number,title,headRefName,labels,author,createdAt,url",
        )
        loaded = json.loads(out or "[]")
        return loaded if isinstance(loaded, list) else []

    def get_issue(
        self, repo: Path, number: int, *, target_repo: str | None = None
    ) -> dict[str, object]:
        """One issue, normalized: labels flattened to a list of names.

        ``target_repo`` (owner/name) selects the repo explicitly; without it `gh`
        resolves from ``repo``'s remote, which answers the WRONG repo when the park
        is on a code-repo issue and baron is running in the collab repo.
        """
        args = ["issue", "view", str(number), "--json", "number,state,labels,title,url"]
        if target_repo:
            args += ["--repo", target_repo]
        out = self._gh(repo, *args)
        data = json.loads(out or "{}")
        if not isinstance(data, dict):
            return {}
        labels = data.get("labels")
        if isinstance(labels, list):
            data["labels"] = [
                lb.get("name") if isinstance(lb, dict) else lb for lb in labels
            ]
        return data

    def create_branch(self, repo: Path, *, branch: str, base: str, message: str) -> None:
        """Branch + empty commit + push, without touching the local checkout:
        ``git commit-tree`` writes an empty commit on top of ``origin/<base>``
        and the push publishes it as ``branch``. (An empty commit is required —
        GitHub refuses a PR whose head equals its base.)"""
        try:
            git(repo, "fetch", "origin", base)
            base_ref = f"origin/{base}"
            tree = git(repo, "rev-parse", f"{base_ref}^{{tree}}").stdout.strip()
            commit = git(
                repo, "commit-tree", tree, "-p", base_ref, "-m", message
            ).stdout.strip()
            git(repo, "push", "origin", f"{commit}:refs/heads/{branch}")
        except GitError as exc:
            raise ForgeError(f"cannot create branch {branch!r}: {exc}") from exc

    def close_pr(self, repo: Path, number: int, *, delete_branch: bool = False) -> None:
        args = ["pr", "close", str(number)]
        if delete_branch:
            args.append("--delete-branch")
        self._gh(repo, *args)
