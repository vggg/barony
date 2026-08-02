---
created: 2026-08-02
type: decision
status: proposed
decided_by: Vikram (pending)
adr: 010
project: barony
related:
  - "[[docs/adr/ADR-002-ways-of-working-2026-07]]"
  - "[[docs/adr/ADR-003-baron-cli]]"
  - "[[docs/adr/ADR-007-session-boundary]]"
---

# ADR-010 (PROPOSED): `baron notify` — waking an idle persona without owning the loop

| Field | Value |
|---|---|
| **Status** | **Proposed** — design only; not implemented, not ratified |
| **Date** | 2026-08-02 |
| **Authors** | Claude (design proposal for Vikram) |
| **Supersedes** | — (extends ADR-002 §2; constrained by [ADR-007](ADR-007-session-boundary.md)) |
| **Evidence base** | FM1 / FM5 + the 2026-07-31 `research-a2a-wake-nudge` survey |
| **Decision owner** | Vikram |

> **This ADR proposes; it does not decide.** §8 lists the questions that need an answer
> before any code.

## 1. The problem

Barony fleets are **poll-based**. A persona acts only when spawned, and at session start it
*chooses* to sweep its surfaces. There is no push channel: when a reviewer posts a verdict or a
handoff lands, nothing wakes the responsible agent. **A human is the message bus** — that is
FM1/FM5, and it is what made the reviewer-feedback stall (D56) possible.

The pilot bridges this with a wall-clock cron re-invoking `claude -p` every 15 minutes: polling
dressed as automation. It spawns whether or not there is work, burns tokens on empty sweeps, and
dies with the laptop lid.

The external survey (`research-a2a-wake-nudge`) settles the landscape question:
**no agent framework wakes a cold headless agent.** LangGraph's `interrupt()` resumes a
checkpointed graph in a running runtime; Temporal signals a hosted durable workflow; A2A push
notifies the *orchestrator that dispatched a task*, and presumes the worker is a long-running
server. Every one of them assumes something is already running. Cold-starting an ephemeral CLI
agent from an external event is owned by the **platform** (GitHub Actions), not by agent
frameworks.

## 2. The departure: there is no new mailbox

The research recommends a new `_mailbox/<persona>/` surface — "a prioritized superset of
`_handoff/`" — as the delivery layer, plus an event for the wake. **This ADR proposes the
delivery half be dropped, because Barony already has it.**

`_handoff/` is already ordered (timestamped filenames), addressed (`for:`), durable
(append-only, never deleted — ADR-002 §2), and already swept at session start by the
`check_handoffs` ritual token. Sweep *order* is already expressible: ADR-008 §2 added
`check_review_feedback` positioned ahead of `check_backlog` precisely to make "this outranks new
work" mechanical.

Adding `_mailbox/` would create **two message surfaces restating one contract** — and this repo
has just spent an entire release learning what that costs. ADR-002 §2's rule is "everything
material gets a handoff. No exceptions"; a second inbox would need that sentence to grow an
exception on day one, and every persona, adapter and ritual token would need to know which
surface to read first.

**So: `_handoff/` IS the mailbox.** What is missing is not delivery. It is *wake*.

This shrinks the feature to its actual novelty and leaves the delivery guarantee exactly where
ADR-002 already put it.

## 3. Decision — `baron notify` = an existing handoff, plus an event

```
baron notify <persona> --title "..." [--body-file F] [--from <slug>] [--no-wake]
```

1. **Deliver** — compose a `_handoff/` addressed to `<persona>` by calling the existing
   `baron handoff create` path. No new format, no new directory, no new lifecycle.
2. **Wake** — fire a forge `repository_dispatch` carrying `event_type: baron-notify` and a
   payload naming the persona and the handoff filename stem.

**Delivery is independent of wake, and that is the design's load-bearing property.** If the
dispatch fails — no forge, no token, no workflow installed, rate-limited — the message is still
a committed file and the persona gets it on its next spawn, exactly as today. The wake is a
latency optimisation over a guarantee that already holds. `--no-wake` makes that explicit and
keeps the command useful with no `gh` at all (ADR-003 §2.3).

## 4. Where the boundary sits (ADR-007)

