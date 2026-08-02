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
  - "[[docs/adr/ADR-008-ways-of-working-2026-07-31]]"
  - "[[docs/adr/ADR-009-baron-decision-reconciliation]]"
---

# ADR-010 (PROPOSED): `baron notify` — waking an idle persona without owning the loop

| Field | Value |
|---|---|
| **Status** | **Proposed** — design only; not implemented, not ratified |
| **Date** | 2026-08-02 (rev. 2, after adversarial design review) |
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

It also already carries **`priority:`** in its frontmatter (`handoff.py`) — which is the
research's "prioritized" requirement, satisfied today. Rev. 1 missed that and argued the weaker
case.

Adding `_mailbox/` would create **two message surfaces restating one contract** — and this repo
has just spent an entire release learning what that costs. Every persona, adapter, ritual token
and runtime kit would need to know which surface to read first.

*(Rev. 1 attributed "everything material gets a handoff. No exceptions" to ADR-002 §2. The
"no exceptions" wording is in the emitted `CONVENTIONS.md`, and ADR-002 §2 governs
findings/decisions/corrections versus PR bodies — a transient wake message is not obviously in
that class. The citation was doing work it could not support; the argument above stands without
it.)*

**So: `_handoff/` IS the mailbox.** What is missing is not delivery. It is *wake*.

This shrinks the feature to its actual novelty and leaves the delivery guarantee exactly where
ADR-002 already put it.

## 3. Decision — `baron notify` = an existing handoff, plus an event

```
baron notify <persona> --title "..." [--body-file F] [--from <slug>]
                       [--in-reply-to <handoff-stem>] [--max-depth N] [--no-wake]
```

**The order is load-bearing, and rev. 1 got it wrong.**

1. **Deliver** — compose a `_handoff/` addressed to `<persona>` via the existing
   `baron handoff create` path. No new format, no new directory, no new lifecycle.
2. **Publish** — `git push`. **This step did not exist in rev. 1 and its absence made the
   design's headline property false.** `handoff.create` commits but never pushes. A dispatch
   reaches GitHub immediately; a local commit does not. The cloud runner would clone the remote
   and find *nothing* — the wake arriving **before** the message, which is precisely the hazard
   §3 claimed was impossible. Notify must push, and must **not** dispatch if the push fails.
3. **Wake** — fire a forge `repository_dispatch` (`event_type: baron-notify`) naming the persona
   and the handoff stem.

**Delivery is independent of wake — in that direction only.** If the *dispatch* fails (no forge,
no PAT, no workflow, rate limit) the message is pushed and the persona gets it on its next spawn.
The converse does not hold and must not be claimed: a wake without a published message is a
runner spawned to read something that isn't there. Hence the ordering, and hence the failure
mode is "no wake" rather than "empty wake".

`--no-wake` skips step 3 and keeps the command useful with no `gh` at all (ADR-003 §2.3).

**Prerequisite this exposes.** `handoff.create` names files `YYYY-MM-DD-<slug>.md`, but the
emitted `CONVENTIONS.md` documents `YYYY-MM-DD-HHMM-<from>-<topic-slug>.md`. Code and template
already disagree; rev. 1 then described the surface as "ordered (timestamped filenames)", which
is false at date granularity — and intra-day order matters *more* under a low-latency wake, not
less. Reconciling the two is a prerequisite, tracked separately (§8 Q6) rather than smuggled in
here.

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

## 5. Loop safety — rebuilt, because rev. 1's guards did not work

A persona that can wake another can be woken back. Reviewer wakes dev, dev pushes, the push
wakes reviewer. Unbounded, that is a cycle spending the owner's Actions minutes unattended.

**Rev. 1 proposed three guards. Review showed two of them were inert, so they are replaced here
rather than restated.**

### 5.1 — Depth, propagated through the substrate (replaces the payload counter)

Rev. 1 put `depth` in the dispatch payload. That has **no channel**: each spawned agent
re-invokes the CLI fresh, and ADR-003 §2.2 forbids sidecar state, so the next `baron notify`
starts at zero and the cap can never trip.

The fix uses the substrate that already carries everything else. The **handoff frontmatter**
records `wake_depth:` and `wake_origin:`. `baron notify --in-reply-to <stem>` reads the handoff
being answered, increments its depth, and **refuses to wake** past `--max-depth` (proposed
default **2**) — delivering the message regardless, and saying why the wake was suppressed. The
chain is durable, auditable in git, and legible to a human reading `_handoff/`, which is the
same argument ADR-003 §2.2 makes for every other piece of baron state.

