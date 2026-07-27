# Using with code-puppy

This repo is packaged as a **Claude Code** plugin/skill (`skills/barony/SKILL.md`,
`.claude-plugin/`). **code-puppy does not auto-discover that skill format** — if you point
code-puppy at this repo and ask it to "use the skill", it will look for its own skill registry
and report that it can't find a `SKILL.md` it understands.

That's expected. The runtime-agnostic v1.0 design means you don't need the skill wrapper at all:
the instructions are plain markdown that any runtime can read and follow. This guide shows the
code-puppy path (Tier 3 — capabilities are *enforced* via a tool allow-list).

> Native code-puppy skill packaging is tracked as a follow-up. Until then, invoke by file path
> as below.

## TL;DR

```bash
git clone https://github.com/vggg/barony
cd <your-collab-repo>          # start code-puppy FROM the project root (see Why below)
```

Then tell code-puppy:

> Read these files from the cloned repo, in order, then follow them to bootstrap a new
> collab project:
> 1. `barony/skills/barony/assets/collab-repo/START.md`
> 2. `barony/skills/barony/assets/collab-repo/ORCHESTRATE.md`
> 3. `barony/skills/barony/assets/collab-repo/adapters/code-puppy/HYDRATE.md`
>
> Use the schemas in `barony/skills/barony/references/`
> (`capability-vocab.v1.md`, `persona.schema.md`, `manifest.schema.md`) as the canonical contract.

code-puppy reads those, identifies its runtime as `code-puppy`, routes (new dir → `ORCHESTRATE`),
and hydrates each persona via the adapter — no skill discovery needed.

## Key file map

| Purpose | Path (under repo root) |
|---|---|
| Front door / router | `skills/barony/assets/collab-repo/START.md` |
| Role 1 — bootstrap a new project | `skills/barony/assets/collab-repo/ORCHESTRATE.md` |
| Role 2 — join an existing project | `skills/barony/assets/collab-repo/PARTICIPATE.md` |
| code-puppy adapter (Tier 3) | `skills/barony/assets/collab-repo/adapters/code-puppy/HYDRATE.md` |
| Capability vocabulary (frozen v1) | `skills/barony/references/capability-vocab.v1.md` |
| Persona schema | `skills/barony/references/persona.schema.md` |
| Manifest schema | `skills/barony/references/manifest.schema.md` |

## Why start the session from the project root

code-puppy discovers project-scoped sub-agents relative to its working directory. If you launch
the session somewhere else, the personas it hydrates won't be found. `cd` into the collab repo
root (your project's `paths.root`) **before** starting code-puppy. (This is `START.md` Step 3.)

## What you'll be asked for

- Project name + one-line description
- Code repo URL + collab repo URL (remote-collab needs both as real repos)
- Backlog source — a `backlog.md` file in the collab repo, or an issue tracker
- Persona roster — at least one `dev` persona (think one per collaborator role)

## Joining an existing project (other collaborators)

Same idea, different recipe: clone the collab repo, start code-puppy from its root, and ask it
to read `START.md` → `PARTICIPATE.md` → `adapters/code-puppy/HYDRATE.md`. Claim a persona, set
your git identity, and validate with a "hello" PR.

## Enforcement note (why Tier 3 matters)

On code-puppy, a persona's `capabilities.allow` is mapped to an **enforced** tool allow-list:
tools that aren't granted are not registered, so denials at whole-tool granularity genuinely
hold (e.g. a read-only reviewer that *cannot* write). Sub-tool denials (e.g. allow `open_pr`,
deny `merge_pr` — both ride `agent_run_shell_command`) remain instruction-level. If you need a
collaborator's guardrails to be hard-enforced, run them on code-puppy rather than a Tier-2 runtime.

## "Vault commit" / `/vc` on code-puppy

`/vc` ("vault commit") is a **Claude Code slash command** (`assets/commands/vc.md`). code-puppy
has no command by that name, so saying "vault commit" or `/vc` to a code-puppy agent does nothing
— it doesn't understand it. There are two ways to get the same behavior:

**Option A — use the emitted per-persona command (if your project was hydrated).**
The code-puppy adapter emits a project-scoped command at `{repo}/.agents/commands/vc-<slug>.md`
(e.g. `vc-scout.md`). If your runtime's customizable-commands plugin is active, invoke it as
`/vc-<slug>`. (Path quirk: agents live under `.code_puppy/` with an underscore, commands under
`.agents/commands/`.)

**Option B — just describe the workflow (always works).**
Tell the agent in plain language:

> Commit my changes the "vault commit" way: run `git status --short` (never `git add -A`), stage
> only the intended files, commit with message `<commit_prefix> <op> | <description>` (my prefix
> is `<your-prefix>:`), push the current branch (never force-push, never push to main directly),
> and for substantive changes open a PR instead. `_handoff/` files may be direct-pushed.

Both produce the canonical `<persona>: <op> | <description>` commit + push that `/vc` does on
Claude Code. The workflow is what matters, not the slash command — code-puppy executes the steps
directly.
