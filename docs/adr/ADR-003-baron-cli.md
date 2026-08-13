---
created: 2026-07-22
accepted: 2026-07-22
type: decision
status: accepted
decided_by: Vikram
adr: 003
project: barony
related:
  - "[[docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap]]"
  - "[[docs/adr/ADR-002-ways-of-working-2026-07]]"
---

# ADR-003: `baron` — a CLI that turns coordination conventions into mechanisms

| Field | Value |
|---|---|
| **Status** | Accepted (2026-07-22) |
| **Date** | 2026-07-22 |
| **Authors** | Vikram + Claude |
| **Supersedes** | — (extends ADR-001/ADR-002; Phase 2 of the roadmap) |
| **Evidence base** | `vggg/baddie-analyzer-collab` (2026-07-13 → 2026-07-22); GardenTwin `multi-agent-audit` results |
| **Decision owner** | Vikram |

## 1. Summary

ADR-002 promoted the July-2026 ways of working from project-local rules to framework
defaults — but they shipped as *conventions*: prose in `CONVENTIONS.md` / `COORDINATION.md`
that every persona must re-read, re-interpret, and manually obey. The field record says
convention alone is not enough:

- **F-number collisions ×3** on badminton-analyzer (F38/F39, F40/F41, F44/F45) — three
  independent times, two writers allocated the same finding number, because "the Librarian is
  the single writer" was a rule, not a mechanism (ADR-002 §2).
- **The 2026-07-22 triple-stranding incident**: an estate-wide assessment found the project's
  two most recent results stranded — one persona's commits never pushed, another's pushed
  branch never merged, and the canonical clone never pulled what origin already had — leaving
  the wiki/status board materially stale for a week
  (`_handoff/2026-07-22-owner-merge-recovery-f50-f51.md` in the collab repo).
- **Markdown LOCK commits**: the manual `_handoff/` lock protocol is itself race-prone — two
  personas grep, both see no lock, both claim (the ADR-002 §3 evidence).
- **Handoff rot**: 18 of 40 handoffs sitting `status: open` at assessment time, several
  weeks old, with no signal distinguishing "being worked" from "forgotten."
- **Enforcement theater**: the GardenTwin `multi-agent-audit` measured operational fidelity
  **0.53** — roughly half of the documented coordination protocol was actually being followed.
  Rules that depend on every session re-reading prose decay; nothing measured, nothing held.

**Decision:** ship a small CLI, **`baron`**, inside this repo (`cli/`), that mechanizes the
record-keeping and divergence-detection conventions. Milestones M1–M3 (validate, status,
ledgers/handoffs/index) land now; the worktree topology work is M6 (planned; pointer only in
§2.7).

## 2. Decisions

### §2.1 — The name: `baron`

Short, typeable, unclaimed on the relevant PATHs, and apt: the baron keeps the estate's
books — land registry, ledgers, disputes — without owning the work done on the land.
The console script is `baron`; the distribution is `baron-cli`. *(Distribution renamed to `barony` at v0.4.0 — see [ADR-005](ADR-005-naming.md); the console script and import package stay `baron`.)*

### §2.2 — The markdown/git substrate IS the database

`baron` is a **disciplined reader/writer over collab-repo files** — `manifest.yaml`,
`persona.yaml`, `findings/index.md`, `decisions/index.md`, `_handoff/*.md`,
`wiki/status.md`. It never introduces another store (no SQLite, no JSON sidecar caches, no
dotfile state), and every file it writes must remain fully human/agent-legible. This is the
load-bearing constraint of the whole framework: personas on any runtime — and humans — read
and write the same files with plain tools; `baron` merely makes the error-prone operations
mechanical. Structured output is a *view* (`--json`), never a second source of truth.
Machine-owned regions inside human files are explicitly marker-delimited
(`BEGIN/END BARON INDEX` in `_handoff/README.md`) so generation never eats prose.

