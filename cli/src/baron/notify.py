"""``baron notify`` (ADR-010) — wake an idle persona without owning the loop.

The command has exactly one novelty over ``baron handoff create``: after
delivering an ordinary ``_handoff/`` message it can fire a forge
``repository_dispatch`` so a project-owned workflow spawns the addressed persona.

Load-bearing ordering (ADR-010 §3): **deliver, push, then wake.** A wake without a
published message is a runner spawned to read something that is not there, so:

1. compose + commit the handoff (via ``handoff.create``);
2. push it to the **default branch** — ``repository_dispatch`` only runs workflows
   from the default branch, so notify refuses to wake from any other branch;
3. fire the dispatch.

Delivery is independent of wake in that direction only: if the dispatch cannot fire
(no forge, no ``dispatch_event`` support, not on the default branch, over the depth
cap, or the ``from`` persona is not in ``manifest.notify.wake_allowed``) the message
is still delivered and the command reports *why* the wake was suppressed. The
converse never holds.

Loop safety (ADR-010 §5.1): the hop count lives in the substrate, not a payload.
``--in-reply-to`` reads the parent handoff's ``wake_depth`` and **persists**
``parent + 1`` into the new one, copying ``wake_origin`` unchanged; wakes past
``--max-depth`` (default 2) are refused. The workflow gate reads the same committed
frontmatter — see ``assets`` template ``baron-notify.yml``.

Monorepo routing (ADR-025 §7 Q2): when the collab path is a project subdir of a
coordination monorepo, the git side of all of the above — default branch, current
branch, push — is the **root's**, because that is the git repo; and the payload gains
``project`` so the root's gate can ``cd`` into the right subdir before resolving the
handoff and the manifest. Everything else is unchanged, deliberately: the handoff is
still read and written in the project, and the wake is still authorized against that
project's committed evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import gitutil, handoff
from .forge.base import supports
from .frontmatter import split_frontmatter

DISPATCH_EVENT_TYPE = "baron-notify"
DEFAULT_MAX_DEPTH = 2


class NotifyError(RuntimeError):
    """A notify operation could not be completed."""


@dataclass
class NotifyResult:
    handoff: Path
    delivered: bool
    woke: bool
    wake_depth: int
    wake_origin: str
    suppressed: str | None  # human-readable reason a wake did NOT fire, or None
    project: str | None = None  # monorepo subdir this wake routes to (ADR-025), if any


def _read_parent(collab: Path, stem: str) -> dict[str, str]:
    """Frontmatter of an existing handoff identified by its stem (no .md)."""
    path = collab / "_handoff" / f"{stem}.md"
    if not path.is_file():
        raise NotifyError(f"--in-reply-to: no handoff {path.name} under _handoff/")
    meta, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    if meta is None:
        raise NotifyError(f"{path.name}: no parseable frontmatter")
    return {str(k): str(v) for k, v in meta.items()}


def _wake_allowed(collab: Path, persona_from: str) -> bool:
    """CLI-side, fail-closed mirror of the workflow gate (ADR-010 §5.5).

    Absent ``notify.wake_allowed`` -> nobody may wake. This is NOT security (the
    real spend gate is the workflow, against committed evidence); it only makes the
    honest case fail before any Actions spend.
    """
    manifest = collab / "manifest.yaml"
    if not manifest.is_file():
        return False
    try:
        import yaml

        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    allowed = (data.get("notify") or {}).get("wake_allowed") or []
    return isinstance(allowed, list) and persona_from in allowed


def notify(
    collab: Path,
    *,
    persona: str,
    title: str,
    from_: str,
    body: str | None = None,
    in_reply_to: str | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    wake: bool = True,
    forge: object | None = None,
    remote: str = "origin",
) -> NotifyResult:
    # --- 0. depth / origin from the substrate (ADR-010 §5.1) ---
    if in_reply_to:
        parent = _read_parent(collab, in_reply_to)
        try:
            depth = int(parent.get("wake_depth", "0")) + 1
        except ValueError:
            depth = 1
        origin = parent.get("wake_origin") or parent.get("from") or from_
    else:
        depth = 0
        origin = from_

    # --- 1. deliver (compose + commit; never pushed by handoff.create) ---
    extra = {"wake_depth": str(depth), "wake_origin": origin}
    if in_reply_to:
        extra["in_reply_to"] = in_reply_to
    path = handoff.create(
        collab, for_=persona, from_=from_, title=title,
        body=body, commit=True, extra=extra,
    )
    stem = path.stem

    # --- 1b. which git repo, and which project? (ADR-025) ---
    #
    # In a monorepo the collab dir is a project SUBDIR: the branch/push checks below
    # and the dispatch itself belong to the root, which is the actual git repo.
    from . import monorepo as monorepo_mod

    located = monorepo_mod.project_of(collab)
    project = located[1].dir if located else None
    git_root = located[0] if located else collab

    result = NotifyResult(
        handoff=path, delivered=True, woke=False,
        wake_depth=depth, wake_origin=origin, suppressed=None, project=project,
    )

    # --- 2. decide whether a wake may fire, collecting the FIRST blocking reason ---
    if not wake:
        result.suppressed = "--no-wake"
        return result
    if depth > max_depth:
        result.suppressed = f"wake_depth {depth} exceeds --max-depth {max_depth}"
        return result
    if forge is None or not supports(forge, "dispatch_event"):
        result.suppressed = "forge cannot dispatch_event (no forge / gh / plugin support)"
        return result
    if not gitutil.is_git_repo(git_root) or not gitutil.has_remote(git_root, remote):
        result.suppressed = f"no git repo or no '{remote}' remote"
        return result
    default = gitutil.default_branch(git_root, remote)
    current = gitutil.current_branch(git_root)
    if default is None:
        result.suppressed = "cannot determine the remote default branch"
        return result
    if current != default:
        result.suppressed = (
            f"not on the default branch (on '{current}', default is '{default}'); "
            "repository_dispatch only runs workflows from the default branch"
        )
        return result
    if not _wake_allowed(collab, from_):
        result.suppressed = (
            f"'{from_}' is not in manifest.notify.wake_allowed (fail-closed)"
        )
        return result

    # --- 3. push BEFORE dispatch; a rejection aborts (no force, no retry) ---
    push = gitutil.git(git_root, "push", remote, current, check=False)
    if push.returncode != 0:
        result.suppressed = (
            "push to the default branch was rejected — handoff is committed "
            f"locally, wake not fired: {push.stderr.strip() or push.stdout.strip()}"
        )
        return result

    # --- 4. wake ---
    payload = {
        "persona": persona,
        "handoff": stem,
        "from": from_,
        "wake_depth": depth,
    }
    if project is not None:
        # Routing only — the gate re-derives authorization from the committed
        # handoff inside this subdir; the payload never grants anything.
        payload["project"] = project
    try:
        forge.dispatch_event(git_root, event_type=DISPATCH_EVENT_TYPE, payload=payload)  # type: ignore[attr-defined]
    except Exception as exc:  # forge-specific errors degrade, never crash
        result.suppressed = f"dispatch failed (message delivered): {exc}"
        return result
    result.woke = True
    return result
