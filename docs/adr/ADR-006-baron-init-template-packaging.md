---
created: 2026-07-27
accepted: 2026-07-27
type: decision
status: accepted
decided_by: Vikram
adr: 006
project: barony
related:
  - "[[docs/adr/ADR-003-baron-cli]]"
  - "[[docs/adr/ADR-005-naming]]"
---

# ADR-006: `baron init` — the deterministic scaffold — and how the templates ship

| Field | Value |
|---|---|
| **Status** | Accepted (2026-07-27) |
| **Date** | 2026-07-27 |
| **Authors** | Vikram + Claude |
| **Supersedes** | — (extends ADR-003; mechanizes the deterministic subset of ORCHESTRATE.md) |
| **Decision owner** | Vikram |

## 1. Summary

Until v1.8.0 the only way to create a Barony project was the **conversational
path**: an agent reads `START.md` → `ORCHESTRATE.md`, interviews the user, and
emits the collab repo by following prose. That path is the right place for
judgment (scope prose, roster design, tier self-assessment) — and the wrong
place for the 90% of scaffolding that is pure mechanics. A stranger with a
laptop and `pip install barony` had NO path at all: the templates live in the
skill, and a pip install carries no skill.

Two decisions:

1. **`baron init`** — a deterministic, non-conversational scaffold command
   (`baron init <name> [--dir] [--code-repo] [--personas archetype:slug,...]
   [--runtime claude|generic|pydantic-ai|code-puppy] [--no-git]`) that emits
   the canonical collab-repo layout and validates its own output with the real
   schemas before committing it.
2. **Templates ship twice, one canonical, drift-guarded** — the skill tree
   stays the single canonical source; baron vendors a byte-identical copy as
   package data, and a CI test fails on any drift.

## 2. Decision — template packaging: vendor-with-drift-guard

**Canonical source (unchanged):** `skills/barony/assets/collab-repo/` plus the
four canon references in `skills/barony/references/`. The Claude plugin reads
them in place; `tests/bi_runtime_accept.py` and `tests/lint_repo.py` parse them
at those paths; the conversational path copies them from there
(ORCHESTRATE.md §2a).

**Vendored copy:** `cli/src/baron/data/templates/{collab-repo/**, references/*}`
— committed package data (same mechanism as `capability-rules.v1.yaml`,
ADR-004 addendum §4.1), refreshed by `python cli/scripts/sync_templates.py`.

**Drift guard:** `cli/tests/test_template_sync.py` asserts the trees are
byte-identical (file set + content) and that every archetype `baron init`
offers is actually packaged. Editing a skill template without re-running the
sync script fails CI; the failure message names the fix.

**Why not MOVE the templates into the package** (the alternative considered):
the skill must keep its assets under `skills/barony/` to remain an installable
Claude plugin, and both stdlib acceptance suites deliberately run **without**
baron installed (CI runs them with plain python; no dependency step). Making
the skill or those suites resolve templates out of an installed package would
couple the plugin to a pip install that plugin users don't have. Two committed
copies with a byte-level CI guard cost one `git status`-visible directory and
zero runtime indirection; a stale vendor cannot ship.

## 3. Decision — what `baron init` covers, and what stays conversational

`baron init` emits, deterministically (dates via the injectable clock):

- `CONVENTIONS.md` / `COORDINATION.md` (placeholders filled), generated
  `README.md`, `manifest.yaml` (schema-conformant: relative paths, `backlog:
  file` + `backlog.md` stub, roster; `workspace.worktrees_root` when a code
  repo is named), `canon/` (3 entrypoints + 4 references) and `adapters/`
  (all 4) copied verbatim per ORCHESTRATE.md §2a.
- `agents/<slug>/persona.yaml` hydrated from the archetype template
  (identity `<slug>@<project>.local`, commit prefix, routing label; librarian
  renameable — `librarian:iris` — with the archetype line kept). Scope text is
  an explicit generic edit-me placeholder, not fake specificity.
- `_handoff/` with a genesis handoff addressed to the librarian; ledger index
  headers (`findings/index.md`, `decisions/index.md`) that the real allocator
  appends to; the wiki stub with a genesis log entry; the lock-guard CI
  template.
- A per-persona **runtime kit** under `agents/<slug>/runtime/` — the
  deterministic floor of each adapter: claude = Tier-2 persona `CLAUDE.md` +
  `.claude/settings.json` wiring the `baron guard` PreToolUse hook (HYDRATE.md
  steps 3b/3c); generic and code-puppy = Tier-1 `AGENTS.md` (code-puppy's
  documented fallback); pydantic-ai = the `agent_setup.py` bootstrap (reusing
  `baron.runtimes`).
- `git init -b main` + a first commit of exactly the files it wrote (never
  `add -A`), unless `--no-git`. Refuses a non-empty target directory.
- A self-check: the scaffold must pass `baron validate` with zero errors
  before init reports success.

**Stays conversational** (canon/ORCHESTRATE.md, by design): interviewing for
real persona scopes, deriving `AGENT.md` manuals, Tier-3 hydration (Claude
subagents and code-puppy JSON agents both require an in-session
capability/tier self-assessment the CLI cannot make), code-repo creation and
`.gitignore` authoring, and workspace/clone setup. Init prints where to go
next; it does not pretend to have done these.

## 4. Consequences

- A pip-only user reaches a working, validated project in minutes; the
  15-minute stranger bar is now a CLI property, not a prompt-engineering
  outcome.
- Two copies of the templates exist in the repo; CI makes divergence
  impossible to ship, and the sync script makes the fix one command.
- The runtime kits restate the adapters' Tier-1/Tier-2 render rules in code.
  That duplication is bounded (prose-only surfaces, no tool allow-lists — the
  Tier-3 mapping tables stay solely in the adapters) and is the same trade
  ADR-004 accepted for guard: deterministic output needs code, not prose.
