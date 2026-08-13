# Barony concepts — the longer form

The [README](../README.md) gives each concept three sentences; this page gives
each one the paragraphs it deserves. The canonical spec itself lives in
`skills/barony/references/` — this page explains, the references define.

## The front door

Every new project and every joiner routes through one file:
`skills/barony/assets/collab-repo/START.md`. It routes by **directory state**,
not by a human choosing a mode: a new/empty directory goes to `ORCHESTRATE.md`
(set up a project — interview the owner, author `manifest.yaml`, hydrate the
roster); an existing collab repo goes to `PARTICIPATE.md` (claim a persona,
hydrate yourself, run the session ritual). Since v1.8,
`baron init` performs ORCHESTRATE's mechanical steps deterministically
([ADR-006](adr/ADR-006-baron-init-template-packaging.md)); the conversational
path keeps the judgment work — real scope prose, roster design, Tier-3
hydration.

The pre-v1.0 Claude-Code-only emit modes are deprecated and quarantined in
[`legacy/`](../legacy/) (existing v0.x projects only). See
[history.md](history.md) for how the repo got here.

## What gets generated

A dedicated **collab repo** — the coordination substrate, separable from your
code repo:

```
README.md                 # project overview
CONVENTIONS.md            # repo-wide rules (single-account constraint, identity, labels,
                          #   routing, handoff lifecycle, machine-local state)
COORDINATION.md           # multi-persona protocol (hot files + lock mechanics, review/merge,
                          #   ADR rules, ticket lifecycle)
manifest.yaml             # machine-readable project spec (repos, backlog, roster)
canon/                    # the runtime-neutral spec, copied in so joiners can resolve it
adapters/                 # per-runtime HYDRATE.md (claude / code-puppy / pydantic-ai / generic)
agents/
  <persona-slug>/
    persona.yaml          # CANONICAL machine truth: identity, capabilities, scope, ritual
    AGENT.md              # human-readable manual, derived from the yaml
    runtime/              # per-runtime kit emitted by baron init (v1.8)
_handoff/                 # cross-persona async messages (append-only; archive/ on close)
decisions/  findings/     # project decisions + investigation outputs (numbered ledgers)
wiki/                     # synthesised by the Librarian
```

Persona archetype templates shipped (each `persona.yaml` + `AGENT.md`):

- **dev** — interactive persona, one per human collaborator
- **librarian** — wiki + indexes + drift checks; always present
- **autonomous-event** — webhook-triggered (e.g. PR checks, backtest runner)
- **autonomous-cron** — scheduled (e.g. PM+UAT)
- **reviewer / merger** *(optional,
  [ADR-002](adr/ADR-002-ways-of-working-2026-07.md))* — adversarial SHA-bound PR
  review (the **signet** pattern: a verdict sealed to the exact commit it
  judged) + a merge gate that isn't the human owner

Plus the `/vc` slash-command template
(`skills/barony/assets/commands/vc.md`) for the canonical
`<persona>: <op> | <description>` commit workflow, and a realistic worked
example of the project spec at
`skills/barony/assets/collab-repo/manifest.example.yaml`.

## Personas and the capability vocabulary

A persona is defined once, runtime-neutrally, in `persona.yaml`: identity (name,
email, commit prefix, routing label), scope prose, session ritual, and
capabilities drawn from the **frozen 10-verb vocabulary**
(`skills/barony/references/capability-vocab.v1.md`): `read_code`,
`read_collab`, `write_code`, `write_path: [<scope>...]`, `open_pr`, `run_tests`,
`merge_pr`, `push_main`, `force_push`, `edit_other_personas`. The verbs are
intent-level (`open_pr`, never `gh_pr_create`); the path-scoped write verb takes
scopes as data (`write_path: [findings, _handoff]`). Additions require observed
need — every v1 verb was coined during adapter work and exercised in a real
dogfood project before freezing.

