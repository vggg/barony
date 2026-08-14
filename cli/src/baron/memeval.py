"""P3.3 — the governed-memory evaluation harness.

`AGENT-TASKS.md` 3.3 asks for *labeled fixtures and a reproducible baseline
before selecting a semantic-memory backend*. This module is that harness: it
materializes a labeled fixture corpus into a throwaway git repository, runs
`baron export` over it for real (so every record carries a real `path +
commit_sha`, ADR-015), and scores a set of **approaches** on the metrics 3.3
names — propagation precision/recall, duplicate suppression, schema/path/status
accuracy, retrieval Recall@k and MRR, source-citation accuracy,
freshness/supersession, and human intervention tax.

**Honesty bound, stated once and repeated in the report.** This measures
retrieval and propagation quality **on fixtures**. It is not a live audit of any
repository, it does not observe a running fleet, and a number produced here is a
statement about the fixture set and nothing else. What it is *for* is comparison:
the same labeled set scored the same way across approaches, so P3.4 can pick a
backend on a measured delta rather than a guess.

**What this deliberately does NOT do** (ADR-015 §4, ADR-022, ADR-031 §5): it
does not build or select a semantic-memory backend, it does not publish a
`baron.knowledge` entry-point group, it names no vendor, and it adds no
dependency. The seam for the two semantic approaches is an **in-process
registry** (:data:`RETRIEVERS`, :func:`register_retriever`) — a dict, not public
API — and the two approaches that need it report `available: false` with the
reason until P3.4 fills it. ``cli/tests/test_memeval.py`` asserts they stay
unfilled.
"""

from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Protocol

import yaml

from . import clock
from .export import Export, Record
from .export import collect as export_collect
from .gitutil import git

#: Wire-format identifier for the report.
FORMAT = "baron.memeval/v1"

#: Fixture-file format this loader understands.
FIXTURE_FORMAT = "baron.memeval-fixtures/v1"

#: Default cutoff for Recall@k.
DEFAULT_K = 5

#: The bound printed on every report surface. Do not soften it.
HONESTY_BOUND = (
    "measures retrieval and propagation quality on FIXTURES; "
    "not a live audit of any repository or fleet"
)


class MemevalError(RuntimeError):
    """The evaluation could not be run."""


# --- fixtures ----------------------------------------------------------------------------


@dataclass
class Query:
    id: str
    text: str
    relevant: list[str]
    stale: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class Event:
    id: str
    type: str
    subject: str
    gold: dict[str, object]
    ref: str | None = None
    status: str | None = None
    source_sha: str | None = None
    duplicate_of: str | None = None
    thesis_changing: bool = False


@dataclass
class FixtureSet:
    root: Path
    today: str
    project: str
    commits: list[dict[str, object]]
    modified: list[dict[str, str]]
    uncommitted: list[str]
    out_of_corpus: list[str]
    queries: list[Query]
    events: list[Event]


def load_fixtures(path: Path) -> FixtureSet:
    """Read ``<path>/fixtures.yaml`` and the sibling ``corpus/`` tree."""
    root = path.resolve()
    manifest = root / "fixtures.yaml"
    if not manifest.is_file():
        raise MemevalError(f"{manifest} not found — --fixtures wants the directory holding it")
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    fmt = data.get("format")
    if fmt != FIXTURE_FORMAT:
        raise MemevalError(f"{manifest}: format is {fmt!r}, expected {FIXTURE_FORMAT!r}")
    if not (root / "corpus").is_dir():
        raise MemevalError(f"{root / 'corpus'} not found — fixtures need a corpus/ tree")

    build = data.get("build") or {}
    queries = [
        Query(
            id=str(q["id"]),
            text=str(q["text"]),
            relevant=[str(r) for r in q.get("relevant", [])],
            stale=[str(r) for r in q.get("stale", [])],
            note=str(q.get("note", "")).strip(),
        )
        for q in data.get("queries", [])
    ]
    events = [
        Event(
            id=str(e["id"]),
            type=str(e["type"]),
            subject=str(e.get("subject", "")),
            gold=dict(e.get("gold") or {}),
            ref=(str(e["ref"]) if e.get("ref") else None),
            status=(str(e["status"]) if e.get("status") else None),
            source_sha=(str(e["source_sha"]) if e.get("source_sha") else None),
            duplicate_of=(str(e["duplicate_of"]) if e.get("duplicate_of") else None),
            thesis_changing=bool(e.get("thesis_changing", False)),
        )
        for e in data.get("events", [])
    ]
    if not queries:
        raise MemevalError(f"{manifest}: no queries — there is nothing to score")
    if not events:
        raise MemevalError(f"{manifest}: no events — there is nothing to score")
    return FixtureSet(
        root=root,
        today=str(data.get("today") or clock.today().isoformat()),
        project=str(data.get("project") or "demo"),
        commits=list(build.get("commits") or []),
        modified=list(build.get("modified") or []),
        uncommitted=list(build.get("uncommitted") or []),
        out_of_corpus=[str(p) for p in (build.get("out_of_corpus") or [])],
        queries=queries,
        events=events,
    )


