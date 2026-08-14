---
created: 2026-08-14
accepted: 2026-08-14
type: decision
status: accepted
adr: 029
project: barony
authors: Claude (design proposal for Vikram)
decided_by: Vikram
related:
  - "[[docs/adr/ADR-002-ways-of-working-2026-07]]"
  - "[[docs/adr/ADR-008-ways-of-working-2026-07-31]]"
  - "[[docs/adr/ADR-009-baron-decision-reconciliation]]"
  - "[[docs/adr/ADR-023-reserved-filenames]]"
---

# ADR-029 (ACCEPTED): the prior-art gate — one canonical home, and a recorded sweep before an ADR is accepted

| Field | Value |
|---|---|
| **Status** | Accepted (2026-08-14) — owner endorsed the direction the same day |
| **Authors** | Claude (design proposal for Vikram) |
| **Decision owner** | Vikram |
| **Family** | The ways-of-working line: [ADR-002](ADR-002-ways-of-working-2026-07.md) → [ADR-008](ADR-008-ways-of-working-2026-07-31.md) → [ADR-023](ADR-023-reserved-filenames.md) → this |
| **Extends** | [ADR-009](ADR-009-baron-decision-reconciliation.md) / `CONVENTIONS.md § Decision & ADR intake` — the same intake surface, one step earlier |
| **Mechanism** | `baron adr check` (fail-closed, exit-nonzero) |
| **Evidence base** | One first-party incident, 2026-08-14 (§2) |

## 1. Summary

Two rules, one of them mechanized:

- **(a) One canonical home.** A decision is not canonical until it is promoted to an
  **accepted ADR in this repo**. Vault research notes and spikes are *inputs*. The
  promotion step is required, not optional, and "it's written down in the vault" is
  not a decision having been made.
- **(b) An enforced prior-art check.** Every new ADR carries a populated
  **Supersedes / Prior art** section recording the sweep that was performed — which
  corpora were searched (this repo's `docs/adr/` **and** the owner's vault), with what
  query, on what date — and citing or explicitly superseding every hit.
  **`baron adr check` refuses an ADR marked `status: accepted` when that record is
  missing, malformed, or incomplete.**

Rule (b) is enforced by a command. Rule (a) is instructed — §6 says so plainly rather
than letting the mechanized half lend the unmechanized half its credibility.

## 2. The incident

On **2026-08-14** an ADR-027 session designed per-persona forge identity from first
principles. A **2026-08-04 vault spike had already explored that ground and decided
against a variant of the same design.** Nothing was lost and nothing shipped wrong;
the work was simply *re-derived* — which is precisely what the vault exists to prevent.

The interesting part is where the failure was **not**. The prior art was written down.
It was findable. It was in the corpus the owner maintains for this purpose. No step in
the ADR-authoring path ever *asked* whether it had been consulted, so the answer was
never wrong — it was never requested. That is the FM4 shape this repo has now written
four ADRs about: **instructed → enforced**. A discipline nobody is asked to demonstrate
degrades to a discipline nobody performs.

