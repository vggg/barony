# Barony

**Git-native governance for teams of AI coding agents.** Barony is a spec, a set of
runtime adapters, and a CLI (`baron`) for running multiple AI coding agents on one
long-lived project with real rules — capability grants and denials, coordination
protocol, handoffs, locks — enforced through the git substrate itself. The pattern is
**runtime-agnostic** (per
[ADR-001](docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md)):
a single runtime-neutral `persona.yaml` hydrates working personas on whatever AI coding agent
you run — Claude Code, code-puppy, pydantic-ai, or anything else — at the highest fidelity
that runtime supports. It started as a Claude Code plugin and remains fully compatible with it.

> Formerly published as `agent-project-bootstrap`; renamed at v1.7.0
> ([ADR-005](docs/adr/ADR-005-naming.md)). Old GitHub URLs redirect.

**This repo also ships a sister skill, [`multi-agent-audit`](skills/multi-agent-audit/),** for **grading** multi-agent projects with evidence — INTERVENTION TAX, dual-lens drift, operational fidelity — instead of vibes. Read-only by construction. See [Sister skill](#sister-skill-multi-agent-audit).

**One front door:** every new project (and every joiner) routes through
`skills/barony/assets/collab-repo/START.md`, which routes by directory state —
new/empty directory → `ORCHESTRATE.md` (set up a project), existing collab repo →
`PARTICIPATE.md` (join it). No modes to pick.

> **Migration note:** this repo previously carried two generations of scaffolding flows. The
> pre-v1.0 Claude-Code-only emit modes are deprecated and quarantined in [`legacy/`](legacy/)
> (existing v0.x projects only). The full v0→v1 story lives in
> [ADR-001](docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md) and [`CHANGELOG.md`](CHANGELOG.md).

## When it's useful

- You're running multiple agent sessions in parallel on the same long-lived project
- You want a knowledge layer (research findings, decisions, reconciliation log) that lives separate from the codebase
- You're a solo or near-solo developer who coordinates with several specialist agents rather than a human team
- You've used multi-agent setups before and want a repeatable starting point instead of rebuilding config files from scratch each time
- Your collaborators run **different** runtimes (Claude Code at home, code-puppy at work, ...) and you need one persona spec that works on all of them

## When it's overkill

- One-shot or throwaway tasks (a single agent session is simpler)
- Projects where you don't need persistent memory across sessions
- Team setups where human engineers handle coordination and you only need one agent at a time

## What gets generated

A dedicated **collab repo** (the coordination substrate, separable from your code repo):

```
README.md                 # project overview
CONVENTIONS.md            # repo-wide rules (single-account constraint, identity, labels,
                          #   routing, handoff lifecycle, machine-local state)
COORDINATION.md           # multi-persona protocol (hot files + lock mechanics, review/merge,
                          #   ADR rules, ticket lifecycle)
manifest.yaml             # machine-readable project spec (repos, backlog, roster)
canon/                    # the runtime-neutral spec, copied in so joiners can resolve it
adapters/                 # per-runtime HYDRATE.md (claude / code-puppy / pydantic-ai / generic)
agents/
  <persona-slug>/
    persona.yaml          # CANONICAL machine truth: identity, capabilities, scope, ritual
    AGENT.md              # human-readable manual, derived from the yaml
_handoff/                 # cross-persona async messages (append-only)
decisions/  findings/     # project decisions + investigation outputs
wiki/                     # synthesised by the Librarian
```

Persona archetype templates shipped (each `persona.yaml` + `AGENT.md`):

- **dev** — interactive persona, one per human collaborator
- **librarian** — wiki + indexes + drift checks; always present
- **autonomous-event** — webhook-triggered (e.g. PR checks, backtest runner)
- **autonomous-cron** — scheduled (e.g. PM+UAT)
- **reviewer / merger** *(optional, [ADR-002](docs/adr/ADR-002-ways-of-working-2026-07.md))* — adversarial SHA-bound PR review (the **signet** pattern: a verdict sealed to the exact commit it judged) + a merge gate that isn't the human owner

Plus the `/vc` slash-command template (`assets/commands/vc.md`) for the canonical
`<persona>: <op> | <description>` commit workflow.

## Runtime support (runtime-agnostic core)

Personas are defined once in a runtime-neutral `persona.yaml` (identity, abstract
*capabilities*, scope, session ritual). Each runtime maps those abstract capabilities onto its
real tools via an **adapter** — the only runtime-specific surface. Adding a runtime means
adding an `adapters/<runtime>/` folder and touching nothing else.

A persona always runs at the highest tier its runtime supports (the **capability ladder**),
and degrades gracefully:

| Tier | Runtime | Mechanism | Enforcement |
|---|---|---|---|
| 3 | Claude Code or code-puppy | native sub-agents (Claude `.claude/agents/<slug>.md`; code-puppy JSON agents) | capabilities enforced via a tool allow-list — **whole-tool denials are real** (a read-only persona genuinely cannot write/run shell); sub-tool denials instructed |
| 3 | pydantic-ai (+ pydantic-ai-harness) | in-process hydration: `baron.runtimes.pydantic_ai.build_agent` assembles a guarded `Agent` | whole-tool denials via capability omission; the five guard-covered **sub-tool denials natively ENFORCED** (in-process interception consuming `capability-rules.v1.yaml`) |
| 2 | Claude Code | persistent `CLAUDE.md` | persistent session context; capabilities instructed |
| 1 | anything | in-prompt + emitted `AGENTS.md` | persona re-read each turn; self-enforced |

The Claude adapter renders **either** Tier 2 **or** Tier 3, selected by a runtime-neutral
`adapters.claude.tier` config (`auto` | `2` | `3`, default `auto`).

Key files:

- `START.md` / `ORCHESTRATE.md` / `PARTICIPATE.md` — neutral entrypoints (front door + the two
  role recipes; routing is by directory state, not a human choice).
- `adapters/{generic,code-puppy,claude,pydantic-ai}/HYDRATE.md` — per-runtime mappings
  (`generic` is the mandatory Tier-1 fallback). Each carries a normalized, machine-readable
  capability map that `tests/bi_runtime_accept.py` checks in CI across all four adapters.
- `references/{capability-vocab.v1,persona.schema,manifest.schema}.md` — the canonical spec;
  `references/capability-rules.md` documents the machine-readable enforcement-rules artifact
  (`capability-rules.v1.yaml`, shipped as baron package data) that every enforcing consumer
  loads instead of restating.
- `assets/collab-repo/manifest.example.yaml` — a realistic worked example of the project spec.

See [ADR-001](docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md) for the full design
and [ADR-002](docs/adr/ADR-002-ways-of-working-2026-07.md) for the field-proven July-2026
coordination rules baked into the templates (single-account constraint, everything-material-
gets-a-handoff, lock-via-open-PR + CI guard, reviewer/merger personas).

## baron CLI (Phase 2)

Phase 2 of the roadmap converts the coordination *conventions* above into *mechanisms*:
**[`baron`](cli/README.md)** (`cli/`, per [ADR-003](docs/adr/ADR-003-baron-cli.md) and
[ADR-004](docs/adr/ADR-004-baron-guard-enforcement.md)) is a small typer CLI — a
disciplined reader/writer over collab-repo files; the markdown/git substrate stays the
only database. Shipped (v1.5.0):

- `baron validate` — persona.yaml / manifest.yaml against the canonical schemas, with the
  frozen 10-verb vocabulary embedded and drift-guarded against the prose spec.
- `baron status` — clone/branch/worktree divergence (the three stranding classes from the
  2026-07-22 field incident), overdue open handoffs, ledger/wiki staleness, CI-usable exit
  codes — plus expiring **waivers** (`baron waiver add`, `.baron-waivers.yaml`) so
  deliberately-parked reds show as warns with the reason, never silently.
- `baron finding|decision new` — race-safe F/D-number allocation via push-retry;
  `baron handoff create|close|list` (archive-not-delete lifecycle) and `baron index`.
- `baron guard` — deterministic capability enforcement as a Claude Code **PreToolUse
  hook** (ADR-004): denied `push_main`/`force_push`/`merge_pr`/`write_path` scopes/
  `edit_other_personas` are blocked *before the tool runs*, upgrading those sub-tool
  denials from instructed to enforced when baron is installed (honest degradation
  otherwise). Overrides are allowed-but-logged to a tracked file.
- `baron lock claim|release|list` — PR-as-lock (ADR-002 §3): a draft PR labeled
  `lock:<path>` is the lock; a dependency-free CI guard template
  (`lock-guard.yml`) fails other PRs touching a locked path.
- `baron worktree add|list|remove` — the branch-per-persona worktree topology (one shared
  object store; migration runbook in [`docs/worktree-migration.md`](docs/worktree-migration.md)).
- `baron hydrate pydantic-ai` — emit a ready-to-edit bootstrap script for a persona on
  pydantic-ai; the working hydrator (`baron.runtimes.pydantic_ai.build_agent`) lives behind
  the pinned optional extra `barony[pydantic-ai]`.

```bash
uv tool install ./cli && baron --help
```

## Sister skill — `multi-agent-audit`

The other half of the kit: a **read-only audit skill** that grades multi-agent projects against an evidence-based rubric. Bootstrap **builds** projects; audit **grades** them.

| Property | Detail |
|---|---|
| **Location** | [`skills/multi-agent-audit/`](skills/multi-agent-audit/) |
| **Headline metric** | INTERVENTION TAX = human touches per autonomous task. High autonomy split + high tax = false win. |
| **Read-only** | Never modifies the audited project. Tool allow-list omits `Edit`; `Write` only for the report, outside the audited repos. |
| **Framework-neutral** | Works on Barony, CrewAI, LangGraph, AutoGen, Copilot agents, custom loops. |
| **Two-layer** | Universal WHAT-to-measure + per-layout WHERE-it-lives discovery (Step 0). |
| **Outputs** | Markdown report + self-contained HTML dashboard (Chart.js + horizontal SVG timeline) + 1 KB short-form executive summary (md or html) + machine-readable snapshot JSON for trend analysis. |
| **v1.3 enhancements** | Multi-substrate Agents lens (claim labels + handoffs + frontmatter, not just git log); snapshot `addenda:` field for revising shipped point-in-time records; weighted operational-fidelity option; 5 stdlib Python helpers (trend reader, timeline extractor, Brandes' betweenness centrality, coverage parsers, per-persona PR attribution); HTML renderer + short-form renderer; subagent-isolation smoke test + automated contract checker. |

Invoke via the bundled `project-auditor` subagent (`skills/multi-agent-audit/agents/project-auditor.md`) which enforces the read-only rule at the tool layer, or read `SKILL.md` directly from any runtime.

Full workflow: Discovery → Agent Inventory + DUAL-LENS drift pass → Metrics mining (platform, not just git) → 1–5 axis scoring → Markdown/HTML report → snapshot persistence (trend mode kicks in once ≥2 snapshots exist).

## Installation

```
/plugin install https://github.com/vggg/barony   # from GitHub
/plugin install /path/to/barony                  # from a local clone (e.g. for development)
```

> The `/plugin install` command syntax may evolve as Claude Code matures. If the above fails, check the [Claude Code docs](https://docs.anthropic.com/claude-code) for the current install command format.

> **On code-puppy?** It doesn't auto-discover the Claude skill format — see
> [`USING-WITH-CODE-PUPPY.md`](USING-WITH-CODE-PUPPY.md) for the invoke-by-file-path quickstart.

## Usage

After installation, tell your agent something like:

> "Use the barony skill to set up a new multi-agent project."

The skill routes through `START.md`: in a new/empty directory it follows `ORCHESTRATE.md`
(interviews you for project name, repos, backlog source, persona roster; authors
`manifest.yaml`; hydrates each persona via your runtime's adapter). In an existing collab
repo it follows `PARTICIPATE.md` (claim a persona, hydrate yourself, run the session ritual).

## Customisation

The archetype templates use `{{PLACEHOLDER}}` tokens for names, scopes, and identity — name
your personas whatever fits your working style. The structural patterns (three-tier write
ownership, capability allow/deny per persona, handoff protocol, COORDINATION.md as single
source for cross-agent rules) are what carry the value, not the names.

The reviewer/merger module and the CI lock guard are opt-in — small teams without contested
seams may not need them.

## Acknowledgements

This skill codifies a multi-agent coordination pattern developed through real iteration on
several software projects. The goal is to make the setup repeatable without requiring each
new project to rediscover the same structural decisions.

---

MIT License · [vggg](https://github.com/vggg)
