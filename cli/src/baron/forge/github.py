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


def _normalize_checks(rollup: object) -> list[dict[str, object]]:
    """``statusCheckRollup`` -> ``[{name, state}]`` across both node shapes.

    A CheckRun carries ``name`` + ``status``/``conclusion``; a legacy StatusContext
    carries ``context`` + ``state``. An in-flight CheckRun has ``conclusion: ""``, so
    the conclusion is used only once ``status`` is COMPLETED — reading it earlier
    turns "still running" into an empty state the gate would have to guess at.
    Unrecognized shapes keep whatever state they had (possibly ``""``) rather than
    being dropped: ``baron merge`` refuses on an uninterpretable check, and dropping
    it here would silently make that PR greener than it is.
    """
    out: list[dict[str, object]] = []
    for node in rollup or []:
        if not isinstance(node, dict):
            continue
        name = node.get("name") or node.get("context") or "?"
        if "conclusion" in node or "status" in node:
            status = str(node.get("status") or "").upper()
            state = str(node.get("conclusion") or "") if status == "COMPLETED" else status
        else:
            state = str(node.get("state") or "")
        out.append({"name": str(name), "state": state})
    return out


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

    def get_pr(
        self, repo: Path, number: int, *, target_repo: str | None = None
    ) -> dict[str, object]:
        """ONE snapshot of a PR, normalized — the merge gate's only evidence.

        Every field the gate scores comes from a single ``gh pr view`` so head sha,
        verdict comments, labels and checks describe the same observed moment. Two
        calls could straddle a push and produce a verdict that "matches" a head the
        checks never ran on — precisely the stale-verdict merge this gate exists to
        stop. ``target_repo`` is required in practice for a merger running in the
        collab repo: without it ``gh`` answers about the collab repo's same-numbered
        PR (the wrong-repo failure ``get_issue`` documents).

        ``statusCheckRollup`` is by definition the rollup for the CURRENT head, and
        it arrives in the same payload as ``headRefOid``.
        """
        args = [
            "pr", "view", str(number),
            "--json",
            "number,state,isDraft,headRefOid,url,labels,reviewDecision,comments,statusCheckRollup",
        ]
        if target_repo:
            args += ["--repo", target_repo]
        data = json.loads(self._gh(repo, *args) or "{}")
        if not isinstance(data, dict) or not data:
            return {}
        labels = data.get("labels")
        if isinstance(labels, list):
            data["labels"] = [
                lb.get("name") if isinstance(lb, dict) else lb for lb in labels
            ]
        data["checks"] = _normalize_checks(data.pop("statusCheckRollup", None))
        if target_repo:
            data["repo"] = target_repo
        return data

    def dispatch_event(
        self, repo: Path, *, event_type: str, payload: dict[str, object]
    ) -> None:
        """Fire a repository_dispatch (ADR-010 §6, optional duck-typed extension).

        Triggers the repo's workflows listening on ``event_type`` FROM ITS DEFAULT
        BRANCH ONLY; the caller (``baron notify``) guarantees the handoff was pushed
        there first. Needs write access — the same access a push needs.
        """
        if not self.available():
            raise ForgeUnavailable("GitHub CLI (`gh`) not found on PATH")
        body = json.dumps({"event_type": event_type, "client_payload": payload})
        proc = subprocess.run(
            ["gh", "api", "--method", "POST",
             "repos/{owner}/{repo}/dispatches", "--input", "-"],
            cwd=str(repo), input=body, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise ForgeError(
                f"repository_dispatch failed: {proc.stderr.strip() or proc.stdout.strip()}"
            )

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
