# Backlog — mechanisms (baron CLI, Phase 2+)

Deliberately deferred work with enough design recorded to pick up cold. Deferred
*candidates* (ideas without commitment) stay in `STATUS.md`; entries here are agreed
direction. See [ADR-003](adr/ADR-003-baron-cli.md) for the architecture these slot into.

## GitLab forge plugin (`baron-gitlab`)

**What:** a GitLab implementation of the forge Protocol, shipped as a *separate
distribution*, not in `baron` core. GitHub stays the only built-in.

**Design sketch:**

- Implements the same `Protocol` as `cli/src/baron/forge/base.py`
  (`name` / `available` / `default_branch` / `open_pr` / `list_open_prs`), backed by the
  `glab` CLI via subprocess — mirroring how `github.py` wraps `gh`. No GitLab SDK dep.
- Discovery via the Python entry-point group **`baron.forges`** (already wired: baron's own
  `get_forge()` resolves built-ins first, then scans the group). The plugin's
  `pyproject.toml` registers:

  ```toml
  [project.entry-points."baron.forges"]
  gitlab = "baron_gitlab:GitLabForge"
  ```

- Selection: an optional manifest key `forge: gitlab` (default `github`); forge-consuming
  commands pass it to `get_forge()`. The key is additive to `manifest.schema.md` and ignored
  by everything that doesn't consume forges.
- Unavailable tooling (`glab` not installed) raises the same `ForgeUnavailable` with an
  actionable message; non-forge commands are never affected.

**Why deferred:** no field forcing function yet — every real project to date is on GitHub
(single-account constraint, ADR-002 §1). Same rule as runtime adapters: add when a real
project on that forge exists.

## Worktree topology — repair commands (rest of baron M6) — DONE (barony 0.5.5)

**Shipped:** the base *tooling* landed in v1.5.0 (`baron worktree add|list|remove`, status
sweep, [`docs/worktree-migration.md`](worktree-migration.md)); the **live migration** of a
real clone-per-persona workspace ran on the pilot 2026-07-23 (see [`STATUS.md`](../STATUS.md));
the *repair* commands that migration showed were needed shipped in **barony 0.5.5**:
`baron worktree prune` (wraps `git worktree prune [-n]` — clears stale `.git/worktrees/`
registrations for moved/deleted dirs) and `baron worktree repair [PATH…]` (wraps
`git worktree repair` — re-registers a moved worktree / main repo). Nothing open.

## Ritual-token coverage in the adapters' HYDRATE.md prose surfaces (post-ADR-008)

**What:** `check_review_feedback` (ADR-008 §2) shipped to three of four runtimes on its first
cut, because each renderer keeps its own ritual-token surface and nothing cross-checked them against
`schemas.RITUAL_TOKENS`. Caught in review. The fix that landed guards the two **code**
renderers (`scaffold._ritual_lines`, `runtimes.pydantic_ai._RITUAL_LINES`); the claude /
code-puppy / generic adapters render from **prose in their `HYDRATE.md`** (two pipe tables and
one bullet list), and no test parses those. A future token can still be added to the vocabulary
and miss all three silently — and silently in two different ways: the code renderers fall back
to echoing the raw token, while the prose surfaces have no fallback at all, so an absent row is
simply not there. Neither path raises.

**Design sketch:** extend `tests/bi_runtime_accept.py` with a second parse pass — it already
reads the adapters' machine-readable capability maps, so it is the natural home — asserting
every `RITUAL_TOKENS` entry appears in each prose-rendered adapter's ritual surface. Needs those
surfaces to be machine-readable first: they are markdown today, in two shapes — two `|`-tables
(claude, code-puppy) and one bullet list (generic). Either normalize those two shapes, or give
the ritual surface the same explicit machine-readable fence the capability maps use.

**Why deferred:** the acceptance harness is stdlib-only and deliberately parses *declared*
contracts, not prose; making the ritual surfaces machine-readable is a small spec change to three
adapters that deserves its own PR rather than being improvised inside the change that exposed
the gap.

## Merger precondition verification (baron, forge-consuming)

**What:** ADR-002 §4 mechanized: a baron subcommand the Merger persona (or CI) runs
against a PR — verifies CI green on the *current* head SHA plus a SHA-bound
`REVIEW:PASS <sha>` comment naming that same head, record obligations, and no lock
collision — and merges or refuses naming the failed precondition. The forge Protocol
(post-M5: `list_open_prs` with labels/author, `close_pr`, `create_branch`) plus a
PR-comment query are the seam. Also still open from the original M4+ sketch:
`baron handoff` PR-awareness (is a lock-holding PR still open?).

## Guard coverage growth (baron guard, post-ADR-004)

