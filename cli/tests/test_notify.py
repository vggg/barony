"""ADR-010 acceptance: ``baron notify`` — deliver always, wake conditionally.

Uses a recorded fake forge (no live ``gh``) and a clone-of-bare collab so the
push-before-dispatch ordering and the default-branch guard are exercised for real.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baron import notify
from baron.frontmatter import split_frontmatter

from conftest import clone, init_bare, run_git


class FakeForge:
    """Records dispatch_event calls. Deliberately minimal — notify only needs
    supports(forge, 'dispatch_event') + the method itself."""

    name = "fake"

    def __init__(self) -> None:
        self.dispatched: list[dict] = []

    def available(self) -> bool:
        return True

    def dispatch_event(self, repo: Path, *, event_type: str, payload: dict) -> None:
        self.dispatched.append({"repo": repo, "event_type": event_type, "payload": payload})


class ForgeWithoutDispatch:
    name = "nodispatch"

    def available(self) -> bool:
        return True


@pytest.fixture
def collab(tmp_path: Path) -> Path:
    """A collab repo that is a clone of a bare origin (so push + origin/HEAD work),
    with a manifest allowing `librarian` to wake."""
    origin = init_bare(tmp_path / "origin.git")
    repo = clone(origin, tmp_path / "collab")
    (repo / "manifest.yaml").write_text(
        "project:\n  name: t\nnotify:\n  wake_allowed: [librarian]\n", encoding="utf-8"
    )
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "bootstrap")
    run_git(repo, "push", "-q", "origin", "main")
    return repo


def _meta(path: Path) -> dict:
    meta, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in (meta or {}).items()}


def test_no_wake_delivers_with_depth0_and_no_dispatch(collab: Path, fixed_clock) -> None:
    forge = FakeForge()
    res = notify.notify(
        collab, persona="reviewer", title="see PR 5", from_="librarian",
        wake=False, forge=forge,
    )
    assert res.delivered and not res.woke
    assert res.suppressed == "--no-wake"
    assert forge.dispatched == []
    m = _meta(res.handoff)
    assert m["for"] == "reviewer" and m["from"] == "librarian"
    assert m["wake_depth"] == "0" and m["wake_origin"] == "librarian"


def test_wake_fires_dispatch_and_pushes(collab: Path, fixed_clock) -> None:
    forge = FakeForge()
    res = notify.notify(
        collab, persona="reviewer", title="see PR 5", from_="librarian", forge=forge,
    )
    assert res.woke and res.suppressed is None
    assert len(forge.dispatched) == 1
    ev = forge.dispatched[0]
    assert ev["event_type"] == "baron-notify"
    assert ev["payload"]["persona"] == "reviewer"
    assert ev["payload"]["handoff"] == res.handoff.stem
    assert ev["payload"]["from"] == "librarian"
    # pushed before dispatch: origin now has the handoff on main
    origin_log = run_git(collab, "log", "origin/main", "--oneline", "-1")
    assert "handoff | open" in origin_log


def test_wake_suppressed_when_from_not_allowlisted(collab: Path, fixed_clock) -> None:
    forge = FakeForge()
    res = notify.notify(
        collab, persona="reviewer", title="x", from_="dev", forge=forge,  # dev not allowed
    )
    assert not res.woke and forge.dispatched == []
    assert "wake_allowed" in res.suppressed


def test_wake_suppressed_off_default_branch(collab: Path, fixed_clock) -> None:
    run_git(collab, "checkout", "-q", "-b", "feature/x")
    forge = FakeForge()
    res = notify.notify(
        collab, persona="reviewer", title="x", from_="librarian", forge=forge,
    )
    assert not res.woke and forge.dispatched == []
    assert "default branch" in res.suppressed


def test_wake_suppressed_when_forge_cannot_dispatch(collab: Path, fixed_clock) -> None:
    res = notify.notify(
        collab, persona="reviewer", title="x", from_="librarian", forge=ForgeWithoutDispatch(),
    )
    assert not res.woke
    assert "dispatch_event" in res.suppressed


def test_in_reply_to_increments_depth_and_copies_origin(collab: Path, fixed_clock) -> None:
    # allow dev too, so a dev reply can wake; origin should still trace to librarian
    (collab / "manifest.yaml").write_text(
        "project:\n  name: t\nnotify:\n  wake_allowed: [librarian, dev]\n", encoding="utf-8"
    )
    run_git(collab, "commit", "-q", "-am", "allow dev")
    run_git(collab, "push", "-q", "origin", "main")
    forge = FakeForge()
    parent = notify.notify(
        collab, persona="dev", title="root ask", from_="librarian", wake=False, forge=forge,
    )
    child = notify.notify(
        collab, persona="reviewer", title="reply", from_="dev",
        in_reply_to=parent.handoff.stem, forge=forge,
    )
    cm = _meta(child.handoff)
    assert cm["wake_depth"] == "1"
    assert cm["wake_origin"] == "librarian"  # copied from the parent, not reset to `dev`
    assert child.woke  # depth 1 <= max_depth 2


def test_wake_refused_past_max_depth(collab: Path, fixed_clock) -> None:
    # a parent already at depth 2; the reply would be depth 3 > default max 2
    from baron import handoff
    parent = handoff.create(
        collab, for_="dev", from_="librarian", title="deep", commit=True,
        extra={"wake_depth": "2", "wake_origin": "librarian"},
    )
    forge = FakeForge()
    res = notify.notify(
        collab, persona="reviewer", title="too deep", from_="librarian",
        in_reply_to=parent.stem, forge=forge,
    )
    assert not res.woke and forge.dispatched == []
    assert "max-depth" in res.suppressed
    assert _meta(res.handoff)["wake_depth"] == "3"  # persisted, even though wake refused
