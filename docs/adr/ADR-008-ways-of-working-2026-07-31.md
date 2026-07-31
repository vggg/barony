---
created: 2026-07-31
accepted: 2026-07-31
type: decision
status: accepted
decided_by: Vikram
adr: 008
project: barony
related:
  - "[[docs/adr/ADR-002-ways-of-working-2026-07]]"
  - "[[docs/adr/ADR-004-baron-guard-enforcement]]"
  - "[[docs/adr/ADR-006-baron-init-template-packaging]]"
---

# ADR-008: July-31-2026 ways of working — the verdict/label split, and decision reconciliation

| Field | Value |
|---|---|
| **Status** | Accepted (2026-07-31) |
| **Date** | 2026-07-31 |
| **Authors** | Vikram + Claude |
| **Supersedes** | — (extends [ADR-002](ADR-002-ways-of-working-2026-07.md); same promotion mechanism) |
| **Evidence base** | The 2026-07-30/31 badminton-analyzer pilot run — a multi-persona fleet operating the v1.8 templates under real load |
| **Decision owner** | Vikram |

## 1. Summary

[ADR-002](ADR-002-ways-of-working-2026-07.md) established the pattern this ADR repeats: when a
coordination failure happens in the field and the fix is proven there, promote it from a
project-local rule to a framework default so the next bootstrapped project starts with it.

The 2026-07-30/31 pilot run produced two such failures. Both are *review-loop* failures, and
both come from the same structural gap: **ADR-002 gave verdicts a SHA but never said what a
label is.** Personas filled in the answer themselves, in opposite directions, and both answers
were wrong.

A third finding is not a review-loop failure at all: a ratified decision that was recorded but
never *reconciled* against the surfaces personas pull work from, so the settled question
re-opened.

`baron init` flows one-way — Barony → new projects. Hardening that stays in the pilot's collab
repo reaches nobody. This ADR promotes it.

## 2. Decisions

### §1 — A label is not evidence, in either direction

**Decision.** State in the emitted `CONVENTIONS.md`: **labels are an index, not a record.** The
record is the verdict comment bound to a head SHA (`REVIEW:PASS <sha>` / `REVIEW:FAIL <sha>`,
per ADR-002 §4). Every persona in the review loop compares that SHA to the PR's current head
before acting — **in both directions**:

- before acting on an **approval** label — if the SHAs differ the approval is void; strip the
  label and stop;
- before concluding a **block** is stale — if the SHAs match the block is *current*, the review
  ran after the push, and nothing is being waited on.

Corollary: **green CI is not the gate either.** CI green plus a pushed fix does not clear a
block; only a verdict at the current head does.

**Rationale / evidence.** Both directions failed in production inside 24 hours. A merger nearly
merged an unreviewed head off a label that survived a later push (2026-07-30). A dev then idled
~40 minutes reporting a current block as *"stale — the reviewer just hasn't re-run yet"* when
the verdict named its exact head and predated the report by 34 minutes (2026-07-31). One root
cause both times: substituting a cheap signal for the expensive one, because the cheap signal
agreed with what the reader wanted. ADR-002 §4 had specified the Merger's SHA check — but as a
*merge precondition*, so nothing bound the dev side, and nothing said what a label meant. Note
the asymmetry the pilot exposed: the approval direction fails **loudly** (a bad merge), the
block direction fails **silently** (an agent that stalls looks like an agent that is working).

**Rejected alternative — a referee persona.** The pilot's first instinct was to add an agent to
adjudicate label-vs-verdict disagreements. Rejected: an adjudicator inherits the same ambiguity
and adds a hop. The framework's own principle applies — prefer removing the ambiguity to
arbitrating it (§3 below is that removal).

### §2 — `check_review_feedback` is a session-ritual token, ordered before `check_backlog`

**Decision.** Add `check_review_feedback` to the frozen-by-convention session-ritual token set
(`references/persona.schema.md`, schema v1.2): *on this persona's open PRs, act on any review
verdict that is LIVE at the current head — before claiming new work.* It ships in the `__DEV__`
template's ritual, resolving **before** `check_backlog`. Every runtime renders it — but note the
two different mechanisms: the claude / code-puppy / generic adapters carry a **token table** in
`HYDRATE.md`, while pydantic-ai hydrates **in code** (`baron.runtimes.pydantic_ai`), so its
rendering lives in a Python table, not in its `HYDRATE.md`. `baron init`'s runtime kits render the
token as prose naming the SHA test.

**Corollary — the vocabulary needs a cross-runtime drift guard.** Both renderers fall back to
echoing the raw token, so a missing entry does not crash: the rule quietly vanishes from that
runtime's persona body. That is exactly what happened on the first cut of this change (caught in
review, before merge — the token shipped to three runtimes and not the fourth, the one whose
selling point is enforcement). `tests/bi_runtime_accept.py` did not catch it because it parses
capability maps, never ritual tokens. A test now asserts every `RITUAL_TOKENS` entry renders real
prose on both **code** renderers — `scaffold._ritual_lines` (the `baron init` runtime kits) and
`runtimes.pydantic_ai._RITUAL_LINES`.

