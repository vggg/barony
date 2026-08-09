# STATUS — Barony

Tracks current progress and deferred candidates. Update on every PR that ships a step (per
`CONTRIBUTING.md`). Full release history lives in `CHANGELOG.md`; the v0→v1 migration story
lives in [`docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md`](docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md).

## P1 — pilot hardening promoted into the canonical templates — COMPLETE (unreleased)

The ordered queue is [`AGENT-TASKS.md`](AGENT-TASKS.md). `baron init` flows one-way
(Barony → new projects), so hardening that lived only in the pilot's collab repo reached
no new adopter. Promoted per [ADR-008](docs/adr/ADR-008-ways-of-working-2026-07-31.md),
the same mechanism ADR-002 used. Ships in the pending **plugin 1.9.0 + CLI 0.6.0** bundle.

- [x] **P1.1 — `CONVENTIONS.md` template: `label-is-not-evidence` + `Decision & ADR
  intake`.** Label = index, verdict-comment-at-head-SHA = record, checked in *both*
  directions (approval and block); the Librarian RECORDS **and RECONCILES** the work-pull
  surfaces a decision contradicts.
- [x] **P1.2 — `check_review_feedback` session-ritual token** (persona schema v1.2), in the
  `__DEV__` ritual ordered before `check_backlog`; mapped in the three prose-rendered adapters
  **and** the pydantic-ai hydrator (which renders in code), rendered by the `baron init`
  runtime kits, added to baron's `RITUAL_TOKENS`, with a drift guard covering the two **code**
  renderers (the `baron init` kits + the pydantic-ai hydrator). Additive. *(At 1.9.0 the three
  adapters' prose surfaces were still ungated; that gap closed in **1.10.0** — see below.)*
- [x] **P1.3 — Reviewer/Merger templates hardened.** Verdict format as a parsed contract +
  new-verdict-on-re-review + labels-follow-the-verdict (Reviewer); *a label is never an
  input to the merge decision* (Merger). `COORDINATION.md § Review and merge` updated.
- [x] **P1.4 — `.github/workflows/strip-stale-verdict.yml`** emitted by `baron init`
  alongside `lock-guard.yml`; owner gates excluded; dependency-free; carries the
  lock-guard-style honest limitation.
- [x] **P1.5 — [ADR-008](docs/adr/ADR-008-ways-of-working-2026-07-31.md)** recording the
  fold-in, with the ADR citations backfilled into the templates.

Remaining before release: the vault handoff to Iris, then the release workflow.

> **Release-tagging gap (noticed 2026-07-31, unrelated to P1).** `CHANGELOG.md` and the
> Shipped table record v1.4.0 → v1.8.x, but the newest tag on `origin` is **v1.3.0** — the
> tag / `gh release create` steps of the release workflow have not run since. Reconcile
> before or with the next release, or the tag history stops matching the record.

## Shipped (unreleased) — ritual-token coverage guard (plugin 1.10.0)

Closes the `docs/BACKLOG.md` gap from the 1.9.0 cycle: the three prose adapter surfaces now
carry a `ritual-map:v1` marker and `tests/bi_runtime_accept.py` parses it, so a ritual token
can no longer reach some runtimes and not others. Token list sourced from the **canon**
(`persona.schema.md`), not from baron — the harness runs without baron installed. Verified by
mutation: deleting one token from one adapter fails the harness naming both.

## Shipped (unreleased) — P2.3 `baron validate` spec↔runtime drift

`barony` **0.7.0**. `baron validate` compares the personas a project declares against the
agents its runtime has registered. **The signal is partial registration:** some registered
and others not is evidence the project hydrates agents here, so the gaps are errors;
all-or-nothing is silent (correct for Tier-2, Tier-1, and a fresh scaffold). Explicit
`tier: 2` is skipped at both the manifest and per-persona level; **`tier: auto` is treated as
Tier 3 — a judgement call, not a sidestep** (under `auto` HYDRATE.md permits per-persona
degradation, which baron cannot distinguish statically from drift), with an escape hatch named
in the error message. Only
runtimes declared in `manifest.adapters` are checked; `--no-runtime-drift` opts out.
Verified both ways against real repos: reports exactly `terrence`/`carson` on the pilot, and
a fresh `baron init` scaffold validates clean.

## Shipped (unreleased) — externalizable capability rules, step 1 (ADR-016)

The enabling refactor for project-level custom guard rules, plus the audit surface.
`rules.CapabilityRules` was a flat record with one field per built-in rule, which
**structurally cannot hold an additional rule** — so the BACKLOG's "mostly a loader" was
wrong about the blocker. It is now a rule LIST (`CommandRule`/`PathRule`, stable ids, a
**closed** matcher set that refuses an unenforceable rule at parse time, `source`
provenance), with every legacy accessor preserved as a derived property; `guard.py` and
`runtimes/pydantic_ai.py` are **byte-identical** across the change. New
`baron rules list|validate|diff|explain` (all `--json`): `list` labels enforcement in three
honest states (`guard` / `tool-omission` = the adapter's, not guard's / `instructed`), and
`explain` is a dry run of the real evaluators with a test pinning its verdict to
`guard.evaluate_bash`'s `Decision`.

**Not shipped:** the `.baron/rules.yaml` loader. `validate --file` parses a candidate but
does not activate it — baron still loads packaged rules only. The one-way doors
(add-only/deny-only precedence, supported ranges on both artifacts, refuse-don't-ignore,
cache safety, the `.baron/` vs root-config convention collision) and the separable
project-defined-verbs question are recorded in ADR-016 §5–§6 for their own ADR.

## Parked after owner review — P2.1 `baron decision` design

[ADR-009](docs/adr/ADR-009-baron-decision-reconciliation.md) (**proposed**, no code) designs the
FM6/D57 mechanism ADR-008 §4 named: a ratified decision must reach the work-pull surfaces, not
just `decisions/`. Boundary held from ADR-007 — baron never infers *what* a decision
contradicts; the surfaces are declared input and baron verifies **discharge**. `baron status`
gains a `decision-unreconciled` red. **Owner review 2026-08-02:** the `park_label` read-side
change is **accepted** (§3.2 stands — a park discharges only when an agent's backlog query stops
returning the item), and **P2.3 is built first** (smaller, no schema change). Q1/Q3/Q4 stay open;
this is parked, not rejected.

## In progress — Phase 2: conventions → mechanisms (baron CLI)

Per [ADR-003](docs/adr/ADR-003-baron-cli.md) / [ADR-004](docs/adr/ADR-004-baron-guard-enforcement.md):
the coordination conventions ADR-002 promoted are being mechanized as the `baron` CLI
(`cli/`, typer+pyyaml core; the pydantic-ai runtime adapter is a pinned optional extra).
M1–M6-tooling + waivers shipped in **v1.5.0**; the rules artifact + pydantic-ai adapter
in **v1.6.0**; `baron init` (the deterministic scaffold, ADR-006) in **v1.8.0**; remaining:

- [x] **Live worktree migration of the pilot workspace** — executed 2026-07-23 on
  BaddieAnalyzer (per-worktree identities, symlink pattern, old clones parked;
  `baron status` 0-red on the new topology). The runbook's identity + symlink steps
  came out of this run.
- [x] **multi-agent-audit telemetry mode (v1.4)** — OTel trace-export ingestion
  (Claude Code / Logfire / Phoenix export files; stdlib-only, files-only) with
  source-tagged snapshot merge; artifact-based audit remains the zero-infra default.
- [ ] **Phase-gate audit** — re-run `multi-agent-audit` against the pilot with guard/lock
  live, to measure whether operational fidelity moves off 0.53 now that the rules are
  mechanisms.
- [ ] **Merger precondition verification** + guard coverage growth — `docs/BACKLOG.md`.
- [ ] **pydantic-ai adapter field validation** — the adapter is test-proven offline
  (v1.6.0); running a real persona on a real project on this runtime is the ADR-001
  acceptance bar for any adapter — `docs/BACKLOG.md`.

## Shipped

| Version | Date | Summary (details in `CHANGELOG.md`) |
|---|---|---|
| **CLI 0.5.6** + plugin **1.8.2** (unreleased bundle) | 2026-07-28 | Session boundary ([ADR-007](docs/adr/ADR-007-session-boundary.md)) from the pydantic-ai interop eval (enforcement solid, orchestration manual): **no `baron run` driver** — Barony does not own the agent execution loop (orchestration is the runtime's job) — **plus** thin, optional session-ritual bookkeeping primitives `baron session start` (optional `git pull --ff-only`; open handoffs + conventions pointer + backlog location) and `baron session end` (regenerate the handoff index; commit dirty `_handoff/ findings/ decisions/ wiki/` by path with the persona prefix; `baron status` divergence check, exit 1 on red). Bookkeeping only — no agent loop, no model calls; opt-in; not new capability verbs (compose `status`/`handoff`/`indexer`/`gitutil`). pydantic-ai HYDRATE.md gains an optional "composing the session ritual" note (1.8.2; vendored copy re-synced). |
| **CLI 0.5.4–0.5.5** + plugin **1.8.1** (unreleased bundle) | 2026-07-28 | **0.5.5:** worktree repair commands (rest of baron M6) — `baron worktree prune [--dry-run]` (wraps `git worktree prune`, clears stale `.git/worktrees/` registrations) + `baron worktree repair [PATH…]` (wraps `git worktree repair`, re-registers a moved worktree/main repo); both admin-only, non-destructive to history. **0.5.4:** interop hardening + backlog burndown from a pydantic-ai dogfood: least-privilege Shell (test-only personas get an allowlisted shell; broad shells deny redirect/pipe operators), guard denies out-of-root writes itself, `RepoContext` wired, `bash -c`/`sh -c` bypass honesty made prominent; `handoff create --body-file`, `handoff close --as`, `BARON_NOW` clock seam, `--author`-vs-git-author docs, version-string fixes. |
| **v1.8.0** | 2026-07-27 | The stranger release — `baron init` (CLI 0.5.0, [ADR-006](docs/adr/ADR-006-baron-init-template-packaging.md)): deterministic collab-repo scaffold + per-persona runtime kits from templates vendored as package data (drift-guarded), self-validated; quickstarts rewritten from a verified bare-venv run. |
| v1.7.0 | 2026-07-27 | The Barony release — the project renamed from `agent-project-bootstrap` to **Barony** (repo `vggg/barony`, plugin/skill `barony`, PyPI distribution `barony` at CLI 0.4.0; the CLI command stays `baron`). [ADR-005](docs/adr/ADR-005-naming.md). |
| v1.6.0 | 2026-07-23 | Capability-rules artifact (`capability-rules.v1.yaml`, single policy source for guard + adapters) + AGENTS.md emission (generic adapter) + the pydantic-ai runtime adapter (4th runtime; sub-tool denials natively enforced in-process) with working hydrator, `baron hydrate pydantic-ai`, and the `barony[pydantic-ai]` extra. See below. |
| v1.5.0 | 2026-07-23 | baron CLI: M1–M3 (validate/status/ledgers-handoffs-index, first released here) + M4 `baron guard` PreToolUse enforcement (ADR-004) + M5 `baron lock` PR-as-lock + lock-guard CI template + M6 worktree tooling + status waivers. |
| v1.4.0 | 2026-07-22 | One front door + legacy quarantine + July-2026 ways-of-working (ADR-002) + archetype parity + real CI. |
| v1.3.0 | 2026-06-12 | `multi-agent-audit` v1.3 — closed all 13 first-real-audit findings + timeline feature. |
| v1.2.0 | 2026-06-12 | `multi-agent-audit` sister skill + `project-auditor` subagent. |
| v1.1.x | 2026-06-04/08 | Claude Tier-3 subagent rendering; docs reconciled to the runtime-agnostic architecture. |
| v1.0.x | 2026-06-03 | The runtime-agnostic milestone (ADR-001 §10 executed; all close-out items done). |

## v1.8.0 — shipped 2026-07-27

The stranger release (`baron init`, ADR-006): a stranger with a laptop reaches a
working, validated project in minutes.

- [x] **`baron init`** — deterministic scaffold: canonical layout, filled
  CONVENTIONS/COORDINATION, schema-conformant manifest, canon/ + adapters/ verbatim,
  hydrated persona.yaml per archetype:slug (librarian renameable), genesis handoff,
  ledger index headers, wiki stub, lock-guard template; self-validated (0 errors)
  then `git init -b main` + a first commit of exactly the files written; refuses a
  non-empty dir; `--no-git`; injectable clock throughout.
- [x] **Runtime kits** (`agents/<slug>/runtime/`) — claude: Tier-2 CLAUDE.md +
  `baron guard` hook settings; generic/code-puppy: Tier-1 AGENTS.md; pydantic-ai:
  agent_setup.py. Tier-3 + scope prose stay conversational (kits say so).
- [x] **Template packaging** — skill tree stays canonical; byte-identical vendored
  copy as package data (`cli/src/baron/data/templates/`, `cli/scripts/sync_templates.py`);
  CI drift guard `cli/tests/test_template_sync.py`.
- [x] **Verified quickstarts** — README + cli/README rewritten from a bare-venv
  wheel-install run (init → validate → status → ledger/handoff/index → worktree →
  guard smoke), all five suites green.

## v1.6.0 — shipped 2026-07-23

The fourth-runtime release (rules artifact + AGENTS.md emission + pydantic-ai adapter;
ADR-004 §4 addendum).

- [x] **capability-rules.v1.yaml** — the verb→enforcement rule table externalized as
  versioned baron package data (`cli/src/baron/data/`, loader `baron/rules.py`); guard
  refactored to consume it with identical behavior (19 guard tests unchanged); new
  `test_rules.py` (verb set ≡ frozen vocabulary; guard follows the data; fail-closed);
  prose contract in `references/capability-rules.md`.
- [x] **AGENTS.md emission** — generic adapter Tier-1 hydration emits a
  generated-do-not-hand-edit `AGENTS.md` (identity, grants AND denials imperative,
  ritual, collab pointers; honest instructed-only note); claude adapter notes CLAUDE.md
  stays native, AGENTS.md optional/additive.
- [x] **pydantic-ai adapter** — `adapters/pydantic-ai/HYDRATE.md` (capability-map:v1,
  all 10 verbs; five guard-covered sub-tool rows natively `enforced` via in-process
  interception; whole-tool via capability omission); working hydrator
  `baron.runtimes.pydantic_ai.build_agent`; `baron hydrate pydantic-ai`;
  `barony[pydantic-ai]` extra pinned to the verified versions (harness 0.10.0 /
  slim 2.16.0); offline tests (TestModel/FunctionModel, no keys);
  `tests/bi_runtime_accept.py` sweeps 4 adapters with tightened tier rules.

## v1.5.0 — shipped 2026-07-23

The mechanisms release (baron, ADR-003/ADR-004). The M1–M3 block had been pushed
unreleased on 2026-07-22; v1.5.0 is its first released version (noted honestly in
`CHANGELOG.md`).

- [x] **M1 `baron validate`** — schema validation for persona.yaml/manifest.yaml; frozen
  10-verb vocabulary embedded + drift-guarded against `capability-vocab.v1.md`.
- [x] **M2 `baron status`** — divergence/staleness report (the 2026-07-22 stranding classes,
  handoff SLA, ledger/wiki staleness); `workspace.*` manifest fields (schema v1.2).
- [x] **M3 ledgers/handoffs/index** — push-retry F/D allocation, handoff lifecycle with
  archive-not-delete, marker-delimited `_handoff/README.md` index.
- [x] **M4 `baron guard`** (ADR-004) — deterministic capability enforcement as a Claude Code
  PreToolUse hook; five sub-tool denials upgrade to `enforced-with-baron (instructed
  otherwise)` in the Claude adapter; fail-closed with the tracked-override escape hatch.
- [x] **M5 `baron lock`** — PR-as-lock (claim/release/list) over the extended Forge
  Protocol + the dependency-free `lock-guard.yml` CI template; COORDINATION.md template
  names the concrete commands.
- [x] **M6 tooling `baron worktree`** — add/list/remove + status sweep +
  `docs/worktree-migration.md` (live migration not part of the v1.5.0 *tooling*
  release; it was later executed on the pilot 2026-07-23 — see the In-progress list).
- [x] **Status waivers** — `.baron-waivers.yaml` + `baron waiver add|list`; red→warn with
  reason, expiry-honest (expired waivers resurface the red and warn on their own).

## v1.4.0 — shipped 2026-07-22

The credibility-debt release: one front door, honest artifacts, real tests.

- [x] **One front door.** `SKILL.md` is now a thin router to `assets/collab-repo/START.md`
  (→ `ORCHESTRATE.md` / `PARTICIPATE.md`). The legacy v0.3 emit path (`vault-project` +
  `workspaces` templates, three-mode emit instructions) is quarantined in `legacy/` —
  deprecated, unmaintained, kept for existing projects.
- [x] **Version coherence.** `plugin.json` ≡ `SKILL.md` frontmatter (1.4.0), enforced by
  `tests/lint_repo.py`; stale "v1.0 shipped" meta-docs corrected.
- [x] **Archetype parity (closes the ADR-001 §10.8 deferred item).** `persona.yaml` templates
  now exist for `librarian`, `__AUTONOMOUS_EVENT__`, and `__AUTONOMOUS_CRON__` alongside
  their `AGENT.md`s; `persona.schema.md`'s legacy-only caveat removed.
- [x] **Missing artifacts.** `assets/collab-repo/manifest.example.yaml` (worked example);
  `__DEV__/persona.yaml` is a real `{{...}}` template (was a verbatim copy of the tess test
  fixture); `docs/notes/{CORRECTION-wibey-vs-codepuppy,code-puppy-capability-map}.md`
  reconstructed so the spec's citations resolve.
- [x] **July-2026 ways-of-working (ADR-002).** Single-account constraint as first principle;
  "everything material gets a handoff"; lock-via-open-PR + CI guard (not CODEOWNERS);
  adversarial Reviewer + Merger persona templates (`__REVIEWER__`, `__MERGER__`) with
  SHA-bound verdicts; persona.yaml CI validation; machine-local agent-state convention.
  Folded into the emitted `CONVENTIONS.md` / `COORDINATION.md`.
- [x] **Real tests + CI.** `tests/bi_runtime_accept.py` now parses the adapters' actual
  machine-readable capability maps (was a tautological Python re-implementation);
  `tests/lint_repo.py` (placeholders, dead links, fixture leaks, version sync);
  `.github/workflows/ci.yml` runs both with plain python on push + PR.

## Deferred candidates

### barony (bootstrap skill + baron CLI)

- **Native code-puppy skill packaging.** code-puppy doesn't auto-discover the Claude
  `SKILL.md` format, so it's invoked by file path today (`USING-WITH-CODE-PUPPY.md`).
- **Cron / failover live wiring.** The templates emit cron stubs and failover runbooks but
  don't wire schedulers automatically; cross-runtime cron auto-registration is real
  engineering work.
- **Additional adapters** — Codex, Wibey, etc. Add when there's a forcing function (a real
  project on that runtime).
- **Template CI emission.** ADR-002 §3/§5 describe the lock-guard Action and persona.yaml
  validation a bootstrapped project should run; ORCHESTRATE could emit a ready-made
  `.github/workflows/` for them.
- **Vault-project modernization.** The lean personal-vault pattern now lives only in
  `legacy/`; if demand returns, re-derive it on the runtime-agnostic architecture rather
  than reviving the v0.3 rails.

### multi-agent-audit

- **Per-runtime adapter docs** for non-bootstrap layouts (CrewAI / LangGraph / AutoGen /
  Copilot agents) — dedicated `references/<runtime>-adapter.md` files when a real audit
  demands them.
- **Sub-tool scoping for `Bash`** in `project-auditor.md` once Claude Code supports it —
  would harden the read-only contract from instruction-enforced to tool-enforced.
- **Weekly throughput histogram** in the snapshot schema.
- **`coverage.py` binary `.coverage` parser**; **native Go cover profile parser**.
- **Trend-mode auto-trigger** from `render_report.py`.
- **HTML email-friendly compact mode** for digest distribution.

## How to use this file

- Update on every PR that ships a step.
- New deferred items get added under "Deferred candidates."
- Completed items move into the current release section with `[x]`.
- Per `CONTRIBUTING.md`, this file is part of every PR that ships a tracked step.