def materialize(fx: FixtureSet, dest: Path) -> Path:
    """Build the fixture corpus into ``dest`` as a real git repo.

    Files are committed in the order the manifest lists them, so SHAs differ
    per record and the citation check has something to fail on. Sources named
    under ``uncommitted`` are written and never added; sources under
    ``modified`` are committed and then edited, which is the two halves of the
    ADR-015 citation gate.
    """
    dest = dest.resolve()
    if dest.exists() and any(dest.iterdir()):
        raise MemevalError(f"{dest} is not empty")
    shutil.copytree(fx.root / "corpus", dest, dirs_exist_ok=True)

    _run_git(dest, "init", "-q", "-b", "main")
    _run_git(dest, "config", "user.name", "Memeval Fixture")
    _run_git(dest, "config", "user.email", "memeval@barony.invalid")
    _run_git(dest, "config", "commit.gpgsign", "false")

    uncommitted = set(fx.uncommitted)
    for commit in fx.commits:
        files = [str(f) for f in (commit.get("files") or [])]
        files = [f for f in files if f not in uncommitted]
        if not files:
            continue
        for rel in files:
            if not (dest / rel).is_file():
                raise MemevalError(f"fixtures name a file the corpus does not have: {rel}")
        _run_git(dest, "add", "--", *files)
        _run_git(dest, "commit", "-q", "-m", str(commit.get("message", "fixture")), "--", *files)

    for entry in fx.modified:
        rel = str(entry["path"])
        target = dest / rel
        if not target.is_file():
            raise MemevalError(f"fixtures mark a missing file as modified: {rel}")
        target.write_text(
            target.read_text(encoding="utf-8") + str(entry.get("append", "\n")), encoding="utf-8"
        )

    for rel in fx.uncommitted:
        if not (dest / rel).is_file():
            raise MemevalError(f"fixtures mark a missing file as uncommitted: {rel}")

    stray = _run_git(dest, "status", "--porcelain", "--untracked-files=all")
    unexpected = sorted(
        line[3:]
        for line in stray.splitlines()
        if line[3:] not in uncommitted
        and line[3:] not in {str(e["path"]) for e in fx.modified}
    )
    if unexpected:
        raise MemevalError(
            "corpus files are in the tree but named by no commit, and the fixture set "
            f"does not mark them uncommitted: {', '.join(unexpected)}"
        )
    return dest


def _run_git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise MemevalError(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")
    return proc.stdout


def record_key(record: Record) -> str:
    """The gold-label key for a record: ``<kind>:<id>``."""
    return f"{record.kind}:{record.id}"


# --- retrieval ---------------------------------------------------------------------------


@dataclass
class Hit:
    key: str
    score: float
    record: Record


class Retriever(Protocol):
    """Rank the corpus against one query. Highest score first."""

    name: str

    def rank(self, query: Query, records: list[Record]) -> list[Hit]:  # pragma: no cover
        ...


_STOPWORDS = frozenset(
    """a an and are as at be but by can did do does for from has have how i in is it its
    of on or that the their there this to was we what when where which who why will with
    you your does not""".split()
)

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9._/-]*")


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS]