## The capability ladder and the honesty ladder

Each runtime maps the abstract verbs onto its real tools via an **adapter** —
the only runtime-specific surface (`adapters/<runtime>/HYDRATE.md`, under
`skills/barony/assets/collab-repo/`). Adding a runtime means adding an adapter
folder and touching nothing else. A persona always runs at the highest tier its
runtime supports and degrades gracefully:

| Tier | Runtime | Mechanism | Enforcement |
|---|---|---|---|
| 3 (code-puppy: 2.75) | Claude Code or code-puppy | native sub-agents (Claude `.claude/agents/<slug>.md`; code-puppy JSON agents) | capabilities enforced via a tool allow-list — whole-tool denials are real (a read-only persona genuinely cannot write/run shell); sub-tool denials instructed, except the five guard-covered ones on Claude, which are enforced-with-baron via the hook (`open_pr`/`run_tests` stay instructed everywhere) |
| 3 | pydantic-ai (+ pydantic-ai-harness) | in-process hydration: `baron.runtimes.pydantic_ai.build_agent` assembles a guarded `Agent` | the five guard-covered sub-tool denials natively ENFORCED (in-process interception consuming `capability-rules.v1.yaml`); whole-tool denials by capability omission **where the hydrator actually omits the tool** — it does not for the read verbs, which is measured, not assumed (see below) |
| 2 | Claude Code | persistent `CLAUDE.md` | persistent session context; capabilities instructed |
| 1 | anything | in-prompt + emitted `AGENTS.md` | persona re-read each turn; self-enforced |

The Claude adapter renders either Tier 2 or Tier 3, selected by a
runtime-neutral `adapters.claude.tier` config (`auto` | `2` | `3`, default
`auto`).

