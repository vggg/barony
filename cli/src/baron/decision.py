"""P2.1 — ``baron decision reconcile`` / ``check`` (ADR-009, `park` obligation only).

The failure this closes (FM6 / badminton-analyzer D57): a ratified decision was
recorded in ``decisions/`` and still silently re-litigated for days, because the
epic encoding the superseded direction sat OPEN generating tickets. Agents do not
re-read ``decisions/`` when choosing work — they re-derive it from the backlog. In
the write-up's words: **decisions/ is a record, the backlog is a control; durability
requires writing the decision into the control.**

Scope: `park` ONLY (owner decision, 2026-08-02 — the obligation that demonstrably
caused FM6). `supersedes` / `broadcast` / `direction_doc` are designed in ADR-009 §3
and deliberately not built here.

Discharge — the part rev. 1 of the ADR got wrong
------------------------------------------------
A park is discharged only when **an agent's own backlog query stops returning the
item**, which is one of:

- **closed** — the issue is closed; nothing returns it.
- **filtered** — the issue carries the park label AND the project declares that label
  in ``manifest.backlog.park_label`` (so the rendered ``check_backlog`` query excludes
  it).

The naive condition — "labelled and commented" — is exactly the state D57 recorded
for epic #214, which it left OPEN. A discharge condition already satisfied by the
motivating incident is not a mechanism. **Without `park_label` declared the only
discharge is `closed`**: the default fails toward the strong condition.

Honest residue: baron verifies the declaration and the label. It cannot verify that a
hand-written agent honoured the query. That part is instructed.

Storage
-------
Obligations live in a marker-delimited region INSIDE the decision's own
``decisions/index.md`` entry (ADR-003 §2.2 — no second store). Unlike the handoff
index, this block is **authored primary data, not a derived view**: it cannot be
regenerated if lost. So this module only ever appends or updates its own block, never
rebuilds it, and a malformed block is REPORTED rather than silently rewritten
(the ADR-003 §2.6 precedent).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

BEGIN_MARKER = "<!-- BEGIN BARON RECONCILE -->"
END_MARKER = "<!-- END BARON RECONCILE -->"

#: Per-obligation state. `unverifiable` is a third state on purpose: collapsing it
#: into discharged would lie, and into outstanding would cry wolf on every CI run
#: that has no forge (ADR-009 §4).
DISCHARGED = "discharged"
OUTSTANDING = "outstanding"
UNVERIFIABLE = "unverifiable"


class DecisionError(RuntimeError):
    """The decision entry or its reconcile block could not be read or written."""


@dataclass(frozen=True)
class Park:
    issue: str
    repo: str | None = None

    def as_dict(self) -> dict:
        d: dict = {"issue": self.issue}
        if self.repo:
            d["repo"] = self.repo
        return d


@dataclass(frozen=True)
class Finding:
    decision: int
    obligation: str  # "park"
    target: str  # the issue reference
    state: str  # DISCHARGED | OUTSTANDING | UNVERIFIABLE
    message: str


# --- locating a decision entry ---------------------------------------------------------

def _entry_span(text: str, n: int) -> tuple[int, int]:
    """(start, end) character offsets of the ``### D<n>`` entry in ``text``.

    The entry ends at the next ``### `` heading or EOF — the same shape ledger.py
    writes.
    """
    m = re.search(rf"^### D{n}\b.*$", text, re.M)
    if not m:
        raise DecisionError(f"no `### D{n}` entry found in the decisions index")
    nxt = re.search(r"^### ", text[m.end():], re.M)
    return m.start(), (m.end() + nxt.start()) if nxt else len(text)


def parse_block(entry: str, *, where: str = "entry") -> dict:
    """Parse the reconcile block out of one decision entry. {} when absent."""
    if BEGIN_MARKER not in entry:
        return {}
    if END_MARKER not in entry:
        raise DecisionError(
            f"{where}: {BEGIN_MARKER} without a closing {END_MARKER} — refusing to "
            f"guess where the block ends. Fix it by hand; baron will not rewrite "
            f"authored data it cannot parse."
        )
    body = entry.split(BEGIN_MARKER, 1)[1].split(END_MARKER, 1)[0]
    try:
        data = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        raise DecisionError(f"{where}: reconcile block is not valid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise DecisionError(f"{where}: reconcile block must be a mapping, got {type(data).__name__}")
    return data


def parks_of(block: dict) -> list[Park]:
    out: list[Park] = []
    for item in block.get("park") or []:
        if isinstance(item, dict) and item.get("issue") is not None:
            out.append(Park(str(item["issue"]), item.get("repo")))
    return out


def render_block(block: dict) -> str:
    body = yaml.safe_dump(block, sort_keys=False, default_flow_style=False).rstrip()
    return f"{BEGIN_MARKER}\n{body}\n{END_MARKER}\n"


def upsert_block(text: str, n: int, block: dict) -> str:
    """Write ``block`` into decision ``n``'s entry, replacing any existing one.

    Appends at the end of the entry when absent. Prose above is never touched — the
    marker exists so generation cannot eat what a Librarian wrote.
    """
    start, end = _entry_span(text, n)
    entry = text[start:end]
    rendered = render_block(block)
    if BEGIN_MARKER in entry:
        parse_block(entry, where=f"D{n}")  # refuse on a malformed existing block
        head = entry.split(BEGIN_MARKER, 1)[0]
        tail = entry.split(END_MARKER, 1)[1]
        new_entry = head + rendered + tail.lstrip("\n")
    else:
        new_entry = entry.rstrip("\n") + "\n\n" + rendered
    return text[:start] + new_entry + text[end:]


# --- discharge --------------------------------------------------------------------------

def _park_label(manifest: dict) -> str | None:
    backlog = manifest.get("backlog")
    if isinstance(backlog, dict) and isinstance(backlog.get("park_label"), str):
        return backlog["park_label"]
    return None


def _backlog_source(manifest: dict) -> str:
    backlog = manifest.get("backlog")
    if isinstance(backlog, dict) and isinstance(backlog.get("source"), str):
        return backlog["source"]
    return "file"


def check_park_file(
    collab: Path, manifest: dict, park: Park, decision: int
) -> Finding:
    """`file` backlog source: a text assertion, no forge needed (ADR-003 §2.3)."""
    backlog = manifest.get("backlog") or {}
    loc = backlog.get("location")
    label = _park_label(manifest)
    if not isinstance(loc, str):
        return Finding(decision, "park", park.issue, UNVERIFIABLE,
                       "backlog.location is not set, so the backlog file cannot be read")
    path = collab / loc
    if not path.is_file():
        return Finding(decision, "park", park.issue, UNVERIFIABLE,
                       f"backlog file {loc} not found")
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if park.issue in ln]
    if not lines:
        return Finding(decision, "park", park.issue, DISCHARGED,
                       f"absent from {loc} — no query returns it")
    if label and all(label in ln for ln in lines):
        return Finding(decision, "park", park.issue, DISCHARGED,
                       f"marked `{label}` in {loc}, which backlog.park_label declares excluded")
    if label:
        return Finding(decision, "park", park.issue, OUTSTANDING,
                       f"still listed in {loc} without the `{label}` marker — an agent "
                       f"reading the backlog will still be offered this work")
    return Finding(decision, "park", park.issue, OUTSTANDING,
                   f"still listed in {loc}, and backlog.park_label is not declared, so the "
                   f"only discharge is removing it (ADR-009 §3.2)")


def check_park_forge(
    forge, repo: Path, manifest: dict, park: Park, decision: int
) -> Finding:
    """`github_issues`: closed, or labelled AND declared-excluded."""
    label = _park_label(manifest)
    from .forge.base import supports

    if not supports(forge, "get_issue"):
        return Finding(decision, "park", park.issue, UNVERIFIABLE,
                       f"this forge ({forge.__class__.__name__}) does not implement the optional "
                       f"get_issue extension, so an issue-tracker park cannot be verified")
    try:
        issue = forge.get_issue(repo, int(park.issue))
    except (ValueError, TypeError):
        return Finding(decision, "park", park.issue, UNVERIFIABLE,
                       f"{park.issue!r} is not a numeric issue reference")
    except Exception as exc:  # ForgeUnavailable and friends
        return Finding(decision, "park", park.issue, UNVERIFIABLE,
                       f"forge could not be queried ({exc.__class__.__name__}: {exc})")
    if issue.get("state", "").upper() == "CLOSED":
        return Finding(decision, "park", park.issue, DISCHARGED,
                       "issue is closed — nothing returns it")
    labels = {str(x) for x in issue.get("labels") or []}
    if label and label in labels:
        return Finding(decision, "park", park.issue, DISCHARGED,
                       f"open but labelled `{label}`, which backlog.park_label declares excluded "
                       f"from the check_backlog query")
    if label:
        return Finding(decision, "park", park.issue, OUTSTANDING,
                       f"OPEN and not labelled `{label}` — this is the FM6 state: an open issue "
                       f"still generating work after the decision that superseded it")
    return Finding(decision, "park", park.issue, OUTSTANDING,
                   "OPEN, and backlog.park_label is not declared, so the only discharge is "
                   "closing it (ADR-009 §3.2 — the default fails toward the strong condition)")


# --- the two operations -------------------------------------------------------------------

def _index_path(collab: Path) -> Path:
    p = collab / "decisions" / "index.md"
    if not p.is_file():
        raise DecisionError(f"no decisions/index.md under {collab}")
    return p


def reconcile(
    collab: Path, n: int, *, parks: list[Park], commit: bool = True
) -> list[Park]:
    """Record ``parks`` as obligations of decision ``n``. Returns the merged list.

    Idempotent: re-running with the same issue does not duplicate it. The block is
    written and committed BEFORE any remote step is attempted, so a network failure
    leaves a recorded obligation rather than a silent no-op (ADR-009 §5).
    """
    path = _index_path(collab)
    text = path.read_text(encoding="utf-8")
    start, end = _entry_span(text, n)
    block = parse_block(text[start:end], where=f"D{n}")

    existing = parks_of(block)
    seen = {(p.issue, p.repo) for p in existing}
    merged = list(existing) + [p for p in parks if (p.issue, p.repo) not in seen]
    if not merged:
        raise DecisionError("nothing to record — pass at least one --park")
    block["park"] = [p.as_dict() for p in merged]

    path.write_text(upsert_block(text, n, block), encoding="utf-8")
    if commit:
        from .gitutil import git, is_git_repo

        if is_git_repo(collab):
            rel = path.relative_to(collab).as_posix()
            git(collab, "add", "--", rel)
            git(collab, "commit", "-m", f"baron: decision | reconcile D{n} ({len(merged)} park)", "--", rel)
    return merged


def check(
    collab: Path, manifest: dict, *, only: int | None = None, forge=None, repo: Path | None = None
) -> list[Finding]:
    """Verify every recorded park obligation. Empty list = nothing recorded."""
    path = _index_path(collab)
    text = path.read_text(encoding="utf-8")
    source = _backlog_source(manifest)
    findings: list[Finding] = []

    for m in re.finditer(r"^### D(\d+)\b", text, re.M):
        n = int(m.group(1))
        if only is not None and n != only:
            continue
        start, end = _entry_span(text, n)
        try:
            block = parse_block(text[start:end], where=f"D{n}")
        except DecisionError as exc:
            findings.append(Finding(n, "park", "-", UNVERIFIABLE, str(exc)))
            continue
        for park in parks_of(block):
            if source == "github_issues":
                if forge is None or repo is None:
                    findings.append(Finding(
                        n, "park", park.issue, UNVERIFIABLE,
                        "backlog.source is github_issues; pass --fetch to query the forge"))
                else:
                    findings.append(check_park_forge(forge, repo, manifest, park, n))
            elif source == "file":
                findings.append(check_park_file(collab, manifest, park, n))
            else:
                findings.append(Finding(
                    n, "park", park.issue, UNVERIFIABLE,
                    f"backlog.source `{source}` has no park support at this cut "
                    f"(ADR-009 §5.1 — named so the omission is deliberate)"))
    return findings


def has_outstanding(findings: list[Finding]) -> bool:
    return any(f.state == OUTSTANDING for f in findings)
