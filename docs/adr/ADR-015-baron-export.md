---
created: 2026-08-09
type: decision
status: proposed
decided_by: Vikram (pending)
adr: 015
project: barony
related:
  - "[[docs/adr/ADR-003-baron-cli]]"
  - "[[docs/adr/ADR-002-ways-of-working-2026-07]]"
  - "[[docs/adr/ADR-009-baron-decision-reconciliation]]"
---

# ADR-015 (PROPOSED): `baron export` — the governed corpus as citable records, and why the knowledge adapter is NOT shipped

| Field | Value |
|---|---|
| **Status** | **Proposed** — the export ships; the knowledge-substrate adapter is deliberately withheld pending §4's owner decision |
| **Date** | 2026-08-09 |
| **Authors** | Claude (the Cognee workstream of the 2026-08 hardening effort) |
| **Scope** | `AGENT-TASKS.md` **3.4** — pluggable knowledge substrate + semantic-memory spike |
| **Decision owner** | Vikram |
| **Blocking question** | §4.1 — projection or authoritative source? |

> **This ADR proposes; it does not decide.** §4.1 is an owner call that predates this
> workstream (`projects/AgentBootstrapNasikoMix/2026-08-04-codex-agent-reconciliation.md`,
> reconciliation item C) and is still open. Nothing here forecloses either answer.

## 1. Summary

The Cognee workstream was scoped to build a knowledge-substrate plugin. It ships **one
command and no plugin**:

```
baron export [--collab .] [--kind adr|decision|finding|handoff]... [--json]
```

`baron export` walks the four corpora a Barony collab repo already keeps — `docs/adr/*.md`,
`decisions/index.md`, `findings/index.md`, `_handoff/**.md` — and emits one flat record per
artifact, each naming the commit whose bytes were parsed. It adds **no dependency, no
entry-point group, no protocol, no network call, and no vendor name anywhere in the
package**.

That is a deliberate scope cut, argued in §4. The short version: the citation requirement in
3.4 is the hard part and it is backend-independent; the plugin seam is the easy part and it
is public API that cannot be retracted once published, on a task that is explicitly gated on
a measurement harness (3.3) that does not exist.

## 2. Context — what 3.4 actually asks for

`AGENT-TASKS.md` 3.4 requires the substrate contract to cover *stable IDs, append/update/
supersede, queries, citations to original evidence, transactions/idempotency, namespace
isolation, export/rebuild, retention, and health*, and states the non-negotiable:

> Every retrieval result must carry an authoritative source ID/version (path+commit SHA for Git).

Read carefully, that sentence is a requirement on the **producer**, not the backend. If the
corpus cannot be walked into records that each carry a verifiable `path@commit_sha`, no
backend can satisfy 3.4, whichever backend is chosen. If it can, every candidate backend
inherits the property for free. The producer is therefore the piece worth building first,
and the only piece whose value is independent of the §4.1 decision.

3.4 also fixes the corpus: *"initial adapter is read-only indexing of ADRs/decisions/
findings/handoffs/curated status; exclude raw transcripts."* This export implements exactly
that list minus curated status (§7).

## 3. Decision — the record format and the citation gate

### 3.1 The record

Nine keys. The first eight are the frozen contract; `meta` is the open bag.

| Key | Type | Notes |
|---|---|---|
| `id` | string | `F40`, `D57`, `ADR-009`, or a handoff filename stem |
| `kind` | string | one of `adr`, `decision`, `finding`, `handoff` |
| `title` | string | ledger heading text, ADR/handoff `# ` H1, or the index-table cell |
| `path` | string | **repo-root-relative**, posix (see below) |
| `commit_sha` | string | the commit whose content was parsed — **always non-empty**, under every flag including `--allow-dirty` (§3.2) |
| `status` | string \| null | handoff frontmatter / ADR status; **null for findings and decisions** |
| `body` | string | the entry prose, frontmatter stripped |
| `links` | list | `{type: url\|path\|wikilink\|ref, target}` |
| `meta` | object | kind-specific extras: ledger `date`/`author`/`form`, ADR frontmatter, handoff `for`/`from`/`created`/`priority`/`archived` |

`path` is **repo-root-relative, not `--collab`-relative**, because its job is to be pasted
into `git show <commit_sha>:<path>` — and `git show`'s `rev:path` resolves from the repository
root regardless of cwd. In every documented Barony layout (collab repo == git root) the two
forms are identical; when the collab repo is a subdirectory, the envelope's `repo_prefix`
recovers the collab-relative form. This is also where git's own path bases disagree —
`git status --porcelain` reports from the repo root while `git ls-files` reports from the cwd
— so the reconciliation has a dedicated test rather than a comment.

The **primary key is `(kind, id)`**, not `id`. Ledger IDs are unique per prefix within a
project and handoff stems are date-prefixed, so collisions are practically absent — but a
duplicate is reported in `duplicates[]` rather than silently overwritten, matching
`baron index`'s report-only posture toward ledger numbering.