class LexicalRetriever:
    """The git+markdown baseline: literal term matching, as `grep -iw` would do.

    A record is a candidate only if at least one query term appears in it as a
    whole word — which is exactly `rg -w` behaviour, misses and all. Ranking is
    by number of *distinct* query terms matched, then by total occurrences, then
    by key, so the ordering is deterministic and reproducible.

    Its known weakness is the whole reason 3.3 exists: a question phrased in
    vocabulary the corpus does not use scores zero everywhere.
    """

    name = "lexical"

    def rank(self, query: Query, records: list[Record]) -> list[Hit]:
        terms = _tokens(query.text)
        hits: list[Hit] = []
        for record in records:
            haystack = f"{record.title}\n{record.path}\n{record.body}".lower()
            distinct = 0
            total = 0
            for term in set(terms):
                found = len(re.findall(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack))
                if found:
                    distinct += 1
                    total += found
            if distinct:
                hits.append(
                    Hit(key=record_key(record), score=distinct + min(total, 99) / 1000.0, record=record)
                )
        hits.sort(key=lambda h: (-h.score, h.key))
        return hits


#: In-process retriever registry. **Not an entry-point group** — ADR-015 §4's
#: rule (a published group with no consumer is unretractable public API) is not
#: repealed by 3.3, and this dict is a seam inside one process, retractable in a
#: patch release. P3.4's semantic retriever registers here via
#: :func:`register_retriever`; until it does, the two semantic approaches report
#: `available: false` with the reason.
RETRIEVERS: dict[str, Callable[[], Retriever]] = {"lexical": LexicalRetriever}


def register_retriever(name: str, factory: Callable[[], Retriever]) -> None:
    """Register a retriever for the current process. See :data:`RETRIEVERS`."""
    RETRIEVERS[name] = factory


# --- propagation -------------------------------------------------------------------------


@dataclass
class Emission:
    """What a propagator did with one event."""

    propagate: bool
    dest: str | None = None
    priority: str | None = None
    path: str | None = None
    status: str | None = None
    schema: list[str] = field(default_factory=list)
    needs_human: bool = False
    reason: str = ""


class Propagator(Protocol):
    name: str

    def decide(self, event: Event, state: dict[str, object], fx: FixtureSet) -> Emission:
        ...  # pragma: no cover


#: The frontmatter a propagated note carries, per CLAUDE.md's handoff protocol:
#: the five common keys, plus `decision`/`urgency` on a decision note and
#: `task-status` on a task note.
_COMMON_SCHEMA = ["created", "from", "for", "status", "priority"]
DECISION_SCHEMA = _COMMON_SCHEMA + ["decision", "urgency"]
TASK_SCHEMA = _COMMON_SCHEMA + ["task-status"]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "item"


def _note_path(fx: FixtureSet, dest: str, event: Event) -> str:
    return f"_handoff/{dest}/{fx.today}-{fx.project}-{_slug(event.ref or event.subject)}.md"


_PROPAGATE_TERMS = (
    "adr",
    "decision",
    "release",
    "milestone",
    "roadmap",
    "direction",
    "phase",
    "finding",
    "version bump",
    "publish",
)
_DECISION_TERMS = ("adr", "decision", "direction", "roadmap", "finding")


class LexicalPropagator:
    """The unassisted baseline: keyword-match a commit subject line.

    This is what an agent grepping `CLAUDE.md`'s propagate/don't-propagate lists
    can actually key on — one line of text, no structure. It cannot see an ADR's
    status, cannot tell a thesis-changing finding from a routine one, cannot know
    whether a source SHA resolves, and can only deduplicate on the exact subject
    string, so a reworded re-report of the same event reads as new.
    """

    name = "lexical"

    def decide(self, event: Event, state: dict[str, object], fx: FixtureSet) -> Emission:
        seen: set[str] = state.setdefault("seen", set())  # type: ignore[assignment]
        subject = event.subject.lower()
        if subject in seen:
            return Emission(propagate=False, reason="identical subject already propagated")
        if not any(term in subject for term in _PROPAGATE_TERMS):
            return Emission(propagate=False, reason="no propagate keyword in subject")
        seen.add(subject)
        dest = "decisions" if any(t in subject for t in _DECISION_TERMS) else "tasks"
        return Emission(
            propagate=True,
            dest=dest,
            priority="medium",
            status="open",
            path=_note_path(fx, dest, event),
            # No kind-specific fields: the baseline has no idea which kind of
            # note it is writing beyond the destination guess.
            schema=list(_COMMON_SCHEMA),
            reason="keyword match",
        )


_ADR_PRIORITY = {
    "accepted": "high",
    "proposed": "medium",
    "superseded": "medium",
    "parked": "low",
    "rejected": "low",
}


