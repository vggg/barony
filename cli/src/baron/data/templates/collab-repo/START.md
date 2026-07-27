# START — Front Door (runtime-neutral)

> The first file any runtime reads. It figures out WHERE you are and routes you to the right
> recipe. Runtime-neutral: it names capabilities and roles, never a specific runtime's tools.

## Step 1 — Identify your runtime

Look up your adapter at `adapters/<runtime>/HYDRATE.md`. Known runtime keys (v1):

| Runtime | Key | Adapter |
|---|---|---|
| code-puppy (work) | `code-puppy` | `adapters/code-puppy/HYDRATE.md` |
| Claude Code (home) | `claude` | `adapters/claude/HYDRATE.md` |
| pydantic-ai (+ harness) | `pydantic-ai` | `adapters/pydantic-ai/HYDRATE.md` |
| anything else | `generic` | `adapters/generic/HYDRATE.md` (always-works Tier-1 fallback) |

If your runtime has no adapter, use `generic`.

## Step 2 — Where are you? (route on directory state)

| You see... | You are... | Go to |
|---|---|---|
| An empty/new dir, or only a `manifest.yaml` to be authored | bootstrapping a NEW project | `ORCHESTRATE.md` (Role 1) |
| An existing collab repo (`CONVENTIONS.md`, `agents/`, `manifest.yaml`) | JOINING an existing project | `PARTICIPATE.md` (Role 2) |

## Step 3 — Launch-dir requirement (Phase 2 F1)

Start your runtime session at the project's `paths.root` (the collab repo root by default).
Project-scoped agent discovery and all relative paths resolve from there. If your runtime
discovers agents relative to the current working directory (check your runtime's adapter),
launching elsewhere means your hydrated personas won't be found.

## Step 4 — Hand off

Read the recipe (`ORCHESTRATE.md` or `PARTICIPATE.md`) end to end, then follow it using your
runtime's adapter for any concrete tool actions.

---

### Mental model

- **Canon** (`canon/`, `manifest.yaml`, `agents/*/persona.yaml`) = WHAT (neutral).
- **Adapter** (`adapters/<runtime>/`) = HOW (runtime-specific).
- **START/ORCHESTRATE/PARTICIPATE** = the routing + recipes that glue them.