**The incident was larger than first recorded.** The reconciliation that followed (queue
integration, same day) found a *second* missed hit, and a worse one: **ADR-011** — an open
PR (#32) in **this repo's own `docs/adr/` corpus**, ten days old, proposing the same
mechanism from the same spike. So the ADR-027 session missed prior art in `vault` *and* in
`repo-adr`. That matters for the design, not just the anecdote: the intuition that a
prior-art sweep is mainly about the vault (the far corpus, the one that is easy to forget)
is wrong. The near corpus was missed too — and the near corpus is the one this gate can
actually check. It is also the reason `docs/adr/README.md § Numbering` now tells an author
to check the *branches*: `baron adr check` reads records, and an in-flight ADR is not yet a
record. **ADR-011 is superseded by ADR-027**, annotated both directions; PR #32 is closed.

This is a **two-hit, single-session evidence base**, thinner than ADR-002's or ADR-008's
pilot runs — the same standing ADR-023 was accepted on, and it is argued the same way: the
exposure is structural (every ADR passes through this path), not statistical.

## 3. Supersedes / Prior art

The sweep this ADR itself is required to record. It changed the design twice: the
storage shape is ADR-009's marker block rather than a new convention, and the gate is
scoped to `docs/adr/` rather than duplicating the decision-intake surface.

- **`baron decision reconcile` / ADR-009** — adjacent, not overlapping. ADR-009 acts
  *after* a decision is ratified (does it reach the work-pull surfaces?). This gate acts
  *before* one is accepted (was it already decided?). Both hang off the same intake rule,
  which is why this ADR extends that surface instead of opening a second one. ADR-009's
  marker-block storage, three-state honesty, and "amber is not green" exit rule are all
  reused verbatim below.
- **`CONVENTIONS.md § Decision & ADR intake` step 1** — already says *"Record with
  supersession … stating explicitly what it overrides."* This ADR does not invent that
  requirement; it **mechanizes the half of step 1 that was prose**, and adds the corpus
  and the sweep record, which step 1 never asked for.
- **ADR-023 §5** — deferred a lint for the reserved-filename rule, keeping the prose
  rule alone until a second collision. That is the same lever in the same repo, resolved
  the other way. Distinct: ADR-023's rule has one incident and a cheap manual check;
  this one is a *procedure* an author performs, and an unperformed procedure leaves no
  trace at all. There is nothing to notice later.
- **The vault's 2026-08-04 identity spike** — the incident's prior art. Cited as
  evidence, not superseded; it is an input, which is the whole point of rule (a).

<!-- BEGIN BARON PRIOR-ART -->
searched:
  - corpus: repo-adr
    location: docs/adr
    query: "prior art, supersedes, decision intake, ADR gate, canonical home"
    date: 2026-08-14
  - corpus: repo-decisions
    location: docs/, STATUS.md, AGENT-TASKS.md, CHANGELOG.md
    query: "prior art, supersedes, claims ladder, ways of working 2026-08"
    date: 2026-08-14
  - corpus: vault
    location: /Users/vikram/Obsidian/Brain
    query: "agent identity spike 2026-08-04, prior art, decision promotion"
    date: 2026-08-14
hits:
  - ref: docs/adr/ADR-009-baron-decision-reconciliation.md
    disposition: cites
    note: same intake surface, one step later; storage shape and exit rule reused
  - ref: docs/adr/ADR-008-ways-of-working-2026-07-31.md
    disposition: cites
    note: §4 is the decision-intake protocol this extends
  - ref: docs/adr/ADR-027-agent-identity.md
    disposition: cites
    note: >-
      the motivating incident's ADR. Merges ahead of this one; carries its own prior-art
      block at §10, which records that the corpus actually missed was `repo-adr` (an open
      PR in this repo) as well as `vault`. See §2.
  - ref: docs/adr/ADR-023-reserved-filenames.md
    disposition: distinct
    note: >-
      also a prose-vs-lint call in this repo, resolved the other way (§5 deferred
      the lint). Distinct because an unreserved filename is visible in the tree
      afterwards, whereas an unperformed prior-art sweep leaves no trace to notice.
<!-- END BARON PRIOR-ART -->

## 4. The rules

### 4a. One canonical home

> **A decision is canonical only as an accepted ADR in this repo.**

Vault notes, spikes, session transcripts and handoffs are **inputs**. They record
exploration; they do not carry decisions. The promotion step — writing the ADR here,
with a number, a status and an owner — is what makes a conclusion binding, and it is
required.

The corollary that matters more than the rule: **an input that is never promoted will be
re-derived.** The vault is not a decision store and cannot be made into one by wishing;
it has no numbering, no status field, no supersession chain, and nothing reads it at
authoring time. Rule (b) is what makes it *reachable* — by forcing the sweep — but only
rule (a) makes the outcome *durable*.

Direction of travel is one-way: vault → repo. This ADR does not ask the vault to change.

### 4b. The recorded prior-art sweep

Every ADR that reaches `status: accepted` carries a **Supersedes / Prior art** section
containing a marker-delimited block:

```markdown
<!-- BEGIN BARON PRIOR-ART -->
searched:
  - corpus: repo-adr          # one of: repo-adr, repo-decisions, vault, external
    location: docs/adr
    query: "the terms you actually searched"
    date: 2026-08-14
  - corpus: vault
    location: /Users/vikram/Obsidian/Brain
    query: "..."
    date: 2026-08-14
hits: []                      # `[]` means "found nothing" — say it, never omit it
<!-- END BARON PRIOR-ART -->
```

Each hit carries `ref` and a `disposition` of **`supersedes`** (this ADR overrides it),
**`cites`** (it stands, and informs this), or **`distinct`** (found it, does not apply)
— and `distinct` **must** carry a `note`, because it is the only disposition that
discharges a hit by assertion.

Four choices are load-bearing:

1. **`corpus` is a closed vocabulary.** A free-text field would let
   `corpus: "had a think about it"` pass, and a gate any string satisfies is a spelling
   exercise. Adding a corpus is a spec change — which is exactly the moment someone asks
   whether it is really a corpus.
2. **The vault is a required corpus by default.** Dropping it would leave the gate green
   on the very incident that motivated it. Projects with no vault pass `--require repo-adr`.
3. **`hits: []` must be written.** An omitted key is indistinguishable from never having
   looked. An explicitly empty result is a claim someone made.
4. **The block lives inside the ADR** (ADR-003 §2.2 — the substrate is the database), as
   *authored primary data*, not a derived view. Like ADR-009 §3.1's block it cannot be
   regenerated if lost, so baron **reports** a malformed block and never rewrites it
   (the ADR-003 §2.6 precedent).

## 5. The mechanism — `baron adr check`

```
baron adr check [docs/adr] [--since YYYY-MM-DD] [--require repo-adr,vault] [--json]
baron adr scaffold          # prints the section to paste into a new ADR
```

**Fail-closed.** Exit 0 = no errors, **1 = gate violation**, 2 = usage. These are errors,
not warnings:

| Check | Refuses when |
|---|---|
| `prior-art-block-missing` | an accepted ADR has no block |
| `prior-art-block-malformed` | unclosed marker, invalid YAML, or not a mapping |
| `prior-art-searched-missing` | no `searched:` entries |
| `prior-art-search-incomplete` | an entry lacks a known `corpus`, a `query`, or an ISO `date` |
| `prior-art-corpus-missing` | a required corpus (default `repo-adr` + `vault`) was not searched |
| `prior-art-hits-missing` | the `hits:` key is absent |
| `prior-art-hit-incomplete` | a hit lacks `ref`, has an unknown `disposition`, or is `distinct` with no `note` |

Warnings (do not block): a sweep dated >90 days before acceptance
(`prior-art-search-stale` — the shape a copy-pasted block leaves), a block with no
prior-art heading, and a `supersedes` ref naming an ADR file absent from the directory
(`prior-art-ref-unresolved` — legitimately true for the reserved-but-unmerged numbers).

**Malformed is an error, never "absent".** Collapsing the two would make a corrupted
block the cheapest route through the gate — the same reasoning that made ADR-009's
unparseable reconcile block `outstanding` rather than `unverifiable`.

**Retrofit.** The gate binds ADRs dated on or after **2026-08-14**, its own acceptance
date. Twenty-six accepted ADRs predate it, and failing them all on day one is how a gate
teaches people to ignore it — ADR-009 §10 Q4 made the identical call for legacy
decisions. Grandfathered records report as `exempt`, never as passing;
`--since 1970-01-01` audits the whole corpus for anyone who wants the real number.
An ADR with no parseable date is exempt for the same reason and reported as such.

**Enforcement tier (ADR-004).** This is not `enforced` in ADR-004's sense — nothing
vetoes a tool call, and an agent can write an accepted ADR without ever running the
command. It is the **`baron guard`/CI class**: a deterministic refusal on a checkable
artifact, wired into CI so the refusal is unavoidable *in the path that matters* (the
PR), while remaining bypassable by someone determined to bypass it. Calling that
"enforced" would be the label-is-not-evidence error this repo keeps documenting.

## 6. The honest bound — what this does NOT do

> **The gate enforces that a search was RECORDED. It does not enforce that the search
> was any good.**

A block naming `corpus: vault`, a query of `"identity"`, and `hits: []` passes — even if
the 2026-08-04 spike was sitting one synonym away. Recall quality is a **separate axis**
and belongs to the memory work (AGENT-TASKS P3.3/P3.4), not here.

What it actually buys, stated at its true size:

- **"I forgot to check" goes from silent to blocked.** That is the incident's failure
  mode, and it is the one this closes.
- The sweep becomes **reviewable**: a reader — or a PR reviewer — can now see which
  corpora were searched with which terms, and say *"you searched `identity`, try
  `spawn credentials`"*. Before, there was nothing to review.
- Rule (a) is **not** mechanized. Nothing checks that a vault spike was promoted; a
  decision can still live and die in the vault unpromoted. The gate only ensures that
  *when* an ADR is written, the vault was looked at.

Three residues, named so they are not mistaken for coverage: a determined author can
record a sweep they did not perform; `--require repo-adr` legitimately drops the vault
for projects without one, and nothing distinguishes that from evasion; and the gate sees
only `docs/adr/`, so a decision made in a PR description and never written up is invisible
to it.

## 7. Alternatives considered

| Alternative | Why rejected |
|---|---|
| **A. Prose rule in `CONVENTIONS.md` only** | This is the status quo — step 1 of the intake rule already says "record with supersession", and the incident happened anyway. The whole ADR is the argument against A. |
| **B. A lint warning in `tests/lint_repo.py`** | A warning on an authoring step nobody is blocked by is the status quo with extra output. ADR-023 §5 deferred exactly this lever, and this is the second incident of the class. |
| **C. baron searches the corpus itself and reports hits** | Crosses [ADR-007](ADR-007-session-boundary.md)'s boundary (semantic search = a model call), and its failure mode is worse: a green "no prior art found" from a tool carries authority a human's blank block does not. baron verifies the record; the searching stays with the author. Genuinely attractive later, alongside P3.3/P3.4. |
| **D. Extend `baron validate`** | `validate` is the persona/manifest **schema** surface; ADRs are a different artifact with a different corpus and a different exit contract. Folding them in would make one exit code mean two unrelated things. A separate verb, wired into the same CI, keeps both legible. |
| **E. Make the vault the canonical decision store** | It has no numbering, no status, no supersession chain, and nothing reads it at authoring time. Rule (a) exists because that was tried by default and produced the incident. |

## 8. Residual owner-decision points

Endorsed as direction on 2026-08-14; these are the calls that remain, none of which
block the mechanism landing:

1. ~~**The two in-flight ADRs** will need a block added.~~ **RESOLVED at queue
   integration, 2026-08-14.** This branch is now stacked *behind* ADR-027 and ADR-028,
   both of which carry populated blocks (ADR-027 §10, ADR-028 §8) written against this
   ADR's format. `--since 2026-08-15` is **not** needed and was not taken — the effective
   date stays 2026-08-14, so this ADR remains gated by its own rule. Worth recording what
   the retrofit cost: writing ADR-028's block is what surfaced that its §4 rested on a
   *rejected* ADR-027. The friction found a defect on its first use.
2. **Is `vault` the right default requirement for *emitted* projects?** The template
   ships the two-corpus default. A scaffolded project with no vault gets a failing gate
   until it passes `--require repo-adr` — arguably the right nag, arguably an unhelpful
   day-one red. Not resolved here.
3. **Should `status: proposed` be gated too?** Currently only `accepted` is. A proposal
   is where the re-derivation actually happens, so gating earlier catches it earlier —
   at the cost of blocking the exploratory writing an ADR is partly for.
4. **Whether rule (a) ever gets a mechanism.** It would mean baron reading the vault,
   which is the ADR-007 boundary again (alternative C).

## 9. Decision record

- [x] **Accepted** (Vikram, 2026-08-14) — direction endorsed; §8 carries what is still open
- [ ] Approved with changes
- [ ] Needs revision
- [ ] Rejected

Shipped with the record, per `CONTRIBUTING.md`: `baron adr check` / `baron adr scaffold`,
the `docs/adr/ADR-TEMPLATE.md` and emitted `decisions/ADR-TEMPLATE.md` carrying the
required section, the CI wiring that runs the gate on this repo's own corpus, and the
`CONVENTIONS.md` intake rule gaining step 0.