class HooksPropagator:
    """Hook-assisted propagation: a rule table over the event's structured fields.

    Same policy as the baseline, different input. It reads `type`, `status`,
    `ref` and `source_sha` rather than a subject line, so it can suppress a
    reworded duplicate (it keys on `(type, ref)`), it can price an ADR's priority
    off its lifecycle status, and it refuses to propagate an event whose source
    SHA is missing — flagging it for a human instead of emitting a note that
    cites nothing.
    """

    name = "hooks"

    def decide(self, event: Event, state: dict[str, object], fx: FixtureSet) -> Emission:
        seen: set[tuple[str, str]] = state.setdefault("seen", set())  # type: ignore[assignment]
        rule = self._rule(event)
        if rule is None:
            return Emission(propagate=False, reason=f"{event.type} is not a project-level event")
        dest, priority = rule
        if not event.source_sha:
            return Emission(
                propagate=False,
                needs_human=True,
                reason="no citable source SHA — a propagated note would cite nothing",
            )
        key = (event.type, event.ref or event.subject.lower())
        if key in seen:
            return Emission(propagate=False, reason=f"already propagated {key[0]}:{key[1]}")
        seen.add(key)
        return Emission(
            propagate=True,
            dest=dest,
            priority=priority,
            status="open",
            path=_note_path(fx, dest, event),
            schema=list(DECISION_SCHEMA if dest == "decisions" else TASK_SCHEMA),
            reason="rule table",
        )

    @staticmethod
    def _rule(event: Event) -> tuple[str, str] | None:
        if event.type == "commit":
            return None
        if event.type == "finding":
            return ("decisions", "high") if event.thesis_changing else None
        if event.type == "adr":
            return ("decisions", _ADR_PRIORITY.get(event.status or "", "medium"))
        if event.type == "decision":
            return ("decisions", "medium")
        if event.type in ("release", "milestone"):
            return ("tasks", "medium")
        return None


PROPAGATORS: dict[str, Callable[[], Propagator]] = {
    "lexical": LexicalPropagator,
    "hooks": HooksPropagator,
}


# --- approaches --------------------------------------------------------------------------


@dataclass(frozen=True)
class Approach:
    name: str
    propagator: str
    retriever: str
    note: str


#: The four approaches 3.3 names, in its order. Two are measurable with no new
#: dependency; two need a retriever P3.4 has not built and are reported unbuilt
#: rather than estimated.
APPROACHES: tuple[Approach, ...] = (
    Approach(
        "git-markdown",
        "lexical",
        "lexical",
        "the substrate as it stands: literal search over the exported corpus",
    ),
    Approach(
        "hooks",
        "hooks",
        "lexical",
        "hook-assisted propagation over structured events; retrieval unchanged",
    ),
    Approach("semantic", "lexical", "semantic", "semantic retrieval, unassisted propagation"),
    Approach("hooks+semantic", "hooks", "semantic", "both"),
)


# --- metrics -----------------------------------------------------------------------------


def _f(numerator: float, denominator: float) -> float | None:
    """Rate, or None when the denominator is empty — never a silent 0.0."""
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


@dataclass
class RetrievalMetrics:
    k: int
    queries: int
    scored: int
    recall_at_k: float | None
    recall_at_k_reachable: float | None
    corpus_ceiling: float | None
    mrr: float | None
    supersession_accuracy: float | None
    supersession_queries: int
    citation_accuracy: float | None
    citations_checked: int
    per_query: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "k": self.k,
            "queries": self.queries,
            "scored": self.scored,
            "recall_at_k": self.recall_at_k,
            "recall_at_k_reachable": self.recall_at_k_reachable,
            "corpus_ceiling": self.corpus_ceiling,
            "mrr": self.mrr,
            "supersession_accuracy": self.supersession_accuracy,
            "supersession_queries": self.supersession_queries,
            "citation_accuracy": self.citation_accuracy,
            "citations_checked": self.citations_checked,
            "per_query": self.per_query,
        }


