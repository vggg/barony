# Design Decisions: Agent-Project Bootstrap

Rationale for the choices baked into this skill. Read before customising.

## Why five agents and not more

Five roles covers the full software development surface without requiring an orchestrator: Iris handles memory and coordination; the two dev slots handle feature parallelism when needed; the analyst handles discovery and issue-filing; the designer handles external-facing content. Adding more agents increases the number of files each session-start must read, which degrades coherence faster than it adds capability.

The two-dev pattern (Dev 1 + Dev 2) is optional. Single-dev projects use only Dev 1.

## Why COORDINATION.md owns cross-agent protocol

Each agent reads its own workspace CLAUDE.md at session start. If cross-agent rules were duplicated in every CLAUDE.md, one edit must propagate to five files — drift is inevitable. Centralising in COORDINATION.md means one edit, one place. CLAUDE.md files become thin pointers.

## Why CONVENTIONS.md is a separate file from COORDINATION.md

CONVENTIONS.md covers vault mechanics (tool hierarchy, wikilink format) — rules that are set once and rarely change. COORDINATION.md covers cross-agent workflows (handoffs, ADRs, PR discipline) — rules that evolve with the project. Keeping them separate prevents vault mechanics from getting polluted with project-specific protocol changes, and vice versa.

## Why Write/Read/Edit tools and not Obsidian MCP

Obsidian MCP tools are unavailable or unreliable across environments. Using `Write`/`Read`/`Edit` at the vault's absolute path works anywhere and makes tool calls auditable. The tradeoff is no Obsidian-native features (tag management, graph updates). For a code-centric workflow this is acceptable — markdown files are the interface.

## Why _handoff/ uses status: open/done and is never deleted

Deleting handoffs after acting on them hides the coordination history. `status: done` preserves the record while suppressing the item from open-handoff greps. The append-only model means any agent can reconstruct what coordination happened and when.

## Why the shared GitHub repo pattern for dev agents

Having two dev workspaces clone the same GitHub repo means the project's engineering CLAUDE.md is authoritative in one place (the repo root). Both workspaces pull it. The alternative — per-workspace CLAUDE.md files that never merge — creates silent divergence. The cost of the shared pattern is that CLAUDE.md is a hot file, but that cost is lower than undetected rule drift.

## Why __PROJECT__ as the folder naming convention

Skill assets must not contain real project names so they stay reusable. `__PROJECT__` is visually distinct from a `{{placeholder}}` token and is meant to be renamed as a directory, not searched-and-replaced. The distinction makes the rename step explicit and hard to miss.

## Why no scripts/ folder in this skill

Scripts require a known runtime, known paths, and ongoing maintenance. Step-by-step emit instructions in SKILL.md are more durable and work in any shell. If emitting becomes repetitive enough to automate, write the script in the project that owns the automation — not here.