`status` is null for findings and decisions because **the canon gives them no lifecycle
field**. Decision supersession is prose (`D51 — Correct D47: …`), and a regex over prose that
produced `status: "superseded"` would be exactly the enforced-vs-instructed overclaim ADR-002
bans. A null that means "this corpus has no machine-readable status" is worth more than a
guess.

### 3.2 The citation gate — the load-bearing decision

**A record is emitted only if its source file is tracked and unmodified.** Then
`git show <commit_sha>:<path>` returns byte-for-byte what was parsed, and the citation is
verifiable rather than decorative. Sources failing the test are **skipped and named** in
`skipped[]` with a reason (`uncommitted` / `modified`) and a count of the records lost.

The three rejected alternatives:

- *Emit with `commit_sha: null`.* Breaks the format invariant, and downstream sinks would
  have to re-derive the rule. A null SHA is a record you cannot cite, i.e. not a record.
- *Emit with the last-touching SHA anyway.* This is the actively harmful option: the
  citation resolves, looks authoritative, and returns different text than the record body.
  A semantic-memory index full of confidently-wrong citations is worse than no index.
- *Refuse the whole export when anything is dirty.* One uncommitted handoff should not
  destroy the other 283 records.

`--allow-dirty` relaxes the gate **for modified tracked sources only**, stamping
`meta.dirty: "modified"` on each affected record so the caveat travels with the data instead
of with the invocation. It deliberately does **not** cover untracked sources: those have no
commit to name, and emitting them would mean an empty `commit_sha`, contradicting the §3.1
invariant and the first rejected alternative above. The honest reading of the flag is
"modified too", never "uncited too" — locked by
`test_allow_dirty_still_refuses_untracked_sources`.

**Implementation note — `git status --porcelain -z` is mandatory, not stylistic.** Plain
`--porcelain` C-quotes any path containing a non-ASCII byte, a space, a quote or a control
character (`"_handoff/2026-01-02-caf\303\251.md"`), while `git ls-files -z` returns the raw
UTF-8 name. Reconciling the two by stripping quote characters leaves the octal escapes
intact, so the names never compare equal, the file tests **clean**, and it is emitted with a
SHA that does not match its bytes — the gate fails *open*, producing exactly the
confidently-wrong citation this section rejects, and only on the filenames no ASCII fixture
covers. `-z` emits raw unquoted paths and removes the failure mode at source;
`-c core.quotePath=false` was rejected because it fixes only the non-ASCII half and leaves
spaces and quotes escaped. The consequence to parse for: under `-z` there is no `' -> '`
separator, and a rename/copy spans two NUL-terminated fields (`XY <dest>\0<src>\0`).
Regression-tested with a literal non-ASCII filename, because the original ASCII-only gate
tests passed while the bug was live.

### 3.3 Determinism

Two consecutive runs must produce identical bytes, or nothing downstream can do incremental
sync. Concretely: records are sorted by `(KIND_ORDER, natural-sort of id)`; sets are sorted
before emission; YAML dates are coerced to ISO strings; and `age_days` — which
`baron handoff list` computes — is **dropped**, because it is a function of today.
`test_records_are_byte_stable_across_consecutive_runs` locks this.

## 4. What is deliberately NOT here, and why

### 4.1 The blocking owner decision

`AGENT-TASKS.md` 3.4 evaluates the semantic-memory backend two ways: **(a)** a rebuildable
projection over git+markdown, and **(b)** a candidate *authoritative* knowledge source. The
2026-08-04 reconciliation flagged that (b) contradicts the architect's product-vision
**invariant #1**:

> The repo is the only source of truth. Any hosted surface is a cache, rebuildable from
> `git clone`. `cat` always works; the product is never on the read path.

That is still open. The recommendation is **(a)**: keep the substrate strictly a projection,
and amend 3.4 to drop mode (b). Two supporting facts, neither decisive alone:
`docs/BACKLOG.md` § *Centralized cross-project memory substrate* records that this surface
was cut once already after five reviews and is "build only on real demand"; and mode (b)
would put a credentialed third-party service on the read path of a product whose entire pitch
is that the substrate is inspectable markdown.

**Nothing in this ADR depends on the answer.** The export is the input either mode consumes.

### 4.2 No entry-point group, no sink protocol

The obvious next move is a `baron.knowledge` entry-point group with a `KnowledgeSink`
protocol, mirroring `baron.forges`. It is not here, for three reasons:

1. **Sequencing.** 3.4 is gated on **3.3**, the governed-memory evaluation harness, which
   does not exist. 3.3's whole purpose is to measure whether semantic retrieval beats the
   git+markdown baseline. Shipping the adapter first inverts the project's own measure-first
   rule on the very task where that rule is written down.