> **SCOPED 2026-08-10 by [ADR-022](ADR-022-substrate-invariant-amended-default-not-only.md).**
> Product-vision invariant #1 now reads *git + markdown is the **DEFAULT** substrate; plugins
> may extend it to other suitable platforms* — bounded by **governance state stays complete in
> git**. This section is unchanged as it applies to `baron` itself: baron introduces no second
> store, and every governance fact stays answerable from the repo alone. What the amendment
> opens is an **out-of-tree plugin** authoritative for **derived or auxiliary** domains
> (semantic search, embeddings, cross-project recall) — never for authority, evidence, or the
> ledger. "It never introduces another store" above is a rule about **baron core**, and it
> still holds without qualification.

### §2.3 — Dependency policy: typer + pyyaml, nothing else

Runtime deps are **typer** (CLI surface) and **pyyaml** (the canon is YAML) only. No `rich`
(plain text tables; typer may pull rich transitively but `baron` never imports it), no
`gitpython` (git via `subprocess`, checked returns, captured output — the same git the
personas use), no `jsonschema` (the two schemas are small; validation is hand-rolled
declarative data in `cli/src/baron/schemas.py`, which also embeds the FROZEN 10-verb
vocabulary with a drift-guard test against `capability-vocab.v1.md`). `gh` is an accepted
*prerequisite* for forge features, invoked via subprocess — but **M1–M3 work with no `gh`
installed**. Python ≥ 3.10, src layout.

### §2.4 — Forge abstraction: a small Protocol; GitLab as a plugin (backlog)

`cli/src/baron/forge/` defines a small runtime-checkable `Protocol` (`base.py`:
`available` / `default_branch` / `open_pr` / `list_open_prs` — intent-level, mirroring the
capability vocabulary) with one built-in implementation, GitHub over `gh` subprocess
(`github.py`, a stub until a forge-consuming milestone). **GitLab is deliberately NOT
implemented**: it arrives as a separately-distributed plugin discovered via the
`baron.forges` Python entry-point group, selected by a `forge: gitlab` manifest key — design
sketch in [`docs/BACKLOG.md`](../BACKLOG.md). This keeps the core dependency-free of any
forge SDK and makes "add a forge" a distribution, not a fork — the same move ADR-001 made
for runtime adapters.

### §2.5 — Ledger ID allocation via push-retry

`baron finding new` / `baron decision new` parse the index for the max ID (both `### F<N>`
headings and `| F<N> |` table rows — real indexes carry both forms), allocate the next,
append a house-style entry, commit, push. **git's push atomicity is the lock**: on push
rejection, roll back the local commit, `pull --rebase`, re-parse, renumber, retry (bounded,
default 3). No LOCK files, no allocation service, no counter file — the exact failure class
of the three F-number collisions is closed by the same substrate that recorded it. Entry
dates come from one injectable clock function (testable). `--no-push` keeps offline work
possible; the retry loop simply runs on the next push.

### §2.6 — Handoff lifecycle: archive, never delete

`baron handoff close` flips `status: open → done`, adds a `closed:` date and optional
blockquote note, then `git mv`s the file to `_handoff/archive/YYYY/` — history preserved,
nothing deleted, directories stay listable (the 18/40-open experience showed the flat
directory becomes noise). Status edits are line-level textual operations so prose a persona
wrote is never reflowed. `baron index` regenerates the marker-delimited summary in
`_handoff/README.md` and verifies ledger numbering — **report-only**: duplicates are errors,
but gaps and out-of-order runs are reported, never renumbered (the badminton-analyzer index
faithfully preserves its historical gap; rewriting history to be tidy would forge the record).

### §2.7 — Worktree topology is M6 (pointer only)

`baron status` (M2) *detects* the stranding classes; *preventing* them with a
worktrees/branch-per-persona local topology (one shared object store, no per-clone drift) is
milestone M6 — planned, tracked in [`docs/BACKLOG.md`](../BACKLOG.md), out of this ADR's
scope. M2's optional `workspace.clones` / `workspace.worktrees_root` manifest fields
(manifest.schema.md v1.2) are forward-compatible with it.