Alongside the capability ladder runs the **honesty ladder**: every denial claim
in an adapter's capability map is classed `enforced`, `enforced-with-baron
(instructed otherwise)`, or `instructed`, and `tests/bi_runtime_accept.py` fails
CI if an adapter claims enforcement it cannot deliver (e.g. a guard claim on an
`open_pr` row). "Emitting a file does not upgrade the tier" is a rule the
templates themselves carry.

`baron rules list` is where that ladder becomes a queryable surface
([ADR-016](adr/ADR-016-externalizable-capability-rules.md)). It reports three
states for *who could* enforce a verb — `guard` (baron mechanically checks it),
`adapter-dependent` (whole-tool class; a runtime with a tool allow-list could
enforce it by omitting the tool), and `instructed` (nothing checks) — and
**only `guard` earns the printed word `enforced`.**

The read verbs are the worked example of what that costs. `read_code` and
`read_collab` were briefly labelled `enforced` on the theory that a whole-tool
verb is enforced by tool omission. The shipped pydantic-ai hydrator builds
`FileSystem` unconditionally, so a persona *denying* `read_code` keeps its read
tools — a test measures it. They now label `instructed`, which means baron
reports **less** enforcement than it used to. That is a correction, not a
regression, and it was made by the owner rather than absorbed from a merge.

Since [ADR-020](adr/ADR-020-read-verb-posture-measured-on-four-adapters.md) the
label rests on **four measured adapters rather than one measurement generalised
to four**, and the reason it was cheap is worth knowing: proving the *absence* of
a baron-emitted enforcement mechanism is a static inspection of what `baron init`
generates, where proving *presence* would need a live runtime. Each static test
is an A/B — two persona specs identical but for the two read verbs — asserting
that the denial reaches the kit's **prose** while every machine-readable artifact
stays byte-identical. If nothing baron emits is even a function of the denial,
the denial cannot be mechanised by anything baron emits.

**The bound is exact, and it is published with the label rather than in a
footnote:** *baron emits no mechanism capable of omitting the read tools* — **not**
*the runtime cannot enforce them*. A hand-written `permissions.deny`, or the
Tier-3 subagent the `claude` and `code-puppy` recipes tell a human to author, does
enforce them; baron generates neither. So those adapters' HYDRATE.md tables print
`enforced` for the read verbs while `baron rules list` prints `instructed`, and
both are right about different things. The divergence is recorded, not resolved by
editing whichever table is more convenient — the durable fix is a per-runtime
matrix that can say "instructed as shipped, enforced at Tier 3 once hydrated"
without either surface lying, and it is on the backlog.

The enforcement rule table itself — which git commands map to which verbs, the
write-path scoping semantics, the conservative-deny ambiguity policy — is a
single versioned artifact, `capability-rules.v1.yaml`, shipped as baron package
data and loaded by every enforcing consumer
(`skills/barony/references/capability-rules.md`). Consumers never restate the
patterns, so a `git push origin main` is judged identically on Claude Code and
on pydantic-ai.

## Ledgers, handoffs, and the index

**Findings** (investigation outputs) and **decisions** are numbered entries
(`F<N>` / `D<N>`) in plain markdown indexes. `baron finding new` /
`baron decision new` allocate race-safely: parse the index for the max ID,
append, commit, push — and on push rejection, roll back, `pull --rebase`,
renumber, retry. Git's push atomicity is the lock; there is no counter file or
allocation service. Duplicate numbers are errors; historical gaps are reported
but never renumbered — rewriting history to be tidy would forge the record.

**Handoffs** are the cross-persona message surface: everything material —
findings, decisions, and especially **corrections** — gets a `_handoff/` file
with standard frontmatter (`created`, `status: open|done`, `for`, `from`,
`priority`). A number in a PR body is not a claim; only a handoff is. Closing a
handoff flips the status, records a `closed:` date and optional note, and
`git mv`s it to `_handoff/archive/YYYY/` — archive, never delete. `baron index`
regenerates a marker-delimited summary block in `_handoff/README.md`
(open/done/archived counts + the open table) without touching prose.

## The divergence radar and waivers

`baron status` is the estate inspection: for every clone and worktree named in
the manifest it reports ahead/behind origin (stranded or stale work), dirt,
unmerged branches with age, open handoffs past the SLA (default 14 days), and
ledger/wiki staleness (a labeled heuristic). Exit 0 green / 1 any red, so CI can
run it. The three red divergence classes are exactly the three stranding modes
of the 2026-07-22 field incident ([ADR-003](adr/ADR-003-baron-cli.md) §1).

`baron validate` covers the other drift axis: the personas a project *declares*
against the agents its runtime has actually *registered*. **The signal is partial
registration** — some registered and others not is evidence the project hydrates
agents here, so the gaps are errors; all-or-nothing is silent, which is the
correct reading for Tier-2, Tier-1 and a fresh scaffold alike. This exact gap
once forced a wrong-persona cron on the pilot.

Deliberately-parked reds get **waivers** (`baron waiver add`,
`.baron-waivers.yaml`): subject pattern, reason, linked handoff, and a
**mandatory expiry**. A matching waiver downgrades the red to a warn with the
reason appended — visible, not alarm-red. An expired waiver stops matching (the
red resurfaces) and is itself reported, so waivers cannot rot into permanent
silence.

## Session-ritual primitives (optional)

`baron session start` and `baron session end` are optional bookkeeping helpers
for the git/markdown parts of the session ritual: `start` optionally
`git pull --ff-only`s the working copies, then surfaces the persona's open
handoffs, the `CONVENTIONS.md`/`COORDINATION.md` pointer, and the backlog
location; `end` regenerates the handoff index, commits dirty coordination
artifacts (`_handoff/`, `findings/`, `decisions/`, `wiki/`) by path with the
persona's commit prefix, and closes with a `baron status` divergence check
(exit 1 on red, CI-usable). They are **opt-in and compose existing commands** —
nothing in baron requires them, and they are not new capability verbs. The
boundary they keep — bookkeeping only, no agent loop, no model calls,
orchestration stays the runtime's job — is
[ADR-007](adr/ADR-007-session-boundary.md).

## Guard: enforcement before the tool runs

`baron guard` ([ADR-004](adr/ADR-004-baron-guard-enforcement.md)) is a Claude
Code **PreToolUse hook**: it reads the pending tool call, maps it to the frozen
verbs (`git push` to the default branch → `push_main`; force flags →
`force_push`; `gh pr merge` → `merge_pr`; file writes → `write_path` scoping /
`edit_other_personas`), and blocks denials with exit 2 + the reason on stderr
before the tool executes. Parsing is conservative — an ambiguous push target is
denied for personas lacking the verb, with the inference named. It fails closed
(malformed input → deny) but is never a brick: `BARON_GUARD_OVERRIDE=<reason>`
allows the call and appends to a **tracked** override log, so every override is
visible in diffs and expected to become a handoff. On pydantic-ai the same
rules artifact is enforced in-process, where the hook cannot be absent.

**Known bypass — command-string wrappers.** The parser inspects each top-level
subcommand's tokens; it does *not* recurse into an interpreter invoked with an
inline program string. So `bash -c '...'`, `sh -c "..."`, and `python3 -c '...'`
run their payload uninspected — a `git push origin main` hidden inside `bash -c`
is **not** caught. `bash -c`/`sh -c` are common enough to hit by honest accident,
not just adversarially. This is an accepted limit of static enforcement of the
honest-mistake class, not a guarantee: where the boundary must actually hold
against a wrapper, use OS-level isolation (a container/sandbox). The pydantic-ai
in-process Shell narrows the class — it denies redirect/pipe operators and
allowlists test-only personas' shells — but does not close it.

**One hook, two jobs** ([ADR-012](adr/ADR-012-hook-coverage-and-evidence-capture.md)).
`baron guard` also answers `SessionStart`, `SessionEnd`, `PostToolUse` and
`PostToolUseFailure`, dispatching internally on `hook_event_name` — one binary,
one command per event. Those four are **evidence only**: they emit a structured
event (correlated by a trace id derived from `session_id`, so a denial can be
placed in its session) and always exit 0. Only `PreToolUse` can ever block, and
that is enforced by a test that feeds every other event a maximally hostile
payload. The reason is not tidiness: a hook that blocks `SessionStart` cannot be
un-blocked from *inside* the session, so an evidence path that fails closed
would brick the agent rather than correct it. Hence the asymmetry — enforcement
fails **closed**, evidence fails **open** and silently
(`BARON_EVENTS_DEBUG=1` to see it). Any hook event baron does not recognise is
inert; Claude Code emits 31 distinct event names and that number keeps moving.

**What a row claims, and what it must not**
([ADR-018](adr/ADR-018-adjudicated-enforcement-on-the-event.md)). Each row carries a
`baron.enforcement` attribute, and it is a **per-call observation**: did a
capability actually adjudicate *this* call? It is read off an explicit
`Decision.adjudicated` flag set at every return site in the evaluators, defaulting
`False` on the trace — so any path that returns without a real decision
(out-of-jurisdiction tool, malformed payload, fail-closed error, human override)
is `unevaluated` **by construction** rather than by someone remembering to say so.
The vocabulary is exactly `enforced` | `unevaluated` | `unknown`.

That design came out of a measured defect in the first cut, which derived the
label from the rules artifact's static `detection` field — a property of a *verb*,
which cannot answer a question about a *call*. It was wrong in both directions at
once: a `..`-escape denial read `enforced` (structural; every persona is refused
identically, no capability adjudicated it) while a genuine persona-dependent
allow read `not-applicable`. Over-counting and under-counting enforcement in the
same field is the exact over-claim this project exists to catch, and it was
sitting in merged code. `instructed` was removed from the event entirely: a
PreToolUse hook cannot observe whether a persona heeded a sentence, so the value
belongs on the posture surface and nowhere near a row.

**The caveat any consumer needs before aggregating:** `baron.capability.verb` can
be non-empty on an `unevaluated` row, and empty on an `enforced` one. The verb
tuple is **not** a proxy for the enforcement field. Filter on
`enforcement == "enforced"` *before* grouping by verb, or the count is fiction —
a test emits two real rows and asserts naive count 2 against correct count 1.

**And the plane is not Claude Code's**
([ADR-019](adr/ADR-019-runtime-neutral-event-plane.md)). The event vocabulary was
runtime-neutral from the start, but for a while only one runtime ever wrote to it,
which makes neutrality an intention rather than a fact. It is now a measurement:
the pydantic-ai adapter's in-process seam (`before_tool_execute`) is a second
producer on the same plane. Driven with the same persona and the same command, the
two runtimes append to the *same* log file and their rows differ in exactly four
attributes — `baron.runtime`, `baron.trigger` (the runtime's own name for its seam),
`tool.name` (each runtime names its own tools) and `session.id`. Verdict, verb,
enforcement label, actor and subject are identical. A third runtime registers by
finding its own pre-execution seam and calling `guard.observe_decision`; **code-puppy
has none today**, so it is deliberately absent rather than emitting post-hoc rows
that would imply an adjudication that never happened.
**The bigger failure was never a bypass — it was absence.** The badminton-analyzer
incident merged 15 PRs under a persona denied `merge_pr`, and nothing had gone
wrong: the hook had never been wired into `.claude/settings.json`, so the denial
degraded to persona text exactly as designed, and silently. An absent guard and a
guard that never had to fire leave identical evidence.
`baron doctor` ([ADR-017](adr/ADR-017-baron-doctor-wiring-selftest.md)) is that
silence's remedy: nine read-only checks — executable resolves, hook present,
matcher covers every governed tool, persona and rules load, a synthetic denial
fed to **the executable the hook names** really exits 2, malformed stdin fails
closed, no exported override — exiting 1 on any FAIL with a remedy line each.
That the denial probe *spawns the hook's own command* rather than calling the
imported `baron.guard` is load-bearing: a project wired to a stale or hand-rolled
`baron` is the same drift as a missing hook, and an in-process probe exercises
the very module the bug assumes is fine. Doctor's own bound is printed on every
run: it verifies **WIRING, not invocation**. It proves the install *can* enforce;
whether the runtime actually called the hook is not observable from outside the
runtime, and a command that implied otherwise would manufacture the very
confidence that produced those merges.

## The substrate, and the bound on extending it

The load-bearing constraint of the whole framework is that `baron` is a
disciplined reader/writer over collab-repo files and introduces no second store
([ADR-003](adr/ADR-003-baron-cli.md) §2.2). Structured output is a *view*
(`--json`), never a second source of truth.

The product-vision invariant above it was amended on 2026-08-10
([ADR-022](adr/ADR-022-substrate-invariant-amended-default-not-only.md)). It used
to read *the repo is the only source of truth*. It now reads **git + markdown is
the DEFAULT substrate; plugins may extend it to other suitable platforms** —
bounded by **governance state stays complete in git**. "Who may do what", "who
did what" and "what is true now" must stay answerable from the repository
**alone**. A plugin may be authoritative for **derived or auxiliary** domains —
semantic search, embeddings, cross-project recall — and **never** for authority,
evidence, or the ledger.

The bound is the load-bearing half, and it has a test a reviewer can run rather
than a taxonomy to interpret: **delete every plugin, clone fresh, ask the three
questions.** If an answer is lost or now needs a second system, the plugin was
holding governance state and is forbidden. If only the *speed of finding it* is
lost, it is permitted.

The argument for the bound is the audit claim itself: *governance you can verify
by reading a diff*. That holds only while the repo is complete. Move a capability
grant into an index and it stops appearing in a PR, the auditor needs credentials
rather than a `git clone`, and the failure is silent — a stale index does not
announce itself the way a missing file does. The claim degrades from "read the
diff" to "trust the index", which is a different product. A project that
publishes its own measured operational fidelity of 0.53 rather than rounding it
up should not ship a headline claim that can only be taken on trust.

**The amendment authorises nothing to be built.** No adapter, no knowledge
entry-point group (an entry-point name is public API and no group ships without a
consumer), and the semantic-memory question is answered as a *rebuildable
projection*, with the authoritative mode refused on the merits. What changed is
the answer to "may we ever?", not to "may we now?".

`baron export [--kind …] [--json]`
([ADR-015](adr/ADR-015-baron-export.md)) is the seam a projection would consume:
the four corpora a collab repo already keeps — ADRs, decisions, findings,
handoffs — walked into flat records that each name the commit whose bytes were
parsed. **The citation gate is the substance.** A source that is untracked or
modified is skipped and named, rather than emitted with a SHA that resolves and
returns different text; `git show <sha>:<path>` always reproduces a record's
bytes. That is what makes a projection auditable, and it is a property of the
corpus walk rather than of any backend, so every candidate backend inherits it
for free. Measured: 284 records out of a real pilot repo, all 284 citations
verified by byte-equality.

## PR-locks

For contested hot files, **the open PR is the lock** (ADR-002 §3): `baron lock
claim <path>` creates a `lock/<slug>` branch with one empty commit and opens a
draft PR labeled `lock:<path>`; claim refuses when an open lock PR for the path
exists; release closes the PR and deletes the branch. The forge's PR list is the
only lock state — no lock files, no markdown lock commits (which raced in the
field). A dependency-free CI template (`lock-guard.yml`) fails any *other* PR
touching a locked path. Honest limitation, carried in the template: without
branch protection a red check is an alarm, not a wall.

## Worktree topology

Instead of clone-per-persona (which drifts), each persona gets a **git
worktree** on branch `persona/<slug>` over one shared object store —
`baron worktree add|list|remove`, rooted at the manifest's
`workspace.worktrees_root`. `remove` refuses on dirt or unmerged commits unless
forced and never deletes the persona branch. `baron status` sweeps worktrees
like clones. Migrating an existing workspace:
[worktree-migration.md](worktree-migration.md).

## Audit, intervention tax, and signets

The sister skill [`multi-agent-audit`](../skills/multi-agent-audit/) is the
other half of the kit: Barony **builds** governed projects; the audit **grades**
them — read-only by construction, framework-neutral (Barony, CrewAI, LangGraph,
AutoGen, custom loops), with evidence instead of vibes. The headline metric is
the **INTERVENTION TAX**: human touches per autonomous task — a high autonomy
split with a high tax is a false win. The dual-lens drift pass compares what a
project *declares* against what it *does* and scores **operational fidelity**
0.00–1.00; the enforced-vs-instructed distinction is load-bearing there too.
Outputs: a markdown report, a self-contained HTML dashboard, a short-form
executive summary, and a machine-readable snapshot for trend analysis.

**Signets** are the accountability primitive for review: a reviewer persona
publishes its verdict as a PR comment bound to the exact head SHA it judged
(never the platform's approve button, which a single-account setup cannot use).
A merger persona — holder of the project's only `merge_pr` — verifies
preconditions mechanically: CI green on the current head SHA, a signet naming
that same SHA, record obligations met. A new push makes the old verdict visibly
stale.

## Customisation

The archetype templates use `{{PLACEHOLDER}}` tokens for names, scopes, and
identity — name your personas whatever fits your working style. The structural
patterns (three-tier write ownership, capability allow/deny per persona, handoff
protocol, `COORDINATION.md` as the single source for cross-agent rules) carry
the value, not the names. The reviewer/merger module and the CI lock guard are
opt-in — small teams without contested seams may not need them.
