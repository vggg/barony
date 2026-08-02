---
created: 2026-08-01
type: decision
status: proposed
decided_by: Vikram (pending)
adr: 009
project: barony
related:
  - "[[docs/adr/ADR-003-baron-cli]]"
  - "[[docs/adr/ADR-007-session-boundary]]"
  - "[[docs/adr/ADR-008-ways-of-working-2026-07-31]]"
---

# ADR-009 (PROPOSED): `baron decision` — making a ratified decision reach the work-pull surfaces

| Field | Value |
|---|---|
| **Status** | **Proposed** — design only; not implemented, not ratified |
| **Date** | 2026-08-01 |
| **Authors** | Claude (design proposal for Vikram) |
| **Supersedes** | — (mechanizes [ADR-008](ADR-008-ways-of-working-2026-07-31.md) §4) |
| **Evidence base** | FM6 / badminton-analyzer D57 + D56 (2026-07-31) |
| **Decision owner** | Vikram |

> **This ADR proposes; it does not decide.** Per `AGENT-TASKS.md`'s rules of the road, product
> direction is the owner's call. §9 lists the questions that need an answer before any code.

## 1. Summary

ADR-008 §4 shipped the decision-intake protocol as **prose**: when a decision is ratified, the
Librarian must record it *and* reconcile the surfaces it contradicts. ADR-008 labelled that
honestly as discipline-in-a-doc and named `baron decision` as the mechanical version. This ADR
designs it.

The failure it addresses, in one line from the FM6 write-up:

> **`decisions/` is a record; the backlog is a control. Durability requires writing the decision
> into the control, not just the record.**

Agents do not re-read `decisions/` when choosing work. They re-derive direction from the direction
doc, the open epics, and the backlog. On the pilot, a directional decision was ratified across
*multiple sessions* and still kept being re-litigated, because the epic encoding the superseded
direction sat open **generating tickets**. Every fresh session read the stale surface and re-derived
the parked direction. The owner's question — *"why do we keep circling on this?"* — is the symptom
this command exists to remove.

## 2. The boundary — what baron decides, and what it must never decide

The single most important design constraint, and the one that makes this buildable:

> **baron never determines *what* a decision contradicts.** Judging that epic #214 encodes a
> direction this decision supersedes is semantic work belonging to the agent or the owner. baron
> takes the contradicted surfaces as **declared input**, performs the mechanical steps, and
> **verifies discharge**.

This is [ADR-007](ADR-007-session-boundary.md)'s boundary applied again: baron is the clerk who
keeps the books, not the judge who decides the case. A `baron decision` that tried to infer
contradiction would need a model call, and would have crossed the line ADR-007 drew.

What is left after that subtraction is still the whole failure mode — because FM6 was never a
*detection* failure. Nobody was confused about which epic contradicted D57; it was named in the
decision entry itself. The failure was that **naming it changed nothing about whether an agent
could still pick it up.** Mechanizing the discharge is mechanizing the part that actually broke.

## 3. Decision — the reconciliation contract lives in the ledger, as data

Per [ADR-003](ADR-003-baron-cli.md) §2.2 the substrate IS the database: no second store, no
sidecar. A ratified decision's obligations live **inside its `decisions/index.md` entry**, in a
marker-delimited machine-owned region — the same pattern `baron index` already uses for
`_handoff/README.md`, so generation never eats prose:

```markdown
### D57 — VLM commodity-footage intelligence is the product (2026-07-31, Vikram)

<prose the Librarian wrote — baron never touches this>

<!-- BEGIN BARON RECONCILE -->
supersedes:
  - ref: docs/adr/ADR-0011.md#phase-priority   # back-pointer required both ways
  - ref: north-star.md#2
park:
  - issue: 214                    # the work generator
    repo: code
broadcast:
  - handoff: _handoff/2026-07-31-...-rfc-all-vlm-intelligence.md
direction_doc:
  - path: docs/north-star.md
    repo: code                    # Librarian cannot write there
    via_ticket: 231               # so the obligation is a routed ticket
<!-- END BARON RECONCILE -->
```

Four obligation types, chosen because each has a **mechanically checkable** discharge condition —
that is the selection criterion, not completeness:

| Obligation | Discharged when |
|---|---|
| `supersedes` | the named artifact carries a back-pointer to this decision (checked both ways) |
| `park` | the issue is closed, **or** carries the project's park label **and** a comment citing this decision |
| `broadcast` | a `_handoff/` with `for: all` exists citing this decision |
| `direction_doc` | the doc references this decision, **or** the routed ticket is closed |

An obligation whose discharge cannot be checked mechanically does not belong here — it belongs in
the prose above the marker.

## 4. Command surface

- **`baron decision new`** (exists, M3) — unchanged. Allocates the number via push-retry.
- **`baron decision reconcile <N> [--supersedes REF] [--park ISSUE] [--broadcast] [--direction-doc PATH [--via-ticket N]]`**
  — writes the obligation block, then performs the mechanical steps it can: applies the park label
  and posts the citing comment via the forge; drafts the `for: all` broadcast handoff. Prints what
  it could **not** do (a direction doc in a repo baron cannot write) as explicit remaining work.
