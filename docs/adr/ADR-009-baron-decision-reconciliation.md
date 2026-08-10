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
| **Status** | **Proposed / parked** — design only; Q2 + Q5 answered 2026-08-02; build order: after P2.3 |
| **Date** | 2026-08-01 (rev. 2, after adversarial design review) |
| **Authors** | Claude (design proposal for Vikram) |
| **Supersedes** | — (mechanizes [ADR-008](ADR-008-ways-of-working-2026-07-31.md) §4) |
| **Evidence base** | FM6 / badminton-analyzer D57 + D56 (2026-07-31) |
| **Decision owner** | Vikram |

> **This ADR proposes; it does not decide.** Per `AGENT-TASKS.md`'s rules of the road, product
> direction is the owner's call. §10 lists the questions that need an answer before any code.

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
direction sat open **generating tickets**. The owner's question — *"why do we keep circling on
this?"* — is the symptom this command exists to remove.

## 2. The boundary — what baron decides, and what it must never decide

> **baron never determines *what* a decision contradicts.** The contradicted surfaces are
> **declared input**. baron performs the mechanical steps and **verifies discharge**.

The justification is **not** "detection was never the problem." Rev. 1 claimed that, on the
grounds that D57 names epic #214 itself. That reasoning is unsound: D57 is the *RCA output*,
written after the failure. During the multi-session window when the decision was silently losing,
no entry named #214. Detection genuinely was part of the failure.

The real justification is [ADR-007](ADR-007-session-boundary.md)'s boundary plus an asymmetry of
costs: inferring contradiction needs a model call (crossing the boundary), and its **worst failure
mode is a false positive that parks live work** — strictly worse than the failure being fixed. A
human or agent naming the surfaces is cheap; baron guessing them is not.

## 3. Decision — the reconciliation contract lives in the ledger, as data

Per [ADR-003](ADR-003-baron-cli.md) §2.2 the substrate IS the database. A ratified decision's
obligations live **inside its `decisions/index.md` entry**, in a marker-delimited region:

> **Scoped 2026-08-10 by [ADR-022](ADR-022-substrate-invariant-amended-default-not-only.md).**
> Product-vision invariant #1 now reads *git + markdown is the **DEFAULT** substrate*, bounded
> by **governance state stays complete in git**. This section is unaffected and the reasoning
> is unchanged: reconciliation obligations are *evidence of an adjudication*, which ADR-022 §2
> places squarely in the column a plugin may **never** be authoritative for. §9 alternative B
> (a sidecar store) stays rejected for the same reason it always was.

```markdown
### D57 — VLM commodity-footage intelligence is the product (2026-07-31, Vikram)

<prose the Librarian wrote — baron never touches this>

<!-- BEGIN BARON RECONCILE -->
supersedes:
  - ref: docs/adr/ADR-0011.md          # a FILE, in a named repo
    repo: code
park:
  - issue: 214
    repo: code
broadcast:
  - handoff: 2026-07-31-carson-rfc-all-vlm-intelligence   # filename STEM, not a path
direction_doc:
  - path: docs/north-star.md
    repo: code
    ticket: 231                        # tracking only — NOT a discharge condition (§3.3)
<!-- END BARON RECONCILE -->
```

`repo:` names an entry in `manifest.repos[].id` — not a backlog location; those are different
things and rev. 1 conflated them.

### 3.1 — Precedent honesty: this is not the handoff index

Rev. 1 justified the marker block by pointing at `_handoff/README.md`. **That precedent is the
wrong shape**, and the difference matters: the handoff index is a **derived view**, fully
regenerable from the handoff files, so a corrupted block is repaired by re-running `baron index`.
This block is **authored primary data** — lose it and the obligations are gone. It is the first
machine-owned region of that kind in the repo (the handoff index is the only one today).

What follows, and must be designed rather than assumed:

- `reconcile` **only appends or updates its own block**, never regenerates it from elsewhere.
- Concurrency: the ledger's push-retry (ADR-003 §2.5) is the model, but **not the code** —
  `ledger.add_entry` rolls back with `git reset --hard HEAD~1`, which is safe only for a
  just-created commit. `reconcile` edits an *existing* entry, so it needs its own narrower
  rollback. Flagged explicitly because copying the ledger's path would be a data-loss bug.
