---
created: 2026-05-29
accepted: 2026-05-30
type: decision
status: accepted
decided_by: Vikram
canonical: https://github.com/vggg/barony/blob/main/docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md
project: multi-agent-setup
adr: 001
co_authors: [Vikram, code-puppy]
related:
  - "[[projects/multi-agent-setup/decisions/2026-05-29-6-bootstrap-genesis-emission]]"
  - "[[projects/multi-agent-setup/2026-05-29-three-collab-patterns-not-two]]"
  - "[[projects/multi-agent-setup/2026-05-28-remote-agents-analysis]]"
  - "[[projects/multi-agent-setup/2026-05-28-gas-town-analysis]]"
  - "[[entities/code-puppy]]"
---

# ADR-001: Runtime-Agnostic Multi-Agent Project Bootstrap & Participation

| Field | Value |
|---|---|
| **Status** | Accepted (2026-05-30) |
| **Date** | 2026-05-29 |
| **Authors** | Vikram + Puppy 🐶 |
| **Supersedes** | — |
| **Context repo** | `agent-project-bootstrap` (Claude Code skill, v0.3.2) |
| **Decision owner** | Vikram |

---

## 1. Summary

We are evolving `agent-project-bootstrap` — today a **Claude-Code-only** skill that
emits multi-agent project scaffolding — into a **runtime-agnostic** specification that
any capable coding agent (Code Puppy, Claude Code, Codex, Wibey, …) can both *produce*
and *operate within*, **without the human ever choosing a runtime-specific mode**.

The work decomposes into two distinct roles:

- **Role 1 — Orchestrator:** an agent that sets up a *new* project (generator).
- **Role 2 — Participant:** an agent that *joins and operates within* an existing
  project (runtime participant).

The central design constraint: **we cannot assume the participant is Code Puppy,
Claude, Codex, or Wibey.** The repo must carry runtime-neutral *intent*; each agent
maps that intent onto its own native primitives, self-selecting the richest mode it
supports — with zero human configuration.

---

## 2. Context & problem statement

### 2.1 What exists today

`agent-project-bootstrap` is a Claude Code skill with three emit modes
(`vault-project`, `collab-repo-project`, `join-collab-project`). It produces markdown
scaffolding: `CONVENTIONS.md`, `COORDINATION.md`, per-persona `AGENT.md`, `_handoff/`,
`decisions/`, `findings/`, `wiki/`, plus a `/vc` slash command.

The *patterns* it encodes are genuinely valuable and largely runtime-neutral already:

- **Three-tier write ownership:** `CONVENTIONS.md` (rare, repo-wide) → `COORDINATION.md`
  (evolving cross-agent protocol) → per-persona `AGENT.md`.
- **`_handoff/` protocol:** append-only async messages, `status: open|done`, never deleted.
- **Persona archetypes:** dev / autonomous-event / autonomous-cron / librarian, each with
  identity, scope, session ritual, and explicit "what never happens" guardrails.
- **Librarian pattern:** single ingest agent that turns raw activity into a navigable wiki.

### 2.2 What is *not* neutral

The skill is deeply coupled to Claude Code:

- Claude tool names (`Read`/`Write`/`Edit`/`Bash`), Obsidian MCP references.
- `CLAUDE.md` as the auto-loaded per-session context file.
- `.claude-plugin/plugin.json`, `/plugin install`, the SKILL.md dispatcher convention.
- `/schedule` skill for cron; Claude-specific failover assumptions.

### 2.3 The problem

If we simply "port to Code Puppy," we trade one runtime lock-in for another. Worse, two
design decisions kept surfacing that *looked* like they needed a human to answer:

1. **Persona representation:** static markdown (portable, faithful) vs. real
   sub-agents (native, enforced tool scope, but config-on-machine breaks portability).
2. **Mode selection:** orchestrate vs. participate.

**Insight:** neither of these should be a human decision. Both can be resolved
deterministically — (1) by the *agent's own runtime capabilities*, (2) by the *state of
the target directory*. The human should only ever say *"set up a project"* or
*"join this repo."*

### 2.4 Concrete forcing function

