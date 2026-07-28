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

## Worktree topology — repair commands (rest of baron M6)

**What (remaining):** the *tooling* shipped in v1.5.0 (`baron worktree add|list|remove`,
status sweep, [`docs/worktree-migration.md`](worktree-migration.md)); the **live migration**
of a real clone-per-persona workspace was executed on the pilot 2026-07-23 (see
[`STATUS.md`](../STATUS.md)). Still open: *repair* commands the migration showed are needed
(e.g. re-registering a moved worktree, `git worktree prune` wrapping).

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
- `RepoContext()` layering (auto-load an emitted `AGENTS.md`) is documented but not
  wired into `build_agent` — add it once field use shows it earns its prompt-cache cost.
- Pin bumps: the harness is 0.x with breaking minors allowed; on each bump of the
  `barony[pydantic-ai]` range, re-verify the `before_tool_execute`/`ModelRetry` veto
  seam and the `FileSystem.protected_patterns` read-only behavior (both are contract
  assumptions recorded in the ADR-004 addendum §4.2).

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

- **Clock override surface:** `baron.clock.set_clock` exists but has no CLI/env
  surface; seeding dated history needed a `sitecustomize` shim. Candidate:
  `BARON_NOW` env var (demos, backfills), documented as a testing seam.
- **`baron handoff create --body-file`** — findings/decisions have it; handoffs
  force a `--no-commit` + manual-append dance for any non-stub body.
- **`handoff close` commit prefix** is `baron:` rather than the closing
  persona's `commit_prefix` — off the discipline the templates preach; persona
  identity survives only via git author env. Decide and align.
- **Guard inference wording on remote-less repos:** every fresh local project
  sees "origin default branch undeterminable; `main` conservatively treated..."
  — correct, but consider a quieter first-run phrasing.
- **Document the `finding new --author X` vs git-author duality** (allocator vs
  proposer; e.g. librarian allocating for a write_path-restricted reviewer) —
  works as designed, currently undocumented.