**What:** deliberately out of the v1.5.0/v1.6.0 guard: `open_pr`/`run_tests` denial
parsing (rarely denied in practice; add on observed need per the vocabulary's rule 4 —
any addition now lands in `capability-rules.v1.yaml` with a `rules_version` bump, and
every consumer picks it up), hook seams for further runtimes (pydantic-ai got its
in-process seam in v1.6.0 — `AbstractCapability.before_tool_execute`; code-puppy still
has no PreToolUse equivalent today), and the lock soft-timeout sweep
(`COORDINATION.md` names a 24h soft timeout; `baron lock list` shows age — flagging
expiry candidates could fold into `baron status`).

## pydantic-ai adapter — field validation + follow-ups (post-v1.6.0)

**What:** the adapter shipped test-proven offline (TestModel/FunctionModel); ADR-001's
acceptance bar for an adapter is a REAL project on the runtime. Still open:

- Run a real persona on a real project via `build_agent` (the ADR-001 §10 step-2 analog);
  fold observed needs back into `capability-rules.v1.yaml` / the HYDRATE.md.
- ~~`RepoContext()` layering (auto-load an emitted `AGENTS.md`)~~ — **wired into
  `build_agent` in 0.5.4** (added when a `collab_root` is passed, clean fallback if the
  installed harness lacks it).
- Pin bumps: the harness is 0.x with breaking minors allowed; on each bump of the
  `barony[pydantic-ai]` range, re-verify the `before_tool_execute`/`ModelRetry` veto
  seam and the `FileSystem.protected_patterns` read-only behavior (both are contract
  assumptions recorded in the ADR-004 addendum §4.2).
