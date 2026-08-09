---
created: 2026-08-02
accepted: 2026-08-02
type: decision
status: accepted
decided_by: Vikram
adr: 010
project: barony
related:
  - "[[docs/adr/ADR-002-ways-of-working-2026-07]]"
  - "[[docs/adr/ADR-003-baron-cli]]"
  - "[[docs/adr/ADR-007-session-boundary]]"
  - "[[docs/adr/ADR-008-ways-of-working-2026-07-31]]"
  - "[[docs/adr/ADR-009-baron-decision-reconciliation]]"
---

# ADR-010 (ACCEPTED): `baron notify` — waking an idle persona without owning the loop

| Field | Value |
|---|---|
| **Status** | **Approved with changes** (Vikram, 2026-08-02) — all §8 questions answered; not yet implemented |
| **Date** | 2026-08-02 (rev. 2, after adversarial design review) |
| **Authors** | Claude (design proposal for Vikram) |
| **Supersedes** | — (extends ADR-002 §2; constrained by [ADR-007](ADR-007-session-boundary.md)) |
| **Evidence base** | FM1 / FM5 + the 2026-07-31 `research-a2a-wake-nudge` survey |
| **Decision owner** | Vikram |

> **Accepted with changes, 2026-08-02.** All eight §8 questions are answered inline there.
> The owner's substantive departures from the draft: a **slow backstop cron** rather than
> retiring it, and a **manifest allowlist** gating who may fire a wake (§5.5).

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

**`--from` is required when a wake is requested.** It is optional only under `--no-wake`, where it
defaults to the git identity as `baron handoff create` already does. Since `--from` is what the
allowlist and `wake_origin:` key on, an omitted value under a fail-closed gate would otherwise be
an unspecified security decision — refuse rather than guess.

**Push semantics, and a hard platform constraint.** `repository_dispatch` runs the workflow from
the repository's **default branch only** — so a handoff pushed to any other branch is invisible to
the gate, which then cannot resolve the stem and fails closed *silently*. Notify therefore pushes
to the **default branch** of the collab repo, and **refuses to wake** (delivering, and saying so)
when the current branch is not it. This constraint is the platform's, not a choice, and it was
missed by two revisions of this ADR.

A non-fast-forward rejection is **not** retried and **not** forced — it aborts before the
dispatch, reports, and leaves the handoff committed locally. (This deliberately differs from
`ledger.py`, which pushes `origin HEAD` *and* retries on rejection; an earlier revision claimed to
match it and was wrong on both counts.) A collab dir that is not a git repo, or has no remote,
means no wake: deliver and say so.

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

Barony emits `.github/workflows/baron-notify.yml` into the **collab repo** as a **template whose
`spawn` job is an explicitly-marked project-owned slot** — the same shape as `lock-guard.yml`.
(It does NOT follow `strip-stale-verdict.yml` to the code repo: the gate must read
`manifest.yaml`, which lives here — see §5.5.) Barony ships the event, the gate and the seam; it
never ships `claude -p`.

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

The fix uses the substrate that already carries everything else. Every handoff `baron notify`
creates carries two frontmatter fields:

| Field | Meaning |
|---|---|
| `wake_depth:` | hops from the originating human/external trigger. A notify with no `--in-reply-to` writes **0**. |
| `wake_origin:` | the slug that started this chain — copied unchanged from the parent, or set to `--from` when depth is 0. Diagnostic: it answers "who set this off" without walking the chain. |

`baron notify --in-reply-to <stem>` reads the parent handoff, and **writes `wake_depth: parent+1`
into the new handoff** — the increment is persisted, not computed and discarded. (An earlier
revision specified the read and the check but not the write, which breaks the chain at hop 2:
every handoff would carry depth 0 or 1 forever.) It **refuses to wake** past `--max-depth`
(default **2**), delivering the message regardless and saying why the wake was suppressed.

Because §3 step 2 pushes before dispatching, the workflow's gate job reads the same
`wake_depth:` from the same committed file — which is what makes §8 Q3's "enforced in both" a
mechanism rather than an aspiration. The chain is durable, auditable in git, and legible to a
human reading `_handoff/`: the same argument ADR-003 §2.2 makes for every other piece of baron
state.

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

