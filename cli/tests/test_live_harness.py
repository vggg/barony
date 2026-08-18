"""The proof-by-invocation harness, exercised WITHOUT a model (default job).

`test_live_runtime.py` is opt-in, paid and nondeterministic, so it may go weeks
between runs. Its shim is the piece most likely to rot in that gap — and a
broken shim fails in the WORST direction: the sentinel is never written, so the
denial assertion passes and the run looks green while measuring nothing. That is
the same false-green shape the negative control defends against, arriving by a
different route.

So the plumbing is pinned here, in the default job, using a fake "runtime" that
is just a shell command: the shim really does record a push, really does record
a `gh pr merge`, really does exec the real git for everything else, and the
scaffold really does produce two installable kits.

Nothing here proves enforcement. It proves the instrument works.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from test_live_runtime import install_kit, scaffold, write_shims


def _run(command: str, cwd: Path, shim_dir: Path, sentinel: Path):
    env = dict(os.environ)
    env["PATH"] = f"{shim_dir}{os.pathsep}{env['PATH']}"
    env["BARON_SENTINEL"] = str(sentinel)
    return subprocess.run(
        ["sh", "-c", command], cwd=cwd, env=env, capture_output=True, text=True
    )


def test_the_shim_records_a_push_and_never_reaches_the_remote(tmp_path: Path) -> None:
    sentinel = tmp_path / "sentinel"
    shim_dir = tmp_path / "shims"
    write_shims(shim_dir, sentinel)
    proc = _run("git push origin main", tmp_path, shim_dir, sentinel)
    assert proc.returncode == 0, proc.stderr
    assert sentinel.is_file(), "the shim did not record the push — a live run "
    "measuring this shim would report a false green"
    assert "git push origin main" in sentinel.read_text(encoding="utf-8")


def test_the_shim_records_a_pr_merge(tmp_path: Path) -> None:
    sentinel = tmp_path / "sentinel"
    shim_dir = tmp_path / "shims"
    write_shims(shim_dir, sentinel)
    assert _run("gh pr merge 1 --squash", tmp_path, shim_dir, sentinel).returncode == 0
    assert "gh pr merge 1 --squash" in sentinel.read_text(encoding="utf-8")


def test_the_shim_execs_real_git_for_everything_else(tmp_path: Path) -> None:
    """Guard shells out to git itself; a shim that swallowed every call would
    change what guard sees and make a denial happen for the wrong reason."""
    sentinel = tmp_path / "sentinel"
    shim_dir = tmp_path / "shims"
    write_shims(shim_dir, sentinel)
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    proc = _run("git symbolic-ref --short HEAD", tmp_path, shim_dir, sentinel)
    assert proc.stdout.strip() == "main", proc.stderr
    assert not sentinel.exists(), "a non-push git call was swallowed by the shim"


def test_the_scaffold_yields_two_installable_kits(tmp_path: Path) -> None:
    """One persona that denies merge_pr, one that grants it — the control pair.

    If these two ever stop differing on merge_pr the live test still runs, but
    its control and its measurement become the same experiment.
    """
    dest = scaffold(tmp_path)
    import yaml

    grants = {}
    for slug in ("carson", "mona"):
        spec = yaml.safe_load(
            (dest / "agents" / slug / "persona.yaml").read_text(encoding="utf-8")
        )
        caps = spec["capabilities"]
        flat = {
            k if isinstance(item, dict) else item
            for key in ("allow", "deny")
            for item in caps.get(key) or []
            for k in ([*item] if isinstance(item, dict) else [item])
            if key == "allow"
        }
        grants[slug] = "merge_pr" in flat
        install_kit(dest, slug)
        settings = json.loads((dest / ".claude" / "settings.json").read_text(encoding="utf-8"))
        assert "PreToolUse" in settings.get("hooks", {}), f"{slug} kit wires no hook"
        assert slug in json.dumps(settings), f"{slug} kit does not name its own persona"

    assert grants["mona"] is True, "the control persona must GRANT merge_pr"
    assert grants["carson"] is False, "the measured persona must DENY merge_pr"


def test_the_live_tier_is_excluded_from_the_default_job() -> None:
    """OD-3, mechanised: the tier must not be able to creep into default CI."""
    import tomllib

    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_cfg = config["tool"]["pytest"]["ini_options"]
    assert "not live_runtime" in pytest_cfg["addopts"]
    assert any(m.startswith("live_runtime:") for m in pytest_cfg["markers"])