This is not a speculative architecture. Vikram's work environment uses **code-puppy**
(Claude Opus 4.8 backed) as its coding-agent runtime — Claude Code is not available at
work, and real work projects are queued that need the multi-agent pattern to run there.
The home stack stays on Claude Code. ADR-001 v1.0 must let the same
`agent-project-bootstrap` artifact emit projects that run on **both** runtimes. Codex /
Wibey / future runtimes are post-1.0 — naturally supported by the architecture but not
v1.0 acceptance criteria.

---

## 3. Decision

Adopt a **canonical-spec + self-adapting-agents** architecture:

> The repository contains a **runtime-neutral canonical layer** that declares *intent*
> (what each role does; what each persona is, may, and may not do) in both human-readable
> (`.md`) and machine-readable (`.yaml`) form. Each agent reads the canon and maps it onto
> its own native primitives via an **adapter**, self-selecting the highest-fidelity
> execution tier it supports. Runtime-specific material is quarantined in an optional
> `adapters/` tree. The human never chooses a runtime or a representation mode.

Analogy: like `.editorconfig` / LSP — one neutral spec, many implementers, no
editor-specific choice forced on the user.

---

## 4. Architecture

### 4.1 Layering

```
┌─────────────────────────────────────────────┐
│  CANONICAL LAYER (runtime-neutral, in repo)  │  ← single source of truth
│  - role recipes (orchestrate / participate)  │
│  - persona intent (caps, identity, runtime)  │
│  - machine-readable manifest                 │
└─────────────────────────────────────────────┘
                    ▲
                    │ each agent reads + adapts via its adapter
        ┌───────────┼───────────┬──────────┐
     Code Puppy    Claude     Codex      Wibey   …new runtimes
     (sub-agent)  (CLAUDE.md) (its way) (its way)
```

### 4.2 Neutral entrypoints (the front door)

No human picks a mode. The **directory state** and the **agent's capabilities** decide.

```
START.md        ← neutral front door read first in any fresh checkout.
                  (Distinct from runtime-native files like CLAUDE.md or AGENTS.md
                   that adapters write per Tier 2 — see §4.3.)
                  Says: "Empty/new target  → read ORCHESTRATE.md
                          Existing collab    → read PARTICIPATE.md"
ORCHESTRATE.md  ← Role 1 recipe: set up a NEW project (runtime-neutral, deterministic).
PARTICIPATE.md  ← Role 2 recipe: join/operate + the capability ladder (below).
```

### 4.3 The capability ladder (resolves "markdown vs. sub-agent")

`PARTICIPATE.md` instructs the agent to introspect itself and operate at the **highest
tier it supports**. All tiers read the *same* `persona.yaml`.

```
Tier 3 — NATIVE AGENTS
  If you can create/restrict sub-agents with scoped tools
  (e.g. Code Puppy /agent, Claude subagents): hydrate each persona into a
  native agent honoring the declared allow/deny capabilities.

Tier 2 — SESSION CONTEXT
  If you load a per-session context file (CLAUDE.md, AGENTS.md, .cursorrules):
  render the active persona's spec there; follow its ritual each session.

Tier 1 — IN-PROMPT (always works)
  Read agents/<persona>/persona.yaml at the start of every turn and
  self-enforce the guardrails as instructions.
```

Graceful degradation: a smart runtime gets enforced tool scoping for free; a minimal
runtime still functions. The user is never asked which tier.

### 4.4 Machine-readable persona spec (intent, not mechanism)

Each persona gains a `persona.yaml` (machine truth); the existing `AGENT.md` becomes its
human-readable rendering.

```yaml
# agents/dave/persona.yaml
persona: Dave
slug: dave
archetype: dev
identity:
  git_name: Dave
  git_email: dave@{{IDENTITY_DOMAIN}}
  commit_prefix: "dave:"
  routing_label: agent-dave
capabilities:                 # ABSTRACT capability vocabulary — NOT tool names
  allow: [read_code, write_code, open_pr, read_collab, write_findings, write_handoff]
  deny:  [merge_pr, write_wiki, edit_other_personas, push_main, force_push]
runtime:
  trigger: interactive        # interactive | event | cron
  scheduler: none             # none | launchd | systemd | gh-actions | cloud
session_ritual: [pull_both_repos, read_conventions, check_handoffs, check_backlog]
```

