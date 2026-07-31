# Barony — Repo Guide

> This file is contributor/agent-facing. The public story — what Barony is and why —
> is `README.md` (outsider front door), with the long form in `docs/concepts.md` and
> `docs/history.md`.

## What this repo is

**Barony** (repo `vggg/barony`; formerly `agent-project-bootstrap`, renamed per ADR-005) — git-native governance for teams of AI coding agents. The **canonical home** for the `barony` skill, the `baron` CLI, and the sister skill `multi-agent-audit` — the runtime-agnostic spec, adapters, references, tests, and meta-docs all live and evolve here.

Current state: **v1.8.0** — one front door (`SKILL.md` routes everything to `skills/barony/assets/collab-repo/START.md`); the legacy v0.3 emit path is quarantined in `legacy/` (deprecated, unmaintained); July-2026 ways-of-working folded in per ADR-002; the `baron` CLI (`cli/`, ADR-003/004) mechanizes the conventions — including the deterministic scaffold `baron init` (ADR-006, templates vendored as package data with a CI drift guard); four runtime adapters (claude, code-puppy, pydantic-ai, generic) with the enforcement-rules artifact (`capability-rules.v1.yaml`) as the single policy source. Track `STATUS.md` for current progress and deferred candidates.

## Canonicality

This repo is canonical for everything. (For the v0→v1 migration story — how canonicality moved here from the vault — see ADR-001 and `CHANGELOG.md`.)