Honest limit: this binds only when the caller passes `--in-reply-to`. An agent that notifies
"fresh" restarts the chain. That is a real hole, and it is why 5.3 matters.

### 5.2 — The concurrency group bounds parallelism, not recursion

Rev. 1 claimed `concurrency: { group: baron-notify-<persona> }` guarded the cycle it named. It
does not: reviewer→dev→reviewer alternates between two *different* per-persona groups and never
contends, and `cancel-in-progress: false` queues rather than blocks. It is worth keeping as a
stampede guard, and worth **not** claiming as a loop guard.

### 5.3 — The real backstop: `GITHUB_TOKEN` cannot chain

A workflow run authenticated with the default `GITHUB_TOKEN` **cannot trigger another
dispatch-driven workflow**. So an agent spawned by a wake cannot, with default credentials, wake
anyone else: the chain terminates at depth 1 by platform design.

This cuts both ways and rev. 1 mentioned neither side. It is the strongest loop guard available
— and it is also a **silent failure**: a project that wants legitimate multi-hop wakes must
supply a PAT, and until it does, chained notifies no-op with no error. The emitted workflow
template must say so, and `baron notify` should detect the no-op case and report it rather than
appearing to succeed.

### 5.4 — No automatic repo-event triggers at first cut

Label/review/comment triggers are tempting and the research lists them as first-class, but they
multiply the cycle surface while 5.1's hole is open. Explicit `baron notify` only, until there is
field evidence.

## 6. Forge Protocol extension (additive)

One method: `dispatch_event(repo, *, event_type, payload)`. Added additively, as ADR-003 §5.1
added `create_branch`/`close_pr` for `baron lock`. A `baron.forges` plugin implementing only the
older surface loses `notify --wake` and nothing else; `--no-wake` keeps working everywhere.

## 7. Honest limits

- **The wake needs a forge, an installed workflow, and (for any chain) a PAT.** Without them
  `baron notify` degrades to deliver-only plus a warning — visibly, not silently (§5.3).
- **Enforcement class: none.** This is delivery-and-latency. Nothing makes a persona *read* its
  handoffs; that stays the ritual's job (instructed).
- **It does not, by itself, fix FM5.** Rev. 1 claimed it did. FM5 is the reviewer/dev deadlock,
  and clearing that needs the reviewer's same-SHA idempotency carve-out — permission to re-verdict
  an unchanged head — as well as a wake. A wake alone delivers a nudge into an unchanged
  deadlock. It fixes **FM1** (delivery + latency) outright; FM5 needs the carve-out too.
- **It does not fix FM6.** A decision reaching the work-pull surfaces is ADR-009's problem;
  broadcasting is not reconciling.
- **Idempotency is unresolved and the default is bad.** `handoff.create` raises on a duplicate
  title within a day, so notifying the same thing twice currently yields **no delivery and no
  wake** — on the repeated-nudge case, which is this command's most likely use. §8 Q7.
- **An unknown persona is accepted silently today.** Notify should refuse a slug absent from
  `manifest.personas` rather than filing mail nobody sweeps.
- **GitHub-only at first cut**, and `get_forge` has no graceful path for a forge lacking
  `dispatch_event` — that degradation has to be built, not assumed.
- **Actions minutes are real money** on private repos. §5 bounds the spend; it does not make it
  free.

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
6. **Handoff filename format.** `handoff.create` emits `YYYY-MM-DD-<slug>.md`; the emitted
   `CONVENTIONS.md` documents `YYYY-MM-DD-HHMM-<from>-<topic-slug>.md`. Code and template already
   disagree, independent of this ADR. Fix as a prerequisite here, or as its own change?
7. **Duplicate-notify policy.** Reuse the existing handoff (wake only), suffix a new one, or
   refuse? Today's raise-on-duplicate is the worst of the three for a nudge command.
8. **Should `notify` be capability-gated?** It is not a new verb (ADR-007's precedent: commands
   are not permissions) — but a wake lets persona A spend the owner's Actions minutes, which is
   the first baron command with a direct cost side effect. Rev. 1 did not raise this at all.

## 9. Decision record

- [ ] Approved as written
- [ ] Approved with changes
- [ ] Needs revision
- [ ] Rejected

**Status: awaiting owner review.** No implementation until §8 is answered.
