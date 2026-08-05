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
    writes. ``\b`` keeps ``### D5`` from matching ``### D57``.
    """
    hits = list(re.finditer(rf"^### D{n}\b.*$", text, re.M))
    if not hits:
        raise DecisionError(f"no `### D{n}` entry found in the decisions index")
    if len(hits) > 1:
        # Refuse rather than pick one: writing into the first would silently orphan
        # the second's obligations, and this is authored data (ADR-009 §3.1).
        raise DecisionError(
            f"`### D{n}` appears {len(hits)} times in the decisions index — a duplicate "
            f"number. baron will not guess which entry owns the obligations; fix the "
            f"index by hand (`baron index` reports duplicates as errors)."
        )
    m = hits[0]
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


# --- matching: token boundaries, never bare substrings ------------------------------------
#
# Substring matching produced THREE independent false DISCHARGEDs, all found in review:
#   * `unparked` contains `parked`, so the negation of the park label discharged the park;
#   * `--park #214` against a line reading `issue 214 ...` matched nothing and was
#     reported ABSENT — the STRONG discharge — while the item sat there, active;
#   * `--park 214` was discharged by an unrelated `SHU-2140`.
# A false DISCHARGED is the one failure that makes this feature worse than nothing: it
# prints green on exactly the FM6 state it exists to catch.

def _issue_core(issue: str) -> str:
    """Canonical form of an issue reference: `#214`, `214` and ` #214 ` all -> `214`."""
    return issue.strip().lstrip("#").strip()


def _issue_pattern(issue: str) -> re.Pattern[str]:
    """Match the id as a whole token, with or without a leading `#`.

    Boundaries are `[\w-]` on both sides so `SHU-2140` does not match `214`, and
    `#21` does not match `#214`.
    """
    return re.compile(rf"(?<![\w-])#?{re.escape(_issue_core(issue))}(?![\w-])")


def _label_pattern(label: str) -> re.Pattern[str]:
    """Match the park label only as a DELIMITED MARKER — `[parked]` or `(parked)`.

    A bare token anywhere on the line is not enough: `- #214 Epic — was parked,
    REOPENED, ACTIVE` discharged the park under that rule, because the word appears
    in prose describing the item's HISTORY. Requiring a delimiter makes the marker a
    deliberate act rather than an accident of wording.

    This is also the honest analogue of what the renderers do for a tracker backlog
    (`--search "-label:<park_label>"` against a real label FIELD). A markdown file has
    no label field, so baron specifies one; `manifest.schema.md` documents it.
    """
    lab = re.escape(label.strip())
    return re.compile(rf"\[{lab}\]|\({lab}\)")


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
        # OUTSTANDING, not unverifiable: the manifest DECLARES this file, so its
        # absence is a project misconfiguration, not an unreachable network — and
        # unverifiable exits 0, which would make deleting the backlog a way to go green.
        return Finding(decision, "park", park.issue, OUTSTANDING,
                       f"backlog file {loc} is declared in the manifest but missing — "
                       f"the park cannot be verified and must not be assumed discharged")
    id_re = _issue_pattern(park.issue)
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if id_re.search(ln)]
    if not lines:
        # ABSENCE IS NOT PROOF. An earlier cut discharged here, and review showed the
        # id simply failing to match — `--park 214` against `GH-214 … ACTIVE` — was
        # indistinguishable from genuine removal. That handed out the STRONG discharge
        # on an epic that was live, and made any typo a permanently green obligation.
        # baron cannot tell "removed" from "never matched", so it says so.
        return Finding(decision, "park", park.issue, UNVERIFIABLE,
                       f"no line in {loc} references `{park.issue}` — baron cannot "
                       f"distinguish 'removed' from 'never matched' (id-format mismatch, "
                       f"e.g. GH-214 vs 214). Confirm removal by hand, or record the id "
                       f"exactly as the backlog writes it")
    label_re = _label_pattern(label) if label else None
    if label_re and all(label_re.search(ln) for ln in lines):
        return Finding(decision, "park", park.issue, DISCHARGED,
                       f"marked `[{label}]` in {loc}, which backlog.park_label declares excluded")
    if label:
        return Finding(decision, "park", park.issue, OUTSTANDING,
                       f"still listed in {loc} without a `[{label}]` marker — an agent "
                       f"reading the backlog will still be offered this work")
    return Finding(decision, "park", park.issue, OUTSTANDING,
                   f"still listed in {loc}, and backlog.park_label is not declared, so the "
                   f"only discharge is removing it (ADR-009 §3.2)")


def _issue_repo(manifest: dict, park: Park) -> str | None:
    """Which forge repo owns this issue.

    Without it, `gh` runs with cwd=collab and no --repo, so a park on a CODE-repo
    issue is answered by the collab repo's same-numbered issue — a wrong answer that
    looks authoritative. `park.repo` names a manifest repos[].id; otherwise a
    github_issues `backlog.location` of the form owner/name is the target.
    """
    if park.repo:
        for r in manifest.get("repos") or []:
            if isinstance(r, dict) and r.get("id") == park.repo:
                remote = r.get("remote")
                if isinstance(remote, str) and "/" in remote:
                    slug = remote.rstrip("/").removesuffix(".git")
                    parts = slug.replace(":", "/").split("/")
                    if len(parts) >= 2:
                        return "/".join(parts[-2:])
        return None
    backlog = manifest.get("backlog") or {}
    loc = backlog.get("location")
    if backlog.get("source") == "github_issues" and isinstance(loc, str) and "/" in loc:
        return loc
    return None


def check_park_forge(
    forge, repo: Path, manifest: dict, park: Park, decision: int
) -> Finding:
    """`github_issues`: closed, or labelled AND declared-excluded."""
    label = _park_label(manifest)
    target = _issue_repo(manifest, park)
    if park.repo and target is None:
        return Finding(decision, "park", park.issue, UNVERIFIABLE,
                       f"park declares repo `{park.repo}` but the manifest has no such repo "
                       f"with a resolvable remote — refusing to query a different repo")
    from .forge.base import supports

    if not supports(forge, "get_issue"):
        return Finding(decision, "park", park.issue, UNVERIFIABLE,
                       f"this forge ({forge.__class__.__name__}) does not implement the optional "
                       f"get_issue extension, so an issue-tracker park cannot be verified")
    try:
        n_issue = int(_issue_core(park.issue))
        try:
            issue = forge.get_issue(repo, n_issue, target_repo=target)
        except TypeError:
            # An older plugin predates the target_repo kwarg. Adding it is the same
            # retroactive-invalidation this PR's own forge lesson is about — so fall
            # back rather than misreport, and refuse when a specific repo was required.
            if target is not None:
                return Finding(decision, "park", park.issue, UNVERIFIABLE,
                               f"this forge does not accept target_repo, so the query would "
                               f"hit the wrong repo — refusing rather than answering wrongly")
            issue = forge.get_issue(repo, n_issue)
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


def unresolved_parks(collab: Path, manifest: dict, parks: list[Park]) -> list[Park]:
    """Parks whose id matches nothing in a `file` backlog, at RECORD time.

    Recording an id the backlog never uses creates an obligation that can never be
    discharged — `check` will report unverifiable forever, because absence is no
    longer treated as proof. Catching the typo when it is typed is far cheaper than
    discovering it as permanent amber. Only meaningful for `file` backlogs; a tracker
    is queried at check time.
    """
    if _backlog_source(manifest) != "file":
        return []
    loc = (manifest.get("backlog") or {}).get("location")
    if not isinstance(loc, str) or not (collab / loc).is_file():
        return []
    text = (collab / loc).read_text(encoding="utf-8")
    return [p for p in parks if not _issue_pattern(p.issue).search(text)]


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

    seen_numbers: set[int] = set()
    for m in re.finditer(r"^### D(\d+)\b", text, re.M):
        n = int(m.group(1))
        if only is not None and n != only:
            continue
        if n in seen_numbers:
            continue  # duplicate heading: reported once by _entry_span below
        seen_numbers.add(n)
        start, end = _entry_span(text, n)
        try:
            block = parse_block(text[start:end], where=f"D{n}")
        except DecisionError as exc:
            # OUTSTANDING, not UNVERIFIABLE: corrupting the block would otherwise be
            # the easiest way to turn the gate green, and a parse error is not the
            # "could not reach the forge" condition ADR-009 §4 defines as unverifiable.
            findings.append(Finding(n, "park", "-", OUTSTANDING,
                                    f"reconcile block cannot be read: {exc}"))
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