| Surface | Canonical home |
|---|---|
| ADRs (`docs/adr/`) | this repo |
| Runtime adapters (`skills/barony/assets/collab-repo/adapters/{claude,code-puppy,pydantic-ai,generic}/`) | this repo |
| Canonical spec (`skills/barony/references/`) | this repo |
| Acceptance tests (`tests/`) | this repo |
| Emit-time templates (everything else under `skills/barony/assets/`) | this repo |
| Meta-docs (`README.md`, `CLAUDE.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `STATUS.md`) | this repo |
| `.claude-plugin/plugin.json` | this repo (bumped at release) |

The vault retains a historical copy under `_meta/skills/agent-project-bootstrap/` (the pre-rename skill name); treat it as archival reference, not a source of truth.

## Persona / role for a fresh agent

A fresh Claude Code (or code-puppy, or any other) session landing in this repo operates as a **generic dev archetype**. This repo does not yet dogfood its own multi-persona pattern — there is no `CONVENTIONS.md` / `COORDINATION.md` / `agents/` at the *repo root*. The repo owner works directly with the agent as a single dev. Persona-routing labels (`agent-<name>`) are not defined for this repo.

**Your work queue is [`AGENT-TASKS.md`](AGENT-TASKS.md)** — a prioritized, chase-top-down list (P1 promote-pilot-hardening → P2 new capabilities → P3 dogfood). `STATUS.md` is the canonical progress tracker; `AGENT-TASKS.md` is the ordered queue. When you ship an item, update STATUS.md and propagate the milestone to the vault (see below).

The `CONVENTIONS.md` and `COORDINATION.md` files you'll see under `skills/barony/assets/collab-repo/` are **emit-time templates** that get copied into projects scaffolded BY this skill — they are not this repo's own convention files.

## Propagate project-level updates to the Iris / Brain vault

This repo's *why*-record is local (`STATUS.md`, `docs/adr/`, `CHANGELOG.md`). But **project-level
decisions, milestones, and direction changes must also reach the owner's vault** — Irisidian / Brain at
`/Users/vikram/Obsidian/Brain` — so the vault librarian (**Iris**) can reconcile them into the
cross-project wiki, log, roadmap, and the `AgentBootstrapNasikoMix` project area. There is no automatic
sync. You drop a handoff.

**Propagate ONLY project-level items** (not every commit):
- a new **ADR** or a material **decision**;
- a **release** / version bump / PyPI publish;
- a **direction / roadmap change**, a **phase completion**, a **milestone**;
- a **finding** that changes the product thesis or the pitch.
Do **not** propagate routine commits, refactors, WIP, or internal-only mechanics.

**How** — write a handoff into the vault, then commit + push it there:
- Needs Vikram's input/awareness (decision, direction) → `/Users/vikram/Obsidian/Brain/_handoff/decisions/YYYY-MM-DD-barony-<topic>.md`
- FYI milestone / release / completion → `/Users/vikram/Obsidian/Brain/_handoff/tasks/YYYY-MM-DD-HHMM-barony-<slug>.md`
- Frontmatter (vault schema — `_meta/CONVENTIONS.md § Handoff protocol`):
  ```yaml
  ---
  created: YYYY-MM-DD
  from: Barony
  for: Iris
  status: open
  priority: low | medium | high
  ---
  ```
  Decision notes add `decision: <one-line>` + `urgency:`. Task notes add `task-status: complete | partial | blocked`.
- **Body:** what changed, why it matters at the project level, links (commit SHA / ADR# / PR#), and any owner action needed. Only what Iris needs to reconcile — not the full internal detail; the detail stays in this repo.
- Commit to the **vault repo** with prefix `barony: handoff | …` and push. Iris reads it at her next session, ingests it into `wiki/`+`log`+roadmap, and marks it `done` (never deleted).

If Barony later grows its **own** collab repo + librarian (dogfooding its own multi-persona pattern),
that librarian owns internal coordination and **forwards the project-level subset** to the vault by this
same mechanism. Until then, you — the dev agent — do it directly.

## Repo layout

```
.claude-plugin/
  plugin.json             # plugin manifest — version number lives here (synced with SKILL.md)
.github/workflows/ci.yml  # runs tests/ with plain python on push + PR
skills/
  barony/
    SKILL.md              # thin front door — routes to assets/collab-repo/START.md
    references/           # canonical spec
      capability-vocab.v1.md
      capability-rules.md   # prose contract for the enforcement-rules artifact (v1.6)
      persona.schema.md
      manifest.schema.md
      collab-repo-design.md
      design-decisions.md
      obsidian-setup.md
      v1-self-hosting-notes.md
    assets/
      collab-repo/
        START.md, ORCHESTRATE.md, PARTICIPATE.md   # neutral entrypoints (v1.0)
        manifest.example.yaml                      # worked example of the project spec
        adapters/
          claude/, code-puppy/, pydantic-ai/, generic/   # runtime adapters (each has
                                                   # HYDRATE.md with a machine-readable
                                                   # capability map)
        agents/                                    # persona.yaml + AGENT.md per archetype
          __DEV__/, __AUTONOMOUS_EVENT__/, __AUTONOMOUS_CRON__/, librarian/,
          __REVIEWER__/, __MERGER__/               # reviewer/merger added v1.4 (ADR-002)
        CONVENTIONS.md, COORDINATION.md, CLAUDE.md, BOOTSTRAP.md,
        BOOTSTRAP-ADMIN.md, QUICKSTART.md, README.md,
        _handoff/, decisions/, findings/, wiki/, workspace-template/,
        _failover-cron-sections/
      commands/           # slash command templates (e.g. vc.md)
  multi-agent-audit/      # sister skill — read-only project grading
cli/                      # the baron CLI (ADR-003/004/006): init/validate/status/ledgers/guard/
                          # lock/worktree/waivers + runtime hydrators (baron/runtimes/), the
                          # packaged capability-rules artifact + vendored templates (baron/data/,
                          # synced by cli/scripts/sync_templates.py); pytest suite
legacy/                   # DEPRECATED v0.3 emit path (vault/, workspaces/, SKILL-v0.3.md)
docs/
  adr/                    # architecture decision records (ADR-001, ADR-002, ...)
  notes/                  # supporting notes cited by the spec
  concepts.md             # longer-form concept explanations (public docs, linked from README)
  history.md              # the v0.3 → v1.x evolution narrative (public docs)
  LEARNINGS.md
tests/
  bi_runtime_accept.py    # acceptance harness — parses the adapters' capability maps
  lint_repo.py            # placeholders, dead links, fixture leaks, version sync
  examples/               # example persona fixtures (rex, tess)
CHANGELOG.md
CLAUDE.md                 # this file
CONTRIBUTING.md           # PR conventions incl. "docs land with code" rule
LICENSE
README.md
STATUS.md                 # progress tracker + deferred candidates
```

## Versioning

Semver. Patch (0.0.x): wording fixes, typos, broken references. Minor (0.x.0): new placeholders, new template sections, structural improvements. Major (x.0.0): breaking changes to the emit process or file layout. The version lives in `.claude-plugin/plugin.json` and the `SKILL.md` frontmatter — keep them in sync (`tests/lint_repo.py` enforces it). Release history and the v0→v1 migration story: `CHANGELOG.md` + ADR-001.

## Release workflow

```bash
# 1. Verify the tests pass (the two stdlib suites + the baron CLI suite):
python3 tests/bi_runtime_accept.py
python3 tests/lint_repo.py
uv run --project cli pytest cli/tests

# 2. Bump version in .claude-plugin/plugin.json AND skills/barony/SKILL.md
# 3. Move [Unreleased] content in CHANGELOG.md to a new version section

git add .
git commit -m "release: vX.Y.Z — <summary>"
git push
git tag -a vX.Y.Z -m "<summary>"
git push origin vX.Y.Z
gh release create vX.Y.Z --title "vX.Y.Z — <summary>" --notes "<notes>"
```

## Testing

Install from a local clone:
```bash
/plugin install /path/to/barony
```

Invoke in a throwaway directory and verify the emitted files match the templates in `skills/barony/assets/`.

**Bi-runtime acceptance test** — the gate for adapter / spec / canonical-contract changes:
```bash
python3 tests/bi_runtime_accept.py
```
(Stdlib only — no PyYAML needed since v1.4.) It parses the machine-readable capability maps
in the adapters' `HYDRATE.md` files plus `references/capability-vocab.v1.md` and asserts that
every v1 verb is mapped in every adapter, the tess/rex fixtures hydrate to an equivalent
behavior contract across runtimes, and enforcement-tier claims are consistent. Run before any
PR touching adapters, references, or the canonical contract files.

**Repo lint** — `python3 tests/lint_repo.py` — unfilled placeholders outside template dirs,
dead relative markdown links, fixture-name leaks into templates, plugin/SKILL version sync.
Both tests run in CI (`.github/workflows/ci.yml`) on every push and PR.

## PR rules

See `CONTRIBUTING.md`. Key rule (post-2026-06-03): **documentation lands with code in the same PR** — never as a follow-up. Affected ADRs, `CLAUDE.md`, `README.md`, `CHANGELOG.md`, and `STATUS.md` updates are all part of "done."

## See also

- `STATUS.md` — progress tracker + deferred candidates
- `docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md` — the accepted v1.0 architecture (and the full v0→v1 migration story)
- `docs/adr/ADR-002-ways-of-working-2026-07.md` — the July-2026 ways-of-working folded in at v1.4
- `CONTRIBUTING.md` — PR conventions including the docs-with-code rule
- `README.md` — user-facing description of the skill