### 5.5 — Who may fire a wake: gated in the WORKFLOW, against committed evidence

A wake spends the owner's Actions minutes, making `notify` the first baron command with a direct
cost side effect. It is still **not** a capability verb — the frozen v1 vocabulary holds, per
ADR-007 (commands are not permissions). The spend is gated by configuration:

**Schema:** additive, optional, and it takes the **next available minor**. ADR-009 §3.2 also
targets the next minor for `backlog.park_label`; the two must be sequenced rather than both
assuming v1.3. Whichever implementation lands first takes it — this ADR deliberately does not
pin a number.

```yaml
# manifest.yaml (additive, optional; collab repo)
notify:
  wake_allowed: [librarian, reviewer]   # personas whose handoffs may trigger a spawn
```

**The check lives in the workflow, not only in the CLI** (owner decision, 2026-08-04). A
CLI-side check gates the *command*; the **dispatch** is what costs, and `gh api …/dispatches`
reaches it without baron ever running. Gating only in `baron notify` would be fail-closed at the
CLI and wide open at the spend point.

#### What the committed handoff does and does not prove

The workflow **must not** read the acting persona from `client_payload`: whoever fires the
dispatch writes it. Nor can it use `github.actor` — under the single-account constraint
(ADR-002 §1) every persona is the same GitHub account.

So the gate reads the handoff that §3 step 2 pushed before dispatching: resolve the **stem** from
the payload (a pointer, not an assertion) under `_handoff/`, then read `from:` and `wake_depth:`
from the committed frontmatter.

**Stated plainly, because two revisions of this ADR overclaimed it: this is detection and audit,
not authentication.** Three reasons, all checkable in the code today:

- `handoff.create` writes `from: {from_}` into the frontmatter *and* `{from_.lower()}:` into the
  commit message **from the same `--from` argument in the same call** (`handoff.py`). A
  "cross-check" between them compares a value with itself and cannot fail except on a hand-edit.
- It passes no `--author`, so the commit author is ambient git config — the one shared account.
- `POST /dispatches` requires **write** access, which is the same access a push requires. An actor
  who can bypass baron can also run `baron notify --from librarian`, which manufactures exactly
  the evidence the gate demands.

The ADR-008 §1 parallel does **not** rescue this. There the SHA is minted by git from content the
reader does not control; here the index and the record are written by one actor in one command.

**What it genuinely buys** — and the reason to keep it — is the ADR-004 §2.2 target class: it
stops the honest and accidental case, catches configuration drift, and turns any bypass into a
committed, attributable git artifact that a human can find afterwards. That is worth having. It
is not a control against a determined actor.

