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

## Ritual-token coverage in the adapters' HYDRATE.md prose surfaces — DONE (plugin 1.10.0)

**Shipped.** Each prose adapter's ritual surface is now delimited by a `ritual-map:v1` fence
(open + close markers) and parsed by `tests/bi_runtime_accept.py` check (d). The token list comes
from the canon (`persona.schema.md`'s session-ritual table), and
`cli/tests/test_schemas.py::test_ritual_tokens_match_the_canon` joins `baron.schemas.RITUAL_TOKENS`
to that same table.

The join is the part that matters, and the first cut shipped without it: adding a token to
`RITUAL_TOKENS` plus both code renderers, without touching the canon, left all three prose
adapters uncovered while every suite stayed green — the guard was wired to one end of a contract
whose other end nothing checked. Caught in review. The chain now runs **code renderers ←
`RITUAL_TOKENS` ← canon → adapters** with no unjoined end.

The fence (rather than "scan to the next heading") is also load-bearing: without it, a prose
bullet mentioning a token *after* the surface was miscounted as a declaration, so a deleted entry
could be masked by a passing mention. Both failure modes are covered by mutation tests.

Nothing open.

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

**Update (2026-08-09, ADR-016) — step 1 landed; the loader is still open.**
"Mostly a loader" was wrong: the parsed form (`rules.CapabilityRules`) was a
flat record with one field per built-in rule, and a fixed field per rule cannot
hold an *additional* rule. The data was external; the shape was not extensible.
ADR-016 fixed the shape (a rule LIST of typed `CommandRule`/`PathRule` with
stable ids and a **closed** matcher set — the cheap/expensive split above, made
mechanical: command rules name their `matcher` in the document, and one outside
the closed set, or one other than the matcher guard implements for that rule, is
refused at parse time) and shipped `baron rules list|validate|diff|explain` as
the audit/diagnostic surface. The parser also refuses any rule or key it does
not implement rather than ignoring it — the property the loader will need most,
since a project rules file that is quietly half-applied is worse than none.
`guard.py` was byte-identical across the change.

The honesty label named above needed correcting in the same round: `enforced`
now means *guard mechanically checks it* and nothing else. `read_code` /
`read_collab` were briefly labelled `enforced` on the theory that a whole-tool
verb is enforced by tool omission — but the shipped pydantic-ai adapter builds
`FileSystem` unconditionally, so a persona denying `read_code` keeps its read
tools. They label `instructed`, gated by a test that hydrates such a persona and
inspects the toolset. When the loader lands, user rules inherit the same rule:
`enforced` only for shapes guard mechanically checks, measured rather than
argued.

Still open, and each is a one-way door (ADR-016 §5, needs its own ADR): the
`.baron/rules.yaml` loader itself, add-only/deny-only precedence, explicit
supported version ranges on *both* artifacts, refuse-don't-ignore on a malformed
project file, `load_rules()` cache safety once it is path-dependent, and the
`.baron/` (machine state) vs root-level `.baron-waivers.yaml` (human config)
convention collision. **Project-defined verbs are a separate, unmade decision**
(ADR-016 §6.1) — custom rules for existing verbs need no vocabulary change and
are the 90% case; do that first, if at all.

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
