"""ADR-029 — the prior-art gate: an accepted ADR must carry a RECORDED prior-art sweep.

The failure this closes (2026-08-14, first-party): an ADR-027 session re-derived an
identity design that a 2026-08-04 vault spike had already decided against. Nothing
was lost and nothing was wrong — the work was simply *re-done*, because no step in
the ADR-authoring path ever asks "was this already decided?". The vault existed
precisely to prevent that, and it was never consulted.

The rule (ADR-029 §4): every ADR that reaches ``status: accepted`` carries a
populated prior-art block naming **what corpus was searched** and **what was found**.
This module refuses the ADR when it does not. Deterministic, exit-nonzero,
guard-style — not a lint warning (ADR-004's class distinction: this is a gate on an
artifact, checked before the artifact is treated as canonical).

What is enforced, and what is NOT
---------------------------------
Enforced: a sweep was **recorded** — corpora named, queries named, dates given, hits
either cited or explicitly dispositioned, and ``hits: []`` written out rather than
left implicit by omission.

**Not** enforced: that the sweep was any good. Recall quality is a different axis
entirely (AGENT-TASKS P3.3/P3.4 — the memory work). This gate converts "I forgot to
check" from silent to blocked. It cannot convert "I checked badly" into anything at
all, and ADR-029 §7 says so in those words. Overclaiming here would be the exact
label-is-not-evidence error this repo keeps writing ADRs about.

Storage
-------
A marker-delimited YAML region inside the ADR's own prior-art section — the ADR-009
§3 precedent, for the same reason: the substrate is the database (ADR-003 §2.2), and
the obligation must be legible in the file a human already reads. Like ADR-009's
block this is **authored primary data, not a derived view**: a malformed block is
REPORTED, never silently rewritten (ADR-003 §2.6).

Retrofit
--------
The gate binds ADRs dated on or after ``DEFAULT_SINCE``. Twenty-six accepted ADRs
predate it; failing them all on day one is how a gate teaches people to ignore it
(ADR-009 §10 Q4 made the same call for legacy decisions). Grandfathered records are
reported as ``exempt``, never as passing — and ``--since 1970-01-01`` audits the
whole corpus for anyone who wants the real number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from .frontmatter import as_date, split_frontmatter

BEGIN_MARKER = "<!-- BEGIN BARON PRIOR-ART -->"
END_MARKER = "<!-- END BARON PRIOR-ART -->"

#: ADRs dated before this are grandfathered (see the module docstring). This is
#: ADR-029's own acceptance date: the gate binds from the day the rule existed, and
#: not one day earlier.
DEFAULT_SINCE = date(2026, 8, 14)

#: Only files named like a numbered record are subject to the gate. ADR-TEMPLATE.md
#: and README.md are deliberately outside it — the template SHOWS the accepted shape
#: and would otherwise have to lie about its own status to survive its own rule.
ADR_FILE_RE = re.compile(r"^ADR-(\d+)[-.]", re.I)

_STATUS_ROW_RE = re.compile(r"^\|\s*\*\*Status\*\*\s*\|\s*(.+?)\s*\|\s*$", re.M)
_ACCEPTED_RE = re.compile(r"\baccepted\b", re.I)
_HEADING_RE = re.compile(r"^#{1,6}\s+.*prior[\s-]*art.*$", re.I | re.M)

#: A closed vocabulary, on purpose. A free-text corpus field would let
#: `corpus: "had a think about it"` satisfy the gate, and a gate that any string
#: passes is a spelling exercise. Adding a corpus is a spec change, which is the
#: point at which someone asks whether it is really a corpus.
CORPORA = ("repo-adr", "repo-decisions", "vault", "external")

#: What a hit can be. `distinct` is the interesting one: it is how an author says
#: "found it, it does not apply" — and it is the only disposition that must carry a
#: reason, because it is the only one that discharges a hit by ASSERTION.
DISPOSITIONS = ("supersedes", "cites", "distinct")

#: Required by default: the repo's own ADR corpus AND the owner's vault. The vault is
#: not optional here because the vault is where the 2026-08-14 incident's prior art
#: actually lived — dropping it would leave the gate green on the motivating failure.
#: Projects with no vault pass `--require repo-adr`.
DEFAULT_REQUIRED = ("repo-adr", "vault")

#: A sweep recorded this long before the ADR was accepted is reported (warning, not
#: error): it is the shape a copy-pasted block from an older ADR leaves behind.
STALE_DAYS = 90

ERROR = "error"
WARNING = "warning"


class AdrError(RuntimeError):
    """The ADR directory could not be read, or an option was invalid."""


@dataclass(frozen=True)
class Finding:
    file: str
    severity: str  # ERROR | WARNING
    check: str
    message: str

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "severity": self.severity,
            "check": self.check,
            "message": self.message,
        }


@dataclass
class AdrRecord:
    """One ADR file, as the gate sees it."""

    path: Path
    rel: str
    number: int | None
    status: str | None
    dated: date | None
    gated: bool  # accepted AND dated on/after `since`
    exempt_reason: str | None = None
    findings: list[Finding] = field(default_factory=list)


# --- reading the record ------------------------------------------------------------------


def read_status(meta: dict, body: str) -> str | None:
    """Frontmatter ``status:`` wins; fall back to the ``| **Status** | … |`` row.

    Deliberately the same precedence `export.py::_adr_status` uses. Two readers
    disagreeing about what an ADR's status IS would be worse than either being wrong.
    """
    value = meta.get("status")
    if isinstance(value, str) and value.strip():
        return value.strip()
    row = _STATUS_ROW_RE.search(body)
    if row:
        return row.group(1).strip()
    return None


def is_accepted(status: str | None) -> bool:
    """`Accepted`, `Accepted with changes`, `Accepted 2026-08-12` — all accepted.

    `Proposed`, `Adopted in part … RETIRED`, `Rejected` are not. The word is matched
    on a token boundary so `Not accepted` would also match — which is why the house
    style never writes that; a rejected ADR says `Rejected`. Erring toward gating is
    the correct direction for a fail-closed check.
    """
    return bool(status and _ACCEPTED_RE.search(status))


def record_date(meta: dict) -> date | None:
    """The ADR's own date: `accepted:` if present, else `created:`, else `date:`."""
    for key in ("accepted", "created", "date"):
        d = as_date(meta.get(key))
        if d:
            return d
    return None