**Honest limit of that guard:** the three table-driven adapters render from prose tables in their
`HYDRATE.md`, and **no test parses those tables**. A future ritual token can still be added to the
vocabulary and silently miss all three. Closing that needs an acceptance-harness extension
(`bi_runtime_accept.py` is capability-maps-only by construction) — tracked in `docs/BACKLOG.md`,
not fixed here, because inventing a token-table parser under review pressure is how the *first*
version of this change went wrong.

**Rationale / evidence.** The dev-side half of §1 needs a *place to happen*. A rule in
`CONVENTIONS.md` that no ritual step executes is exactly the enforcement theater
[ADR-003](ADR-003-baron-cli.md) was written against. The ordering is the substance: its purpose
is to stop a persona claiming a new ticket while a live verdict is outstanding on work it
already has — feedback on existing work outranks a new ticket. This is additive to the schema:
personas whose ritual omits the token behave exactly as before, and unknown ritual tokens were
already a warning rather than an error, so no existing project's spec becomes invalid.

### §3 — `strip-stale-verdict.yml` — the mechanical form of §1

**Decision.** Ship `.github/workflows/strip-stale-verdict.yml` in the collab-repo template,
emitted by `baron init` alongside `lock-guard.yml`: on every `synchronize`, remove the
project's reviewer verdict labels and comment saying the head moved. **Owner gates**
(`needs-human`, `hold`, `contract-change`) are explicitly excluded — they are not reviewer
verdicts and only the owner lifts them.

This makes "a review-state label is present" mean "a verdict exists at *this* head" by
construction, which is what personas were already assuming.

**Rationale / evidence.** ADR-002 §3's precedent: where a coordination rule can be made
mechanical with a dependency-free CI action, make it mechanical and keep the prose as the
statement of intent. Same honest limitation, carried in the file header: this removes a
misleading label, it cannot stop a persona that never reads verdicts — the merge gate itself
still lives in the Merger's preconditions. It is scoped deliberately narrower than the guard:
a workflow that removes a label is not an enforcement mechanism in the
[ADR-004](ADR-004-baron-guard-enforcement.md) sense, and the templates must not claim it is.

**Placement note.** `baron init` writes it into the **collab** repo, because that is the repo it
scaffolds — but most reviewed PRs live in the **code** repo. The file header says so and
instructs copying it there during code-repo setup. Consistent with
[ADR-006](ADR-006-baron-init-template-packaging.md) §3: code-repo creation stays conversational,
and init does not pretend to have done it.

### §4 — Decision & ADR intake: the Librarian RECORDS *and* RECONCILES

**Decision.** The emitted `CONVENTIONS.md` specifies a five-step intake, triggered by a
`for: Librarian` handoff whose topic starts `DECISION:` (or an owner ratification):

1. **Record with supersession** — state what the decision overrides, back-pointer both ways.
2. **Reconcile the work-pull surfaces** (load-bearing) — park or close every open epic, backlog
   item, ticket, and roadmap line the decision contradicts, so no persona can claim now-wrong
   work.
3. **Reconcile the authoritative direction doc** — route a ticket if it lives in a repo the
   Librarian cannot write.
4. **Broadcast** — a `for: all` handoff with per-persona queue impact; update the status board.
5. **Directional decisions** additionally get hydrated at session start, before ticket selection.

**Rationale / evidence.** Personas re-derive "what to build next" from the direction doc, the
open epics, and the backlog — **never** from `decisions/`. So a decision recorded but not
reconciled is invisible to exactly the surfaces that drive work, and the settled question gets
silently re-litigated by the next session that pulls a contradicting epic. Recording is the
obvious half; reconciling is the half that makes a decision binding. Stated honestly in the
template as discipline-in-a-doc — the mechanical version is a `baron decision` command that
performs the reconciliation, tracked as a candidate capability, not shipped here.

## 3. Universal vs. opt-in

Following ADR-002 §3's split: **§1 and §4 are universal** (baked into the emitted
`CONVENTIONS.md`). **§2 is universal for the dev archetype** and available to any persona whose
ritual includes the token. **§3 is opt-in** — it ships in the scaffold, but a project with no
Reviewer/Merger module can delete it; like `lock-guard.yml`, an emitted workflow is a default,
not a requirement.

## 4. Consequences

- Positive: the review loop's two failure directions both get a rule, a ritual step that
  executes it, and a mechanism that narrows the window. New projects inherit all three.
- Positive: decisions become reconcilable-by-protocol rather than by whoever remembers.
- Negative / costs: one more session-ritual token to render on every runtime and in the scaffold
  (bounded — a token table row each); one more emitted workflow that a project may not want;
  the §4 intake is real Librarian work per decision, and it is discipline, not enforcement —
  the templates say so rather than overselling.
- The capability vocabulary is untouched. Everything here composes from the frozen v1 verbs and
  the existing verdict/label surfaces — as in ADR-002, that the contract absorbed a second round
  of field pressure without a new verb is itself evidence it is the right contract.

## 5. Decision record

- [x] Approved as written

**Notes (Vikram, 2026-07-31):** promoted from the 2026-07-30/31 badminton-analyzer pilot run,
with that project's `CONVENTIONS.md` and dev/reviewer/merger persona specs as the reference
implementation. Template changes ship with this ADR (AGENT-TASKS P1.1–P1.5, one PR).
