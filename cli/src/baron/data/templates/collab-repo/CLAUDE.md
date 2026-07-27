# {{PROJECT_NAME}} — Collab Repo Pointer

> **You are running inside the {{PROJECT_NAME}} collab repo.** This is the project's coordination substrate, not the codebase. The actual code lives at https://github.com/{{CODE_REPO}}.

## Read these first

1. **`QUICKSTART.md`** — fastest path to operational (agent-led, ~30 min). Use this if you're onboarding via an AI coding agent (Claude Code, code-puppy, etc.).
2. **`BOOTSTRAP.md`** — manual step-by-step onboarding (~45 min). Use this if you're onboarding without an agent, or want the deeper reference.
3. **`CONVENTIONS.md`** — repo-wide rules.
4. **`COORDINATION.md`** — multi-persona protocol; session-start checklist; ADR rules; hot files.
5. **Your `agents/<you>/AGENT.md`** — your persona-specific operating manual.

## Quick orientation

| | |
|---|---|
| **Project** | {{PROJECT_NAME}} |
| **Description** | {{PROJECT_DESCRIPTION}} |
| **Code repo** | github.com/{{CODE_REPO}} |
| **This repo (collab)** | github.com/{{COLLAB_REPO}} |
| **Live URL** | {{LIVE_URL}} |
| **Tech stack** | {{TECH_STACK}} |
| **Project owner** | {{USER_NAME}} (`@{{OWNER_HANDLE}}`) |

## Personas

See `COORDINATION.md § Personas at a glance` for the team roster. Full operating manuals live in `agents/<persona>/AGENT.md`.

## Recent project state

Run the Librarian's wiki for current state:
- `wiki/log.md` — append-only reconciliation log (most recent at top)
- `wiki/entities/` — durable entities (people, components, integrations)
- `wiki/concepts/` — design concepts, strategies, patterns

If `wiki/log.md` looks stale, the Librarian may be behind — see `agents/librarian/FAILOVER.md` if you need to take over the Librarian role.