def parse_block(text: str, *, where: str) -> dict | None:
    """Parse the prior-art block. ``None`` when absent; raises when malformed.

    Malformed is not the same as absent and must never be collapsed into it: an
    unparseable block would otherwise be the cheapest way through the gate.
    """
    if BEGIN_MARKER not in text:
        return None
    if END_MARKER not in text:
        raise AdrError(
            f"{where}: {BEGIN_MARKER} without a closing {END_MARKER} — refusing to "
            f"guess where the block ends"
        )
    body = text.split(BEGIN_MARKER, 1)[1].split(END_MARKER, 1)[0]
    try:
        data = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        raise AdrError(f"{where}: prior-art block is not valid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise AdrError(
            f"{where}: prior-art block must be a mapping, got {type(data).__name__}"
        )
    return data


# --- the gate ------------------------------------------------------------------------------


def _check_searched(rel: str, block: dict, required: tuple[str, ...], dated: date | None) -> list[Finding]:
    out: list[Finding] = []
    searched = block.get("searched")
    if not isinstance(searched, list) or not searched:
        out.append(Finding(
            rel, ERROR, "prior-art-searched-missing",
            "the prior-art block records no `searched:` entries — an ADR may not be "
            "accepted on a sweep that was never described. List each corpus you "
            f"actually searched (one of: {', '.join(CORPORA)}), with the query and date.",
        ))
        return out

    seen: set[str] = set()
    for i, entry in enumerate(searched):
        at = f"searched[{i}]"
        if not isinstance(entry, dict):
            out.append(Finding(rel, ERROR, "prior-art-search-incomplete",
                               f"{at} is not a mapping"))
            continue
        corpus = entry.get("corpus")
        if not isinstance(corpus, str) or corpus not in CORPORA:
            out.append(Finding(
                rel, ERROR, "prior-art-search-incomplete",
                f"{at}: `corpus: {corpus!r}` is not one of {', '.join(CORPORA)}. The "
                f"vocabulary is closed so that a corpus name means something.",
            ))
        else:
            seen.add(corpus)
        query = entry.get("query")
        if not isinstance(query, str) or not query.strip():
            out.append(Finding(
                rel, ERROR, "prior-art-search-incomplete",
                f"{at}: `query:` is missing or empty. What you searched FOR is the part "
                f"a later reader needs in order to judge whether your sweep was narrow.",
            ))
        d = as_date(entry.get("date"))
        if d is None:
            out.append(Finding(rel, ERROR, "prior-art-search-incomplete",
                               f"{at}: `date:` is missing or not an ISO date (YYYY-MM-DD)"))
        elif dated and (dated - d).days > STALE_DAYS:
            out.append(Finding(
                rel, WARNING, "prior-art-search-stale",
                f"{at}: searched {d.isoformat()}, {(dated - d).days} days before this ADR "
                f"was accepted ({dated.isoformat()}) — that is the shape a block "
                f"copy-pasted from an older ADR leaves behind. Re-run the sweep or say "
                f"in prose why the old one still holds.",
            ))

    missing = [c for c in required if c not in seen]
    if missing:
        out.append(Finding(
            rel, ERROR, "prior-art-corpus-missing",
            f"required corpus not searched: {', '.join(missing)} (searched: "
            f"{', '.join(sorted(seen)) or 'nothing'}). The vault is required because the "
            f"2026-08-14 incident's prior art lived there and nowhere else; a project "
            f"without one passes `--require repo-adr`.",
        ))
    return out