@dataclass
class PropagationMetrics:
    events: int
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float | None
    recall: float | None
    f1: float | None
    duplicates: int
    duplicates_suppressed: int
    duplicate_suppression: float | None
    dest_accuracy: float | None
    path_accuracy: float | None
    status_accuracy: float | None
    schema_accuracy: float | None
    flagged: int
    intervention_tax: float | None
    per_event: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "events": self.events,
            "confusion": {"tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn},
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "duplicates": self.duplicates,
            "duplicates_suppressed": self.duplicates_suppressed,
            "duplicate_suppression": self.duplicate_suppression,
            "dest_accuracy": self.dest_accuracy,
            "path_accuracy": self.path_accuracy,
            "status_accuracy": self.status_accuracy,
            "schema_accuracy": self.schema_accuracy,
            "flagged_for_human": self.flagged,
            "intervention_tax": self.intervention_tax,
            "per_event": self.per_event,
        }


@dataclass
class ApproachResult:
    approach: Approach
    available: bool
    reason: str
    propagation: PropagationMetrics | None
    retrieval: RetrievalMetrics | None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.approach.name,
            "propagator": self.approach.propagator,
            "retriever": self.approach.retriever,
            "note": self.approach.note,
            "available": self.available,
            "reason": self.reason,
            "propagation": self.propagation.to_dict() if self.propagation else None,
            "retrieval": self.retrieval.to_dict() if self.retrieval else None,
        }


@dataclass
class Report:
    generated: str
    fixtures: str
    k: int
    corpus: dict[str, object]
    approaches: list[ApproachResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "format": FORMAT,
            "generated": self.generated,
            "fixtures": self.fixtures,
            "honesty_bound": HONESTY_BOUND,
            "k": self.k,
            "corpus": self.corpus,
            "approaches": [a.to_dict() for a in self.approaches],
        }


# --- scoring -----------------------------------------------------------------------------


def score_propagation(
    propagator: Propagator, fx: FixtureSet
) -> PropagationMetrics:
    state: dict[str, object] = {}
    tp = fp = fn = tn = 0
    flagged = 0
    dup_total = dup_suppressed = 0
    dest_ok = path_ok = status_ok = schema_ok = 0
    per_event: list[dict[str, object]] = []

    for event in fx.events:
        emission = propagator.decide(event, state, fx)
        gold = event.gold
        want = bool(gold.get("propagate"))
        got = emission.propagate
        if emission.needs_human:
            flagged += 1
        if want and got:
            tp += 1
        elif want and not got:
            fn += 1
        elif not want and got:
            fp += 1
        else:
            tn += 1

        if event.duplicate_of:
            dup_total += 1
            if not got:
                dup_suppressed += 1

        if want and got:
            if emission.dest == gold.get("dest"):
                dest_ok += 1
            glob = str(gold.get("path_glob", ""))
            if glob and emission.path and fnmatch.fnmatch(emission.path, glob):
                path_ok += 1
            if emission.status == "open" and emission.priority == gold.get("priority"):
                status_ok += 1
            if set(emission.schema) == set(str(s) for s in gold.get("schema", [])):
                schema_ok += 1

        per_event.append(
            {
                "id": event.id,
                "type": event.type,
                "gold_propagate": want,
                "propagated": got,
                "outcome": (
                    "tp" if want and got else "fn" if want else "fp" if got else "tn"
                ),
                "dest": emission.dest,
                "priority": emission.priority,
                "path": emission.path,
                "needs_human": emission.needs_human,
                "reason": emission.reason,
            }
        )

    # A human has to touch an event when the propagator asks for help, when it
    # emitted a note that should not exist (someone deletes it), and when it
    # stayed silent about something that had to reach the vault (someone writes
    # it). Flags are counted once even if they are also a miss.
    flagged_and_wrong = sum(
        1
        for e, row in zip(fx.events, per_event)
        if row["needs_human"] and row["outcome"] in ("fp", "fn")
    )
    touches = flagged + fp + fn - flagged_and_wrong

    return PropagationMetrics(
        events=len(fx.events),
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=_f(tp, tp + fp),
        recall=_f(tp, tp + fn),
        f1=_f(2 * tp, 2 * tp + fp + fn),
        duplicates=dup_total,
        duplicates_suppressed=dup_suppressed,
        duplicate_suppression=_f(dup_suppressed, dup_total),
        dest_accuracy=_f(dest_ok, tp),
        path_accuracy=_f(path_ok, tp),
        status_accuracy=_f(status_ok, tp),
        schema_accuracy=_f(schema_ok, tp),
        flagged=flagged,
        intervention_tax=_f(touches, len(fx.events)),
        per_event=per_event,
    )