[ADR-007](ADR-007-session-boundary.md) is unambiguous: **Barony does not own the agent execution
loop.** A command that spawns an agent would cross that line, so it must not.

The split:

| Layer | Owner |
|---|---|
| Write the handoff | **baron** |
| Fire `repository_dispatch` | **baron** |
| Receive the event, spawn a persona | **the project's workflow, not baron** |
| Run the agent loop | **the runtime** |

Barony emits `.github/workflows/baron-notify.yml` as a **template with the spawn command left as
an explicitly-marked project-owned slot** — the same shape as `lock-guard.yml` and
`strip-stale-verdict.yml`. Barony ships the event and the seam; it never ships `claude -p`.

That keeps ADR-007 intact: baron makes no model calls, drives no loop, and is runtime-neutral.
It fires an event; what the project does with it is the project's.

## 5. Loop safety — the failure this invites

A persona that can wake another persona can be woken back. Reviewer wakes dev, dev pushes, the
push wakes reviewer. Unbounded, that is a token-burning cycle running on someone's Actions
minutes with nobody watching.

Three guards, all cheap:

- **Origin chain in the payload.** Each dispatch carries `depth` and the originating persona.
  `baron notify` refuses to fire beyond `--max-depth` (proposed default **2**), and says so.
  Delivery still happens; only the wake is suppressed.
- **Concurrency guard in the template.** `concurrency: { group: baron-notify-<persona>,
  cancel-in-progress: false }` so a persona cannot be spawned into itself.
- **A wake is never automatic on repo events at first cut.** Label/review/comment triggers are
  tempting (the research lists them as first-class) but they multiply the cycle surface. Explicit
  `baron notify` only, until the loop guards have field evidence.

This is stated here because a wake mechanism whose failure mode is "spends money in a loop"
deserves its guards in the decision record, not in a follow-up.

## 6. Forge Protocol extension (additive)

One method: `dispatch_event(repo, *, event_type, payload)`. Added additively, as ADR-003 §5.1
added `create_branch`/`close_pr` for `baron lock`. A `baron.forges` plugin implementing only the
older surface loses `notify --wake` and nothing else; `--no-wake` keeps working everywhere.

## 7. Honest limits

- **The wake needs a forge and an installed workflow.** Without both, `baron notify` degrades to
  `baron handoff create` plus a warning. That is a real degradation, not a silent one.
- **Enforcement class: none.** This is a delivery-and-latency mechanism. Nothing here makes a
  persona *read* its handoffs; that remains the ritual's job (instructed).
- **GitHub-only at first cut**, like every other forge-consuming command.
- **Actions minutes are real money** on private repos, and a wake spawns a run. The guards in §5
  bound it; they do not make it free.
- **It does not fix FM6.** A decision reaching the work-pull surfaces is ADR-009's problem. A
  broadcast wake could *announce* a decision, but announcing is not reconciling.

## 8. Open questions for the owner (blocking implementation)

1. **Is dropping the mailbox right?** §2 departs from the research's recommendation. The
   counter-argument is that `_handoff/` carries a lot of traffic and a dedicated high-priority
   inbox is easier for a persona to sweep first. My read is that a second surface costs more than
   it buys, and sweep order is already expressible — but the research argued otherwise and this is
   the call worth challenging.
2. **Does `baron notify` retire the pilot's 15-minute cron, or run beside it?** The research says
   it retires it. Retiring removes the safety net that catches a *missed* wake; keeping both keeps
   the empty-sweep token burn. A middle option is a much slower cron (hourly/daily) purely as a
   backstop.
3. **`--max-depth 2` — right default?** And should the depth guard live in the CLI, the workflow,
   or both?
4. **Repo-event triggers (label/review/comment) — in or out of the first cut?** §5 proposes out.
5. **Is this the right next build** versus P2.2 (deterministic enforcement — the largest, with
   the sharpest evidence in FM4), P2.4 (`baron promote`), or P3.1 (Barony governs Barony)?

## 9. Decision record

- [ ] Approved as written
- [ ] Approved with changes
- [ ] Needs revision
- [ ] Rejected

**Status: awaiting owner review.** No implementation until §8 is answered.
