# HYDRATE - generic adapter (Tier 1, always-works fallback)

> **Runtime:** ANY. The mandatory floor of the capability ladder (ADR section 10.4). If a
> runtime has no native sub-agents (Tier 3) and no persistent session/context file (Tier 2),
> it uses THIS. Every runtime can run it, because it needs nothing but "follow instructions
> each turn."
>
> **Tier:** 1 - in-prompt, fully instruction-based. NOTHING is hard-enforced; the operating
> agent self-enforces by re-reading the spec. That is the design, not a weakness - see
> docs/LEARNINGS.md L3 (instruction-only guardrails demonstrably catch real mistakes).
>
> **Read first:** `canon/PARTICIPATE.md` (capability ladder) and
> `canon/capability-vocab.v1.md` (verb contract).

---

## When you (the operating agent) are here

You cannot register a scoped sub-agent and have no persistent system-prompt file that
survives between turns. So you cannot "install" a persona once and trust the runtime to keep
it. Instead you **carry the persona yourself, every turn.**

The core loop:

> **Each turn: (1) re-read `persona.yaml`, (2) check the action you are about to take against
> `capabilities.allow` / `deny`, (3) act only if allowed, (4) follow the ritual + conventions.**

Tier-1 hydration emits ONE artifact: an **`AGENTS.md`** in the persona's working-copy root
(step 3 below). `AGENTS.md` is the emerging cross-runtime context-file convention —
AGENTS.md-aware runtimes (pydantic-ai-harness `RepoContext()`, code editors and agents that
walk up for `AGENTS.md`) auto-load it at session start, which gives even a Tier-1 persona a
persistent restatement of its spec. Runtimes that do NOT auto-load it lose nothing: the file
doubles as your re-read target for the core loop. Everything in it is still
**instruction-only** — emitting a file does not upgrade the tier.

---

## Capability map (v1, normalized)

Tier 1 has no tool allow-list to configure — the runtime hands you everything, and you
self-enforce. The map below exists so the contract is still explicit (and machine-checkable):
**Grants** is the runtime-neutral category each verb needs (`read` | `write` | `shell`);
every **Deny enforcement** at this tier is `instructed`, because nothing is hard-enforced.

<!-- capability-map:v1 — machine-readable; parsed by tests/bi_runtime_accept.py.
     Keep exactly one row per v1 verb; keep the column order. -->

| Verb | Class | Grants | Runtime tools | Deny enforcement |
|---|---|---|---|---|
| `read_code` | whole-tool | read | — (in-prompt; use whatever read tools the runtime offers) | instructed |
| `read_collab` | whole-tool | read | — | instructed |
| `write_code` | whole-tool | write | — | instructed |
| `write_path` | sub-tool | write | — | instructed |
| `open_pr` | sub-tool | shell | — | instructed |
| `run_tests` | sub-tool | shell | — | instructed |
| `merge_pr` | sub-tool | shell | — | instructed |
| `push_main` | sub-tool | shell | — | instructed |
| `force_push` | sub-tool | shell | — | instructed |
| `edit_other_personas` | sub-tool | write | — | instructed |

## Steps

### 1. Load the project + persona spec
- Read `manifest.yaml` -> find your persona `spec` path and the `repos` / `backlog` / `paths`.
- Read your `agents/<slug>/persona.yaml`.
- Read `CONVENTIONS.md` + `COORDINATION.md`.
- Keep `persona.yaml` close - re-open it whenever context may have drifted (after long tool
  output, after a summary, at the start of each new sub-task).

### 2. Build your self-enforcement checklist (from `capabilities`)
Translate the verbs into a literal yes/no list you consult before EVERY action:

- `capabilities.allow` -> "I MAY ..." (e.g. read_code, write_code, run_tests).
- `capabilities.deny`  -> "I MUST NOT ..." (e.g. merge_pr, push_main, force_push,
  edit_other_personas, and any denied write scope such as wiki).

Before any file write, shell command, or git action, ask: does the verb behind this action
appear under allow? Is it under deny? If denied or not in allow, **do not do it** - drop a
`_handoff/` to the owner instead (the golden rule from PARTICIPATE.md).

> Tier-1 reality: the runtime WILL hand you the tools to violate these (there is no allow-list
> to remove them). The guardrail is your discipline. Treat `deny` as inviolable.

### 3. Emit `AGENTS.md` in the persona's working-copy root

