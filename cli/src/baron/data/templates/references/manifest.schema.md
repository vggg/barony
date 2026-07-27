# `manifest.yaml` Schema v1

> The CANONICAL, runtime-neutral PROJECT spec: what repos exist, where the backlog lives, and
> which personas are on the team. Consumed by the orchestrator (ORCHESTRATE.md) at bootstrap
> and by adapters when hydrating personas. Runtime-neutral; names no runtime tools.
>
> This schema is where the Phase 2 "location & transport independence" theme (F1/F7/F8) is
> resolved structurally.

## Fields

| Field | Req | Type | Notes |
|---|---|---|---|
| `project.name` | yes | str | e.g. `tasklib-agents` |
| `project.description` | yes | str | one line |
| `repos` | yes | list | each repo the team operates on (see below) |
| `paths.strategy` | yes | enum | `relative` (default, REQUIRED for portability) or `absolute` |
| `paths.root` | no | str | anchor for relative resolution; default = collab repo root |
| `backlog.source` | yes | enum | `file` or `github_issues` or `jira` (resolves F8) |
| `backlog.location` | yes | str | path (for `file`) or repo/project ref (for trackers) |
| `personas` | yes | list | roster: each entry points at a `persona.yaml` |
| `adapters` | no | map | per-runtime adapter overrides (project defaults); runtime-neutral envelope — see below |
| `workspace` | no | map | where persona working copies live locally (v1.2, optional) — see below |

### adapters (runtime-neutral envelope)

A namespaced block so the canon can carry per-runtime defaults **without naming runtime tools
in the core fields**. Each key under `adapters` is a runtime id; the keys *inside* it are owned
by that runtime's adapter, not by this schema. The canon defines only the SHAPE
(`adapters.<runtime>.<key>`); adapters document their own keys.

| Key | Owner | Notes |
|---|---|---|
| `adapters.claude.tier` | Claude adapter | `auto` \| `2` \| `3` (default `auto`). Project default rendering tier; see `adapters/claude/HYDRATE.md`. A persona may override via `runtime.adapters.claude.tier`. |

> Unknown `adapters.<runtime>` blocks are ignored by adapters that don't recognize them —
> additive and forward-compatible. Absence = every adapter uses its own default.

### repos[]

| Field | Req | Notes |
|---|---|---|
| `id` | yes | logical name used by capability verbs: `code`, `collab` |
| `path` | yes | location RELATIVE to `paths.root` (F7 fix - never absolute) |
| `remote` | no | optional git remote; absent means local-only (valid, per Phase 2) |
| `role` | yes | `code` (app) or `collab` (coordination substrate) |

### personas[]

| Field | Req | Notes |
|---|---|---|
| `slug` | yes | matches a `persona.yaml` slug |
| `spec` | yes | path to the persona.yaml (relative) |

### workspace (optional, v1.2)

Describes where persona **working copies** live on the local machine, so tooling
(`baron status`, ADR-003) can sweep them for divergence — the stranding classes the
2026-07-22 badminton-analyzer incident exposed (unpushed commits, unmerged branches, an
unpulled canonical clone). Both keys are optional and additive; paths are relative to
`paths.root`, like `repos[].path` (F7).

| Field | Req | Notes |
|---|---|---|
| `workspace.clones` | no | list of `{persona, path}` — one entry per persona-local clone of a project repo |
| `workspace.worktrees_root` | no | a directory whose git-containing subdirectories are persona working copies (worktree-style layout; the topology itself is baron M6, planned) |

```yaml
workspace:
  clones:
    - persona: fern
      path: ../gardenkit-fern      # fern's clone of the code repo
    - persona: moss
      path: ../gardenkit-moss
  # worktrees_root: ../worktrees   # alternative: every git dir under here is swept
```

Absence means: only `repos[]` working copies are swept. This block is *local-topology*
metadata — it never affects hydration or capability mapping.

## Example (tasklib-agents, derived from the Phase 2 dogfood)

```yaml
project:
  name: tasklib-agents
  description: Autonomous multi-agents to improve testing coverage for tasklib.
paths:
  strategy: relative          # F7: hydration emits ../code, never /Users/...
  root: .                     # resolved from the collab repo root
repos:
  - id: code
    path: ../code             # relative - travels on re-clone
    role: code
    # remote: omitted -> local-only (Phase 2 proved this is valid)
  - id: collab
    path: .
    role: collab
backlog:
  source: file                # F8: not hardcoded to GitHub
  location: backlog.md        # lives in the collab repo
personas:
  - slug: tess
    spec: agents/tess/persona.yaml
adapters:                     # optional; runtime-neutral envelope
  claude:
    tier: auto                # auto | 2 | 3 — project default rendering tier
```

## How this fixes the Phase 2 friction

- **F7 (absolute paths):** `paths.strategy: relative` + relative `repos[].path` means the
  adapter renders `git -C ../code ...`, never a home-dir absolute path. Re-clone anywhere and
  it still works.
- **F8 (GitHub-only backlog):** `backlog.source`/`location` make the `check_backlog` ritual
  token resolve to a file read OR an issue-tracker query, per project.
- **F1 (cwd coupling):** ORCHESTRATE.md + the adapter document that the runtime session starts
  at `paths.root`; discovery and relative paths resolve from there.

## Changelog

- **v1** (Phase 3): new, derived from the Phase 2 dogfood. Encodes location & transport
  independence (relative paths, configurable backlog source) to fix F1/F7/F8.
- **v1.1** (Claude Tier-3): added the optional, runtime-neutral `adapters.<runtime>` override
  envelope. First consumer: `adapters.claude.tier`. Additive — existing manifests are
  unchanged and every adapter falls back to its own default when the block is absent.
- **v1.2** (baron M2, ADR-003): added the optional `workspace` block
  (`clones` / `worktrees_root`) describing local persona working copies for divergence
  sweeps (`baron status`). Additive — existing manifests are unchanged.