2. **Irreversibility.** An entry-point group name is public API. `baron.forges` has a
   consumer (`GitHubForge`) and a documented second case (GitLab). A group with zero
   consumers is a name we would have to keep honouring for a plugin ecosystem that may never
   exist.
3. **It costs nothing to defer.** The sink is a day's work once there is something to sink
   into. The corpus walk, the citation gate, and the parsers for two ledger entry-forms are
   the part that needed doing.

`test_no_new_entry_point_group_was_published` asserts `baron.forges` is still the only group,
so a future change here is a deliberate, reviewed act.

### 4.3 No vendor in core

Any `import cognee` under `cli/src/baron/` is a straight **ADR-003** violation (runtime
dependencies are typer + pyyaml, full stop). When an adapter is built it ships as a **separate
distribution** (`barony-cognee`) declaring its own dependency, following the
`[project.optional-dependencies].pydantic-ai` + clean-ImportError precedent — or it does not
ship. Two tests lock this: the dependency list is asserted to be exactly `["typer", "pyyaml"]`,
and `cli/src/baron/**.py` is asserted to contain no occurrence of the vendor's name at all
(which is why this ADR, not the module docstring, is where the vendor is discussed).

## 5. Format versioning

The payload carries `"format": "baron.export/v1"`. The rule:

- Adding a **`meta` key** is not a version change. `meta` is explicitly open.
- Adding a **core field** is not a version change either — consumers must ignore unknown keys.
  (`author` and `date` at top level are the likeliest additions; they live in `meta` today.)
- Changing the meaning or type of a core field, or changing the ID scheme, **is** `v2`.

`test_cli_json_shape` pins the core key set, so widening it is a visible diff.

**Link targets are literal, not resolved.** A project writing `ADR-0007` and one writing
`ADR-7` emit different `ref` tokens; joining them is the consumer's job. Ref extraction is a
regex over prose and is recall-biased — an occasional false positive is the accepted cost of
catching cross-references nobody bothered to hyperlink. This is observation, not enforcement,
so the asymmetry is the right way round (the same reasoning that keeps the capability
vocabulary frozen keeps this one loose).

## 6. Honest bounds — what is NOT verified

- **No semantic-memory backend was run.** No `cognify`, no `remember`, no index, no
  retrieval, no Recall@k. The vendor's documented surface was read, not exercised. Nothing in
  this change claims a working integration, because none was built.
- The vendor's V1 API (`remember` / `recall` / `improve` / `forget`, legacy `add` / `cognify`
  / `search`, `COGX` export) and its deployment shape (managed cloud with a free key at
  `platform.cognee.ai`, or self-host on Postgres / a Rust build) come from its public docs
  read on 2026-08-09. The exact env-var names and the minimum credential set for a local run
  **could not be confirmed from the published docs**, so no claim is made about them beyond
  this: the ingest path is LLM- and embedding-backed, so it requires credentials, and an
  end-to-end integration could not have been verified in this workstream regardless of scope.
- The export's own numbers, by contrast, are measured: 284 records (62 decisions, 62
  findings, 160 handoffs) from `baddie-analyzer-collab`, and 10 ADRs from this repo
  (ADR-015 is itself exported). All 284 citations were checked by **byte-equality** —
  `git show <sha>:<path>` compared against the file on disk, 0 mismatches — not merely by
  `git cat-file -e`, which a miscited record also passes.

## 7. Known limitations

- **Curated status is not exported.** 3.4 lists it; `wiki/status.md` has no schema and
  `baron status` already emits `--json`. Deferred rather than guessed at.
- **ADRs in the code repo are invisible.** `baddie-analyzer-collab` keeps its ADRs in the
  *code* repo, so its export has zero `adr` records. `--adr-dir` retargets within the collab
  repo; a cross-repo walk needs the manifest and is a separate change.
- **Ledger entries are cited at file granularity.** `commit_sha` is the last commit touching
  `findings/index.md`, not the commit that wrote `F40`. The citation is exact for the bytes
  parsed, which is the property that matters; per-entry blame would need `git log -L` per
  entry and is not worth it yet.
- **One `git log` per source file.** ~50 subprocesses on a large collab repo (measured: 284
  records in well under a second). Batching is available if it ever matters.
- **Non-git collab directories are refused outright.** There is no provenance-free mode, by
  design.

## 8. Consequences

- Anyone can answer "what has this project decided, and where is the evidence" with
  `baron export --json | jq`, today, with no backend and no service.
- 3.4's hardest requirement is discharged and testable before a backend is chosen, so the
  eventual bake-off compares retrieval quality rather than plumbing.
- Barony gains a stable extraction point that a `baron.knowledge` sink, a static site, or an
  audit script can all read — without any of them being committed to yet.
- The owner decision in §4.1 stays open, and the cost of either answer stays the same.