def _citation_holds(repo: Path, record: Record) -> bool:
    """Does ``git show <commit_sha>:<path>`` reproduce what this record cites?"""
    if not record.commit_sha or not record.path:
        return False
    proc = git(repo, "show", f"{record.commit_sha}:{record.path}", check=False)
    if proc.returncode != 0:
        return False
    text = proc.stdout
    if record.kind in ("adr", "handoff"):
        probe = record.body.strip()[:160]
        return bool(probe) and probe in text
    # Ledger kinds: the record is a slice of the index, not the whole file, so
    # the anchor is its id in the line that introduces it — a `### F4 — …`
    # heading or a `| F4 | … |` table row, the two forms `parse_ledger` reads.
    return (
        re.search(
            rf"^(?:#{{1,3}}\s+|\|\s*){re.escape(record.id)}(?![A-Za-z0-9])",
            text,
            re.M,
        )
        is not None
    )


def score_retrieval(
    retriever: Retriever, fx: FixtureSet, export: Export, repo: Path, k: int
) -> RetrievalMetrics:
    records = export.records
    reachable = {record_key(r) for r in records}
    by_key = {record_key(r): r for r in records}

    recalls: list[float] = []
    reachable_recalls: list[float] = []
    ceilings: list[float] = []
    rr: list[float] = []
    supersession_hits = 0
    supersession_total = 0
    citation_ok = 0
    citation_total = 0
    checked: set[str] = set()
    per_query: list[dict[str, object]] = []

    for query in fx.queries:
        gold = set(query.relevant)
        gold_reachable = gold & reachable
        ranked = retriever.rank(query, records)
        top = ranked[:k]
        top_keys = [h.key for h in top]
        found = gold & set(top_keys)

        recalls.append(len(found) / len(gold) if gold else 0.0)
        ceilings.append(len(gold_reachable) / len(gold) if gold else 0.0)
        if gold_reachable:
            reachable_recalls.append(len(found) / len(gold_reachable))

        first = next((i for i, key in enumerate(top_keys, 1) if key in gold), None)
        rr.append(1.0 / first if first else 0.0)

        stale_reachable = set(query.stale) & reachable
        if stale_reachable and gold_reachable:
            supersession_total += 1
            best_gold = next((i for i, key in enumerate(top_keys, 1) if key in gold), None)
            best_stale = next(
                (i for i, key in enumerate(top_keys, 1) if key in stale_reachable), None
            )
            if best_gold is not None and (best_stale is None or best_gold < best_stale):
                supersession_hits += 1

        for key in top_keys:
            if key in checked:
                continue
            checked.add(key)
            citation_total += 1
            if _citation_holds(repo, by_key[key]):
                citation_ok += 1

        per_query.append(
            {
                "id": query.id,
                "gold": sorted(gold),
                "gold_reachable": sorted(gold_reachable),
                "unreachable": sorted(gold - reachable),
                "top_k": top_keys,
                "found": sorted(found),
                "recall_at_k": round(len(found) / len(gold), 4) if gold else None,
                "first_relevant_rank": first,
            }
        )

    return RetrievalMetrics(
        k=k,
        queries=len(fx.queries),
        scored=len(reachable_recalls),
        recall_at_k=_f(sum(recalls), len(recalls)),
        recall_at_k_reachable=_f(sum(reachable_recalls), len(reachable_recalls)),
        corpus_ceiling=_f(sum(ceilings), len(ceilings)),
        mrr=_f(sum(rr), len(rr)),
        supersession_accuracy=_f(supersession_hits, supersession_total),
        supersession_queries=supersession_total,
        citation_accuracy=_f(citation_ok, citation_total),
        citations_checked=citation_total,
        per_query=per_query,
    )