def _check_hits(rel: str, block: dict, adr_dir: Path) -> list[Finding]:
    out: list[Finding] = []
    if "hits" not in block:
        out.append(Finding(
            rel, ERROR, "prior-art-hits-missing",
            "the prior-art block has no `hits:` key. A sweep that found nothing must say "
            "so explicitly — write `hits: []`. Omission is indistinguishable from never "
            "having looked, which is the whole failure this gate exists for.",
        ))
        return out
    hits = block.get("hits")
    if hits is None:
        hits = []
    if not isinstance(hits, list):
        out.append(Finding(rel, ERROR, "prior-art-hit-incomplete",
                           f"`hits:` must be a list, got {type(hits).__name__}"))
        return out

    for i, hit in enumerate(hits):
        at = f"hits[{i}]"
        if not isinstance(hit, dict):
            out.append(Finding(rel, ERROR, "prior-art-hit-incomplete",
                               f"{at} is not a mapping"))
            continue
        ref = hit.get("ref")
        if not isinstance(ref, str) or not ref.strip():
            out.append(Finding(rel, ERROR, "prior-art-hit-incomplete",
                               f"{at}: `ref:` is missing — name what you found"))
            ref = None
        disp = hit.get("disposition")
        if disp not in DISPOSITIONS:
            out.append(Finding(
                rel, ERROR, "prior-art-hit-incomplete",
                f"{at}: `disposition: {disp!r}` is not one of {', '.join(DISPOSITIONS)}",
            ))
        elif disp == "distinct":
            note = hit.get("note")
            if not isinstance(note, str) or not note.strip():
                out.append(Finding(
                    rel, ERROR, "prior-art-hit-incomplete",
                    f"{at}: `disposition: distinct` needs a `note:` saying why the prior "
                    f"art does not apply. It is the one disposition that discharges a hit "
                    f"by assertion, so the assertion has to be on the record.",
                ))
        if ref and disp == "supersedes":
            out.extend(_check_ref_resolves(rel, at, ref, adr_dir))
    return out


def _check_ref_resolves(rel: str, at: str, ref: str, adr_dir: Path) -> list[Finding]:
    """A superseded ref that points at a file in THIS adr dir should exist.

    WARNING, not error: refs legitimately point into the vault or another repo, which
    baron cannot read (ADR-009 §4's `unverifiable`). Only a ref that names a local ADR
    file is checkable at all, and only its existence — never the back-pointer the
    house convention asks for. Verifying that would mean editing the other record.
    """
    name = ref.strip().split("#", 1)[0].rstrip("/")
    base = Path(name).name
    if not ADR_FILE_RE.match(base):
        return []
    if (adr_dir / base).is_file():
        return []
    return [Finding(
        rel, WARNING, "prior-art-ref-unresolved",
        f"{at}: `{ref}` names an ADR file that is not in this directory — it may live on "
        f"an unmerged branch (the numbering convention reserves those), in which case this "
        f"warning is correct and expected.",
    )]


