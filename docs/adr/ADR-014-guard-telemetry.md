---
created: 2026-08-09
type: decision
status: adopted-in-part-transport-retired
decided_by: Vikram
adr: 014
project: barony
related:
  - "[[docs/adr/ADR-013-observation-plane-events-and-sinks]]"
  - "[[docs/adr/ADR-018-adjudicated-enforcement-on-the-event]]"
  - "[[docs/adr/ADR-021-audit-ingester-partitions-observation-rows]]"
  - "[[docs/adr/ADR-003-baron-cli]]"
---

# ADR-014: Guard-decision telemetry — ADOPTED IN PART; its TRANSPORT is RETIRED

| Field | Value |
|---|---|
| **Status** | **Adopted in part (2026-08-09) · transport RETIRED (2026-08-10)** — not rejected, and not superseded wholesale |
| **Date** | authored 2026-08-09 · disposition recorded 2026-08-10 |
| **Authors** | Claude (the OpenTelemetry workstream of the 2026-08 hardening effort); disposition by Vikram |
| **Full text** | `harden/otel:docs/adr/ADR-014-guard-telemetry.md` — branch intact, 3 commits, tip `3b9a4d8` |
| **Decision owner** | Vikram |

> **What this file is.** ADR-014 was written on `harden/otel`, which was **never merged**. This
> file is the **status record** for the reserved number, on the branch where the decision about
> it was taken. It is not a copy of the ADR and does not restate its argument — the 435-line
> original stays where it was written. Read it there; it is a good document, and this
> disposition is not a criticism of it.
>
> This file exists because the repository is supposed to answer *"what is true now"* on its own
> (see [ADR-022](ADR-022-substrate-invariant-amended-default-not-only.md) §2). An ADR number
> cited by two merged ADRs, whose disposition could only be reconstructed by checking out
> another branch, is a hole in that answer.

## 1. The decision, in one line

**ADR-014's analysis was correct and has been adopted in part. Its producer transport —
`baron.telemetry` — is retired.** The forward path for a live OTel exporter is an out-of-tree
plugin over the existing `baron.sinks` entry-point group.

## 2. Why this is not recorded as "rejected"

Because that would misstate the history, and the history is checkable.

ADR-014's central finding — that an enforcement label derived from "the evaluator ran" or from
"the verb tuple is non-empty" is wrong **in both directions** — was measured, was right, and is
now the merged behaviour of baron. [ADR-018](ADR-018-adjudicated-enforcement-on-the-event.md)
cites ADR-014 §4.2 as **"the correct basis"** and ports `Decision.adjudicated` from it
essentially unchanged, including the design property that carries the honesty: the flag is set
explicitly at all eleven return sites and defaults `False` on the trace, so every path that
returns without a real `Decision` is `unevaluated` *by construction* rather than by someone
remembering to say so.

A workstream whose analysis was adopted, whose fix is in merged code, and which corrected a
defect the merged plane actually had, has not been rejected. Filing it under "rejected" would
also lose the more useful record: **the branch that lost the merge was the branch that was
right about the label.**

## 3. What was adopted, and where it lives now

| From ADR-014 | Landed as | Status |
|---|---|---|
| §4.2 — `Decision.adjudicated`; `enforced` requires a rule match **and** persona-dependence; the `enforced` / `unevaluated` vocabulary; the consumer caveat that a non-empty verb tuple is not a proxy for `enforced` | [ADR-018](ADR-018-adjudicated-enforcement-on-the-event.md) | **MERGED** |
| §9.1 — guard rows are evidence, not agent activity; `partition_guard_records` | [ADR-021](ADR-021-audit-ingester-partitions-observation-rows.md) | **MERGED**, re-measured against the merged producer rather than carried over |
| §3 — **no `opentelemetry-api` in baron core, ever** | ADR-013 §6, and `DECISIONS-FOR-REVIEW.md` §C row C2 | **STANDS** — see §5 |
| §12.2 — "if ADR-013 ships an event bus, `baron.telemetry` should become a consumer of it rather than a parallel emitter" | this decision | **HONOURED**, by retirement rather than by reconciliation |

Note the last row. ADR-014 anticipated this outcome and named it as the correct resolution
while its own module was still being built. What is retired here is the branch that its own
author flagged.

