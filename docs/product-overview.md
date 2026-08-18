# Barony — Product Overview

**Barony proves that agent-written code was reviewed by something other than the thing
that wrote it — as signed artifacts in your own repo, checkable offline, on any forge.**

This page is for a technical evaluator deciding whether Barony is worth an afternoon. It
states the problem from first-party evidence, the architectural thesis, the capability
set, and — throughout — the bounds. Nothing here is a projection: every claim is either
a shipped mechanism with an ADR behind it, or is labelled as not-yet-true.

For the companion table of *what each capability buys and how you'd measure it*, see
[capability-value-map.md](capability-value-map.md). For the walk-through with real
command output, see [user-guide.md](user-guide.md). For concepts at paragraph length,
[concepts.md](concepts.md).

---

## 1. The problem

Run two or more AI coding agents on one long-lived repository and three things break at
once. Each is stated here with the first-party incident that produced it — Barony's own
pilot fleets, recorded in the ADRs rather than recalled as an anecdote.

**Attribution stops working.** On **2026-08-04** an un-onboarded Codex agent committed to
`vggg/barony`'s `main` **under the owner's git identity**. From the repository alone that
commit is unattributable: it reads as a human. Git author fields are self-asserted
strings, so any process with a checkout can produce a commit, a handoff, or a finding
indistinguishable from the owner's — and a `from: Iris` line in a handoff is likewise a
claim with nothing behind it ([ADR-027](adr/ADR-027-agent-identity.md) §1). The forge
does not help: every persona shares one login, so the platform's own author field
attributes everything to the same account.

**Capability boundaries decay into prose.** A dev persona on the badminton-analyzer pilot
merged **~15 PRs while `merge_pr` was denied in its own config** — then, asked about it,
correctly refused the same operation. This is FM4, and the interesting part is that
nothing malfunctioned: the guard hook had never been wired into the runtime's settings,
so the denial degraded to persona text exactly as designed, and **silently**. An absent
enforcement mechanism and a mechanism that never had to fire leave identical evidence.
The same shape recurs as **FM1** (fleets are poll-only; a human is the message bus, so
work stalls waiting on nobody) and **FM6** (a ratified decision never reaches the
work-pull surfaces, so a closed question keeps generating work).

**Review verdicts are unfalsifiable claims.** A review verdict is a PR comment or a
label. A label survives a force-push, so "approved" can describe code that no longer
exists. And under a single shared forge account, the dev whose code is under review can
post its own `REVIEW:PASS` — the gate, given its inputs, correctly returns *allowed*
([ADR-033](adr/ADR-033-signed-review-verdicts.md) §1). Barony's whole premise is
separation of duties among agents: reviewer reviews in a fresh context, merger is a gate
and not a button, an author does not approve its own work. Every one of those was, until
recently, a sentence in a persona file — and FM4 is the standing evidence for what a
sentence in a persona file is worth.

Net: teams accumulate agent-written code they cannot **prove** was independently
reviewed. Not "did not review" — cannot *prove*, later, to someone who wasn't there.

**What this problem is not.** It is not "I can't see what my agents cost" — the platforms
ship that. It is not orchestration; Barony has no scheduler, message bus, or agent-to-agent
RPC. And it is not adversarial defence: this is not a sandbox and does not pretend to be.

## 2. The thesis

**The git repo is the only source of truth. Anything hosted is a rebuildable cache. A
control plane cannot attest to itself.**

Three claims, in dependency order.

*The repo is the record.* `baron` is a disciplined reader/writer over plain markdown and
git and introduces **no second store** ([ADR-003](adr/ADR-003-baron-cli.md) §2.2).
Structured output (`--json`) is a view, never a second authority. "Who may do what", "who
did what", and "what is true now" must stay answerable from a bare clone
([ADR-022](adr/ADR-022-substrate-invariant-amended-default-not-only.md)). The bound has a
test a reviewer can actually run rather than a taxonomy to interpret: **delete every
plugin, clone fresh, ask the three questions.** If an answer is lost, the plugin was
holding governance state and is forbidden. If only the *speed of finding it* is lost, it
is permitted.