def check_file(path: Path, adr_dir: Path, *, since: date, required: tuple[str, ...]) -> AdrRecord:
    rel = path.name
    m = ADR_FILE_RE.match(rel)
    number = int(m.group(1)) if m else None
    text = path.read_text(encoding="utf-8")
    meta, body = split_frontmatter(text)
    meta = meta or {}
    status = read_status(meta, body)
    dated = record_date(meta)

    rec = AdrRecord(path=path, rel=rel, number=number, status=status, dated=dated, gated=False)

    if not is_accepted(status):
        rec.exempt_reason = f"status is {status!r}, not accepted"
        return rec
    if dated is None:
        # No date at all: cannot place it relative to the effective date. Grandfather
        # it rather than fail it — an undated record is a pre-existing-corpus smell,
        # and `--since 1970-01-01` still surfaces it for anyone auditing.
        rec.exempt_reason = "no accepted/created/date in frontmatter — cannot date it"
        return rec
    if dated < since:
        rec.exempt_reason = f"dated {dated.isoformat()}, before the gate's effective date {since.isoformat()}"
        return rec

    rec.gated = True
    try:
        block = parse_block(text, where=rel)
    except AdrError as exc:
        rec.findings.append(Finding(rel, ERROR, "prior-art-block-malformed", str(exc)))
        return rec

    if block is None:
        rec.findings.append(Finding(
            rel, ERROR, "prior-art-block-missing",
            f"accepted ADR carries no prior-art block. Add a `## Supersedes / Prior art` "
            f"section with a {BEGIN_MARKER} … {END_MARKER} region recording the sweep "
            f"(ADR-029 §4b). `baron adr scaffold` prints one.",
        ))
        return rec

    if not _HEADING_RE.search(body):
        rec.findings.append(Finding(
            rel, WARNING, "prior-art-section-missing",
            "the block is present but no heading mentions prior art — a human reading "
            "the rendered ADR will not find it (the block is an HTML comment region).",
        ))

    rec.findings.extend(_check_searched(rel, block, required, dated))
    rec.findings.extend(_check_hits(rel, block, adr_dir))
    return rec


def check_dir(
    adr_dir: Path, *, since: date = DEFAULT_SINCE, required: tuple[str, ...] = DEFAULT_REQUIRED
) -> list[AdrRecord]:
    if not adr_dir.is_dir():
        raise AdrError(f"no such ADR directory: {adr_dir}")
    for c in required:
        if c not in CORPORA:
            raise AdrError(f"unknown corpus {c!r} in --require (known: {', '.join(CORPORA)})")
    out: list[AdrRecord] = []
    for path in sorted(adr_dir.glob("*.md")):
        if not ADR_FILE_RE.match(path.name):
            continue  # README.md, ADR-TEMPLATE.md — not numbered records
        out.append(check_file(path, adr_dir, since=since, required=required))
    return out


def errors_of(records: list[AdrRecord]) -> list[Finding]:
    return [f for r in records for f in r.findings if f.severity == ERROR]


def warnings_of(records: list[AdrRecord]) -> list[Finding]:
    return [f for r in records for f in r.findings if f.severity == WARNING]


SCAFFOLD = f"""## Supersedes / Prior art

<Prose: what you set out to find, and what the sweep changed about this ADR. The block
below is the machine-checked part; this paragraph is the part a reader actually uses.>

{BEGIN_MARKER}
searched:
  - corpus: repo-adr
    location: docs/adr
    query: "<the terms you actually searched>"
    date: <YYYY-MM-DD>
  - corpus: vault
    location: <vault path or name>
    query: "<the terms you actually searched>"
    date: <YYYY-MM-DD>
hits: []          # `[]` means the sweep found nothing — say it, never omit it
# hits:
#   - ref: docs/adr/ADR-0NN-slug.md
#     disposition: supersedes | cites | distinct
#     note: <required for `distinct`: why the prior art does not apply>
{END_MARKER}
"""