## 4. What is retired

The **transport only**, and nothing else:

- `cli/src/baron/telemetry.py` — its `Sink` Protocol, `NullSink`, `JsonlSink`, `guard_span()`
- `cli/tests/test_telemetry.py` (668 lines)
- the `BARON_TELEMETRY` environment variable
- the `.baron/telemetry/` on-disk location
- ADR-014's own declaration of a `baron.sinks` entry-point group (declared there, built-ins
  unregistered; the merged ADR-013 group ships two registered built-ins)

**Nothing is deleted.** Retiring is a **recording** action here, because none of the above was
ever merged. There is no revert, no removal, and no code change in this decision.

- `harden/otel` is **NOT deleted**. It is the reference and stays as history.
- **Nothing further is merged from it.** Both producer-independent halves already landed (§3).
- The 668-line `test_telemetry.py` is not lost; it is one `git show` away, and it tests a module
  that does not exist here.

### 4.1 Why retire rather than reconcile

Baron ships **one** observation plane (ADR-013), and after §3's ports there is nothing left on
`harden/otel` that the merged plane lacks. What remains is a second, complete, incompatible
producer that collides with the merged one on the module, the entry-point group, the env var,
the on-disk location and the span name.

Keeping both is not neutral. The moment sinks are turned on, two transports writing the same
governance fact in two wire shapes is a **schema fork in every downstream repo** — a consumer
would have to know which of `.baron/events/` and `.baron/telemetry/` its rows came from, and
the two disagree on span name and on the verbs key. That hazard was the reason F3's cost was
recorded as *"low right now, rising the moment D4 flips."*

**The two decisions interlock, and the hazard is now moot.** The same 2026-08-10 pass decided
that the shipped sink default stays `BARON_EVENTS_SINK=null` (ADR-013 §7.1). Retiring the
second transport removes the fork; the default keeps the window open regardless. Neither
decision depends on the other, and both point the same way.

## 5. The forward path, and its constraint

A live OTel exporter — OTLP, a collector, a hosted backend — belongs **out-of-tree**, as a
separately distributed plugin registered over the **existing `baron.sinks` entry-point group**.
No new group is needed; `baron.sinks` already exists, already has two registered built-ins, and
already resolves through real `importlib.metadata` discovery under test.

The constraint on that path is ADR-014's own §3, restated in ADR-013 §6 and pinned as one-way
door **C2**: **no `opentelemetry-api` in baron core, ever.** Three reasons, all still live —
ADR-003 pins runtime deps to typer + pyyaml; guard is a cold Python start on *every* tool call,
so an SDK import is latency paid by every user including the majority with telemetry off; and
the entire consumer-side value of OTel is already obtained by a ~40-line stdlib writer, since
`ingest_otel.record_from_flat` parses the flat rows with zero code changes.

This decision is **consistent with C2, not an exception to it.** C2 says a live exporter belongs
out-of-tree under `baron.sinks`; this says the second in-tree transport goes away and that
out-of-tree path is the only one. The plugin carries its own dependency, which is the point.

**Nothing is authorised here.** No plugin is planned, scheduled or promised. The forward path is
recorded so that the next person to want OTLP finds the shape of the answer instead of
re-litigating the transport.

## 6. Consequences

- `DECISIONS-FOR-REVIEW.md` **§D** and **F3** move from open to **RESOLVED**. D1's last open
  item — *"retire `telemetry.py`"* — is discharged.
- **No code change. No test change.** The cli suite is unchanged at **424 passing**; a
  retirement of something never merged cannot move it, and if it had, that would be the bug.
- `skills/multi-agent-audit/scripts/ingest_otel.py` keeps matching ADR-014's
  `baron.guard.evaluate` span name as a belt-and-braces convenience (ADR-021 §7). That is
  **deliberately kept**: the branch exists, someone may have run it, and an ingester that
  refuses rows it can read would be worse than one that accepts a name nothing emits.
- **Reversible?** Yes, cheaply, and that is worth saying: the branch is intact, so reviving the
  transport costs a merge and an ADR, not a reconstruction. What would *not* be cheap is
  reviving it after downstream repos have consumed the merged wire shape — which is the
  argument for deciding now, in the window where the default sink is `null` and no consumer
  exists.