def run(
    fixtures_dir: Path,
    workdir: Path,
    *,
    k: int = DEFAULT_K,
    approaches: Iterable[str] | None = None,
) -> Report:
    """Materialize the fixtures, export them, and score every approach."""
    fx = load_fixtures(fixtures_dir)
    repo = materialize(fx, workdir)
    export = export_collect(repo)

    wanted = set(approaches) if approaches else {a.name for a in APPROACHES}
    unknown = wanted - {a.name for a in APPROACHES}
    if unknown:
        raise MemevalError(
            f"unknown approach(es): {', '.join(sorted(unknown))} — "
            f"known: {', '.join(a.name for a in APPROACHES)}"
        )

    results: list[ApproachResult] = []
    for approach in APPROACHES:
        if approach.name not in wanted:
            continue
        if approach.retriever not in RETRIEVERS:
            results.append(
                ApproachResult(
                    approach=approach,
                    available=False,
                    reason=(
                        f"no {approach.retriever!r} retriever is registered — P3.4 has not "
                        "built one, and this harness will not estimate a number it did "
                        "not measure"
                    ),
                    propagation=None,
                    retrieval=None,
                )
            )
            continue
        results.append(
            ApproachResult(
                approach=approach,
                available=True,
                reason="",
                propagation=score_propagation(PROPAGATORS[approach.propagator](), fx),
                retrieval=score_retrieval(RETRIEVERS[approach.retriever](), fx, export, repo, k),
            )
        )

    ceiling = results[0].retrieval.corpus_ceiling if results and results[0].retrieval else None
    corpus = {
        "records": len(export.records),
        "by_kind": {
            kind: sum(1 for r in export.records if r.kind == kind)
            for kind in sorted({r.kind for r in export.records})
        },
        "skipped_sources": [s.to_dict() for s in export.skipped],
        "out_of_corpus": fx.out_of_corpus,
        "retrieval_ceiling": ceiling,
        "head": export.head,
    }
    return Report(
        generated=clock.today().isoformat(),
        fixtures=fx.root.as_posix(),
        k=k,
        corpus=corpus,
        approaches=results,
    )


# --- rendering ---------------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "  n/a" if value is None else f"{value * 100:5.1f}"


def render(report: Report) -> str:
    lines: list[str] = []
    corpus = report.corpus
    lines.append(f"governed-memory eval — {report.fixtures}")
    lines.append(f"honesty bound: {HONESTY_BOUND}")
    lines.append("")
    by_kind = ", ".join(f"{k}={v}" for k, v in (corpus.get("by_kind") or {}).items())
    lines.append(f"corpus  {corpus['records']} citable record(s) at {str(corpus['head'])[:8]}"
                 + (f" ({by_kind})" if by_kind else ""))
    for skipped in corpus.get("skipped_sources") or []:  # type: ignore[union-attr]
        lines.append(
            f"        skipped {skipped['path']}: {skipped['reason']} "
            f"({skipped['records']} record(s) not citable)"
        )
    for path in corpus.get("out_of_corpus") or []:  # type: ignore[union-attr]
        lines.append(f"        outside the exported corpora: {path}")
    ceiling = corpus.get("retrieval_ceiling")
    if ceiling is not None:
        lines.append(
            f"        retrieval ceiling {float(ceiling) * 100:.1f}% — the share of gold "
            "answers any strategy could reach"
        )
    lines.append("")

    header = (
        f"{'approach':16s} {'prec':>5s} {'rec':>5s} {'dup':>5s} {'schema':>6s} "
        f"{'path':>5s} {'stat':>5s} {'R@' + str(report.k):>5s} {'MRR':>5s} "
        f"{'fresh':>5s} {'cite':>5s} {'tax':>5s}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for result in report.approaches:
        if not result.available:
            lines.append(f"{result.approach.name:16s} NOT MEASURED — {result.reason}")
            continue
        p = result.propagation
        r = result.retrieval
        assert p is not None and r is not None
        lines.append(
            f"{result.approach.name:16s} {_pct(p.precision)} {_pct(p.recall)} "
            f"{_pct(p.duplicate_suppression)} {_pct(p.schema_accuracy):>6s} "
            f"{_pct(p.path_accuracy)} {_pct(p.status_accuracy)} "
            f"{_pct(r.recall_at_k)} {_pct(r.mrr)} {_pct(r.supersession_accuracy)} "
            f"{_pct(r.citation_accuracy)} {_pct(p.intervention_tax)}"
        )
    lines.append("")
    lines.append(
        "columns are percentages: propagation precision/recall, duplicate suppression, "
        "schema/path/status accuracy, Recall@k, MRR, freshness (supersession), "
        "source-citation accuracy, human intervention tax (lower is better)."
    )
    return "\n".join(lines)
