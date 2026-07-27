# v1 Self-Hosting Outcome Notes (ADR-001 §10.2)

> The empirical backbone the §10 plan promised: which capability verbs and schema fields
> **surfaced from observed need** (vs. designed up-front), **where the spec held**, **where it
> bent**, and **what was discarded as YAGNI**. Companion to [`LEARNINGS.md`](../../../docs/LEARNINGS.md)
> (the short lessons index) — this is the fuller writeup.
>
> **Provenance / honesty note:** this synthesizes the durable record — the capability-vocab
> Q-resolutions, the `persona.schema`/`manifest.schema` changelogs, the ADR's own gap analysis,
> and the dogfood PRs (#2, #4, #7, #8) — rather than a fresh replay of the Phase 2 session logs.
> Where the original sessions left no durable evidence for a claim, it isn't asserted here.

## Context

- **Phase 1** — adapter spike: prove one `persona.yaml` hydrates on more than one runtime
  (code-puppy first).
- **Phase 2** — self-hosting validation: code-puppy built the v1.0 implementation **on this very
  repo** (PRs #2, #4, #7, #8). The `tests/bi_runtime_accept.py` harness exercises the contract
  automatically; this doc is the qualitative companion to that automated gate.

## 1. Which verbs surfaced from observed need (not designed up-front)

The v1 vocabulary is **10 verbs** and stayed short by rule: *a verb enters v1.x only when a real
persona on a real task needed it* (`capability-vocab.v1.md` design rule 4; `LEARNINGS.md`
Proven #2). Concretely, the set was driven by the dev (Tess) and read-only reviewer (Rex)
personas actually run during the dogfood:

- `read_code` / `read_collab`, `write_code`, `write_path`, `open_pr`, `run_tests` — the working
  surface a dev persona exercised.
- `merge_pr`, `push_main`, `force_push`, `edit_other_personas` — appeared because they had to be
  **denied**; a deny is the same verb under `deny:`, not a separate `no_*` verb (design rule 3).

No verb was added speculatively. The read-only reviewer is what proved the *deny* side of the
contract carries real weight (it gains the most enforcement; see §4).

## 2. Where the spec held up well

- **Intent-level, not tool-level.** `open_pr` (never `gh_pr_create`) survived contact with two
  runtimes whose tools differ completely (code-puppy `agent_run_shell_command` vs. Claude `Bash`).
  The canon never had to name a runtime tool.
- **`code`/`collab` read split (Q2).** Observed use only ever needed two repos, and the repo name
  rode naturally on the verb (`read_code`/`read_collab`). A parametric `read(repo)` form would have
  been more vocabulary for no gain. **Kept as-is.**
- **`run_tests` as an intent verb (Q3).** Never exposing "run arbitrary shell" as a capability
  held up — the persona still needs the shell for git/gh, but the *vocabulary* stays intent-level.
- **Deny-as-guardrail.** The "what never happens" block earned its place — the `git add -A` /
  force-push / wrong-branch denials caught real mistakes even when only instructed (`LEARNINGS.md`
  L3).

## 3. Where it bent (changed under real use)

- **Path-scoped writes collapsed to one parametric verb (Q1).** The v0 draft had separate
  `write_findings`, `write_handoff`, `write_wiki` verbs. Phase 2 showed these are the **same
  capability at different path scopes**, so v1 collapsed them into `write_path: [<scope>...]`
  (scope is *data*, not vocabulary). This is the clearest "the spec bent toward what was observed"
  moment.
- **Transport coupling removed.** The v0 ritual token `pull_both_repos` assumed exactly two
  remote repos; it became `sync_repos` over `manifest.repos` so local-only and N-repo projects
  both work (`persona.schema` changelog).
- **Location independence (F7) and backlog source (F8).** Real use surfaced that baking absolute
  home paths and a hardcoded GitHub backlog broke portability/failover. The fixes —
  `paths.strategy: relative` and a configurable `backlog.source` — are structural, not cosmetic
  (`manifest.schema`).
- **Enforceability is a property of the runtime, not the capability** (`LEARNINGS.md` L2). The
  same verb is whole-tool-enforceable on a runtime that allow-lists tools and only
  instruction-enforceable on one that doesn't — the canon describes intent; the adapter decides
  how much the runtime can guarantee.

## 4. What was discarded as YAGNI

- **Separate `write_*` verbs** (`write_findings`/`write_handoff`/`write_wiki`) — folded into
  `write_path` (§3).
- **A "run shell" capability** — deliberately never added; it would defeat intent-level verbs (Q3).
- **A third repo axis / `read(repo)` parametric form** — not added; revisit only if a 3rd repo
  type actually appears (Q2).
- **Speculative archetypes / fields** — `persona.yaml` formalized only what the dogfood used; the
  archetype enum ships `dev` end-to-end and explicitly defers `librarian`/`autonomous-*` rather
  than pre-building them (see `persona.schema.md` "Archetype support").

## 5. Enforcement reality (don't oversell)

| Class | What the dogfood proved |
|---|---|
| **whole-tool** (deny all writes / all shell) | Genuinely enforceable where the runtime allow-lists tools — omit the tool and the action is impossible. Read-only personas gain the **most** (write+shell hard-denied). |
| **sub-tool** (allow `open_pr`, deny `merge_pr` — both ride one shell tool) | **Instruction-only**, at every tier. Dev personas gain the **least** enforcement because they need shell+write. Still valuable (L3), but the spec must say plainly what is enforced vs. instructed. |

This honesty boundary is identical across runtimes: code-puppy (`tools` JSON list) and Claude
Tier 3 (`.claude/agents/<slug>.md` `tools:` allow-list) enforce whole-tool denials; both render
sub-tool denials as persona-body instructions.

## 6. Known gaps surfaced (carried forward)

- **Cron / `/schedule` / failover has no universal equivalent** (ADR §6.1 / §7). The orchestrator
  emits failover runbooks + cron stubs but cannot guarantee a live scheduled runtime. Tracked as
  a v1.2+ candidate.
- **Claude enforcement was Tier-2-only at v1.0** (instructed). Closed in **v1.1** with Tier-3
  subagents (enforced `tools:` allow-list).
- **Archetype parity** — only `dev` hydrates end-to-end; `autonomous-*`/`librarian` remain legacy
  `AGENT.md` templates. v1.2+ candidate.

## See also

- [`LEARNINGS.md`](../../../docs/LEARNINGS.md) — short lessons index (L1–L3, Proven #1–#2).
- [`capability-vocab.v1.md`](capability-vocab.v1.md) — the frozen verb contract + Q-resolutions.
- [`persona.schema.md`](persona.schema.md) / [`manifest.schema.md`](manifest.schema.md) — schema changelogs (the F4/F7/F8 fixes).
- `docs/adr/ADR-001-...md` §10 — the execution plan this closes out.