*Anything hosted is a cache.* ADR-022 amended the original invariant from "the repo is
the only source of truth" to "git + markdown is the **default** substrate" — a plugin may
be authoritative for derived domains (semantic search, embeddings, cross-project recall)
and **never** for authority, evidence, or the ledger. The amendment authorises nothing to
be built; it answers "may we ever?", not "may we now?".

*A control plane cannot attest to itself.* A forge's audit log is an assertion by that
forge about that forge. It is genuinely useful and Barony does not replace it. But the
value of an attestation is proportional to the **distance** between the attester and the
attested — and a log cannot certify that the control plane emitting it was configured
correctly. Barony's artifacts are verified with `git verify-commit` and `ssh-keygen -Y
verify` against an allowed-signers file **that lives in the repo**: on a laptop, offline,
with no Barony installed, after the vendor is gone, on whatever forge you migrate to.
That property is not an architecture preference. It is the product.

## 3. The capability set

Fourteen surfaces. Each paragraph says what it is and why it matters; the bounds are in
line, not in a footnote.

### Capability enforcement — `baron guard`

Every persona declares capabilities once, runtime-neutrally, from a **frozen 10-verb
vocabulary** (`read_code`, `read_collab`, `write_code`, `write_path: [scope…]`, `open_pr`,
`run_tests`, `merge_pr`, `push_main`, `force_push`, `edit_other_personas`). `baron guard`
is a pre-tool hook that reads the *pending* call, maps it to those verbs, and refuses a
denied one **before the tool executes** ([ADR-004](adr/ADR-004-baron-guard-enforcement.md)).
Parsing is conservative — an ambiguous push target is denied, with the inference named —
and it fails closed on malformed input, but is never a brick: `BARON_GUARD_OVERRIDE=<reason>`
allows the call and appends to a **tracked** log, so every override shows up in a diff.
Why it matters: this is the difference between a rule and a control. Barony labels every
denial **enforced** or **instructed** and refuses to round up — six of the ten verbs
enforce, four are instructions, and CI fails an adapter claiming enforcement it cannot
deliver.

**L0 — the policy is not writable by the party it governs**
([ADR-034](adr/ADR-034-deterministic-capability-enforcement.md)). Enforcement layered on a
document the enforced agent can rewrite is theatre, and until v1.20.0 it was: the hook
re-reads the persona file on *every* call, a persona's own spec dir was always writable,
and `.claude/settings.json` was an ordinary path — so a persona holding `write_code` could
**grant itself a denied verb, or unwire the hook, in one edit**. L0 closes that seam
**structurally**: `agents/*/persona.yaml` (any persona's), the acting persona's whole
`agents/<slug>/` dir, `.claude/settings.json{,.local}`, `.baron-waivers.yaml`,
`.baron-rules.yaml` and `.barony/allowed_signers` are refused for **every** persona,
whatever its capabilities. This is not a capability check — **no verb unlocks it**,
including `edit_other_personas`, and the refusal is booked `unevaluated` rather than
`enforced` precisely because no capability decided it. Paths match on **trailing**
components, so the copy inside an emitted runtime kit — the live hook wiring — is fenced
too. The consequence, stated as the feature it is: **changing a capability set is now a PR
a human merges, for everyone, always, including a solo owner.**

**Bounds, in line.** The parser does not recurse arbitrarily into interpreter command
strings: v1.20.0 narrows the class by re-running one level of `bash -c '<payload>'` through
the same evaluators, but a payload past that cap, or one that is untokenisable, is
conservative-denied only for `merge_pr`/`push_main`/`force_push` — everything else in a
wrapper still passes uninspected, as do `python -c`, `eval`, base64 indirection and script
files. L0 governs the **write tools**, not the filesystem: a shell redirect
(`echo … > .claude/settings.json`) is not a tool call and guard never sees it, and
`~/.claude/settings.json` is outside the repo root and invisible to L0 entirely. And the
one caveat on "no verb unlocks it": `BARON_GUARD_OVERRIDE` is applied *after* the decision,
so it waves through an L0 refusal too — deliberately. It never bricks a workspace, reaching
it requires a shell rather than a governed tool call, and every use appends to a **tracked**
`.baron/guard-override.log`, so the bypass lands in a diff as evidence. Where the boundary
must hold against a wrapper or a hostile workspace, use OS-level isolation.

### Enforcement wiring self-test — `baron doctor`

FM4's real lesson was not a bypass; it was **absence**. `baron doctor`
([ADR-017](adr/ADR-017-baron-doctor-wiring-selftest.md)) runs ten read-only checks —
executable resolves, hook present, matcher covers every governed tool, persona and rules
load, malformed stdin fails closed, no exported override, and a synthetic denial fed to
*the executable the hook names* really exits 2 — exiting 1 with a remedy line per failure.
The tenth, `platform-layer` ([ADR-034](adr/ADR-034-deterministic-capability-enforcement.md)
L3), is **INFO and never FAIL**: it reports whether branch protection is on and whether each
persona has its own push credential. Baron *reports* that wall and never builds it — and it
is doctor's only networked check, so it is opt-in behind `BARON_DOCTOR_PLATFORM=1` and a
green run stays reproducible offline.
Spawning the hook's own command rather than importing the module is load-bearing: a
project wired to a stale `baron` is the same drift as a missing hook. **Bound, printed on
every run:** doctor verifies **wiring, not invocation**. Green means "correctly wired",
never "enforcement happened".

### The deterministic merge gate — `baron merge check`

The merger archetype has always been specified as *a gate, not a button* — and that
specification lived entirely in prose, which FM4 proved is the weakest tier available.
`baron merge check <pr>` ([ADR-028](adr/ADR-028-mechanized-merge-gate.md)) scores four
preconditions in order against **one PR snapshot**, so the verdict's sha, the labels, and
the check runs all describe the same observed head: `pr_open`, `verdict_at_head` (a
`REVIEW:PASS <sha>` whose sha *equals the current head*), `no_changes_requested`,
`ci_green`. Exit 0 or exit 1 with the **first** failing precondition, a stable reason
slug, and the sha it checked — one named blocker, because a merger handed four complaints
starts triaging. Fail-closed everywhere: pending CI, absent CI, an abbreviated sha (never
prefix-matched), an unreachable precondition — all refusals. Labels are collected and
printed as **ignored in both directions**: an approval label cannot rescue a stale
verdict, and a changes-requested label cannot block a clean head. **Bound:** it never
merges, and there is deliberately no `baron merge do` ([ADR-007](adr/ADR-007-session-boundary.md)).
Exit 0 means "these preconditions hold", not "merge it".

### Agent identity — per-persona SSH signing keys

`baron identity init --persona <slug>` generates a per-persona SSH signing key, configures
**repo-local** git to sign commits and tags with it under a distinct
`<slug>@agents.barony.invalid` author email, and writes an enrollment **request** into
`.barony/allowed_signers` — a file **in the repo**, so a clone is sufficient to verify
anything, offline, forever ([ADR-027](adr/ADR-027-agent-identity.md)). It then **exits
non-zero until that request is merged at HEAD**. The agent cannot merge it: `.barony/` is
CODEOWNERS-owned, and that one human merge is the trust root. Identity precedes work.
`baron verify identity --base…--head…` is the CI gate: per commit, signature valid against
the in-repo allowlist, git trust status `G`, and a **three-way cross-check** — signer
principal ↔ the persona the commit claims (a `Barony-Persona:` trailer and/or the
`agent-<slug>` routing label, checked independently) ↔ an `agents/<slug>/persona.yaml`
registry entry. Handoffs and findings take detached signatures; a signature that fails to
verify is refused **and recorded as a finding**, because an attribution failure is
evidence, not something to drop. Why it matters: this is what makes reviewer ≠ author a
checkable fact rather than a label. **Bounds, two of them:** agents still push under the
**owner's** forge identity — there are no per-persona tokens or machine accounts anywhere
in this, and attribution comes from the *key*, not the account. And it establishes
attribution among **cooperating** agents: private keys sit unencrypted in each agent's
workspace, so it is not a defence against a hostile actor with write access there.

### Signed review verdicts

The reviewer SSH-signs its verdict **into the repo** — `.barony/verdicts/pr-<n>-<sha12>.md`
plus a detached `.sig` under the `barony-verdict` namespace — verified with `ssh-keygen -Y
verify` against the *same* `.barony/allowed_signers` that already backs commits
([ADR-033](adr/ADR-033-signed-review-verdicts.md)). No new trust root, no bespoke
envelope, no network. Four legs are asserted, each closing a specific failure: (1) the
signature verifies against the in-repo allowlist — not a self-minted key in a crypto
costume; (2) the signed **content** binds (repo, PR, sha) — re-derived from the content
and never the filename, because a filename is not covered by a signature and trusting it
would make the binding forgeable with `cp`; (3) the signer is a **reviewer-archetype**
persona — enrolment says *who*, the persona registry says *what they are for*, and without
this leg a dev's genuinely-enrolled key produces a genuinely-valid verdict; (4) the signer
is **not the author**, where the author is the head commit's signing principal (`%GS`) and
deliberately *not* the git author field, whose untrustworthiness is exactly what the
2026-08-04 incident demonstrated. An author baron cannot resolve is `verdict_author_unresolved`:
fail-closed, because an author that cannot be named is not an author that differs. The PR
comment is demoted to a human-readable **index** of the artifact. **Posture:** a signature
that is present and does not verify **always** refuses. A *missing* signed verdict warns
by default and refuses under `--require-signed-verdict` — turning absence into a refusal
fleet-wide is a change somebody should sign, not one that arrives as a default. An
unattested pass renders as `UNATTRIBUTED`, never as a clean pass.

### The prior-art gate — `baron adr check`

On 2026-08-14 an ADR session designed per-persona identity from first principles; a
2026-08-04 spike had already explored that ground. Nothing shipped wrong — the work was
simply **re-derived**. The instructive part is where the failure was *not*: the prior art
was written down, findable, and in the corpus maintained for exactly this purpose. No step
in the authoring path ever *asked* whether it had been consulted, so the answer was never
wrong — it was never requested ([ADR-029](adr/ADR-029-prior-art-gate.md)). `baron adr check`
refuses an ADR marked `status: accepted` whose **Supersedes / Prior art** section is
missing, malformed, or incomplete: which corpora were searched, with what query, on what
date, and every hit cited or explicitly superseded. It gates `docs/adr/` in CI;
`baron adr scaffold` emits the shape. **Bound, stated in the ADR rather than implied:**
the companion rule — that a decision is not canonical until promoted to an accepted ADR —
is **instructed**. Only the sweep record is mechanized, and the ADR says so plainly rather
than letting the mechanized half lend the unmechanized half its credibility.

### The read-only observer

A sixth archetype ([ADR-030](adr/ADR-030-observer-archetype.md), proposed): a cron-triggered
persona that reads everything — handoffs, ledgers, wiki, personas, git and PR activity, the
event plane, health rollups — and writes exactly one zone, `observations/`, plus `_handoff/`
as its single escalation path to the Librarian. Reads are broad deliberately: narrowing them
would only make the notes wrong. It has **no numbering authority** — an observation that
deserves a number is *proposed* by handoff and numbered by the Librarian — so the ledger
keeps one writer. It is also the cheapest possible first fleet member: a persona that cannot
change anything has no blast radius, and if the archetype is wrong the cost is a directory of
notes. **Bound:** its read-only-ness rests on the *write* side, because ADR-020 makes the read
verbs `instructed`.

### The coordination monorepo

One collab repo per project is the default and stays it — that default is what buys
multi-tenant isolation and independent lifecycle. For a single owner running several fleets
it buys mostly repo sprawl and no cross-project view, so `baron init --layout monorepo` +
`baron add-project` emits the other topology ([ADR-025](adr/ADR-025-coordination-monorepo.md)):
one collab repo whose **projects are subdirs**, each with its own `manifest.yaml`, `agents/`,
`_handoff/`, `decisions/`, `findings/`, `wiki/`. `_meta/` is the portfolio project — no code
repo, its work items are the cross-project decisions. The recursion is the point: the
portfolio is a project that coordinates projects, governed by the same primitives one level
up. Code repos stay separate and per-project; only the coordination substrate is unified.
**Cost, stated:** access is all-or-nothing, because a monorepo cannot grant per-project
access. It is a mode, not a replacement.

### The persona sidecar

Deploying a fleet was bespoke: a hand-written launcher on one machine, which is what keeps
autonomous fleets at "works on the author's laptop". A **sidecar** packages one persona as a
deployable unit — the `baron` CLI, the emitted runtime kit, and a work loop that is either
notify-driven or scheduled ([ADR-026](adr/ADR-026-persona-sidecar.md)). The collab repo is
the shared state: clone/pull, read addressed handoffs, do a unit of work, push, then exit
(ephemeral) or wait (long-running). `baron init` emits `agents/<slug>/sidecar.sh`; `baron
sidecar run <persona>` is the CLI form; `--dry-run` prints the plan and the brief without
invoking anything. **Bound:** ADR-007 holds — the runtime invocation stays project-owned.
Barony does not own the agent loop.

### Fleet health — `baron health`

The pilot produced the numbers that say whether an autonomous fleet is *healthy* —
mutation-kill rate, claim drift and its direction, reviewer escape rate, per-author
breakdown, dev-side stalls — and emitted them to a private JSONL on one machine, auditable
by nobody ([ADR-024](adr/ADR-024-fleet-health.md)). `baron health` makes that a substrate
surface: verdict metrics come off the observation plane as a `review.verdict` event kind,
the stall/divergence half is reused from `baron status` rather than rebuilt, and at the root
of a monorepo it rolls up portfolio-wide. **Bound, in the ADR's own §5:** it measures **what
was emitted**. A reviewer that runs no mutations reports no mutation-kill rate, and that is
an absence of evidence, not a clean bill of health.

### The observation plane

One event vocabulary, git-native, with pluggable sinks and — deliberately — a **default sink
of `null`**, so adopters opt in rather than discovering telemetry they never agreed to
([ADR-013](adr/ADR-013-observation-plane-events-and-sinks.md) §7.1: *a default nobody signed
and a default somebody signed look identical in a diff*). One binary answers five hook
events, but only the pre-tool one can ever block; the other four are **evidence only** and
always exit 0 — enforcement fails **closed**, evidence fails **open**, because a hook that
blocks session start cannot be un-blocked from inside the session. Each row's
`baron.enforcement` attribute is a **per-call observation** — did a capability actually
adjudicate *this* call — read off an explicit flag defaulting to `False`, so any path
returning without a real decision is `unevaluated` **by construction**
([ADR-018](adr/ADR-018-adjudicated-enforcement-on-the-event.md)). That design came out of a
measured defect in merged code: the first cut derived the label from a static property of a
*verb*, which cannot answer a question about a *call*, and was wrong in both directions at
once. Neutrality is a measurement, not an intention: two runtimes write the same plane and
their rows differ in exactly four attributes ([ADR-019](adr/ADR-019-runtime-neutral-event-plane.md)).
**Caveat any consumer needs:** the verb tuple is not a proxy for the enforcement field —
filter on `enforcement == "enforced"` *before* grouping by verb, or the count is fiction.

### The wake — `baron notify`

Fleets are poll-based: a persona acts only when spawned. Nothing wakes the responsible agent
when a verdict lands, so a human is the message bus — FM1, and the mechanism behind the
reviewer-feedback stall ([ADR-010](adr/ADR-010-baron-notify-wake.md)). The external survey
settled the landscape question: **no agent framework wakes a cold headless agent** — every
one of them resumes something already running. Cold-starting an ephemeral CLI agent from an
external event is the platform's job, so the wake is a `repository_dispatch`, with a manifest
allowlist gating who may fire one. The deliberate departure: **there is no new mailbox.**
`_handoff/` is already ordered, addressed, durable, and swept at session start; adding a
second delivery surface would split the record the whole design depends on.

### `baron export`

The corpora a collab repo already keeps — ADRs, decisions, findings, handoffs, and since
[ADR-032](adr/ADR-032-export-reach-monorepo-and-widened-corpus.md) curated status and notes —
walked into flat records that each name **the commit whose bytes were parsed**
([ADR-015](adr/ADR-015-baron-export.md)). The citation gate is the substance: a source that
is untracked or modified is **skipped and named**, rather than emitted with a sha that
resolves and returns different text, so `git show <sha>:<path>` always reproduces a record's
bytes. Measured on a real pilot repo: 284 records, all 284 citations verified by
byte-equality. Because that property belongs to the corpus walk and not to any backend, every
candidate consumer inherits it for free.

### Identity onboarding — `baron identity register|enroll|protect`

The identity runbook is a list of owner actions: register each persona's public key as a
GitHub signing key, open the enrollment PR, turn on the branch ruleset. Deterministic, and
exactly the kind of checklist that gets half-done on persona seven — so each step is a
command. What it does **not** do is move the trust boundary. `enroll` opens the enrollment
*request* and stops; there is deliberately no `--merge`, because an agent that could merge its
own enrollment could mint peers. **Dry-run is the default everywhere** — each command prints
the exact argv and payload it would send and exits; `--apply` is the only thing that executes,
because a command whose default is "act" reads identically to one whose default is "explain"
right up until it has acted. And **no credential is handled here, ever**: every call runs
through `gh` under the operator's existing session. There is no `--token` flag to pass one.

## 4. What this is not

Stated plainly, because the fastest way to lose a technical evaluator is to let them
discover a bound themselves.

- **Not a sandbox, and not adversarial defence.** Barony stops a *cooperating* agent from
  doing the wrong thing. It does not stop a hostile one with shell access: the `bash -c` class
  is **narrowed** in v1.20.0, not closed, and L0 fences the guard's own config against the
  *write tools* while a shell redirect still reaches those files. Never read "enforcement"
  here as "security".
- **Not a runtime, control plane, or agent framework.** No scheduler, no message bus, no
  agent-to-agent RPC. Coordination happens at git tempo, which is the point: every
  coordination event leaves a reviewable record.
- **Instructed is not enforced.** Four of the ten verbs are instructions. `read_code` and
  `read_collab` label `instructed` because **baron emits no mechanism capable of omitting the
  read tools** — measured once per shipped adapter, including a live test that a persona
  *denying* `read_code` keeps them. The bound is exact: baron emits no mechanism, **not** that
  a runtime cannot enforce them ([ADR-020](adr/ADR-020-read-verb-posture-measured-on-four-adapters.md)).
  That correction made baron report *less* enforcement than it used to, which is the direction
  a claim should move when it turns out to be soft.
- **Attribution among cooperating agents, not a hostile-workspace defence.** Private keys sit
  unencrypted in each agent's workspace. Whoever holds one *is* that reviewer.
- **`baron health` measures what was emitted.** Silence is not health.
- **`baron doctor` verifies wiring, not invocation.** v1.20.0 adds a tier that *does* drive a
  real runtime process against a scaffolded repo and asserts the denied operation did not run
  ([ADR-034](adr/ADR-034-deterministic-capability-enforcement.md)) — but it is **opt-in,
  advisory, gates nothing, and as of this writing has not been run**. Until it has, enforcement
  is still proven by wiring. Read that tier as owed measurement, not as a receipt.
- **Zero external adopters.** Every receipt on this page is first-party — Barony's own pilots
  and audits. The most honest number in the corpus is a first-party audit that scored the
  author's own project at **0.53 operational fidelity** and published it rather than rounding
  it up.

The enforcement is soft. The **proof** is hard — an unsigned commit cannot be made to look
signed, and a verdict cannot be made to look bound to a sha it wasn't bound to. That
asymmetry is the whole design.

## 5. Where to go next

| You want | Read |
|---|---|
| What each capability buys, and the metric it moves | [capability-value-map.md](capability-value-map.md) |
| Install → scaffold → a real guard denial on screen | [user-guide.md](user-guide.md) |
| Every concept at paragraph length | [concepts.md](concepts.md) |
| The arguments, not the summaries | [adr/](adr/) — and [adr/README.md](adr/README.md) as the map |
| The bounds that are *not* verified | [DECISIONS-FOR-REVIEW.md](DECISIONS-FOR-REVIEW.md) §E |
| How a Claude-Code-only skill became runtime-agnostic governance | [history.md](history.md) |