The `capabilities` vocabulary is **abstract** (`merge_pr`), never tool-named. Each runtime
maps abstract capabilities onto its real tools via its adapter.

### 4.5 Adapters (the only runtime-specific surface)

```
adapters/
  generic/HYDRATE.md      ← Tier-1 fallback (MANDATORY; always present)
  code-puppy/HYDRATE.md   ← optional: persona.yaml → enforced Puppy sub-agent
  claude/HYDRATE.md       ← optional: persona.yaml → CLAUDE.md rendering
  pydantic-ai/HYDRATE.md  ← optional: persona.yaml → in-process guarded Agent (v1.6)
  codex/HYDRATE.md        ← optional
  ...
```

> **Current adapters (v1.6.0):** four ship today — `claude` (Tier 2/3 + the baron guard
> hook), `code-puppy` (Tier 3), `pydantic-ai` (in-process hydration; the five
> guard-covered sub-tool denials are natively enforced — ADR-004 addendum §4.2), and the
> mandatory `generic` Tier-1 fallback. `codex` remains illustrative.

Participant flow: read `persona.yaml` → look for `adapters/<my-runtime>/HYDRATE.md` →
if present, follow it; else fall back to `adapters/generic/`. Adding a runtime = add a
folder, touch nothing else (**Open/Closed Principle** for runtimes).

### 4.6 Resulting repo shape

> **This diagram is the shape of an EMITTED PROJECT** (a collab repo this skill scaffolds) — it is
> NOT the layout of the Barony skill repo itself (formerly `agent-project-bootstrap`). In the skill repo these files
> are emit-time templates under `skills/barony/assets/collab-repo/` (entrypoints +
> `adapters/`) and `skills/barony/references/` (the canon spec); at scaffold time
> they are copied into the target project at the root paths shown below (`canon/` + `adapters/` —
> see `ORCHESTRATE.md` step 2a). The two structures are consistent; only the root differs.

```
START.md                  ← neutral front door: self-select role
ORCHESTRATE.md            ← Role 1 recipe (runtime-neutral)
PARTICIPATE.md            ← Role 2 recipe + capability ladder
CONVENTIONS.md            ← already neutral (minor de-Claude-ing)
COORDINATION.md           ← already neutral (minor de-Claude-ing)
manifest.yaml             ← project + persona roster (machine-readable)
agents/
  <persona>/
    persona.yaml          ← machine truth (caps, identity, runtime)
    AGENT.md              ← human-readable render
adapters/
  generic/HYDRATE.md      ← Tier-1 fallback (mandatory)
  code-puppy/HYDRATE.md   ← optional richer mapping
  claude/HYDRATE.md
  pydantic-ai/HYDRATE.md  ← (v1.6)
  ...
_handoff/  decisions/  findings/  wiki/   ← unchanged patterns
```

---

## 5. How this removes the human burden

| Decision that used to need a human | Resolved by |
|---|---|
| Orchestrate or participate? | **Directory state** (empty vs. populated) → `START.md` routes |
| Markdown persona vs. real sub-agent? | **Agent's own capability detection** → climbs the ladder |
| Which runtime's quirks apply? | **`adapters/<runtime>/`** — agent reads its own folder |
| Fill `{{placeholders}}`? | **Orchestrator interviews** the user and writes final values |

End-user experience: *"set up a project"* or *"join this repo"* — said to whatever agent
they happen to have. Everything else is self-determined.

---

## 6. Role-by-role assessment

### 6.1 Role 1 — Orchestrator

- **Fit:** Excellent. Agents are natural file-emitters with shell access.
- **Upgrade over Claude original:** the orchestrator *interviews* the user and writes
  final values, so the `{{placeholder}}` → fill → grep-verify dance largely disappears.
