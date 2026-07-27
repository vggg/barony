"""Shared fixtures: repo-root discovery, git scaffolding, injectable clock."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from baron import clock

#: The Barony repo root (cli/tests/ -> cli/ -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[2]

FIXED_NOW = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _hermetic_git_identity(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Give every git process in the tests a deterministic identity.

    CI runners have no user.name/email (v1.8.0's scaffold tests failed there
    with "Author identity unknown" while passing locally off the developer's
    gitconfig); pointing GIT_CONFIG_GLOBAL at a temp config makes the suite
    hermetic in both directions — subprocesses spawned by `baron init`
    included.
    """
    cfg = tmp_path_factory.mktemp("gitcfg") / "gitconfig"
    cfg.write_text(
        "[user]\n\tname = Test Runner\n\temail = test@barony.invalid\n"
        "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))


@pytest.fixture
def fixed_clock() -> object:
    """Pin baron's clock to 2026-07-22 for deterministic dates/ages."""
    clock.set_clock(lambda: FIXED_NOW)
    yield FIXED_NOW
    clock.reset_clock()


def run_git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc.stdout


def init_repo(path: Path) -> Path:
    """git init -b main with a deterministic identity."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(path)],
        capture_output=True, text=True, check=True,
    )
    configure_identity(path)
    return path


def init_bare(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(path)],
        capture_output=True, text=True, check=True,
    )
    return path


def clone(origin: Path, dest: Path) -> Path:
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(dest)],
        capture_output=True, text=True, check=True,
    )
    configure_identity(dest)
    return dest


def configure_identity(repo: Path) -> None:
    run_git(repo, "config", "user.name", "Test Persona")
    run_git(repo, "config", "user.email", "test@example.invalid")
    run_git(repo, "config", "commit.gpgsign", "false")


def commit_file(repo: Path, rel: str, content: str, message: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    run_git(repo, "add", "--", rel)
    run_git(repo, "commit", "-q", "-m", message, "--", rel)