- A malformed block is **reported, never silently rewritten** — the ADR-003 §2.6 precedent
  (report numbering problems; don't renumber).

### 3.2 — `park`: the read-side is the mechanism

This is what rev. 1 got wrong, and it is the heart of the design.

Rev. 1 discharged `park` on *"issue closed **or** park label + citing comment."* **D57's own
surfaces table records epic #214 as parked exactly that way — `label 'parked' + decision comment`
— and left OPEN. FM6's root cause is that #214 "sat open generating work."** Rev. 1's check would
have printed green on the precise state that caused the failure it cites. A discharge condition
already satisfied by the motivating incident is not a mechanism.

The fix: **a park is discharged only when an agent's own backlog query stops returning the item.**

| Discharge | Condition |
|---|---|
| **closed** | the issue is closed — nothing returns it |
| **filtered** | the issue carries the park label, **and** the project declares that label in `manifest.backlog.park_label`, **and** the rendered `check_backlog` query excludes it |

The `filtered` route needs a real spec change — the honest cost of doing this properly:

- `manifest.backlog` gains an optional **`park_label`** (additive; schema v1.3).
- The `check_backlog` renderers — the two code renderers and the three adapter prose surfaces
  (ADR-008 §2's list) — emit a query that **excludes** `park_label` when declared.
- `check` verifies the declaration and the label; it cannot verify that a hand-written agent
  honoured the query. That residue is instructed, and §7 says so.

**Without `park_label` declared, the only discharge is `closed`.** The default fails toward the
strong condition.

### 3.3 — `direction_doc`: a ticket is an index, not a record

Rev. 1 discharged this on *"the doc references this decision, **or** the routed ticket is closed."*
The second branch is exactly what this repo shipped into every template eight days ago and called
a failure: **an index substituted for the record** (ADR-008 §1, and its corollary that a green
signal elsewhere is not the gate). A closed ticket asserts that someone believes the doc was
updated.

**Discharge is the doc itself referencing this decision.** `ticket:` is retained for routing and
traceability — so `check` can say *"outstanding; tracked by #231"* — but never as a discharge
condition. Where the doc lives in a repo baron cannot read, the obligation reports
**`unverifiable`**, never green (§4).

### 3.4 — `supersedes` and `broadcast`

**`supersedes`** discharges when the named artifact contains a literal reference to this decision
(`D57`, or the ADR id) **and** the decision entry names the artifact — a back-pointer both ways,
as a plain substring search over a **file in a declared repo**. Rev. 1's examples used section
anchors (`ADR-0011.md#phase-priority`, `north-star.md#2`); those are **not mechanically
verifiable** and are dropped. Anchor-level precision belongs in the prose above the block.

**`broadcast`** discharges when a `_handoff/` with `for: all` references this decision. Store the
filename **stem**, not a path: `baron handoff close` relocates files to `_handoff/archive/YYYY/`,
so a stored path would rot. Resolution searches both locations.

## 4. Three states, not two

`check` reports per obligation: **discharged** / **outstanding** / **unverifiable** (forge
unreachable, `gh` absent, or the artifact is in a repo not present locally). `unverifiable` is
never counted as discharged and never raised as red — it is a warn naming exactly what could not
be reached. Collapsing it into either neighbour would make the command lie in one direction or cry
wolf in the other.

## 5. Command surface, and what `baron status` may assume

- **`baron decision new`** (exists, M3) — unchanged.
- **`baron decision reconcile <N> [--supersedes REF] [--park ISSUE] [--broadcast] [--direction-doc PATH [--ticket N]]`**
  — writes/updates the block, then performs the mechanical steps it can. **Idempotent and
  resumable**: a re-run after partial failure re-attempts only what is outstanding. The local block
  is committed *before* remote steps are attempted, so a network failure leaves a recorded
  obligation rather than a silent no-op.
- **`baron decision check [N] [--fetch] [--json]`** — exit 0 = nothing outstanding / 1 = outstanding.
- **`baron status`** gains a `decision-unreconciled` row — **red only for locally-decidable
  obligations.** This is a constraint, not a detail: `status.py` is pure local git today, with
  network behind opt-in `--fetch`, and ADR-003 §2.3 keeps `gh` optional. So by default `status`
  evaluates what it can read locally and reports the rest as `unverifiable` warns; forge-dependent
  checks run only under `--fetch`. Waiver SUBJECT: `decision-unreconciled:D<N>`, so
  `.baron-waivers.yaml` can park a known-outstanding obligation with a reason and an expiry.

### 5.1 — Backlog sources

`manifest.backlog.source` admits `file`, `github_issues`, and `jira`.

| Source | `park` support |
|---|---|
| `github_issues` | full — `closed` or `filtered`, via the forge |
| `file` | `filtered` only, as a text assertion (item absent, or marked with `park_label`); **needs no `gh`**, per ADR-003 §2.3 |
| `jira` | **not supported at first cut** — reports `unverifiable`. Named so the omission is deliberate; a Jira path needs the forge-plugin treatment (`docs/BACKLOG.md`) |

## 6. Forge Protocol extension (additive)

Needs `list_issues`, `label_issue`, `comment_issue`, `close_issue` — added additively, exactly as
ADR-003 §5.1 added `create_branch` / `close_pr` for `baron lock`. A `baron.forges` plugin
implementing only the older surface loses decision-reconciliation and nothing else.

## 7. Enforcement class — stated plainly

**Nothing in this design is `enforced` in the [ADR-004](ADR-004-baron-guard-enforcement.md) sense.**
ADR-004 defines enforced as *blocked before the call runs*. Nothing here vetoes a tool call.

Rev. 1 claimed tier `enforced` for "a closed issue cannot be picked up" while citing ADR-008 §3's
lesson in the same sentence — and ADR-008 §3 says verbatim that a label-manipulating workflow "is
not an enforcement mechanism in the ADR-004 sense." A closed or filtered issue is the same class:
it changes what a **query returns**. That is genuinely valuable — the difference between work that
is claimable and work that is not — but it is *removal from a default view*, not a veto, and the
templates must not blur the two. Rev. 1 was also internally inconsistent, saying "does not make
claiming it impossible" and `enforced` one line apart.

Honest tier: **instructed, with a mechanical visibility surface** — the same class of strength as
`lock-guard.yml`: enforcement by convention plus a visible alarm that `baron status` will not let
you forget.

## 8. Deliberately out of scope

- **Semantic contradiction detection** (§2).
- **Auto-parking without an explicit declared list.**
- **Editing a direction doc baron cannot write** — route a ticket; never reach across the
  capability boundary.
- **D57's fifth move — delivered-value tracking.** A fleet-health metric, not a decision
  obligation; AGENT-TASKS P3.2.
- **ADR-008 §4 step 5 — session-start hydration of directional decisions.** Complementary, and
  currently mechanized nowhere; `baron session start` (ADR-007) is the natural host. Not designed
  here, and **added to `docs/BACKLOG.md`** so it is tracked rather than quietly dropped.
- **Supersession lifecycle.** When D60 supersedes D57, D57's outstanding obligations should stop
  being red. `check` treats decisions independently at this cut, so a superseded decision must be
  waived by hand — a known gap, §10 Q4.

## 9. Alternatives considered

| Alternative | Why rejected |
|---|---|
| **A. Prose protocol only** (status quo, ADR-008 §4) | Already shipped and already known insufficient — the pilot re-litigated a decision that *was* correctly recorded. |
| **B. A sidecar store** (JSON/SQLite) | Violates ADR-003 §2.2. Obligations must be legible in the file humans and agents already read. |
| **C. baron infers contradictions** | Model call; crosses ADR-007's boundary; worst failure is parking live work (§2). |
| **D. Fold into `baron session start`** | Complementary, not a substitute — it puts the obligation in front of an agent but never discharges it. Tracked as the §8 session-hydration item. |

## 10. Open questions for the owner (blocking implementation)

1. **Scope for a first cut.** `park` alone — demonstrably the obligation that caused FM6 — or all
   four? `park` alone is the smallest thing that addresses the incident, but it is also the one
   that now carries a schema change (§3.2).
2. ~~**Is the `park_label` read-side change acceptable?**~~ — **ANSWERED (Vikram, 2026-08-02):
   yes.** §3.2 stands as designed: `park` discharges on *closed* **or** *filtered via a declared
   `manifest.backlog.park_label`*. The schema change (v1.3) and the five `check_backlog` renderers
   are in scope when this is built.
3. **Who may run `reconcile`?** ADR-008 §4 makes intake the Librarian's surface. Capability-gate to
   the librarian archetype, or leave it to convention?
4. **Retrofit and supersession.** Block-less legacy decisions: green (opt-in) or warn? And is
   hand-waiving a superseded decision's obligations acceptable for a first cut (§8)?
5. ~~**Is this the right next build at all**~~ — **ANSWERED (Vikram, 2026-08-02): P2.3 first.**
   `baron validate` spec↔runtime drift is smaller and carries no schema change; this design is
   **parked, not rejected**, and is picked up after P2.3 lands. Q1, Q3 and Q4 stay open until then.

## 11. Decision record

- [ ] Approved as written
- [ ] Approved with changes
- [ ] Needs revision
- [ ] Rejected

**Status: PARKED after partial owner review (2026-08-02).** Q2 answered (the `park_label`
read-side change is accepted, so §3.2 stands); Q5 answered (**P2.3 is built first**). Q1 (first-cut
scope), Q3 (who may run `reconcile`) and Q4 (retrofit + supersession) remain open. No
implementation until they are.

> **Currency note, 2026-08-10.** Q5's *sequencing* condition is discharged: **P2.3 shipped**
> in barony 0.7.0 (`baron validate` spec↔runtime drift). So "after P2.3 lands" no longer
> holds this back — **Q1, Q3 and Q4 do**, and they are unanswered. Recording the difference
> matters: a design waiting on a build is not the same as a design waiting on three owner
> answers, and only the second is true now.
