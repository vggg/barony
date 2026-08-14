---
created: 2026-08-14
type: decision
status: proposed
adr: 031
project: barony
related:
  - "[[docs/adr/ADR-015-baron-export]]"
  - "[[docs/adr/ADR-022-substrate-invariant-amended-default-not-only]]"
---

# ADR-031 (PROPOSED): the governed-memory evaluation harness — measure first, then choose a backend

| Field | Value |
|---|---|
| **Status** | **Proposed** — the harness ships; no backend is selected, built, or named |
| **Date** | 2026-08-14 |
| **Authors** | Claude (P3.3) |
| **Scope** | `AGENT-TASKS.md` **3.3**; unblocks **3.4** |
| **Decision owner** | Vikram |
| **Number** | 031. Drafted as **028**; renumbered at integration because 028 landed first as the mechanized merge gate. See `README.md § Numbering` |

## 1. Summary

`baron memeval --fixtures <dir>` scores governed-memory approaches against a
labeled fixture corpus. It materializes the fixtures into a throwaway git
repository, walks them with the **existing** `baron export` producer (ADR-015),
and reports the metrics 3.3 names: propagation precision/recall, duplicate
suppression, schema/path/status accuracy, retrieval Recall@k and MRR,
source-citation accuracy, freshness/supersession, and human intervention tax.

Two of 3.3's four approaches are **measured**; two are **declared and left
unmeasured**, because the retriever they need is 3.4's job and this harness is
the gate on 3.4. An unavailable approach reports `NOT MEASURED` with the reason.
It never reports an estimate.

Adds no dependency, no entry-point group, no vendor name, and no backend.

## 2. Context — why a harness before a backend

3.4 says the default *"remains git+markdown until 3.3 shows material retrieval
or scale benefit"*. That sentence only means something if 3.3 can produce a
number the default can lose to. Without it, "semantic memory would help here" is
a preference, and the ADR-022 boundary — a plugin may be authoritative for
derived domains and never for authority, evidence, or the ledger — would be
argued rather than measured.

ADR-015 already shipped the producer half: a deterministic walk of ADRs,
decisions, findings, and handoffs into flat records that each carry
`path + commit_sha`, with sources that cannot honour that citation skipped by
name. The harness **consumes** that walk; it does not reimplement it. That is
also why source-citation accuracy is cheap to measure here — the harness
resolves every `git show <commit_sha>:<path>` it reports on.

## 3. Decision — what is measured, and against what

### 3.1 The fixture set (`evals/governed-memory/`)

A `corpus/` tree shaped like a collab repo plus a `fixtures.yaml` carrying the
build manifest, the labeled queries, and the labeled events. The manifest is
ordered commits, so records get distinct SHAs and the citation check has
something to fail on; it also names the two sources that deliberately cannot be
cited (one committed-then-modified, one never committed) and the one file that
sits outside the four exported corpora.

The case set 3.3 enumerates is covered and asserted by test: routine commit,
release, accepted / proposed / parked / superseded ADR, thesis-changing finding,
duplicate event, and bad/missing source-SHA.

**The flagship fixture is the 2026-08-04 identity incident**, the one this repo
actually lived through: an un-onboarded agent committed under the owner's
identity, a survey note was written, and a decision promoted it. In the fixtures
that is a finding, a handoff pointing at the survey, an ADR that accepts it, and
a second handoff in which another persona re-derives the same question a day
later. Its numbers are pinned in `cli/tests/test_memeval.py` — the case the
harness exists to prevent is a regression test, not a demo.

### 3.2 The approaches

| # | Approach | Propagator | Retriever | Status |
|---|---|---|---|---|
| 1 | `git-markdown` | keyword match over a commit subject | literal term match over the exported corpus | **measured** |
| 2 | `hooks` | rule table over structured event fields | literal term match | **measured** |
| 3 | `semantic` | keyword match | *unregistered* | not measured |
| 4 | `hooks+semantic` | rule table | *unregistered* | not measured |

The baseline is a faithful `rg -w`: a record is a candidate only if a query term
appears in it as a whole word, ranked by distinct terms matched then by
frequency. Its misses are real misses.

### 3.3 The seam left for 3.4

`memeval.RETRIEVERS` is an **in-process dict** with one entry, and
`register_retriever(name, factory)` adds to it. That is deliberately *not* an
entry-point group: ADR-015 §4's rule — a published group with no consumer is
public API that cannot be retracted — is not repealed by 3.3. A dict inside one
process is retractable in a patch release. When 3.4 builds a retriever, it
registers it, and approaches 3 and 4 start reporting numbers with no change to
this harness.

## 4. The honest bound

**This measures retrieval and propagation quality on fixtures.** It is not a
live audit of any repository, it observes no running fleet, and a number it
prints is a statement about the fixture set and nothing else. The bound is a
constant in the module, printed on the table, and carried in the JSON envelope
as `honesty_bound`, so it cannot be dropped by quoting the output.

Three further limits, stated rather than discovered later:

1. **The `hooks` propagator encodes the same policy the labels do.** It is
   `CLAUDE.md`'s propagate/don't-propagate rules mechanized, scored against gold
   labels derived from those rules, so a high score is partly definitional. What
   the comparison *actually* isolates is the effect of reading **structure**
   instead of **text**: duplicate suppression on a reworded re-report, and
   refusing to propagate an event whose source SHA is missing. Read those two
   columns; discount the rest.