- **Primary gap:** cron/`/schedule`/failover wiring has no universal equivalent. The
  orchestrator can still *emit* failover runbooks + cron stubs (launchd/systemd/GH-Actions),
  but cannot guarantee a live scheduled runtime. (See §7.)
- **Verdict:** low risk, high fidelity. Build *after* one participant adapter is
  validated end-to-end (see updated §10 — sequencing flipped to adapter-first per §2.4).

### 6.2 Role 2 — Participant

- **Fit:** Good, with a real design tension (now resolved by the capability ladder).
- **2a Onboarding** (clone, claim persona, set git identity, hello-PR): easy; pure
  shell + file edits.
- **2b Operating as a persona:** the ladder lets each runtime operate at its best tier.
  Tier-3 *adapter renderings* gain *enforced* tool scoping (a genuine upgrade over the
  Tier-2 markdown rendering used by today's v0.3.x skill — including the existing
  CLAUDE.md path). Note: Claude as a runtime supports *both* Tier 2 (CLAUDE.md) and
  Tier 3 (subagents); the v1 Claude adapter should render Tier 3 to deliver the upgrade.
  Each adapter author chooses which tier to render when multiple are available — this
  is an open design question (how to pick).
- **Primary gap:** autonomous/cron personas as *unattended* runtimes still need external
  scheduling. As *interactive* agents they are fine. (See §7.)
- **Verdict:** achievable and arguably better; the ladder removes the only decision that
  looked like it needed a human.

---

## 7. Open questions / unresolved

1. **Cron & failover.** Do we (a) emit OS-level cron stubs (launchd/systemd/GH-Actions)
   from the existing `_failover-cron-sections/` templates, or (b) declare autonomous
   personas interactive-only for v1 and defer scheduling? **Recommendation: (b) for v1**,
   keep the runbooks as emitted markdown.
2. **Capability vocabulary stability.** The abstract `allow/deny` verbs (`merge_pr`,
   `write_wiki`, …) become an API. We must define a small, stable, documented set in v1
   and version it. Risk: vocabulary churn invalidates adapters.
3. **Adapter discovery.** How does an agent know its own "runtime key" (`code-puppy`,
   `claude`, …)? Proposal: each runtime self-identifies; if it has no matching adapter
   folder, it MUST fall back to `generic`. Document the known keys in `START.md`.
4. **`persona.yaml` vs. `AGENT.md` drift.** Two representations of one persona. Either
   generate `.md` from `.yaml` (single source) or have the Librarian drift-check them.
   **Recommendation:** `.yaml` is canonical; `.md` is generated/derived.
5. **Vault-project mode.** Does the neutral model also cover the lean `vault-project`
   pattern, or is v1 scoped to `collab-repo-project` + `join`? **Recommendation
   (updated per §2.4):** vault-project mode stays on v0.3.x rails during v1.0.
   Re-integration with the runtime-agnostic architecture is post-1.0. This keeps the
   home Iris stack stable while v1.0 ships the bi-runtime story.
6. **Distribution.** Is the runtime-agnostic artifact a "skill" (Puppy/Claude), a plain
   git template repo, or both? A plain template repo is the most runtime-neutral; skills
   can wrap it per-runtime.

---

## 8. Alternatives considered

| Alternative | Why rejected |
|---|---|
| **A. Straight port to Code Puppy** | Trades Claude lock-in for Puppy lock-in; violates the no-assume-runtime constraint. |
| **B. Personas as Puppy sub-agents only** | Breaks runtime portability & failover (config-on-machine); excludes non-Puppy runtimes. |
| **C. Keep Claude-only, document for others** | Pushes adaptation burden onto every other runtime's user; no shared contract. |
| **D. Ask the human to choose mode/representation** | Exactly the burden we are removing; brittle and confusing. |
| **E (chosen). Canonical spec + self-adapting adapters** | Satisfies the constraint; degrades gracefully; Open/Closed for new runtimes. |

---

## 9. Consequences

### Positive
- No runtime lock-in; new runtimes added via a single adapter folder.
- Human burden reduced to two verbs: *orchestrate* / *participate*.
- Tier-3 adapter renderings gain enforced guardrails (better than Tier-2 markdown
  rendering, which is what v0.3.x ships today via CLAUDE.md).
