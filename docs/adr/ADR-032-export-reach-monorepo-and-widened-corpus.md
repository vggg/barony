---
created: 2026-08-14
accepted: 2026-08-14
type: decision
status: accepted
decided_by: Vikram (decision #5, owner-approved 2026-08-14)
adr: 032
project: barony
related:
  - "[[docs/adr/ADR-015-baron-export]]"
  - "[[docs/adr/ADR-022-substrate-invariant-amended-default-not-only]]"
  - "[[docs/adr/ADR-025-coordination-monorepo]]"
---

# ADR-032 (ACCEPTED): `baron export` reaches the whole estate — the monorepo walk, and the corpus P3.3 said was the binding constraint

| Field | Value |
|---|---|
| **Status** | **Accepted** (2026-08-14) |
| **Date** | 2026-08-14 |
| **Authors** | Claude (dev) |
| **Decision owner** | Vikram — owner-approved as decision #5 |
| **Scope** | `baron export` (ADR-015): topology coverage + corpus coverage |

## 1. Summary

Two changes to `baron export`, both about **what the walker can see**:

1. **It is monorepo-aware.** Run at an ADR-025 coordination-monorepo root it walked no
   project subdir and reported **0 records**, while per-project runs returned real counts.
   It now walks the registry in `.baron-monorepo.yaml` and aggregates, with per-project
   provenance on every record.
2. **The corpus can be six kinds, not four.** `status` (curated status) and `note`
   (`wiki/`, `docs/notes/`) join the four ledgers, behind **`--wide`** — the capability
   closes the gap ADR-015 §7 recorded as a deferral and 3.4 named in its own corpus list,
   while the *default* record set stays the four ledgers so no existing consumer moves.
   §3.1 records why that default was amended at integration.

Neither change touches the citation gate, and neither builds a knowledge backend. ADR-015
§4.2 and ADR-022 §5.1 are untouched: no `baron.knowledge` group, no vendor, no new
dependency. The three guard tests stay green and were not relaxed.

## 2. Context — why now, and why coverage rather than ranking

### 2.1 The monorepo bug

Found by running `baron export` at a real coordination-monorepo root. Measured, before:

```
$ baron export --collab <root>          →  0 record(s)
$ baron export --collab <root>/barony   →  2 record(s)   (adr=1, finding=1)
$ baron export --collab <root>/_meta    →  2 record(s)
```

`collect()` resolves its corpora relative to the directory it is handed. A monorepo root
holds no `docs/adr/`, no `findings/index.md` and no `_handoff/` — those live one level
down, in each project subdir — so every glob missed, every walk returned nothing, and the
command printed `no records` in the tone of a fact about the estate.

This is the **same silent-false-zero class** as ADR-025 §6.8's health bug, and the exact
instance §6.3's generalisation predicted:

> any single-project check that shells out to git needs re-auditing for a shared work
> tree — the monorepo turns "the repo" and "the project" into different things, and every
> place that conflated them is a latent version of this bug.

`baron export` shells out to git for provenance *and* assumes its own nesting depth for
corpus discovery, so it was a latent version twice over. A zero from a knowledge producer
is worse than a zero from a health report: health is read by a human who might notice,
while an export is piped into an index, and an empty index answers every future question
with silence.

### 2.2 The coverage finding

**ADR-031** (P3.3) built the measurement gate P3.4 was waiting on, and returned a result that
was not the expected one. On the flagship fixture — this repo's own 2026-08-04 identity
incident — **the lexical baseline already retrieved every in-corpus gold record, the first at
rank 1**. Its only miss was a survey note in `wiki/` that `baron export` never walked.

> **Updated at integration:** ADR-031 was on unmerged PR #51 when this ADR was written, so it
> was referenced by number and deliberately not linked. **PR #51 has since landed**, and this
> branch is stacked on top of it, so
> [ADR-031](ADR-031-governed-memory-eval-harness.md) is now a live link. That change is not
> cosmetic — it is why §3.1 was amended: a merged ADR-031 means the export has a consumer in
> the tree, and the default-corpus question stopped being hypothetical.

The binding constraint was therefore **coverage, not ranking**. Adding embeddings to 22
records that already rank correctly buys nothing; the gold answer was not badly ranked, it
was *absent*. So the first move for P3.4 is to widen what the producer reaches — which is
this ADR — and only then to ask whether a semantic layer beats the baseline on a corpus
that actually contains the answers.

## 3. Decision

### 3.1 The corpus is six kinds — opt-in, four by default

`KIND_ORDER = (adr, decision, finding, handoff, status, note)` is the set of kinds that
*exist*; `DEFAULT_KINDS = LEDGER_KINDS = (adr, decision, finding, handoff)` is what a caller
that names none *gets*.

| Kind | Source | ID |
|---|---|---|
| `status` | `wiki/status.md`, `STATUS.md` | path minus extension (`wiki/status`) |
| `note` | every `*.md` under `wiki/` and `docs/notes/` | path minus extension (`wiki/research-x`) |

Three decisions inside that table:

- **An explicit include-list, not "every `.md` in the repo."** `note` means *curated*. A
  recursive walk of the collab repo would sweep in agent templates, workspace scaffolding
  and emit-time fixtures — none of which anyone wrote to be retrieved, all of which would
  dilute a small corpus. `--note-dir` retargets, repeatable.
- **The ID is the path, not the stem.** Whole-file corpora have no ID scheme of their own
  — that is exactly what makes them not ledgers — and the path is the only thing about them
  both unique within a project and stable across runs. `wiki/x.md` and `docs/notes/x.md`
  are different notes; a stem-based ID would collide them into `duplicates[]`.
- **`status` is claimed before `note`.** `wiki/status.md` is inside a note dir, so without
  an ordering rule it would be exported twice under two kinds and two IDs. The kind that
  describes it wins. Likewise a `--adr-dir` pointing inside a note tree does not re-export
  its ADRs as notes.

**These kinds are opt-in — `--wide`, or an explicit `--kind`.** `DEFAULT_KINDS ==
LEDGER_KINDS`; a caller that names no kinds gets exactly the four-ledger record set it got
before this ADR.

> **AMENDED 2026-08-14, at integration.** As first written this section said the opposite —
> *"these kinds are on by default"*, on the argument that a widened corpus behind a flag
> leaves the default export still missing the records §2.2 identified as the binding
> constraint. That argument was made while **ADR-031 was unmerged** (§4.2), i.e. while the
> export had no consumer in the tree whose behaviour a default change could move. It has one
> now: ADR-031 landed on `main` before this branch, and `baron memeval` calls `collect()`
> with no kinds.
>
> **Measured on the integrated stack**, a six-kind default moved the harness's pinned
> numbers — MRR **81.2 → 68.8**, citation accuracy **100 → 94.4** — and failed three
> `test_memeval.py` assertions, for the two reasons §4.3 predicted. The claimed ceiling gain
> did **not** materialise either: the gold label still did not match, so the note counted as
> unreachable and the ceiling stayed 84.4%. A default that regresses the estate's only
> consumer of the thing it is widening is not a safe default, and "fix the consumer in this
> PR" would mean editing a just-merged, owner-approved harness's published numbers from a PR
> whose scope is the exporter.
>
> So the *capability* ships whole — same walker, same citation gate, same records, reachable
> by one flag — and the *default* stays where every existing consumer already is. This costs
> §2.2's argument nothing that a flag cannot buy back, and §4.3's two harness fixes become an
> ordinary follow-up on `main` rather than a merge-blocking prerequisite. When they land,
> flipping `DEFAULT_KINDS` to `KIND_ORDER` is a one-line change with a test
> (`test_the_widened_corpus_is_opt_in_not_the_default`) that will fail loudly and correctly
> to mark the moment.

### 3.2 `project` is a core record field, in both layouts

Every record carries `project` — the manifest's `project.name`, or `null` when the collab
repo has no readable manifest. **Present in the single layout too**, not only the monorepo
one: a consumer must not have to know which topology produced a payload in order to know
which project a record belongs to, and an index built from two single-project exports needs
the same attribution a monorepo export gives it for free.

Reading it is deliberately total — a malformed `manifest.yaml` yields `null`, not an error.
A directory can be a perfectly good corpus without being a well-formed Barony project, and
putting a validation failure on the read path would reintroduce a zero for a reason
unrelated to the corpus.

Per ADR-015 §5 this widens the core key set without a format bump (consumers ignore unknown
keys), but it must be a **visible diff** — `test_cli_json_shape` pins the key set and was
updated by hand.

### 3.3 The monorepo walk returns the same envelope

`collect_portfolio(root, projects)` runs `collect()` once per registered project and
concatenates. The payload is the **same `Export` shape** with `layout: "monorepo"`, plus
`projects[]` (per-project counts, path and prefix), `unregistered[]` and `unreadable{}`.

The shape is shared on purpose. The bug being fixed is a silent zero, and the fix is worth
much less if it also forces every consumer of `baron export --json | jq '.records[]'` to
learn a second payload shape depending on the producer's topology. Per-project provenance
rides on each record and on `projects[]`, so nothing is lost by flattening.

**`path` needed no adjustment, and that is load-bearing.** `_repo_prefix` already resolves
each subdir's offset from the git top-level, so a record walked in `<root>/barony` comes
back as `barony/docs/adr/ADR-001-topology.md` and `git show <sha>:<path>` works from the
root exactly as ADR-015 §3.1 requires. The ADR-015 design note that `path` is
repo-root-relative rather than collab-relative — written when "the collab repo is a
subdirectory" was hypothetical — is what made this a no-op.

`export.py` does not import `baron.monorepo` (which imports the scaffolder); the CLI reads
the registry and passes `[(dir, name)]` in. The export has no business dragging the
scaffolder onto a read path.

### 3.4 The primary key gains the project

`(project, kind, id)`, was `(kind, id)`.

In a monorepo two projects legitimately both hold an `ADR-001` and an `F1` — ADR numbers
and ledger IDs are per-project by construction. Keying on `(kind, id)` alone would have
reported the second project's entire corpus as duplicates and dropped it, trading the
silent zero this ADR fixes for a **silent halving**: the same bug wearing a different
number, and a harder one to notice because `duplicates[]` would be populated and look like
a report rather than a loss.

### 3.5 One bad leg does not zero the portfolio

A registered project that is missing, or whose walk raises, lands in `unreadable{}` by name;
the other projects still export. This is ADR-015 §3.2's rejection of "refuse the whole
export when anything is dirty" applied one level up — one unwalkable project should not
destroy the other four's records. Subdirs holding a `manifest.yaml` that the marker does
not list are reported in `unregistered[]` and **not** included, matching `baron status`'s
posture: declared *and* discovered, never silently either way.

## 4. Measured

### 4.1 The monorepo fix

On a two-project fixture monorepo, root-level export: **0 → 6 records**, matching the sum of
the per-project runs exactly, with both projects' `ADR-001` surviving and every citation
byte-verified from the root. `test_monorepo_root_export_is_not_silently_zero` asserts the
root sees what the subdirs see and fails on the pre-fix code.

### 4.2 Coverage against the P3.3 fixtures

Originally measured by overlaying this exporter onto ADR-031's harness in a scratch worktree,
because PR #51 was unmerged. **It has since landed and this branch is stacked on it**, so the
rows below are now directly reproducible — with the caveat that they describe the corpus
`--wide` produces, not the default one (§3.1, amended).

| | records | ceiling | R@5 | MRR | cite |
|---|---|---|---|---|---|
| ADR-031 baseline (four kinds) — **the default, and what ships** | 22 | 84.4 | 76.0 | 81.2 | 100 |
| + ADR-032 exporter, `--wide`, §4.3 fixes applied | 23 (`note=1`) | 87.5 | **79.2** | **75.0** | 100 |
| + ADR-032 exporter, `--wide`, §4.3 fixes **not** applied — *measured on the integrated stack* | 23 | 84.4 | 76.0 | 68.8 | 94.4 |

**The third row is why §3.1 was amended.** It is what a six-kind default actually produces
against the harness as merged: no ceiling gain at all, and two real regressions. The middle
row is reachable only once §4.3's two one-line fixes land on `main`.

**The coverage gap closes at the producer.** Q1 — the flagship, modelling the 2026-08-04
incident — goes from one permanently unreachable gold record to `unreachable: []`. The
retrieval ceiling, the share of gold answers *any* strategy could reach, rises 84.4 → 87.5,
and R@5 rises with it. That is the whole thesis of §2.2, and it is now measured rather than
argued.

**MRR fell 81.2 → 75.0, and that is a real cost, not noise.** Widening a 22-record corpus
adds competition: the research note is identity-adjacent, so on queries where it is *not*
gold it now outranks the record that used to be first, dropping that query's reciprocal
rank from 1/1 to 1/2. Reported rather than suppressed, because it is exactly the trade
P3.4 has to reason about — coverage and precision-at-1 are not the same axis, and the note
that closes Q1's gap is the note that crowds Q3's top slot. Whether a semantic layer
recovers the MRR *while keeping* the coverage is now a well-posed question, which it was
not before.

### 4.3 Two harness assumptions this exposed, now an open follow-up on `main`

Running the unmodified ADR-031 harness against this exporter first produced a *worse*
number (MRR 68.8, citation accuracy 94.4) for reasons that are not defects in the export:

- `fixtures.yaml` labels the gold note `wiki:research-agent-identity-lightweight` — a
  kind/ID scheme guessed before an exporter emitted one. The shipped record is
  `note:wiki/research-agent-identity-lightweight`, so the gold never matched and the
  retrieved note scored as a false positive.
- `memeval._citation_holds` branches on a **closed kind allowlist** — `("adr", "handoff")`
  take the whole-file path, everything else falls through to a ledger-heading regex. A
  `note` record has no `### <id>` heading, so its perfectly valid citation was scored as
  broken.

Both are one-line fixes. They were out of scope for this PR when ADR-031 was unmerged, and
they stay out of scope now that it is merged — editing a just-landed, owner-approved
harness's published numbers from the exporter's PR is exactly the coupling this section is
about. **They are the prerequisite for flipping `DEFAULT_KINDS` to `KIND_ORDER`** (§3.1),
and that is the follow-up this ADR hands to `main`.

Recorded here because the failure mode generalises: **a harness that hardcodes its
producer's vocabulary reports a producer improvement as a regression**, and a reader who saw
only the unfixed run would have concluded the widened corpus made retrieval worse. All three
§4.2 rows are reported so the correction is auditable rather than asserted.

## 5. Format versioning

Still `baron.export/v1`. Per ADR-015 §5, adding a core field (`project`) and adding kinds
are not version changes — consumers ignore unknown keys, and `kind` was always an open
enumeration read from `KIND_ORDER`. What *would* be `v2` is changing the meaning of an
existing field or the ID scheme of an existing kind, and neither happened: every record the
four-kind export emitted is emitted identically, with one more key.

The envelope gains `layout`, `project`, `projects[]`, `unregistered[]`, `unreadable{}`.
A consumer reading only `records[]` and `summary.records` is unaffected in either topology.

## 6. What is deliberately NOT here

- **No knowledge backend, no `baron.knowledge` entry-point group, no vendor.** ADR-015 §4.2
  and ADR-022 §5.1 are untouched, and their three guard tests
  (`test_no_knowledge_entry_point_group_was_published`,
  `test_baron_core_never_imports_or_mentions_cognee`,
  `test_runtime_dependencies_are_still_typer_and_pyyaml_only`) stay green and unrelaxed.
  This ADR makes the producer reach further; it does not make anything consume it.
- **No semantic retriever.** ADR-031's `semantic` row still reports `NOT MEASURED`. Widening
  the corpus is the move §2.2's finding argued for *instead of* embeddings, not a step
  toward shipping them.
- **No per-entry blame for the new kinds.** `status` and `note` are whole-file records, so
  file-granularity citation is exact for them — the limitation ADR-015 §7 records for
  ledgers does not apply here.
- **No cross-repo ADR walk.** ADR-015 §7's "ADRs in the code repo are invisible" is
  unchanged; that still needs the manifest and is still a separate change. The monorepo walk
  crosses *project subdirs of one collab repo*, not repository boundaries.

## 7. Known limitations

- **The note include-list is a convention, not a discovery.** A project keeping curated
  prose somewhere other than `wiki/` or `docs/notes/` needs `--note-dir`. Making this
  manifest-declared is the obvious next step and is deliberately not taken here — one new
  config surface per ADR.
- **`--note-dir` can be pointed at a large tree.** No cap, no warning. The include-list
  default is what keeps this honest; an operator who points it at the repo root gets what
  they asked for.
- **`note` bodies are whole files.** A long wiki page is one record with one body, so a
  retriever gets no sub-document granularity. Chunking is a consumer concern and a
  backend's job, and guessing at it here would bake a retrieval assumption into the
  producer — precisely the layering ADR-015 §2 argued against.
- **Portfolio exports are serial.** One `collect()` per project, each with its own `git
  log` per source. Fine at portfolio sizes measured so far; batching remains available.

## 8. Supersedes / Prior art

The sweep set out to find (a) any prior decision about *what* `baron export` walks, (b) any
prior treatment of monorepo-root aggregation for a read command, and (c) any prior art on
measuring retrieval coverage in the estate. It changed this ADR in two places: §3.3's
"same envelope" rule is borrowed from ADR-025 §6.8's *one plane, read once* correction
(which chose to reshape the rollup rather than the record), and §4.2 reports the MRR
regression because the GardenTwin evaluation protocol found in the vault treats
small-corpus retrieval deltas as directional rather than significant — a caveat this ADR
inherits rather than re-derives.

The most important hit is ADR-015 §7 itself: *"Curated status is not exported… deferred
rather than guessed at."* This ADR is the un-deferral, and it is a supersession of that
limitation rather than a new idea.

<!-- BEGIN BARON PRIOR-ART -->
searched:
  - corpus: repo-adr
    location: docs/adr
    query: "baron export, curated status, corpus coverage, monorepo aggregation, silent zero, knowledge substrate"
    date: 2026-08-14
  - corpus: vault
    location: /Users/vikram/Obsidian/Brain
    query: "baron export, governed corpus, knowledge substrate, semantic memory, retrieval coverage, Recall@k"
    date: 2026-08-14
hits:
  - ref: docs/adr/ADR-015-baron-export.md
    disposition: supersedes
    note: >-
      §7 records "curated status is not exported… deferred rather than guessed at"
      as a known limitation. §3.1 of this ADR un-defers it. The rest of ADR-015 —
      the citation gate, the format, §4.2's withheld adapter — is untouched and
      still governs.
  - ref: docs/adr/ADR-031-governed-memory-eval-harness.md
    disposition: cites
    note: >-
      Merged (PR #51) and stacked below this branch. Its measured finding — the miss was
      coverage, not ranking — is this ADR's entire motivation, and §4.2 reports
      against its fixtures.
  - ref: docs/adr/ADR-025-coordination-monorepo.md
    disposition: cites
    note: >-
      §6.3's generalisation predicted this bug and §6.8 is the same silent-zero
      class in `baron health`. §3.3's single-envelope decision follows §6.8's
      "one plane, read once" precedent.
  - ref: docs/adr/ADR-022-substrate-invariant-amended-default-not-only.md
    disposition: cites
    note: >-
      §5.4 holds that `baron export` "is the interface, and it was already
      right". This widens its reach without changing what it is; §5.1's refusal
      to publish `baron.knowledge` is untouched and still tested.
  - ref: _handoff/tasks/2026-08-12-1930-atlas-barony-d2-substrate-backlog.md
    disposition: distinct
    note: >-
      Vault. Records the owner's direction for a config-driven, manifest-selected
      knowledge BACKEND. Distinct: that is about which substrate consumes the
      export, this is about what the export contains. Nothing here selects or
      configures a backend, and P3.4's backend question stays open.
  - ref: projects/GardenTwin/architecture/whitepaper-agentic-memory-embeddings.md
    disposition: distinct
    note: >-
      Vault. §6's evaluation framework is the estate's prior Precision@k/Recall@k
      protocol, already cited by ADR-031 §4. Distinct here: it governs how to
      MEASURE a retrieval change, not what a governed corpus should contain. Its
      small-corpus caveat is borrowed in §4.2 rather than re-derived.
<!-- END BARON PRIOR-ART -->

## 9. Consequences

- `baron export` at a coordination-monorepo root reports the estate instead of nothing, so
  the portfolio is answerable from one command in both ADR-025 topologies. This half is
  unconditional — it is a bug fix, not a new default.
- The widened corpus is reachable (`--wide`) but not default, so this PR changes **no**
  existing consumer's record set. `baron memeval`'s ADR-031 numbers are byte-identical
  before and after.
- P3.4 is unblocked in the direction P3.3 measured: the corpus now contains the answers, so
  a semantic bake-off would compare retrieval quality rather than re-discovering that the
  gold record was absent.
- Every consumer of the export gains per-record project attribution, which an index built
  across projects needed and could not previously derive.
- The MRR cost in §4.2 gives P3.4 a concrete question it did not have: whether a semantic
  layer recovers precision-at-1 on a widened corpus.
- ADR-031's two producer-coupled assumptions (§4.3) need fixing on `main` before its
  numbers are re-run against a six-kind export.

## 10. Decision record

- [x] Approved as written — Vikram, decision #5, 2026-08-14 (owner-approved before
      implementation; this ADR records the decision as executed).
- [ ] Approved with changes
- [ ] Needs revision
- [ ] Rejected
