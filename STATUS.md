# STATUS — Barony

Tracks current progress and deferred candidates. Update on every PR that ships a step (per
`CONTRIBUTING.md`). Full release history lives in `CHANGELOG.md`; the v0→v1 migration story
lives in [`docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md`](docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md).

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
  `docs/worktree-migration.md` (live migration deliberately not included).
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
