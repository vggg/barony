---
created: 2026-07-28
accepted: 2026-07-28
type: decision
status: accepted
decided_by: Vikram
adr: 007
project: barony
related:
  - "[[docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap]]"
  - "[[docs/adr/ADR-003-baron-cli]]"
  - "[[docs/adr/ADR-004-baron-guard-enforcement]]"
---

# ADR-007: the session boundary — Barony does not own the agent loop; it ships thin session-ritual primitives

| Field | Value |
|---|---|
| **Status** | Accepted (2026-07-28) |
| **Date** | 2026-07-28 |
| **Authors** | Vikram + Claude |
| **Supersedes** | — (extends ADR-001's three-layer positioning; resolves the `docs/BACKLOG.md` "reverse-direction / `baron run` driver — decision pending" fork) |
| **Evidence base** | The 2026-07-28 pydantic-ai interop eval: enforcement solid, orchestration manual |
| **Decision owner** | Vikram |

## 1. Summary

The 2026-07-28 pydantic-ai interop eval put an agent behind a Barony persona on a
non-interactive runtime and measured what actually held. Two halves came apart:

- **Enforcement works, live.** The in-process guard vetoes denied tool calls
  (`before_tool_execute` + `ModelRetry`), proven against a scripted
  `git push origin main` — the same rule table `baron guard` uses on Claude Code
  ([ADR-004](ADR-004-baron-guard-enforcement.md)).
- **The session RITUAL is manual.** The bookkeeping around a run — sync the
  repos, read `CONVENTIONS.md`/`COORDINATION.md`, check the backlog, surface
  open handoffs, then on close record findings/handoffs, commit with the right
  prefix, regenerate the handoff index, run a divergence check — was *instructed
  prose only*. Nothing automated it; a human or a script had to drive it.

That gap invites the obvious wrong fix: a `baron run` that drives the loop. This
ADR records two decisions that, together, close the gap without crossing the
boundary the whole design defends.

## 2. Decision — Barony does NOT own the agent execution loop

**There is no `baron run` agent-driver, and there will not be one.** Driving an
agent — the plan/act/observe loop, model calls, tool dispatch, retries, durable
state — belongs to the **runtime layer**, not to Barony.

This follows directly from ADR-001's three-layer positioning: **Barony is the
coordination-policy + governance + audit layer; the runtime is the execution
layer.** The runtimes already own orchestration and own it well — pydantic-ai
has Sub-agents, `DynamicWorkflow`, and durable-execution; Claude Code has
interactive sessions and hooks; Temporal-style engines own durable loops
wholesale.

Rationale:

- **Strategic bet.** Staying a governance *layer* — complementary, cross-runtime,
  useful no matter whose loop you run — is the position that wins. A driver
  would make Barony one more orchestrator competing with, and losing to,
  pydantic-ai / Temporal / Claude Code.
- **Scope creep across the defended boundary.** A `baron run` would duplicate
  runtime machinery baron has no advantage building, and would couple the
  governance layer to one execution model — the exact coupling ADR-001 refused
  when it made runtimes pluggable adapters.
- **It solves the wrong half.** The eval's failure was not "no loop exists" — the
  runtime supplies the loop. It was "the git/markdown bookkeeping around the loop
  wasn't mechanized." That half *is* Barony's job (§3).

## 3. Decision — Barony DOES provide thin, optional session-ritual PRIMITIVES

`baron session start` and `baron session end` mechanize **only the git/markdown
bookkeeping steps** of the session ritual — the parts that genuinely are the
coordination layer's job — by composing existing baron functions
(`status`, `handoff`, `indexer`, `gitutil`). Nothing new is invented.

- **`baron session start [--collab] [--persona] [--sync] [--json]`** — session-open,
  read-mostly: with `--sync`, `git pull --ff-only` each manifest working copy
  (never merge, never force; non-fast-forwards are reported, not forced —
  without `--sync` this is skipped, because it is an honest git mutation). Then
  surface, for the persona (else all): OPEN handoffs addressed to them, a pointer
  to `CONVENTIONS.md`/`COORDINATION.md`, and the manifest backlog location — a
  plain-text brief (or `--json`). Read-only except the opt-in pull.
- **`baron session end [--collab] [--persona] [--json]`** — session-close:
  regenerate the handoff index (`baron index` logic); commit any dirty
  coordination artifacts (`_handoff/`, `findings/`, `decisions/`, `wiki/`) —
  staged **by path, never `git add -A`** — with the persona's `commit_prefix`
  when `--persona` resolves one (the same attribution mechanism `baron handoff
  close --as` uses), else `baron:`; skip cleanly when nothing is outstanding;
  then end with a `baron status` divergence check. Exit 0 green / 1 on red
  (CI-usable).

### The boundary these primitives keep (stated explicitly)

- **Bookkeeping only.** They do NOT run an agent, make NO model calls, and have
  NO runtime coupling. If an implementation ever reaches for an agent loop, a
  model call, or runtime-specific logic, it has crossed this boundary and is
  wrong.
- **Opt-in.** Nothing in baron requires them. Interactive sessions and every
  existing command work exactly as before; a project that never types
  `baron session` loses nothing.
- **Not new capability verbs.** The frozen 10-verb vocabulary
  (`capability-vocab.v1.md`) is untouched. `start`/`end` are composable
  *commands*, not *permissions* — they grant nothing and gate nothing.

### Traceability

This maps one-to-one onto the eval finding: enforcement was already solid
(guard, ADR-004); orchestration stays the runtime's (Decision §2); the manual
bookkeeping the eval exposed becomes two composable primitives (Decision §3).

### Future opt-in (build-on-demand, not speculative)

Any runtime adapter MAY wrap these primitives — a pydantic-ai capability that
calls `session start`/`end` around a run, a Claude Code session hook, a cron/CI
driver that composes them — but **Barony ships only the runtime-neutral CLI**.
Those wrappers are built when a real runtime needs one, not speculatively; the
CLI is the stable seam they compose against.

## 4. Consequences

- The `docs/BACKLOG.md` driver-vs-runtime fork is resolved: no driver; thin
  primitives shipped in CLI **0.5.6**; runtime-specific capability wrappers are
  build-on-demand.
- Headless / autonomous / CI operation now has a composable bookkeeping seam
  without Barony taking on an orchestrator's scope or maintenance surface.
- Two new commands restate a little of the ritual prose in code — bounded to the
  deterministic git/markdown steps (the same trade ADR-006 accepted for
  `baron init`: deterministic output needs code, not prose). The judgment steps
  (what to work on, what a finding says) stay where they belong — with the agent,
  on the runtime.
- The substrate is unchanged: `session` reads and writes the same human-legible
  collab-repo files every other command does (ADR-003 §2.2); no new store.

## 5. Decision record

- [x] Approved as written

**Notes (Vikram, 2026-07-28):** the primitives land with CLI 0.5.6
(`cli/src/baron/session.py`, `cli/README.md` "session ritual primitives"). The
pydantic-ai adapter HYDRATE.md gains an optional "composing the session ritual"
note (plugin/skill 1.8.2) — documentation that a driver MAY wrap them, not a
shipped wrapper.
