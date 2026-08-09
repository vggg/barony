"""P3.4 (partial) — ``baron export``: the governed corpus as citable records.

AGENT-TASKS.md 3.4 asks for a pluggable knowledge substrate whose every
retrieval result carries "an authoritative source ID/version (path+commit SHA
for Git)". This module ships **only the producer side of that requirement**: a
deterministic walk of the four governed corpora a collab repo already keeps —
ADRs, decisions, findings, handoffs — emitted as flat records that each name
the file and the exact commit whose content was read.

**There is no knowledge backend here, and deliberately no plugin seam** — no
entry-point group, no sink protocol, and no vendor named anywhere in this
package. See `docs/adr/ADR-015-baron-export.md` §4: 3.4 is gated on 3.3 (the
governed-memory evaluation harness), which does not exist, and a published
entry-point group with no consumer is public API that cannot be retracted. The
export stands on its own — `baron export --json | jq` is useful today with no
backend at all — and is the input either answer to the open owner decision
would consume. The vendor evaluation, and the reason no adapter ships, live in
the ADR; `cli/tests/test_export.py` asserts that this package stays free of it.

The citation contract (ADR-015 §3): a record is emitted only when its source
file is **tracked and unmodified**, so ``git show <commit_sha>:<path>`` returns
byte-for-byte the text that was parsed. Sources failing that test are skipped
and reported by name — never silently dropped, never emitted with a SHA that
does not match their content. ``--allow-dirty`` relaxes the gate for local
iteration and marks every affected record ``meta.dirty: true``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import clock
from .frontmatter import split_frontmatter
from .gitutil import git, is_git_repo
from .handoff import iter_handoffs
from .ledger import KINDS


class ExportError(RuntimeError):
    """The corpus could not be exported."""


#: Wire-format identifier. The eight core record fields (id, kind, title, path,
#: commit_sha, status, body, links) are the frozen part of the contract; `meta`
#: is the open, kind-specific bag. Adding a core field is a version bump;
#: adding a `meta` key is not. See ADR-015 §5.
FORMAT = "baron.export/v1"

#: Emission order. Stable, and independent of filesystem iteration order.
KIND_ORDER = ("adr", "decision", "finding", "handoff")

#: Default location of the ADR corpus, relative to the collab repo root.
ADR_DIR = "docs/adr"


# --- record ----------------------------------------------------------------------------


@dataclass
class Record:
    """One governed artifact. Primary key is ``(kind, id)``."""

    id: str
    kind: str
    title: str
    # Repo-root-relative, posix — NOT collab-relative, so that
    # `git show <commit_sha>:<path>` is a verbatim, working citation even when
    # the collab repo is a subdirectory. The envelope's `repo_prefix` recovers
    # the collab-relative form. In every documented Barony layout (collab repo
    # == git root) the two are identical.
    path: str
    commit_sha: str
    status: str | None
    body: str
    links: list[dict[str, str]] = field(default_factory=list)
    meta: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "path": self.path,
            "commit_sha": self.commit_sha,
            "status": self.status,
            "body": self.body,
            "links": self.links,
            "meta": self.meta,
        }


@dataclass
class Skipped:
    """A source file excluded from the export, with the reason."""

    path: str
    reason: str  # "uncommitted" | "modified"
    records: int

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "reason": self.reason, "records": self.records}


@dataclass
class Export:
    generated: str
    collab: str
    repo_prefix: str
    head: str
    records: list[Record]
    skipped: list[Skipped]
    duplicates: list[str]

    def to_dict(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for r in self.records:
            counts[r.kind] = counts.get(r.kind, 0) + 1
        return {
            "format": FORMAT,
            "generated": self.generated,
            "collab": self.collab,
            "repo_prefix": self.repo_prefix,
            "head": self.head,
            "records": [r.to_dict() for r in self.records],
            "skipped": [s.to_dict() for s in self.skipped],
            "duplicates": self.duplicates,
            "summary": {
                "records": len(self.records),
                "by_kind": {k: counts.get(k, 0) for k in KIND_ORDER if counts.get(k)},
                "skipped_sources": len(self.skipped),
            },
        }


# --- parsing ---------------------------------------------------------------------------

# House style is `### F40 — title (2026-07-13, Terrence)`, but real ledgers carry
# hyphen/en-dash separators and entries with no trailing (date, author) at all
# (badminton-analyzer's D48+ run) — both parse, neither is required.
_ENTRY_HEAD_RE = re.compile(r"^###\s+(?P<id>[A-Z]\d+)\s*(?:[—–:-]\s*)?(?P<rest>.*)$")
_ENTRY_TAIL_RE = re.compile(
    r"^(?P<title>.*?)\s*\((?P<date>\d{4}-\d{2}-\d{2})\s*,\s*(?P<author>[^)]*)\)\s*$"
)
_TABLE_ROW_RE = re.compile(r"^\|\s*(?P<id>[A-Z]\d+)\s*\|(?P<rest>.*)$")
_SECTION_RE = re.compile(r"^#{1,3}\s")
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_ADR_FILE_RE = re.compile(r"^(ADR-\d+)")
_ADR_STATUS_ROW_RE = re.compile(r"^\|\s*\*{0,2}Status\*{0,2}\s*\|\s*(.+?)\s*\|", re.MULTILINE)

_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*<?([^)>\s]+)>?[^)]*\)")
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")
_REF_RE = re.compile(r"\b(?:ADR-\d+|[FD]\d+)\b")
# Bare URLs, i.e. not already captured as a markdown-link target: the lookbehind
# skips `](http…` and `<http…`. Trailing sentence punctuation is stripped.
_BARE_URL_RE = re.compile(r"(?<![(<\w])(https?://[^\s<>)\]]+)")


def _scalar(value: object) -> object:
    """Coerce a frontmatter value into something JSON-stable and re-runnable."""
    if isinstance(value, datetime):  # must precede date — datetime subclasses it
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_scalar(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _scalar(v) for k, v in value.items()}
    return str(value)


def extract_links(text: str, *, own_id: str | None = None) -> list[dict[str, str]]:
    """Outgoing references in ``text``, deduped and sorted.

    Four types: ``url`` (http/https), ``path`` (a relative markdown link
    target), ``wikilink``, and ``ref`` (a literal in-project record token —
    ``F40``, ``D57``, ``ADR-009``). Ref targets are **literal, not resolved**:
    a project writing ``ADR-0007`` and one writing ``ADR-7`` produce different
    tokens, and reconciling them is the consumer's job (ADR-015 §5). Ref
    matching is a regex over prose, so it is recall-biased — an occasional
    false positive is the cost of catching cross-references nobody linked.
    """
    found: set[tuple[str, str]] = set()
    for target in _MD_LINK_RE.findall(text):
        if target.startswith("#"):
            continue
        kind = "url" if target.startswith(("http://", "https://")) else "path"
        found.add((kind, target))
    for target in _BARE_URL_RE.findall(text):
        found.add(("url", target.rstrip(".,;:!?")))
    for target in _WIKILINK_RE.findall(text):
        found.add(("wikilink", target.strip()))
    for token in _REF_RE.findall(text):
        if own_id is not None and token == own_id:
            continue
        found.add(("ref", token))
    return [{"type": t, "target": v} for t, v in sorted(found)]


def parse_ledger(text: str, prefix: str) -> list[tuple[str, str, str, dict[str, object]]]:
    """Parse one ledger index into ``(id, title, body, meta)`` tuples.

    Two entry forms coexist in real ledgers and both are read: full ``### F40 —
    …`` heading blocks (body = everything up to the next heading) and bare
    ``| F40 | title |`` index rows (body = ""). A heading block always wins over
    a row for the same ID — migrated ledgers list an ID in the summary table
    *and* carry its full text below.
    """
    lines = text.splitlines()
    headings: dict[str, tuple[str, str, dict[str, object]]] = {}
    rows: dict[str, tuple[str, str, dict[str, object]]] = {}
    order: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        head = _ENTRY_HEAD_RE.match(line)
        if head and head.group("id").startswith(prefix):
            entry_id = head.group("id")
            rest = head.group("rest").strip()
            meta: dict[str, object] = {"form": "heading"}
            tail = _ENTRY_TAIL_RE.match(rest)
            if tail:
                title = tail.group("title").strip()
                meta["date"] = tail.group("date")
                meta["author"] = tail.group("author").strip()
            else:
                title = rest
            body_lines: list[str] = []
            i += 1
            while i < len(lines) and not _SECTION_RE.match(lines[i]):
                body_lines.append(lines[i])
                i += 1
            if entry_id not in headings:
                headings[entry_id] = (title, "\n".join(body_lines).strip(), meta)
                order.append(entry_id)
            continue
        row = _TABLE_ROW_RE.match(line)
        if row and row.group("id").startswith(prefix):
            entry_id = row.group("id")
            cells = [c.strip() for c in row.group("rest").split("|")]
            title = cells[0] if cells else ""
            if entry_id not in rows:
                rows[entry_id] = (title, "", {"form": "table-row"})
                if entry_id not in headings:
                    order.append(entry_id)
        i += 1

    out: list[tuple[str, str, str, dict[str, object]]] = []
    seen: set[str] = set()
    for entry_id in order:
        if entry_id in seen:
            continue
        seen.add(entry_id)
        title, body, meta = headings.get(entry_id) or rows[entry_id]
        out.append((entry_id, title, body, meta))
    return sorted(out, key=lambda t: _sort_key(t[0]))


def _sort_key(entry_id: str) -> tuple[str, int, str]:
    """Natural order: F9 before F10, unnumbered ids fall back to text."""
    m = re.match(r"^([A-Za-z-]*?)-?(\d+)$", entry_id)
    if m:
        return (m.group(1), int(m.group(2)), "")
    return (entry_id, 0, entry_id)


def _adr_status(meta: dict[str, object], body: str) -> str | None:
    """Frontmatter `status:` wins; fall back to the `| **Status** | … |` row."""
    value = meta.get("status")
    if isinstance(value, str) and value.strip():
        return value.strip()
    row = _ADR_STATUS_ROW_RE.search(body)
    if row:
        return row.group(1).strip()
    return None


def _title_from_body(body: str, fallback: str) -> str:
    m = _H1_RE.search(body)
    return m.group(1).strip() if m else fallback


def _related_links(meta: dict[str, object]) -> list[dict[str, str]]:
    related = meta.get("related")
    if not isinstance(related, list):
        return []
    out: list[dict[str, str]] = []
    for item in related:
        text = str(item).strip()
        wiki = _WIKILINK_RE.search(text)
        if wiki:
            out.append({"type": "wikilink", "target": wiki.group(1).strip()})
        elif text:
            out.append({"type": "path", "target": text})
    return out


def _merge_links(*groups: list[dict[str, str]]) -> list[dict[str, str]]:
    found = {(g["type"], g["target"]) for group in groups for g in group}
    return [{"type": t, "target": v} for t, v in sorted(found)]


# --- git provenance --------------------------------------------------------------------


def _head_sha(root: Path) -> str:
    proc = git(root, "rev-parse", "HEAD", check=False)
    if proc.returncode != 0:
        raise ExportError(
            f"{root} has no commits yet — every exported record must cite a commit SHA"
        )
    return proc.stdout.strip()


def _repo_prefix(root: Path) -> str:
    proc = git(root, "rev-parse", "--show-prefix", check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _source_state(root: Path, rels: list[str], prefix: str) -> dict[str, str]:
    """Map each collab-relative source path to "clean" | "modified" | "uncommitted".

    `git status --porcelain` reports paths relative to the repository TOP LEVEL
    even under `-C <subdir>`, while `git ls-files` reports them relative to the
    cwd — the prefix dance below reconciles the two.
    """
    if not rels:
        return {}
    tracked_proc = git(root, "ls-files", "-z", "--", *rels, check=False)
    tracked = {p for p in tracked_proc.stdout.split("\0") if p}
    status_proc = git(
        root, "status", "--porcelain", "--untracked-files=all", "--", *rels, check=False
    )
    dirty: set[str] = set()
    for line in status_proc.stdout.splitlines():
        if len(line) < 4:
            continue
        entry = line[3:].strip()
        if " -> " in entry:  # rename/copy: the destination is what we read
            entry = entry.split(" -> ", 1)[1]
        dirty.add(entry.strip('"'))
    out: dict[str, str] = {}
    for rel in rels:
        top_rel = f"{prefix}{rel}"
        if rel not in tracked:
            out[rel] = "uncommitted"
        elif top_rel in dirty:
            out[rel] = "modified"
        else:
            out[rel] = "clean"
    return out


def _commit_sha(root: Path, rel: str, cache: dict[str, str]) -> str:
    """SHA of the newest commit touching ``rel`` — the version whose bytes we read."""
    if rel in cache:
        return cache[rel]
    proc = git(root, "log", "-1", "--format=%H", "--", rel, check=False)
    sha = proc.stdout.strip()
    cache[rel] = sha
    return sha


# --- collection ------------------------------------------------------------------------


def _candidates(
    root: Path, kinds: set[str], include_archived: bool, adr_dir: str
) -> list[tuple[str, Record]]:
    """(collab-relative source path, record) pairs.

    ``Record.path`` is set to the collab-relative path here and rewritten to the
    repo-root-relative form in :func:`collect`; the collab-relative form is what
    git pathspecs need (they resolve against the cwd baron passes to ``git -C``).
    """
    out: list[tuple[str, Record]] = []

    if "adr" in kinds:
        adr_root = root / adr_dir
        if adr_root.is_dir():
            for path in sorted(adr_root.glob("*.md")):
                m = _ADR_FILE_RE.match(path.name)
                if not m:
                    continue
                rel = path.relative_to(root).as_posix()
                meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
                meta = {str(k): _scalar(v) for k, v in (meta or {}).items()}
                record_meta = {k: v for k, v in meta.items() if k != "related"}
                out.append(
                    (
                        rel,
                        Record(
                            id=m.group(1),
                            kind="adr",
                            title=_title_from_body(body, path.stem),
                            path=rel,
                            commit_sha="",
                            status=_adr_status(meta, body),
                            body=body.strip(),
                            links=_merge_links(
                                extract_links(body, own_id=m.group(1)),
                                _related_links(meta),
                            ),
                            meta=record_meta,
                        ),
                    )
                )

    for kind_name in ("finding", "decision"):
        if kind_name not in kinds:
            continue
        kind = KINDS[kind_name]
        index_path = root / kind.index
        if not index_path.is_file():
            continue
        rel = kind.index
        text = index_path.read_text(encoding="utf-8")
        for entry_id, title, body, meta in parse_ledger(text, kind.prefix):
            out.append(
                (
                    rel,
                    Record(
                        id=entry_id,
                        kind=kind_name,
                        title=title,
                        path=rel,
                        commit_sha="",
                        # Ledger entries carry no lifecycle field in the canon —
                        # supersession is prose. Inventing a status here would be
                        # exactly the enforced-vs-instructed overclaim ADR-002 bans.
                        status=None,
                        body=body,
                        links=extract_links(f"{title}\n{body}", own_id=entry_id),
                        meta=meta,
                    ),
                )
            )

    if "handoff" in kinds:
        for h in iter_handoffs(root, include_archived=include_archived):
            rel = h.path.relative_to(root).as_posix()
            meta, body = split_frontmatter(h.path.read_text(encoding="utf-8"))
            meta = {str(k): _scalar(v) for k, v in (meta or {}).items()}
            out.append(
                (
                    rel,
                    Record(
                        id=h.path.stem,
                        kind="handoff",
                        title=_title_from_body(body, h.path.stem),
                        path=rel,
                        commit_sha="",
                        status=h.status,
                        body=body.strip(),
                        links=_merge_links(
                            extract_links(body), _related_links(meta)
                        ),
                        # age_days is deliberately dropped: it is a function of
                        # today, and records must be byte-stable across runs.
                        meta={
                            "for": h.for_,
                            "from": h.from_,
                            "created": h.created,
                            "priority": h.priority,
                            "archived": "archive/" in rel,
                        },
                    ),
                )
            )

    return out


def collect(
    collab: Path,
    *,
    kinds: set[str] | None = None,
    include_archived: bool = True,
    allow_dirty: bool = False,
    adr_dir: str = ADR_DIR,
) -> Export:
    """Walk the governed corpora and return citable records.

    Raises :class:`ExportError` when ``collab`` is not a git repository or has
    no commits — provenance is not optional, so there is no degraded mode.
    """
    root = collab.resolve()
    if not root.is_dir():
        raise ExportError(f"{root} does not exist")
    if not is_git_repo(root):
        raise ExportError(
            f"{root} is not a git repository — `baron export` cites commit SHAs, "
            "which requires git history"
        )
    selected = set(kinds) if kinds else set(KIND_ORDER)
    unknown = selected - set(KIND_ORDER)
    if unknown:
        raise ExportError(
            f"unknown kind(s): {', '.join(sorted(unknown))} — known: {', '.join(KIND_ORDER)}"
        )

    head = _head_sha(root)
    prefix = _repo_prefix(root)
    candidates = _candidates(root, selected, include_archived, adr_dir)

    rels = sorted({rel for rel, _ in candidates})
    state = _source_state(root, rels, prefix)
    sha_cache: dict[str, str] = {}

    records: list[Record] = []
    skipped_counts: dict[tuple[str, str], int] = {}
    for rel, record in candidates:
        condition = state.get(rel, "uncommitted")
        sha = "" if condition == "uncommitted" else _commit_sha(root, rel, sha_cache)
        if not sha:
            # Belt and braces: a file reported clean but with no commit touching
            # it is not citable, whatever the reason.
            condition = "uncommitted"
        if condition != "clean" and not allow_dirty:
            key = (f"{prefix}{rel}", condition)
            skipped_counts[key] = skipped_counts.get(key, 0) + 1
            continue
        record.path = f"{prefix}{rel}"
        record.commit_sha = sha
        if condition != "clean":
            record.meta = {**record.meta, "dirty": condition}
        records.append(record)

    duplicates: list[str] = []
    seen: set[tuple[str, str]] = set()
    deduped: list[Record] = []
    for record in records:
        key = (record.kind, record.id)
        if key in seen:
            duplicates.append(f"{record.kind}:{record.id}")
            continue
        seen.add(key)
        deduped.append(record)

    deduped.sort(key=lambda r: (KIND_ORDER.index(r.kind), _sort_key(r.id)))
    skipped = [
        Skipped(path=rel, reason=reason, records=count)
        for (rel, reason), count in sorted(skipped_counts.items())
    ]
    return Export(
        generated=clock.today().isoformat(),
        collab=root.as_posix(),
        repo_prefix=prefix,
        head=head,
        records=deduped,
        skipped=skipped,
        duplicates=duplicates,
    )


def render_table(export: Export) -> str:
    """Human surface — one line per record, then the provenance caveats."""
    lines: list[str] = []
    for r in export.records:
        status = r.status or "-"
        title = r.title if len(r.title) <= 72 else r.title[:69] + "..."
        lines.append(f"{r.kind:8s} {r.id:14s} {status:12s} {r.commit_sha[:8]}  {title}")
    if not lines:
        lines.append("no records")
    tally: dict[str, int] = {}
    for r in export.records:
        tally[r.kind] = tally.get(r.kind, 0) + 1
    counts = ", ".join(f"{k}={tally[k]}" for k in KIND_ORDER if k in tally)
    lines.append("")
    lines.append(
        f"{len(export.records)} record(s) at {export.head[:8]}"
        + (f" ({counts})" if counts else "")
    )
    for s in export.skipped:
        lines.append(f"warning skipped {s.path}: {s.reason} ({s.records} record(s) not citable)")
    for dup in export.duplicates:
        lines.append(f"warning duplicate record id {dup} — first occurrence kept")
    return "\n".join(lines)