- **Session-ritual driver — RESOLVED in [ADR-007](adr/ADR-007-session-boundary.md):**
  no driver; thin session primitives shipped (0.5.6); runtime-specific capability wrappers
  = build-on-demand. Barony does not own the agent execution loop (orchestration is the
  runtime's job); `baron session start/end` mechanize only the git/markdown bookkeeping of
  the ritual, opt-in and runtime-neutral. A pydantic-ai capability / Claude Code hook / cron
  driver MAY wrap them, but Barony ships only the CLI — wrappers are built on demand.

## Consciously deferred inside M1–M3

- **`baron validate` does not resolve `manifest.personas[].spec` paths** to validate the
  referenced persona files in one pass — run validate over the directory instead.
- **`baron status` reads local git state only** (plus `--fetch`); it does not query the
  forge for open PRs / unmerged remote branches with no local ref.
- **`baron index` summarizes `_handoff/` only**; findings/decisions get numbering
  verification, not a regenerated table of contents (the index files are human-authored
  surfaces — see ADR-003 §2.2).
- **Handoff `updated:`-field maintenance** on close is not touched; only `status`/`closed:`
  are edited, textually.

> The **`baron status` waivers** entry that lived here (surfaced by the first pilot
> triage, 2026-07-23) shipped in v1.5.0 as `.baron-waivers.yaml` + `baron waiver add|list`
> — see `cli/README.md`.

## From the demo-seeding stranger test (2026-07-27, [`barony-demo`](https://github.com/vggg/barony-demo))

> **All five items below shipped in `barony` 0.5.4** (2026-07-28 interop
> hardening + backlog burndown — see `CHANGELOG.md`):
>
> - ~~**Clock override surface**~~ → `BARON_NOW` env var honored by the default
>   clock (ISO date/datetime), documented as a testing/backfill seam.
> - ~~**`baron handoff create --body-file`**~~ → added; body-file content lands
>   under the frontmatter (parity with findings/decisions).
> - ~~**`handoff close` commit prefix**~~ → `baron handoff close --as <slug>`
>   attributes the close commit as `<slug>:` (default stays `baron:`).
> - ~~**Guard inference wording on remote-less repos**~~ → reworded to a calmer,
>   still-honest first-run phrasing.
> - ~~**`finding new --author X` vs git-author duality**~~ → documented in
>   `cli/README.md` + the `--author` command help (allocator vs proposer).

## Considered directions — from launch Q&A (2026-07-28, LinkedIn thread w/ a staff/SRE reviewer)

### User-extensible guard rules (project-level custom enforcement)
Today `baron guard` enforces the frozen 10-verb vocabulary via the packaged
`capability-rules.v1.yaml`; each rule's `detection` is one of a fixed set of
modalities (`command` = git/gh command-pattern, `file-op` = path scope), hand-
implemented in `guard.py`. There is no project-level custom-rules file — a user
can *express* any constraint in `CONVENTIONS.md`/`COORDINATION.md`/persona
`scope` (instructed tier), but cannot add a new *deterministically enforced*
rule from config.

- **Cheap (natural next step):** a project-level `.baron/rules.*` (or a manifest
  block) that guard loads *in addition to* the packaged rules, for the **existing
  modalities** — extra command patterns and path scopes a team wants blocked.
  The rules are already externalized data; this is mostly a loader + merge + a
  precedence/validation story, no new detection code. Keep the honesty label:
  user rules are still `enforced` only for the shapes guard can mechanically check.
- **Expensive (needs new detection code):** new modalities — file size, time
  windows, rate/turn limits, anything semantic ("small tasks only"). Each is a
  new matcher in `guard.py`, not a config line. Gate on observed need
  (vocabulary design rule 4), same as the core verbs.

### Centralized cross-project memory substrate
Within a project the collab repo already *is* the shared memory substrate
(findings/decisions/wiki/handoffs in git+markdown). Extending to a **centralized,
cross-project** memory (the Irisidian-vault pattern, productized) is coherent
because the substrate is plain git+markdown — but it is a distinct product
surface, not a free consequence, and depends on gaps we already track:

- **Memory lifecycle** — ledgers/handoffs are append-only and grow unbounded;
  centralizing compounds it. Needs an archive tier + retention story (already a
  known gap).
- **Retrieval at scale** — today it's grep + a human-curated wiki; cross-project
  central memory wants indexing / semantic search.
- **Single-writer reconciliation** — the librarian model that keeps one project's
  memory coherent strains under many projects writing one substrate; needs a
  scoping/namespacing + reconciliation story.

Positioning note: this is Phase-3/4 territory and overlaps the per-agent Memory
capability some runtimes ship (e.g. pydantic-ai-harness) — but those are
in-process/per-agent/private; Barony's differentiator is shared, human-legible,
git-audited memory. Build only on real demand.

## From the 2026-08-02 scope + product-vision synthesis

Five independent reviews (research/architect/PM scope-discipline pass + architect/PM
product-vision pass — vault `projects/AgentBootstrapNasikoMix/2026-08-02-synthesis-plan.md`) added
the entries below. Actionable near-term items moved to `AGENT-TASKS.md` P2 (2.0, 2.6, 2.7) instead
of here; what's below is genuinely build-gated or paid-tier.

### Verified per-persona identity + `baron join`

**What:** per-persona GitHub App installation / bot-account provisioning in `init`/`join`,
attributable commits and PRs, signed commits as the light path. Unlocks `AGENT-TASKS.md` 2.2's
credential half (branch protection only binds if personas hold distinct credentials) and provable
two-party review (an App can't approve its own PR — verified live on the pilot: "Can not approve
your own pull request").

**Build vs integrate:** integrate GitHub Apps + git signing; do not build a credential
issuance/attestation service. Adopt A2A Agent-Card vocabulary as the naming north star only.

**Why deferred:** genuinely disputed sequencing, not just low priority — see `AGENT-TASKS.md`'s
open-decision callout after 2.7. The architect review wants this built first; the PM review wants
it design-only until a real second operator exists. Sits here, not in `AGENT-TASKS.md`, until the
owner resolves the fork; the design is ready to pick up cold either way.

### Delivered-value ledger (PM product-vision D3 — novel, no market equivalent)

**What:** track shipped capabilities as first-class ledger objects ("what exists and works"),
hydrated at session start alongside direction, so fleets stop rebuilding what already shipped.

**Evidence:** the pilot's D56/D57 root cause — "shipped wins generate no tickets," so a dozen PRs
rebuilt a parked path while an already-shipped capability (the VLM path) sat invisible. Not named
by either scope review or the original competitive study; the PM's read is that no product in any
adjacent segment addresses this.

**Build:** thin — a `delivered/` ledger + `status` surfacing, same mechanism family as `baron
decision` (`AGENT-TASKS.md` 2.1). Sequence as v2 of decision durability, after 2.1 ships.

### Ledger search / retrieval at scale

**What:** `baron search` over findings/decisions/handoffs/wiki — structured grep + frontmatter
filters first; embeddings only on demand.

**Why deferred:** retrieval today is grep + a hand-curated `wiki/` and it works at 57 findings
because the librarian is diligent — not a scalable property, but not needed for adopter #1 either.
Build before the 10-team stage, not before.

### Hosted fleet dashboard (the paid anchor)

**What:** a hosted **read-only cache** over N collab repos — intervention-tax / operational-fidelity
trends, drift scorecards, and the attention view as a product screen ("60 open handoffs, oldest 17d,
3 personas stalled"). Rebuildable from clones (never a store); integrate Langfuse/Phoenix for the
trace layer, own only the git+review-event metrics no tracer sees.

**Why deferred:** demand-gated by design — paid tier, build when an org buyer asks the cross-team
question. Depends on verified identity (above) and a remote/`--fetch`-based `status` sweep (today
`status` reads local git state only).

### Compliance-grade audit export (paid tier, not a rules engine)

**What:** export the ledger + audit scores as an evidence pack mapped, where honest, to EU-AI-Act
Art. 12 / SOC-2 change-management *evidence categories* — "your repo is the evidence," not a
citation engine painted onto `capability-rules.v1.yaml`.

**Where this differs from the original competitive study:** the study recommended leaning into
OWASP/CWE/EU-AI-Act rule citations now. Both the PM and architect scope reviews reject that — on a
solo, zero-adopter project it "reads as costume" and enters the GRC/Credo category Barony should
cede outright. This entry replaces that recommendation: a paid export artifact, sold only once a
real org buyer exists, never a rules/citation feature shipped speculatively.
