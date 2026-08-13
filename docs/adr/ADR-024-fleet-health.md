---
created: 2026-08-13
accepted: 2026-08-13
type: decision
status: accepted
adr: 024
project: barony
authors: Atlas (design proposal for Vikram)
decided_by: Vikram
related:
  - "[[docs/adr/ADR-003-baron-cli]]"
  - "[[docs/adr/ADR-007-session-boundary]]"
  - "[[docs/adr/ADR-013-observation-plane-events-and-sinks]]"
  - "[[docs/adr/ADR-010-baron-notify-wake]]"
---

# ADR-024 (ACCEPTED): `baron health` — a fleet-health surface from the substrate, not a bespoke script

> **ACCEPTED 2026-08-13 (Vikram) — all five §8 questions answered as recommended:**
> Q1 emit to the **ADR-013 event plane** (not a ledger); Q2 **`review.verdict` as a new event kind on
> the default-`null` sink** (opt-in, per D4); Q3 **v1 metrics = mutation-kill, claim-drift
> (+understating), reviewer-escape-rate, stalls** — altitude and intervention-tax **deferred**
> (intervention-tax needs a definition first); Q4 `baron health` **sits beside `baron status`** and
> calls into it; Q5 **build the measurement lean now** (internal + adopters) — the paid-observability
> positioning is held as a later (Stage-C) bet, not built now.
> Atlas drafted this so P3.2 had a design to decide against rather than code invented ahead of an
> owner call (AGENT-TASKS: "propose/scope with the owner before large builds").

## 1. Problem (FM — first-party, from the badminton pilot)

The badminton-analyzer fleet produces the exact numbers that tell you whether an autonomous fleet is
*healthy* — mutation-kill rate, claim drift and its direction, **reviewer escape rate**, recurring-bug
altitude, per-author breakdown, and dev-side stalls. They are proven and running
(`fleet-runner/metrics-report.sh`, `reviewer-prompt.txt`). But they are emitted to a **private
`logs/metrics.jsonl`** that one runner writes on one machine. No adopter of `baron init` gets any of
it, and none of it is auditable from a `git clone`. Fleet health is a capability the pilot proved and
the product does not have.

## 2. What already exists — the *divergence/stall* half is largely done

`baron status` (M2, ADR-003) already computes the read-half that needs no reviewer cooperation:
stranded/unmerged branches, **open handoffs past SLA** (`handoff-overdue`), ledger staleness vs. code
activity, wiki staleness, and dirty working copies. Stall detection is a thin extension of this, not a
new subsystem. **This ADR does not rebuild it — it extends `status` and composes it into `health`.**

## 3. The gap — *reviewer-quality* metrics have no substrate-native home

The metrics in §1 are not derivable from git alone: they are judgements a reviewer makes per verdict
(`mutations_run/killed`, `drift_instances`, `drift_understating`, `altitude`, `escape`). Today they
live in a bespoke JSONL the reviewer prompt tells the agent to append to. That is the same
"prose-instructed, private-store" pattern ADR-013 exists to replace for guard evidence. Fleet health
needs a **canonical emission surface** before `baron` can aggregate anything.

## 4. Proposal

**(a) Emission — reviewer/merger emit a `review.verdict` record onto the observation plane (ADR-013).**
Rather than a bespoke file, a verdict is one more `Event` kind on the plane ops-plane just landed:
git-native, one shape, pluggable sinks, **default sink `null`** so adopters opt in (D4). The reviewer
persona template gains a `baron` call that records the verdict fields it already computes. No second
store; the substrate stays the database (ADR-003 §2.2).

*Alternative considered:* a dedicated `metrics/` ledger (like findings/decisions). Rejected as the
default — verdicts are telemetry (one per review, high volume), not governance records that belong in a
numbered, never-deleted ledger. But see Q1: this is the owner's call.

**(b) `baron health [--since DATE] [--json]`** — a **read-only** aggregation that (i) rolls up the
`review.verdict` events and (ii) reuses `status`'s stall/divergence checks. Output mirrors the
badminton `metrics-report.sh` (the first-party reference), one screen:

- **Mutation-kill rate** — test-suite defense strength (survivors = undefended code).
- **Claim drift** — instances/PR, **with the understating count** (overclaim-only checks miss the
  safe-direction ones — the same asymmetry ADR-008 cares about).
- **Reviewer escape rate** — the one metric that grades the *reviewer*: defects caught now that a prior
  review of an earlier head passed.
- **Recurring-bug altitude**, **per-author breakdown**, and **stalls** (from `status`).

## 5. Honest bounds (the part that keeps it truthful)

`baron health` measures **what was emitted**, not what happened. A reviewer that records nothing shows a
clean board — the absence of a signal is not a good signal, and the report must say so rather than
imply health. This is `instructed`, not `enforced` (ADR-008 vocabulary): baron ships the record call and
the aggregator; it cannot make an agent tell the truth about its own misses. Escape rate in particular
is a **self-report of a miss** — valuable precisely because it is voluntarily surfaced, and worthless if
gamed. The report should label its own coverage (how many verdicts carried metrics vs. how many reviews
happened) so a thin denominator is visible, not hidden.

## 6. Boundary (ADR-007) and relation to `baron notify`

`baron health` **aggregates and reports; it never spawns or drives a loop.** It is the *measure* half
of the orchestration story whose *wake* half is ADR-010 (`baron notify`) — but it is independent of it
and lands on its own. No model calls, runtime-neutral.

## 7. §8 — Owner decisions (all RESOLVED 2026-08-13, answers in the header callout)

1. **Emission surface:** `review.verdict` on the ADR-013 event plane (recommended) **or** a dedicated
   metrics ledger?
2. **Event kind + sink:** if the plane — is `review.verdict` a new `KNOWN_KIND`, riding the default-`null`
   sink so adopters opt in (consistent with D4)?
3. **Canonical v1 metric set:** which of {mutation-kill, claim-drift(+understating), escape-rate,
   altitude, intervention-tax} are v1 vs. deferred? (Intervention-tax needs a definition — owner input.)
4. **Command shape:** does `baron health` extend/subsume `baron status`, or sit beside it and call into it?
5. **Product scope:** is this the "Workstream-D paid observability anchor" (a productization bet), or an
   internal tool kept off the public roadmap? (This gates how much to build.)

## 8. Evidence base

Badminton-analyzer `fleet-runner/` — first-party, running: `metrics-report.sh` (the aggregation this
mirrors), `reviewer-prompt.txt` (the verdict schema the reviewer already emits), `review-cycle.sh`
(`detect_stalls`). `baron status` (`cli/src/baron/status.py`) for the divergence/stall half.