2. **22 records is a small corpus, and small corpora flatter literal search.**
   The vocabulary-mismatch query (Q2) was written to defeat term overlap and
   did not — the baseline scored 1.0 on it. That is reported as measured, not
   corrected by rewriting the corpus until the expected answer appears.
3. **No latency, index-size, or scale metric is collected.** 3.4's "or scale
   benefit" clause is not addressed here.

## 5. What this ADR does NOT authorise

Unchanged by shipping the harness, and asserted by test:

- **No knowledge backend is built or selected.** `RETRIEVERS` has one entry.
- **No `baron.knowledge` entry-point group.** The published groups are still
  `baron.forges` and `baron.sinks`.
- **No vendor is named, run, ingested, or measured.** Nothing about the vendor
  has been run (ADR-015 §6 is unchanged and still true).
- **No new runtime dependency.** Still typer + pyyaml (ADR-003).
- **ADR-022 stands.** Any future semantic layer is a rebuildable projection over
  git+markdown; authority, evidence, and the ledger stay in the repo.

## 6. Consequences

3.4 has a gate it can pass or fail. The first number it has to beat is on the
board, and the first finding is already actionable and was not the expected one:
on the flagship query the baseline retrieves **every in-corpus gold record at
rank 1**, and its only miss is a document `baron export` never walks. On this
fixture set the binding constraint is **corpus coverage, not ranking** — which
argues that 3.4's first move is widening what gets exported (curated status,
the research notes that live outside the four corpora), and that a semantic
retriever bolted onto the same 22 records would have had little left to win.

The cost of the ADR-015 citation gate also has a number now: one labeled query
is unanswerable because its answer sits in an uncommitted file. That is the
gate working as designed, priced rather than assumed.

## 7. Supersedes / Prior art

Recorded under **ADR-029**, which was on a parallel branch when this ADR was drafted and is
live in CI by the time it lands. This ADR is `status: proposed`, so the gate treats it as
**exempt** rather than gated; the block is written anyway, because a sweep an ADR acquires
only at the moment someone accepts it has the discipline backwards.

The sweep looked for two things: an existing retrieval-evaluation protocol in the estate that
this harness should have reused instead of inventing, and any prior decision that already
picked a knowledge backend (which would make the harness moot). It found the first and not
the second. The vault carries a **completed Precision@5 / Recall@5 protocol from GardenTwin**
(2026-05-27) whose method this harness converges on independently — binary relevance
judgements, a small hand-labeled target set, anomalies reported rather than smoothed. Reading
it did not change the design, but it did change §4: GardenTwin's protocol names its own
small-corpus bias in the same terms, and the honest-bound section is stronger for citing a
second instance of the failure than for claiming the observation as novel.

<!-- BEGIN BARON PRIOR-ART -->
searched:
  - corpus: repo-adr
    location: docs/adr
    query: "retrieval, recall, MRR, embedding, semantic memory, knowledge backend, evaluation harness, benchmark"
    date: 2026-08-14
  - corpus: repo-decisions
    location: STATUS.md, AGENT-TASKS.md, CHANGELOG.md, docs/, open branches on vggg/barony
    query: "governed memory, memeval, P3.3, P3.4, baron.knowledge, semantic adapter"
    date: 2026-08-14
  - corpus: vault
    location: /Users/vikram/Obsidian/Brain
    query: "recall@, precision@, retrieval eval, memory eval, semantic memory, embedding, vector, governed memory, knowledge backend"
    date: 2026-08-14
hits:
  - ref: docs/adr/ADR-015-baron-export.md
    disposition: cites
    note: >-
      §4.2 withholds the knowledge adapter pending a measurement; this is that measurement.
      Its walker is consumed rather than rebuilt, and §4's entry-point-group rule is upheld
      here (§5) rather than quietly repealed.
  - ref: docs/adr/ADR-022-substrate-invariant-amended-default-not-only.md
    disposition: cites
    note: >-
      settles that a semantic layer would be a rebuildable projection, not an authority.
      That is what makes measuring approaches legitimate at all — §5 restates the bound.
  - ref: /Users/vikram/Obsidian/Brain/projects/GardenTwin/ClaudeAnalyst/research/2026-05-27-precision5-eval-protocol.md
    disposition: cites
    note: >-
      the estate's prior retrieval-eval protocol (Precision@5 / Recall@5 proxy, binary
      relevance, anomalies reported not smoothed). Different domain — plant-image
      similarity, not governed records — so its harness is not reusable, but its method
      is the same and §4's small-corpus caveat is borrowed from it rather than re-derived.
  - ref: /Users/vikram/Obsidian/Brain/projects/GardenTwin/decisions/2026-05-15-1806-agentic-memory-embeddings.md
    disposition: distinct
    note: >-
      an accepted embeddings decision in the estate, and the nearest thing to "a backend was
      already chosen". Distinct: it is GardenTwin's product decision over plant images with
      a pgvector store, made against a different substrate and with no governance-record
      semantics. It does not pre-decide Barony's backend, and §5 still selects none.
  - ref: /Users/vikram/Obsidian/Brain/projects/AgentBootstrapNasikoMix/phase-3-plan.md
    disposition: cites
    note: >-
      records "centralized cross-project memory" as an unprompted demand signal from the
      launch thread, explicitly "not a spec to build yet". This harness is the measure-first
      step that plan asks for, not the build it defers.
<!-- END BARON PRIOR-ART -->