- Canon stays clean; all runtime quirks quarantined in `adapters/`.

### Negative / costs
- Adds an abstraction layer (`persona.yaml`, capability vocabulary, adapters) — more
  upfront design than a straight port. Justified only because multi-runtime is an explicit
  requirement (not speculative — YAGNI respected).
- Capability vocabulary becomes a versioned contract requiring governance.
- Dual persona representation (`.yaml` + `.md`) needs a single-source discipline.

---

## 10. Proposed execution plan (post-approval)

**Sequencing principle (revised — supersedes earlier draft):** adapter-first, derive
spec from observed use. The earlier spec-first ordering risked months of design before
validation; the forcing function in §2.4 makes adapter-first the right call.

1. **Write `adapters/code-puppy/HYDRATE.md` end-to-end for ONE persona** (dev
   archetype, since code-puppy at work runs dev work), targeting a real work project.
2. **Ship that work project on code-puppy.** Validate the adapter against real use,
   not a throwaway. This is the v1.0 critical path.
3. **Derive the canonical contract from observed needs:** capability vocabulary,
   `persona.yaml` schema, `manifest.yaml` schema, `START.md`, `ORCHESTRATE.md`,
   `PARTICIPATE.md`. The empirical adapter teaches the spec more than the spec teaches
   the adapter.
4. **Write `adapters/generic/HYDRATE.md`** (mandatory Tier-1 fallback) to match what
   code-puppy needed.
5. **Write `adapters/claude/HYDRATE.md`** — Tier-2 (CLAUDE.md rendering, mirroring v0.3.x for
   home compatibility) shipped in v1.0. **Claude Tier-3 (native subagents with an enforced
   `tools:` allow-list) shipped in v1.1** as one configurable adapter (tier resolved from a
   runtime-neutral `adapters.claude.tier` config: `auto` | `2` | `3`, `auto` by default).
6. **De-Claude the neutral docs:** scrub tool names / MCP / CLAUDE.md from
   `CONVENTIONS.md`, `COORDINATION.md`.
7. **Cut v1.0 release.** Acceptance: home (Claude Code) + work (code-puppy) both
   producing equivalent project shapes from the same spec.
8. **Defer to post-1.0:** ~~Claude Tier-3 subagent rendering~~ (shipped v1.1 — see step 5),
   vault-project mode re-integration, cron/failover live wiring, additional adapters
   (Codex, Wibey, etc.).

> **v1.1 amendment (Claude Tier-3).** The tier config lives in a runtime-neutral
> `adapters.<runtime>` envelope (`manifest.adapters.claude.tier` project default;
> `persona.yaml > runtime.adapters.claude.tier` per-persona override) rather than a bare
> `claude_tier` key — this keeps the canonical `manifest.yaml` / `persona.yaml` schemas free of
> runtime tool names (preserving the §10.6 runtime-neutrality invariant) and generalizes to
> future adapters. One configurable Claude adapter renders either tier; `auto` self-assesses
> subagent support and degrades to Tier 2 when the session can't host subagents. Decided with
> Vikram, 2026-06-03.

---

## 11. Decision record

- [x] Approved as written
- [ ] Approved with changes (note below)
- [ ] Needs revision
- [ ] Rejected

**Reviewer notes (Vikram, 2026-05-30, recorded via Iris):**

> Accepted on the strength of the concrete forcing function added in §2.4: work
> environment runs code-puppy (Claude Opus 4.8), Claude Code unavailable at work,
> real work projects queued. v1.0 critical path is bi-runtime (Claude Code +
> code-puppy); other runtimes post-1.0. Two internal contradictions surfaced
> during local review were fixed pre-merge: AGENTS.md → START.md rename
> (resolves triple-duty); Tier-3 framing clarified (runtime capability vs.
> adapter rendering choice). Execution per updated §10: adapter-first; derive
> spec from observed use against a real work project. Canonical now lives in
> `vggg/agent-project-bootstrap/docs/adr/`; this vault file becomes a pointer
> stub on merge.