**Dependency: ADR-011 (agent identity at spawn — PR #32, not yet merged).** Per-persona commit signing is what
would make "who wrote this handoff" a fact rather than an assertion, and ADR-011 records that
`from:` has already been forged in practice (a stand-in wrote `from: Iris`, 2026-08-01). Until it
lands, §5.5's gate is bounded as above. When it lands, this section should be revisited rather
than left claiming more than it did on the day it shipped.

#### Two jobs, so a refusal is cheap

A job-level `if:` cannot help — it evaluates before checkout and cannot see repo files. So:

```yaml
jobs:
  gate:    # ~seconds: resolve the handoff, read manifest + wake_depth, emit allowed=true/false
  spawn:   # needs: gate — if: needs.gate.outputs.allowed == 'true'   ← the project-owned slot
```

A skipped job consumes nothing, so an unauthorized wake costs **one short gate job** rather than a
full agent run with model calls. **Honest limit: this bounds the blast radius, not the trigger.**
Anyone who can push to the repo can still cause a gate job to run. The CLI-side check is retained
as well — not as security, but so the honest case fails before any spend at all.

#### Placement: the workflow lives in the COLLAB repo

`manifest.yaml` is in the collab repo, so the gate reads its own data locally with no cross-repo
token — the reason for this choice (owner, 2026-08-04) over the `strip-stale-verdict` precedent of
living beside the reviewed PRs. Where the spawned persona then operates in the code repo, that is
the project-owned `spawn` job's business, using whatever credential the project already gives it.

**Absent `notify.wake_allowed` → nobody may wake.** Fail-closed: a project that has not decided
who may spend money does not spend money. `--no-wake` delivery is unaffected, so the command is
never useless.

### 5.4 — No automatic repo-event triggers at first cut

Label/review/comment triggers are tempting and the research lists them as first-class, but they
multiply the cycle surface while 5.1's hole is open. Explicit `baron notify` only, until there is
field evidence.

## 6. Forge Protocol extension (additive)

One method: `dispatch_event(repo, *, event_type, payload)`. Added additively, as ADR-003 §5.1
added `create_branch`/`close_pr` for `baron lock`.

**It must NOT join the `@runtime_checkable` Protocol** — an earlier revision of this ADR said it
should, and building P2.1 proved that wrong. Declaring `get_issue` on the Protocol there instantly
broke a recorded fake forge in the existing test suite, because `runtime_checkable` `isinstance`
checks test method **presence**: adding a method retroactively invalidates every implementation
that predates it, which is the opposite of additive and would break any third-party
`baron.forges` plugin identically.

So `dispatch_event` follows the pattern P2.1 established: an **optional extension declared outside
the Protocol**, documented as a duck-typed contract and detected with `forge.base.supports()` at
the call site. A forge without it degrades — `notify` reports that the wake could not be fired and
names the missing capability — rather than `AttributeError`-ing at dispatch time.
`--no-wake` keeps working everywhere.

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

*All answered — Vikram, 2026-08-02. Recorded verbatim so the reasoning survives.*

1. ~~**Is dropping the mailbox right?**~~ — **YES, stands.** Adversarial review upheld it
   independently and supplied the stronger argument (`_handoff/` already carries `priority:`).
2. ~~**Cron: retire or keep?**~~ — **SLOW BACKSTOP.** Drop the pilot's 15-minute cron to
   hourly/daily as a safety net rather than retiring it. Rationale (owner): §5.3's silent-no-op
   paths — missing PAT, missing workflow, rate limit — are real, so something must still catch a
   wake that never fired; a slow cron kills most of the empty-sweep burn without removing the net.
3. ~~**`--max-depth 2`, and where does the guard live?**~~ — **default 2, enforced in BOTH.** The
   CLI refuses to fire past the cap; the workflow re-checks. Belt and braces, because §5.1's chain
   only binds when the caller passes `--in-reply-to`.
4. ~~**Repo-event triggers in the first cut?**~~ — **OUT**, as §5.4 proposed.
5. ~~**Is this the right next build?**~~ — **build everything, sequenced by dependency**
   (owner: "all either in parallel or sequential as it makes sense"). Measurement work that needs
   no decision runs first/alongside; design-blocked items follow their ADRs.
6. ~~**Handoff filename format.**~~ — **its own change.** The code/template disagreement predates
   this ADR; fixing it here would smuggle an unrelated behaviour change into a wake feature.
7. ~~**Duplicate-notify policy.**~~ — **reuse the existing handoff and wake only.** Today's
   raise-on-duplicate yields neither delivery nor wake on the repeated-nudge case, which is this
   command's most likely use. Specifics an implementer would otherwise guess: a `--body-file` on a
   reuse is **appended** as a dated note, never overwriting what is there (append-only, ADR-002
   §2); and a same-day handoff already `git mv`'d to `_handoff/archive/` is **not** reused — it is
   closed, so a new one is created. Reuse means "still open and addressed to the same persona".
8. ~~**Capability-gating.**~~ — **GATE VIA MANIFEST CONFIG** (owner's call; §5.5 below). Not a new
   capability verb: the frozen 10-verb vocabulary stays frozen, per ADR-007's rule that commands
   are not permissions. Instead an explicit allowlist in `manifest.yaml` names which personas may
   fire a wake.

## 9. Decision record

- [ ] Approved as written
- [x] **Approved with changes** (Vikram, 2026-08-02)
- [ ] Needs revision
- [ ] Rejected

**Changes from the draft:** the pilot cron becomes a slow backstop rather than being retired
(§8 Q2), and who may fire a wake is gated by a fail-closed `manifest.notify.wake_allowed`
allowlist rather than left ungoverned (§8 Q8 → §5.5). Rev. 2's four corrections — push before
dispatch, depth via handoff frontmatter, the concurrency group demoted to a stampede guard, and
the `GITHUB_TOKEN` chain limit — are folded in. Cleared for implementation.