Write an `AGENTS.md` at the root of the persona's working copy (the code-repo clone or
worktree the persona operates in), derived ENTIRELY from `persona.yaml` + `manifest.yaml`.
It is a generated file — regenerate it when `persona.yaml` changes; never hand-edit it.

Why: `AGENTS.md` is the cross-runtime context-file convention. Runtimes that auto-load it
(pydantic-ai-harness `RepoContext()`, other AGENTS.md-aware agents) start every session
already carrying the persona; for everything else it is the single file to re-read in the
core loop. **Honesty:** at this tier the file is instructions only — nothing in it is
enforced.

Template (fill from `persona.yaml`; paths RELATIVE per `manifest.paths` — never absolute):

```markdown
<!-- GENERATED from agents/<slug>/persona.yaml — do not hand-edit; re-derive on change. -->
# <Persona> — <archetype> persona for <project>

You are <Persona>. Re-read this file (or the canonical
<collab.path>/agents/<slug>/persona.yaml) whenever context may have drifted.

## Identity
- Git author: <git_name> / <git_email>
- Commit prefix: <commit_prefix>
- Routing label: <routing_label>
Before committing, set per-repo git config:
  git config user.name "<git_name>"
  git config user.email "<git_email>"

## Scope
<scope.summary>
- <scope.focus[0]>
- ...

## Session-start ritual (every session, in order)
<render session_ritual per step 5's token table>

## What you may do
<one imperative line per capabilities.allow verb, e.g. "You may write code and tests.",
 "You may write the collab scopes: findings/, _handoff/.">

## What never happens (instruction-only at this tier — nothing here is enforced)
<one imperative line per capabilities.deny verb, e.g. "Never merge a pull request.",
 "Never push to the default branch.", "Never write wiki/.">
- Never git add -A / git add . (stage only intended files; avoids leaking secrets).

## Collab repo
- Conventions: <collab.path>/CONVENTIONS.md · Coordination: <collab.path>/COORDINATION.md
- Handoffs: <collab.path>/_handoff/ (yours to write, always)
- Canonical spec: <collab.path>/agents/<slug>/persona.yaml (this file is derived from it)
```

### 4. Set git identity (every session, before committing)
Use `identity.git_name` / `identity.git_email`, and prefix commits with
`identity.commit_prefix`. Never `git add -A` / `git add .` (stage only intended files;
avoids leaking secrets).

### 5. Run the session-start ritual (resolve intent tokens via the manifest)
- `sync_repos` -> update each repo in `manifest.repos` that has a `remote` (use RELATIVE
  paths from `manifest.paths.root`); skip local-only repos.
- `read_conventions` -> read collab `CONVENTIONS.md` + `COORDINATION.md`.
- `check_handoffs` -> search `_handoff/` for items addressed to you or `all` with open status.
- `check_backlog` -> resolve `manifest.backlog` (a file read, or an issue-tracker query).

### 6. Do the work, re-checking capabilities each step
Claim a backlog item -> branch -> work -> report to the allowed write scope (e.g. findings/)
-> commit with your prefix -> open a PR if `open_pr` is allowed (else hand off). Re-read
`persona.yaml` (or the derived `AGENTS.md`) if you are unsure whether an action is permitted.

### 7. Hand off + close
Drop a `_handoff/` if another persona is needed; update the backlog item status.

---

## Self-audit prompt (paste into your working notes)

```
I am <persona>. My git identity is <git_name> <git_email>, prefix <commit_prefix>.
I MAY: <allow verbs>
I MUST NOT: <deny verbs + denied write scopes>
Before each action I will confirm it is in MAY and not in MUST NOT.
If unsure, I deny myself and hand off to the owner.
```

## Why Tier 1 still works (do not skip it)

- It is the only universal path - proves the canon is truly runtime-neutral.
- Instruction-only guardrails caught real junk in the Phase 2 dogfood (the "never git add -A"
  catch). Discipline is a real control, not a placeholder.
- A Tier-3 runtime degrading to Tier 1 (e.g. sub-agents unavailable) can still operate every
  persona correctly by following this file. Graceful degradation, guaranteed.

## What this adapter does NOT do

- It emits no ENFORCED artifact — `AGENTS.md` (step 3) is generated context, not an
  allow-list; nothing at this tier is hard-enforced. If the runtime later gains Tier 2/3
  support, switch to that adapter to gain enforcement / persistence. Tier 1 is correct,
  not optimal.