## 3. Consequences

- Positive: every mechanism traces to a paid-for failure — collisions get a retry loop
  instead of a rule; stranding gets a red exit code instead of an estate-wide manual
  assessment; handoff rot gets an SLA check and an index; spec corruption gets `baron
  validate` in CI (mechanizing ADR-002 §5). The substrate stays exactly as ADR-001 designed
  it — plain markdown + git, no second store.
- Negative / costs: a real Python package in a hitherto stdlib-only repo (CI gains a uv job;
  the two stdlib test suites stay untouched); divergence checks are only as fresh as the last
  `--fetch`; the ledger-staleness check is a heuristic and is labeled as such in output.
- The capability vocabulary is untouched; `baron` consumes it read-only and drift-guards its
  embedded copy against the prose spec.

## 4. Decision record

- [x] Approved as written

**Notes (Vikram, 2026-07-22):** M1–M3 land with this ADR (`cli/`, see
[`cli/README.md`](../../cli/README.md)). M4+ (forge-consuming commands, lock guard
mechanization, worktree topology M6) are tracked in [`docs/BACKLOG.md`](../BACKLOG.md) and
`STATUS.md`.

## 5. Addendum (2026-07-23): M4/M5/M6-tooling + waivers decisions

Shipped with v1.5.0; recorded here because they execute this ADR's roadmap. The one
*contract*-changing decision — `baron guard` upgrading five sub-tool denials from
instructed to enforced on Claude Code — got its own record,
[ADR-004](ADR-004-baron-guard-enforcement.md), since it amends the enforceability-class
honesty boundary rather than just adding a mechanism.

- **§5.1 — Lock = the forge's PR state, nothing else (M5).** `baron lock claim|release|list`
  mechanizes ADR-002 §3: claim = draft PR labeled `lock:<path>` from a `lock/<slug>` branch
  carrying one empty commit (created via `git commit-tree` + push — never touching the local
  checkout; GitHub refuses a PR whose head equals its base, so the empty commit is
  load-bearing); release = close PR + delete branch; the open-PR list is the only query
  surface. Consistent with §2.2: no lock files, no state — the forge already holds the
  authoritative open/closed bit, exactly like §2.5 lets git's push atomicity hold the ID
  lock. The forge Protocol grew `create_branch`/`close_pr` + label-aware `open_pr`/
  `list_open_prs` (additive; plugins implementing the old surface miss only lock support).
  The CI side ships as a dependency-free template,
  `assets/collab-repo/.github/workflows/lock-guard.yml` (bash + `gh`), which fails any
  *other* PR touching a locked path — closing the §1 "markdown LOCK commits" race for real.
- **§5.2 — Worktree topology commands (M6 tooling).** `baron worktree add|list|remove`
  builds the §2.7 topology: one shared object store, branch `persona/<slug>`, worktrees
  under `workspace.worktrees_root` (manifest v1.2 — the M2 seam, consumed unchanged).
  `remove` refuses on dirt or unmerged commits unless `--force`, and NEVER deletes the
  persona branch — removing a working copy must not destroy history. `baron status` sweeps
  worktrees with the same checks as clones but runs the repo-wide branch sweep only once
  (worktrees share every local branch; sweeping per worktree would duplicate findings).
  Migration runbook: [`docs/worktree-migration.md`](../worktree-migration.md). The live
  migration of a real workspace is deliberately NOT part of this release.
- **§5.3 — Status waivers, expiry-honest.** `.baron-waivers.yaml` (collab root,
  human-legible YAML per §2.2) + `baron waiver add|list`: a waiver fnmatch-es the status
  SUBJECT column and downgrades matching reds to warn with the reason appended — parked
  work stays *visible*, just not alarm-red. Expiry is mandatory: an expired waiver stops
  matching (the red resurfaces) and is itself reported as a warn, so waivers cannot rot
  into permanent silence. Malformed entries are reported, never silently dropped — a
  waiver that doesn't parse must not hide a red.
