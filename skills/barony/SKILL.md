---
name: barony
description: Barony — scaffold or join a runtime-agnostic multi-agent software project. Use when the user wants to set up a new multi-agent project (personas, collab repo, conventions, coordination) or join an existing one — one runtime-neutral persona.yaml hydrates working personas on any AI coding agent (Claude Code, code-puppy, ...) via per-runtime adapters.
version: 1.11.0
created: 2026-05-22
updated: 2026-08-04
---

# Skill: Barony (project bootstrap)

Bootstraps a runtime-agnostic multi-agent project: a machine-readable `manifest.yaml` +
one `persona.yaml` per persona, hydrated onto **any** runtime at the highest fidelity it
supports (the capability ladder: Tier 3 enforced native sub-agents → Tier 2 session
context → Tier 1 in-prompt).

## One front door

**All new-project creation and joining routes through one file:**

> **`assets/collab-repo/START.md`**

`START.md` routes by directory state:

- New/empty directory → **`assets/collab-repo/ORCHESTRATE.md`** (Role 1 — set up a new project).
- Existing collab repo → **`assets/collab-repo/PARTICIPATE.md`** (Role 2 — join it).

Concrete tool actions go through the runtime's adapter —
`assets/collab-repo/adapters/{claude,code-puppy,pydantic-ai,generic}/HYDRATE.md`
(`generic` is the mandatory Tier-1 fallback). The canonical contract lives in
`references/{capability-vocab.v1,persona.schema,manifest.schema}.md` (plus
`references/capability-rules.md` for the machine-readable enforcement-rules artifact); a
worked project spec example is at `assets/collab-repo/manifest.example.yaml`.

When invoked, read `assets/collab-repo/START.md` and follow it. Do not improvise an emit
sequence from this file — this file only routes.

> **Deterministic shortcut (v1.8):** when the `baron` CLI is installed, `baron init`
> emits ORCHESTRATE's mechanical steps (skeleton, manifest, hydrated personas, runtime
> kits) from the same templates, vendored as package data (ADR-006). ORCHESTRATE.md
> marks where the conversational recipe resumes — don't hand-emit what init covers.

## Non-Claude runtimes

code-puppy (and other runtimes that don't auto-discover this skill format) invoke the same
neutral files by path — see `USING-WITH-CODE-PUPPY.md` at the repo root.

## Legacy path

The pre-v1.0 template-emit modes (`vault-project`, `collab-repo-project`,
`join-collab-project`) are deprecated and quarantined in `legacy/` at the repo root
(see `legacy/README.md`). Existing v0.x projects only; never for new projects.