- **`baron decision check [N] [--json]`** — verifies each declared obligation against live state.
  Exit 0 all-discharged / 1 outstanding. CI-usable.
- **`baron status`** gains a `decision-unreconciled` **red** row. This is the load-bearing
  integration: `baron status` already gates CI and is already the thing personas and the owner
  read. A ratified decision with an open obligation becomes an alarm, not a memory.

## 5. Forge Protocol extension (additive)

Reconciliation needs issue operations the Protocol lacks: `list_issues`, `label_issue`,
`comment_issue`, `close_issue`. Added **additively**, exactly as ADR-003 §5.1 added
`create_branch` / `close_pr` for `baron lock`: a `baron.forges` plugin implementing only the older
surface loses decision-reconciliation and nothing else. `park` obligations on a project whose
backlog is a **file** (`manifest.backlog.source: file`) need no forge at all — the check is a
text assertion, and that path must keep working with no `gh` installed (ADR-003 §2.3).

## 6. Deliberately out of scope

- **Semantic contradiction detection** — §2. The declared list is the input.
- **Auto-parking without an explicit list** — a command that closes work it inferred was
  contradicted is a much worse failure than the one being fixed.
- **Editing a direction doc baron cannot write.** Route a ticket; never reach across the
  capability boundary. (ADR-008 §4 step 3.)
- **D57's fifth move — "track delivered-value, because shipped wins generate no tickets."** Real,
  and the same class of invisibility, but it is a *fleet-health metric*, not a decision obligation.
  It belongs to AGENT-TASKS P3.2. Noted so the omission is deliberate rather than forgotten.
- **Enforcement.** `park` makes contradicting work *visible as un-parked* and stops it being
  silently claimable; it does not make claiming it impossible. Honest tier: **enforced where the
  forge state is the control** (a closed issue cannot be picked up), **instructed elsewhere**. The
  templates must not oversell this — the ADR-008 §3 lesson.

## 7. Alternatives considered

| Alternative | Why rejected |
|---|---|
| **A. Prose protocol only** (status quo, ADR-008 §4) | Already shipped and already known insufficient — the pilot re-litigated a decision that *was* correctly recorded. Prose does not reach the control surface. |
| **B. A sidecar reconciliation store** (JSON/SQLite) | Violates ADR-003 §2.2 head-on. The obligations must be legible to the humans and agents reading `decisions/index.md`, in the file they already read. |
| **C. baron infers contradictions from decision text** | Needs a model call; crosses ADR-007's boundary; and the highest-cost failure mode is a false positive that parks live work. |
| **D. Fold into `baron session start`** (surface un-reconciled decisions at session open) | Complementary, not a substitute — it would put the obligation in front of an agent but still never discharge it. Worth doing *after* this lands (§9). |

## 8. Consequences

- Positive: the pilot's exact failure gets a mechanism at the layer it failed — a ratified decision
  cannot quietly leave contradicting work claimable, because `baron status` goes red until it
  does not. Decision durability becomes a *governed operation* rather than a Librarian's memory.
- Positive: the obligation block makes reconciliation **auditable after the fact** — which is what
  the `multi-agent-audit` rubric wants to measure and currently cannot.
- Negative / costs: a fourth machine-owned region in a human file; a forge Protocol extension; real
  Librarian work per decision (the command reduces it, it does not remove it). Projects whose
  backlog is a file get a weaker check than those on a forge.
- The capability vocabulary is untouched — `baron decision` composes existing verbs and gates
  nothing new. Consistent with ADR-007: these are commands, not permissions.

## 9. Open questions for the owner (blocking implementation)

1. **Scope for a first cut.** Is the full four-obligation model right, or does `park` alone —
   demonstrably the one that caused FM6 — earn its way in first?
2. **Park label name.** Reuse the pilot's `parked`, or a namespaced `baron:parked`? Affects whether
   `strip-stale-verdict.yml`-style workflows could ever confuse it with a verdict label.
3. **Who may run `reconcile`?** ADR-008 §4 makes intake the Librarian's surface. Should the command
   refuse when the acting persona is not the librarian archetype, or stay uncapability-gated and
   leave it to convention?
4. **Retrofit or not.** Existing decisions have no obligation block. Does `check` treat a
   block-less decision as green (opt-in) or warn (nudging retrofit)?
5. **Is this the right next build at all** — versus AGENT-TASKS P2.3 (`validate` spec↔runtime
   drift, small and self-contained) or P2.5 (`baron notify`, which shares the "signal doesn't reach
   the agent" family)? P2.1 is marked "the next thing to extend on," which is why it is drafted
   first, but the sequencing is the owner's call.

## 10. Decision record

- [ ] Approved as written
- [ ] Approved with changes
- [ ] Needs revision
- [ ] Rejected

**Status: awaiting owner review.** No implementation until §9 is answered.
