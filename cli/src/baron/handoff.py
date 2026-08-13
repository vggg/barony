"""M3 — ``baron handoff create|close|list``: the _handoff/ lifecycle as a mechanism.

Lifecycle (archive-not-delete, ADR-003): open -> done -> archived under
``_handoff/archive/YYYY/`` via ``git mv`` so history is preserved. Handoffs are
never deleted. Closing is a textual edit (status flip + ``closed:`` date +
optional blockquote note) so prose a persona wrote is never reflowed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import clock
from .frontmatter import as_date, split_frontmatter
from .gitutil import git, is_git_repo


class HandoffError(RuntimeError):
    """A handoff operation could not be completed."""


PRIORITIES = ("low", "medium", "high")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "handoff"


@dataclass
class Handoff:
    path: Path
    status: str
    for_: str
    from_: str
    created: str
    priority: str
    age_days: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "file": self.path.name,
            "status": self.status,
            "for": self.for_,
            "from": self.from_,
            "created": self.created,
            "priority": self.priority,
            "age_days": self.age_days,
        }


def create(
    collab: Path,
    *,
    for_: str,
    from_: str,
    title: str,
    priority: str = "medium",
    body: str | None = None,
    commit: bool = True,
    extra: dict[str, str] | None = None,
) -> Path:
    handoff_dir = collab / "_handoff"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    date = clock.today().isoformat()
    path = handoff_dir / f"{date}-{slugify(title)}.md"
    if path.exists():
        raise HandoffError(f"{path} already exists — pick a different title")
    content = (
        "---\n"
        f"created: {date}\n"
        "status: open\n"
        f"for: {for_}\n"
        f"from: {from_}\n"
        f"priority: {priority}\n"
        + "".join(f"{k}: {v}\n" for k, v in (extra or {}).items())
        + "---\n"
        "\n"
        f"# {title}\n"
    )
    # A --body-file body becomes the handoff body under the frontmatter/title,
    # so a non-stub handoff no longer needs the --no-commit + manual-append dance.
    if body is not None and body.strip():
        content += "\n" + body.rstrip("\n") + "\n"
    path.write_text(content, encoding="utf-8")
    if commit and is_git_repo(collab):
        rel = path.relative_to(collab).as_posix()
        git(collab, "add", "--", rel)
        git(collab, "commit", "-m", f"{from_.lower()}: handoff | open {path.name}", "--", rel)
    return path


_STATUS_OPEN_RE = re.compile(r"^status:\s*open\s*$", re.MULTILINE)


def close(
    collab: Path,
    file: Path,
    *,
    note: str | None = None,
    prefix: str = "baron:",
    commit: bool = True,
) -> Path:
    """Flip an open handoff to done and git-mv it to _handoff/archive/YYYY/.

    ``prefix`` is the commit-message prefix (default ``baron:``); pass the
    closing persona's commit prefix so the close is attributed to whoever closed
    it, matching the discipline the templates preach for other commits.
    """
    path = file if file.is_absolute() else (Path.cwd() / file)
    if not path.is_file():
        candidate = collab / "_handoff" / file.name
        if candidate.is_file():
            path = candidate
        else:
            raise HandoffError(f"handoff not found: {file}")
    text = path.read_text(encoding="utf-8")
    meta, _ = split_frontmatter(text)
    if meta is None:
        raise HandoffError(f"{path.name}: no parseable frontmatter")
    if not _STATUS_OPEN_RE.search(text):
        raise HandoffError(f"{path.name}: status is not `open` (already closed?)")

    date = clock.today().isoformat()
    text = _STATUS_OPEN_RE.sub(f"status: done\nclosed: {date}", text, count=1)
    if note:
        # Insert the note as a blockquote right after the frontmatter block.
        parts = text.split("---\n", 2)
        if len(parts) == 3:
            text = f"{parts[0]}---\n{parts[1]}---\n\n> **Closed {date}.** {note}\n{parts[2]}"
        else:
            text += f"\n> **Closed {date}.** {note}\n"
    path.write_text(text, encoding="utf-8")

    created = as_date(meta.get("created"))
    year = str(created.year if created else clock.today().year)
    archive_dir = collab / "_handoff" / "archive" / year
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / path.name

    if commit and is_git_repo(collab):
        rel_src = path.relative_to(collab).as_posix()
        rel_dst = dest.relative_to(collab).as_posix()
        git(collab, "add", "--", rel_src)  # ensure tracked (covers never-committed files)
        git(collab, "mv", rel_src, rel_dst)  # preserve history
        git(collab, "commit", "-m", f"{prefix} handoff | close {path.name}")
    else:
        path.rename(dest)
    return dest


def iter_handoffs(collab: Path, *, include_archived: bool = False) -> list[Handoff]:
    handoff_dir = collab / "_handoff"
    if not handoff_dir.is_dir():
        return []
    paths = sorted(p for p in handoff_dir.glob("*.md") if p.name.upper() != "README.MD")
    if include_archived:
        paths += sorted(handoff_dir.glob("archive/*/*.md"))
    today = clock.today()
    out: list[Handoff] = []
    for path in paths:
        meta, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        meta = meta or {}
        created = as_date(meta.get("created"))
        out.append(
            Handoff(
                path=path,
                status=str(meta.get("status", "?")),
                for_=str(meta.get("for", "?")),
                from_=str(meta.get("from", "?")),
                created=created.isoformat() if created else "?",
                priority=str(meta.get("priority", "?")),
                age_days=(today - created).days if created else None,
            )
        )
    return out
