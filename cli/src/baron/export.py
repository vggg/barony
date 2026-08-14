"""P3.4 (partial) — ``baron export``: the governed corpus as citable records.

AGENT-TASKS.md 3.4 asks for a pluggable knowledge substrate whose every
retrieval result carries "an authoritative source ID/version (path+commit SHA
for Git)". This module ships **only the producer side of that requirement**: a
deterministic walk of the governed corpora a collab repo already keeps — ADRs,
decisions, findings, handoffs, plus curated status and research notes — emitted
as flat records that each name the file and the exact commit whose content was
read.

**Why the corpus is six kinds and not four (ADR-032).** P3.3's harness
(ADR-031) measured the lexical baseline over this export and found the miss was
**coverage, not ranking**: on the flagship query the baseline already retrieved
the gold record at rank 1, and its only failure was a research note in ``wiki/``
that this walker never visited. Widening what gets walked is therefore the move
that changes the numbers; ``status`` and ``note`` close 3.4's own corpus list
("ADRs/decisions/findings/handoffs/curated status"), which ADR-015 §7 recorded
as a deliberate deferral rather than a decision.

**There is no knowledge backend here, and deliberately no plugin seam** — no
entry-point group, no sink protocol, and no vendor named anywhere in this
package. See `docs/adr/ADR-015-baron-export.md` §4: 3.4 is gated on 3.3 (the
governed-memory evaluation harness — shipped 2026-08-14 as ``baron memeval``,
ADR-031, which consumes this walk and has not yet been answered by a backend),
and a published entry-point group with no consumer is public API that cannot be
retracted. The
export stands on its own — `baron export --json | jq` is useful today with no
backend at all — and is the input either answer to the open owner decision
would consume. The vendor evaluation, and the reason no adapter ships, live in
the ADR; `cli/tests/test_export.py` asserts that this package stays free of it.

The citation contract (ADR-015 §3): a record is emitted only when its source
file is **tracked and unmodified**, so ``git show <commit_sha>:<path>`` returns
byte-for-byte the text that was parsed. Sources failing that test are skipped
and reported by name — never silently dropped, never emitted with a SHA that
does not match their content. ``--allow-dirty`` relaxes the gate for *modified*
sources only, stamping ``meta.dirty: "modified"`` on each affected record;
untracked sources stay skipped under every flag, because ``commit_sha`` is
always non-empty and a file with no commit has nothing to cite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

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
KIND_ORDER = ("adr", "decision", "finding", "handoff", "status", "note")

#: The four ledger corpora — kept as a named set so a caller (or a consumer
#: pinning the old behaviour) can ask for exactly them.
LEDGER_KINDS = ("adr", "decision", "finding", "handoff")

#: What a caller that names no kinds gets. ADR-032 §3.1 (amended): the four
#: ledgers, i.e. the pre-ADR-032 set. `status` and `note` are shipped, walked by
#: the same code path and covered by the same citation gate, but a widened corpus
#: is **opt-in** (`--wide`, or an explicit `--kind`) rather than the default.
#: The reason is measured, not stylistic: a default widening silently changes the
#: record set under every existing consumer, and the estate has one — `baron
#: memeval` (ADR-031), whose pinned numbers a six-kind default moves without
#: anyone asking it to. See ADR-032 §3.1 and §4.3.
DEFAULT_KINDS = LEDGER_KINDS

#: Default location of the ADR corpus, relative to the collab repo root.
ADR_DIR = "docs/adr"

#: Default trees walked for the ``note`` kind — curated, human-written markdown
#: that is not one of the four ledgers. Deliberately an explicit include-list and
#: not "every .md in the repo": `note` means *curated*, and a recursive walk of
#: the whole collab repo would sweep in agent templates, workspace scaffolding
#: and the emit-time fixtures, none of which anyone wrote to be retrieved.
NOTE_DIRS = ("wiki", "docs/notes")

#: Files exported as the ``status`` kind — 3.4's "curated status". Both spellings
#: exist in the wild: `wiki/status.md` is what the collab-repo template emits,
#: `STATUS.md` at the collab root is what a repo that predates the template keeps.
STATUS_FILES = ("wiki/status.md", "STATUS.md")


# --- record ----------------------------------------------------------------------------


@dataclass
class Record:
    """One governed artifact. Primary key is ``(project, kind, id)``.

    ``project`` joined the key at ADR-032. In a coordination monorepo two
    projects legitimately both hold an ``ADR-001``; keying on ``(kind, id)``
    alone would have reported the second one as a duplicate and dropped it —
    trading the silent zero this change fixes for a silent halving.
    """

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
    #: The project this record was governed by — the manifest's `project.name`,
    #: or None when the collab repo has no readable manifest. Present in BOTH
    #: layouts (ADR-032 §3.2): a consumer must not have to know which topology
    #: produced a payload to know which project a record belongs to.
    project: str | None = None

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
            "project": self.project,
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
class ProjectExport:
    """Per-project provenance for one leg of a portfolio export (ADR-032 §3.3)."""

    dir: str  # subdir under the monorepo root
    name: str  # project name (identity domain / manifest project.name)
    collab: str  # absolute path walked
    repo_prefix: str  # what was prepended to make `path` repo-root-relative
    records: int
    skipped_sources: int

    def to_dict(self) -> dict[str, object]:
        return {
            "dir": self.dir,
            "name": self.name,
            "collab": self.collab,
            "repo_prefix": self.repo_prefix,
            "records": self.records,
            "skipped_sources": self.skipped_sources,
        }


@dataclass
class Export:
    generated: str
    collab: str
    repo_prefix: str
    head: str
    records: list[Record]
    skipped: list[Skipped]
    duplicates: list[str]
    #: "single" (one collab repo) or "monorepo" (ADR-025 coordination monorepo,
    #: aggregated across the registry). The record shape is identical in both —
    #: that is the point, so `--json | jq '.records[]'` does not fork per layout.
    layout: str = "single"
    #: Single layout: the one project's name (None when no readable manifest).
    project: str | None = None
    #: Monorepo layout: one entry per registered project actually walked.
    projects: list[ProjectExport] = field(default_factory=list)
    #: Monorepo layout: subdirs holding a manifest.yaml the marker does not list.
    #: Reported, never silently included — same posture as `baron status`.
    unregistered: list[str] = field(default_factory=list)
    #: Monorepo layout: registered projects that could not be walked, and why.
    unreadable: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for r in self.records:
            counts[r.kind] = counts.get(r.kind, 0) + 1
        return {
            "format": FORMAT,
            "generated": self.generated,
            "layout": self.layout,
            "collab": self.collab,
            "repo_prefix": self.repo_prefix,
            "project": self.project,
            "projects": [p.to_dict() for p in self.projects],
            "unregistered": self.unregistered,
            "unreadable": self.unreadable,
            "head": self.head,
            "records": [r.to_dict() for r in self.records],
            "skipped": [s.to_dict() for s in self.skipped],
            "duplicates": self.duplicates,
            "summary": {
                "records": len(self.records),
                "by_kind": {k: counts.get(k, 0) for k in KIND_ORDER if counts.get(k)},
                "by_project": {
                    p.name: p.records for p in self.projects
                } if self.projects else {},
                "projects": len(self.projects),
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


def _parse_porcelain_z(payload: str) -> set[str]:
    """Paths reported dirty by ``git status --porcelain -z``.

    ``-z`` is not a convenience here, it is the correctness requirement. Without
    it, git C-quotes any path containing a non-ASCII byte, a space, a quote or a
    control character — ``"_handoff/2026-01-02-caf\\303\\251.md"`` — while
    ``git ls-files -z`` returns the raw UTF-8 name. Undoing that quoting by hand
    means reimplementing git's escaping; getting it wrong makes the two names
    compare unequal, which silently marks a *modified* file **clean** and emits
    it with a SHA that does not match its bytes. The gate would fail open on
    exactly the files nobody tests with. ``-z`` emits raw, unquoted paths and
    removes the problem at the source (``-c core.quotePath=false`` fixes only
    the non-ASCII half, leaving spaces and quotes still escaped).

    The other ``-z`` consequence: there is **no ``' -> '`` separator**. A
    rename/copy entry spans two NUL-terminated fields, ``XY <dest>\\0<src>\\0``.
    Both are recorded — the destination is what we would read, and the source no
    longer holds the content its last commit says it does.
    """
    fields = payload.split("\0")
    dirty: set[str] = set()
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:  # "XY " + at least one path character
            continue
        xy, path = entry[:2], entry[3:]
        dirty.add(path)
        if ("R" in xy or "C" in xy) and i < len(fields):
            dirty.add(fields[i])  # the rename/copy source, its own field
            i += 1
    return dirty


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
        root, "status", "--porcelain", "-z", "--untracked-files=all", "--", *rels, check=False
    )
    dirty = _parse_porcelain_z(status_proc.stdout)
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


def _doc_record(root: Path, path: Path, kind: str, corpus: str) -> tuple[str, Record]:
    """A whole-file markdown record (``status`` / ``note``).

    The ID is the collab-relative path minus the extension — ``wiki/research-x``.
    Whole-file corpora have no ID scheme of their own (that is exactly what makes
    them *not* ledgers), and the path is the only thing about them that is both
    unique within a project and stable across runs.
    """
    rel = path.relative_to(root).as_posix()
    meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
    meta = {str(k): _scalar(v) for k, v in (meta or {}).items()}
    status_value = meta.get("status")
    return (
        rel,
        Record(
            id=rel[: -len(path.suffix)] if path.suffix else rel,
            kind=kind,
            title=_title_from_body(body, path.stem),
            path=rel,
            commit_sha="",
            status=status_value.strip()
            if isinstance(status_value, str) and status_value.strip()
            else None,
            body=body.strip(),
            links=_merge_links(extract_links(body), _related_links(meta)),
            meta={
                **{k: v for k, v in meta.items() if k != "related"},
                "corpus": corpus,
            },
        ),
    )


def _candidates(
    root: Path,
    kinds: set[str],
    include_archived: bool,
    adr_dir: str,
    note_dirs: tuple[str, ...] = NOTE_DIRS,
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

    # --- ADR-032: the two whole-file corpora ---------------------------------
    #
    # `status` is claimed FIRST so that a file listed in STATUS_FILES which also
    # sits inside a note dir (`wiki/status.md` does) is exported once, as the
    # kind that describes it, rather than twice under two IDs.
    status_paths: set[Path] = set()
    if "status" in kinds:
        for rel in STATUS_FILES:
            path = root / rel
            if path.is_file():
                status_paths.add(path.resolve())
                out.append(_doc_record(root, path, "status", "status"))

    if "note" in kinds:
        # A note dir that contains (or IS) the ADR dir would re-export every ADR
        # under a second ID and a second kind. `--adr-dir` makes that reachable,
        # so exclude the ADR tree explicitly rather than relying on the defaults
        # never overlapping.
        adr_root = (root / adr_dir).resolve()
        for note_dir in note_dirs:
            note_root = root / note_dir
            if not note_root.is_dir():
                continue
            for path in sorted(note_root.rglob("*.md")):
                resolved = path.resolve()
                if resolved in status_paths:
                    continue
                if resolved == adr_root or adr_root in resolved.parents:
                    continue
                out.append(_doc_record(root, path, "note", note_dir))

    return out


def project_name(collab: Path) -> str | None:
    """The collab repo's ``project.name``, or None when there is no readable manifest.

    Deliberately total: a directory can be a perfectly good corpus without being
    a well-formed Barony project, and refusing to export one over a malformed
    manifest would put a validation failure on the read path.
    """
    manifest = collab / "manifest.yaml"
    if not manifest.is_file():
        return None
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    name = project.get("name")
    return str(name) if name else None


def collect(
    collab: Path,
    *,
    kinds: set[str] | None = None,
    include_archived: bool = True,
    allow_dirty: bool = False,
    adr_dir: str = ADR_DIR,
    note_dirs: tuple[str, ...] = NOTE_DIRS,
    project: str | None = None,
) -> Export:
    """Walk the governed corpora and return citable records.

    Raises :class:`ExportError` when ``collab`` is not a git repository or has
    no commits — provenance is not optional, so there is no degraded mode.

    ``project`` overrides the name read from ``manifest.yaml``; the portfolio
    walk passes the registry's name so a subdir whose manifest disagrees with
    the marker is still attributed to the project the monorepo registered it as.
    """
    root = collab.resolve()
    if not root.is_dir():
        raise ExportError(f"{root} does not exist")
    if not is_git_repo(root):
        raise ExportError(
            f"{root} is not a git repository — `baron export` cites commit SHAs, "
            "which requires git history"
        )
    selected = set(kinds) if kinds else set(DEFAULT_KINDS)
    unknown = selected - set(KIND_ORDER)
    if unknown:
        raise ExportError(
            f"unknown kind(s): {', '.join(sorted(unknown))} — known: {', '.join(KIND_ORDER)}"
        )

    head = _head_sha(root)
    prefix = _repo_prefix(root)
    name = project if project is not None else project_name(root)
    candidates = _candidates(root, selected, include_archived, adr_dir, note_dirs)

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
        # `uncommitted` is skipped unconditionally — `--allow-dirty` cannot cover
        # it. A file with no commit has no SHA to name, and `commit_sha` being
        # always non-empty is the format invariant (ADR-015 §3.1). So the flag
        # means "modified too", never "uncited too".
        if condition == "uncommitted" or (condition != "clean" and not allow_dirty):
            key = (f"{prefix}{rel}", condition)
            skipped_counts[key] = skipped_counts.get(key, 0) + 1
            continue
        record.path = f"{prefix}{rel}"
        record.commit_sha = sha
        record.project = name
        if condition != "clean":
            record.meta = {**record.meta, "dirty": condition}
        records.append(record)

    deduped, duplicates = dedupe(records)
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
        layout="single",
        project=name,
    )


def dedupe(records: list[Record]) -> tuple[list[Record], list[str]]:
    """Drop repeat ``(project, kind, id)`` keys, in emission order, naming each.

    Shared by the single and portfolio walks so the two cannot disagree about
    what a duplicate *is* — which matters because the portfolio walk is where
    the answer changed (ADR-032 §3.4).
    """
    seen: set[tuple[str | None, str, str]] = set()
    duplicates: list[str] = []
    out: list[Record] = []
    for record in records:
        key = (record.project, record.kind, record.id)
        if key in seen:
            prefix = f"{record.project}:" if record.project else ""
            duplicates.append(f"{prefix}{record.kind}:{record.id}")
            continue
        seen.add(key)
        out.append(record)
    out.sort(
        key=lambda r: (r.project or "", KIND_ORDER.index(r.kind), _sort_key(r.id))
    )
    return out, duplicates


def collect_portfolio(
    root: Path,
    projects: list[tuple[str, str]],
    *,
    unregistered: list[str] | None = None,
    kinds: set[str] | None = None,
    include_archived: bool = True,
    allow_dirty: bool = False,
    adr_dir: str = ADR_DIR,
    note_dirs: tuple[str, ...] = NOTE_DIRS,
) -> Export:
    """Aggregate one export across a coordination monorepo's registered projects.

    ``projects`` is ``[(subdir, project_name), ...]`` — the caller supplies it
    from the registry so this module does not import :mod:`baron.monorepo` (which
    imports the scaffolder, and the export has no business dragging that in).

    The **same** ``Export`` shape comes back, with ``layout: "monorepo"`` and the
    records of every project concatenated. That is deliberate: the bug being
    fixed is that a root-level run reported zero, and the fix is worthless if it
    also forces every consumer of ``--json | jq '.records[]'`` to learn a second
    payload shape. Per-project provenance rides on each record (``project``) and
    on ``projects[]``, so nothing is lost by the flattening.

    ``path`` needs no adjustment: ``_repo_prefix`` already resolves each subdir's
    offset from the git top-level, so a record walked in ``<root>/barony`` comes
    back with ``barony/docs/adr/...`` and ``git show <sha>:<path>`` works from
    the root exactly as ADR-015 §3.1 requires.
    """
    resolved = root.resolve()
    if not is_git_repo(resolved):
        raise ExportError(
            f"{resolved} is not a git repository — `baron export` cites commit SHAs, "
            "which requires git history"
        )
    head = _head_sha(resolved)
    records: list[Record] = []
    skipped: list[Skipped] = []
    duplicates: list[str] = []
    legs: list[ProjectExport] = []
    unreadable: dict[str, str] = {}
    for subdir, name in projects:
        path = resolved / subdir
        if not path.is_dir():
            unreadable[subdir] = f"{path} does not exist"
            continue
        try:
            leg = collect(
                path,
                kinds=kinds,
                include_archived=include_archived,
                allow_dirty=allow_dirty,
                adr_dir=adr_dir,
                note_dirs=note_dirs,
                project=name,
            )
        except ExportError as exc:
            # One unwalkable project must not zero the portfolio — the same
            # reasoning ADR-015 §3.2 used to reject "refuse the whole export
            # when anything is dirty", one level up.
            unreadable[subdir] = str(exc)
            continue
        records.extend(leg.records)
        skipped.extend(leg.skipped)
        duplicates.extend(leg.duplicates)
        legs.append(
            ProjectExport(
                dir=subdir,
                name=name,
                collab=leg.collab,
                repo_prefix=leg.repo_prefix,
                records=len(leg.records),
                skipped_sources=len(leg.skipped),
            )
        )
    deduped, cross_duplicates = dedupe(records)
    return Export(
        generated=clock.today().isoformat(),
        collab=resolved.as_posix(),
        repo_prefix=_repo_prefix(resolved),
        head=head,
        records=deduped,
        skipped=sorted(skipped, key=lambda s: (s.path, s.reason)),
        duplicates=duplicates + cross_duplicates,
        layout="monorepo",
        project=None,
        projects=legs,
        unregistered=sorted(unregistered or []),
        unreadable=unreadable,
    )


def render_table(export: Export) -> str:
    """Human surface — one line per record, then the provenance caveats."""
    lines: list[str] = []
    monorepo = export.layout == "monorepo"
    for r in export.records:
        status = r.status or "-"
        title = r.title if len(r.title) <= 72 else r.title[:69] + "..."
        lead = f"{(r.project or '-'):14s} " if monorepo else ""
        lines.append(
            f"{lead}{r.kind:8s} {r.id:32s} {status:12s} {r.commit_sha[:8]}  {title}"
        )
    if not lines:
        lines.append("no records")
    tally: dict[str, int] = {}
    for r in export.records:
        tally[r.kind] = tally.get(r.kind, 0) + 1
    counts = ", ".join(f"{k}={tally[k]}" for k in KIND_ORDER if k in tally)
    lines.append("")
    scope = (
        f"{len(export.projects)} project(s) in this monorepo"
        if monorepo
        else (export.project or "this collab repo")
    )
    lines.append(
        f"{len(export.records)} record(s) at {export.head[:8]} from {scope}"
        + (f" ({counts})" if counts else "")
    )
    if monorepo:
        for leg in export.projects:
            lines.append(f"  {leg.dir + '/':20s} {leg.records:4d} record(s)")
    for s in export.skipped:
        lines.append(f"warning skipped {s.path}: {s.reason} ({s.records} record(s) not citable)")
    for dup in export.duplicates:
        lines.append(f"warning duplicate record id {dup} — first occurrence kept")
    for name in export.unregistered:
        lines.append(
            f"warning {name}/ holds a manifest.yaml but is not registered in "
            ".baron-monorepo.yaml — its records are NOT in this export "
            "(`baron adopt-project` registers it)"
        )
    for name, why in sorted(export.unreadable.items()):
        lines.append(f"warning {name}/ could not be exported: {why}")
    return "\n".join(lines)
