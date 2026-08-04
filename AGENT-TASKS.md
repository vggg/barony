# Barony — agent task queue

Prioritized, chase-top-down work for the generic dev agent on this repo. Scoped from the
2026-07-30/31 badminton-analyzer pilot run (first-party evidence) + the standing roadmap.
`STATUS.md` is the canonical progress tracker; this file is the *ordered queue* — when you ship an
item, update STATUS.md, and **propagate the milestone to the vault** per `CLAUDE.md § Propagate
project-level updates to the Iris / Brain vault`.

Rules of the road: one item at a time; each ships as its own PR with tests + a STATUS.md update
(docs-with-code); anything that changes the spec gets an ADR; do not self-decide product direction —
propose to the owner. Full rationale for P1/P2 lives in the vault:
`projects/AgentBootstrapNasikoMix/roadmap.md`, `…/probe-findings-to-capabilities.md`,
`…/research-*.md` (FM4/FM5/FM6), and badminton `decisions/index.md` D56/D57.

> **Item numbers are allocated here, in order, and never reused.** Before adding an item, read the
> whole queue — including open PRs that touch this file — and take the next free number. Two branches
> independently allocated `2.6` on 2026-08-02/04 and the collision only surfaced at review. This is
> the same allocate-by-convention failure the ledgers fixed with push-atomic numbering (`baron finding
> new`); this file has no such mechanism, so the discipline is manual.

---

## P0 — Ship what is already built (blocks real users, not in the queue until now)

*Why above P1: both items below are recorded as "owner actions" in `STATUS.md` but appear nowhere in
the ordered queue, so a top-down agent never reaches them. The project's stated #1 credibility gap is
having no external adopter — and right now the latest CLI cannot be installed by one.*

- [ ] **0.1 — Publish the CLI to PyPI.** `barony` 0.5.1–0.5.3 are live; **0.5.4 → 0.7.0 are
  unpublished.** Everything since 0.5.3 — the interop hardening, `baron session`, worktree repair,
  guard growth, and P2.3 spec↔runtime drift — is invisible to anyone who installs from PyPI. Highest
  real-user leverage on the board. Owner-credentialed, so this is a "prepare and hand over" item
  unless Vikram delegates the token.
- [ ] **0.2 — Backfill the release tags.** `CHANGELOG.md`/`STATUS.md` record v1.4.0 → v1.9.0 as
  shipped; the newest tag on `origin` is **v1.3.0** — the tag / `gh release create` steps have not run
  since. Backfill steps were prepared and verified against `origin/main` (all five release commits
  confirmed, CHANGELOG sections confirmed for note extraction); awaiting the owner's go. Lower user
  impact than 0.1, but it is what makes the record match reality.

---

## P1 — Promote the pilot hardening into the canonical templates (highest leverage)

*Why first: `baron init` flows one-way (Barony → new projects). The 2026-07-31 hardening lives only in
the badminton pilot's collab repo, so the next scaffold ships WITHOUT it. Until these land, every new
adopter gets templates missing battle-tested rules. Precedent: ADR-002 folded the July learnings.*

- [x] **1.1 — Fold `label-is-not-evidence` + the `Decision & ADR intake (record AND reconcile)`
  protocol into the CONVENTIONS template** (`skills/barony/assets/collab-repo/CONVENTIONS.md`). Source
  text: badminton `CONVENTIONS.md` §§ (2026-07-31). DoD: template carries both rules; drift-guard test green.
  *(Shipped: both rules generalized off the pilot text — project-neutral names, pilot evidence kept as
  rationale; vendored copy re-synced; lint + bi-runtime + 131 CLI tests green. ADR citation backfills in 1.5.)*
- [x] **1.2 — Fold the FEEDBACK-SWEEP step-0 `reviewed-sha == head` check into the dev persona
  template** (`agents/__DEV__/persona.yaml`). Source: badminton dev `CLAUDE.md` FEEDBACK SWEEP step 0.
- [x] **1.3 — Encode SHA-bound verdict discipline in the reviewer + merger templates**
  (`agents/__REVIEWER__/`, `agents/__MERGER__/persona.yaml`) — verdict = comment bound to a head SHA;
  never GitHub-approve; merger verifies `reviewed-sha == head` before merge.
- [x] **1.4 — Ship `strip-stale-verdict` as a scaffolded workflow** in the template (`baron init` emits
  a `.github/workflows/strip-stale-verdict.yml` that removes `reviewed-approved` + `changes-requested`
  on `synchronize`). Reference impl: badminton `fleet-runner/strip-stale-approval.yml`.
- [x] **1.5 — ADR "ways-of-working 2026-07-31"** documenting the fold-in (follows ADR-002). One PR can
  bundle 1.1–1.5 or split; ADR lands with the templates.

> **P1 CLOSED** — 1.1–1.5 shipped as one PR (owner call, 2026-07-31) in the pending
> **plugin 1.9.0 + CLI 0.6.0** bundle. [ADR-008](docs/adr/ADR-008-ways-of-working-2026-07-31.md)
> is the record; `STATUS.md` carries the per-item detail. Vault handoff filed at P1 close.

## P2 — New capabilities surfaced by the pilot (the probe items)

*Each is a candidate net-new differentiator — several may be things no competitor has. Probe/scope
with the owner before large builds: `…/probe-findings-to-capabilities.md`.*

> **2026-08-02 — reconciled against five independent reviews** (research/architect/PM scope-discipline
> pass + architect/PM product-vision pass; full synthesis in the vault at
> `projects/AgentBootstrapNasikoMix/2026-08-02-synthesis-plan.md`). Converged verdict: the *shipped*
> product is well scoped; the overreach lives in the roadmap and the public narrative. Changes below:
> new 2.0; 2.2 reframed; 2.4 demoted; new 2.7/2.8; the identity-sequencing fork logged as an open
> owner decision rather than silently resolved.

- [ ] **2.0 — Guard self-test: fail LOUD when the hook/executable is missing.** Converged
  highest-priority item across all five reviews ("highest-value item in the whole roadmap" — PM;
  "do immediately, no dependencies" — architect). Closes the real residual of FM4: the guard is a
  genuine deterministic block for recognized ops, but its *absence* is silent — that is how ~15 PRs
  merged past a denied `merge_pr` with nothing noticing. Ship alongside: enforcement-strength labels
  (`enforced` / `enforced-with-baron` / `instructed`) surfaced in every generated persona and audit
  report, plus an explicit fail-open/fail-closed policy (currently undefined). Detail: vault
  `roadmap.md` § `baron guard` hardening.
- [~] **2.1 — `baron decision`** — the FM6/D57 mechanism: a ratified decision must *reconcile the
  work-pull surfaces it contradicts* (park/close contradicting epics, update direction doc, broadcast),
  not just append to `decisions/`. This is the "next thing to extend on" (owner, 2026-07-31). Start with
  a design ADR.
  *(Design ADR: [ADR-009](docs/adr/ADR-009-baron-decision-reconciliation.md), status **proposed / parked**.
  Owner 2026-08-02: `park_label` read-side change **accepted**; **P2.3 first**. Q1/Q3/Q4 still open —
  pick this up after P2.3 lands.)*
- [ ] **2.2 — Platform-enforced merge gate** (reframed 2026-08-02 — was "Deterministic enforcement").
  **Cut the "make the denied call *impossible* / generalize the interceptor across the vocab"
  ambition** — converged finding across the research and architect scope reviews: that is the
  sandbox/authorization category `baron guard`'s own positioning disclaims ("not a security
  boundary"), a static shell parser cannot win that arms race (the `bash -c` bypass is documented in
  `guard.py`'s own docstring), and OS/container sandboxing plus GitHub branch protection already own
  hard denial for free. **What survives:** `baron platform apply` provisions branch-protection
  rulesets + required checks from the manifest; a `signet-verify` Action re-derives the reviewer's
  SHA-bound verdict as a required status; the merger persona's `merge_pr` becomes real because *only
  its App credential can merge*. This closes the enforcement story honestly — guard stays the
  cooperating-agent nudge, and the platform gate is where anything irreversible is actually stopped.
  **Depends on identity** (see the open-decision callout at the end of P2) for the credential half;
  the ruleset-generator and verify-Action half can be designed now. FM4 remains the driver evidence.
- [x] **2.3 — `baron validate` spec↔runtime drift** — a persona declared in `persona.yaml` but absent
  from the registered runtime agents is a validate-time error (this exact gap forced a wrong-persona
  cron on the pilot).
  *(Shipped in `barony` 0.7.0, owner-prioritised 2026-08-02. `cli/src/baron/drift.py`. NOTE the
  check keys off `manifest.personas`, not `agents/*/persona.yaml` — the manifest is the roster.
  Signal is **partial registration**, so Tier-1/Tier-2/fresh-scaffold projects stay silent;
  claude + code-puppy registries; `--no-runtime-drift` opts out. Verified against the real pilot
  repo (reports terrence + carson) and against a fresh scaffold (clean).)*
- [ ] **2.4 — `baron promote`** — **demoted from the product roadmap (2026-08-02).** The research
  scope review (#9) and the PM scope review (#3) independently concluded this solves the
  *maintainer's own* template-sync chore, not any adopter's problem — "internal tooling wearing a
  product-feature costume." Keep it as a script or Makefile target; do not build it as a governed
  `baron` subcommand and do not carry it on the public roadmap. (P1 remains the manual precedent for
  the fold-in itself, which stays real and necessary — only the mechanized *product feature* is cut.)
- [ ] **2.5 — `baron notify` — wake/nudge idle agents** (fixes FM1/FM5: agents are poll-only, nothing
  wakes the responsible agent when a verdict or handoff lands; today a human is the message bus).
  Researched 2026-07-31 — external survey confirms **no agent framework wakes a cold headless agent**
  (that's a *platform* capability; A2A wakes the orchestrator, not the worker; MCP is orthogonal).
  **Design — two layers, most designs conflate them:** (a) **delivery** — a git-native mailbox
  `_mailbox/<persona>/` swept first each loop, can't-miss, survives everything; (b) **wake** — a
  `repository_dispatch` GitHub Actions event that *spawns* a fresh headless persona. `baron notify
  <persona> <msg>` writes the mailbox AND fires the event. Laptop-off durable; **retires the wasteful
  wall-clock cron** the badminton pilot polls on now; no bespoke server; on-brand git-native. Adopt A2A
  *vocabulary* as the interop north-star only; reserve Temporal signals for true sub-second mid-run
  steering. Start with a design ADR. Detail: vault
  `projects/AgentBootstrapNasikoMix/research-a2a-wake-nudge.md` + `research-agent-messaging.md` (FM1/FM5).
- [ ] **2.6 — Governed vault propagation** — mechanize the current project-level handoff convention
  without giving a runtime hook arbitrary cross-repository write authority. Proposed seam:
  `baron vault propose --input <event.json> --json` classifies/normalizes a candidate; `baron vault
  publish <proposal> --json` validates an allowlisted target repo/branch/path, schema/frontmatter,
  source path+SHA, idempotent event ID, and fast-forward safety, then emits a receipt linking source
  evidence to the vault commit. Claude `Stop` hook is the first adapter, rolled out shadow → draft →
  automatic FYI milestones; decisions/direction changes retain owner confirmation. DoD: release or
  accepted ADR produces exactly one valid handoff; routine commits produce none; duplicate hook calls
  are idempotent; failed publication cannot report success. **Start with a design ADR**; preserve
  ADR-007's boundary — the runtime owns the agent loop, Barony owns governed bookkeeping/evidence.
- [ ] **2.7 — Handoff lifecycle under pressure** (new 2026-08-02, PM product-vision M5). Wire the
  archive tier into `handoff close` by default — the pilot's 156-file flat `_handoff/` directory with
  **zero** archived shows the lifecycle mechanism exists but exerts no pressure to use it. Add SLA
  autotriage to `baron status` (overdue-open counts already exist; add a "stale-open → propose-close"
  batch helper). `baron index` stays the generated view. Small, and it builds on shipped
  `handoff`/`status`. Evidence: 60 of 156 open (38%), triage currently a manual ~20-item librarian
  sweep.
- [ ] **2.8 — `baron merge-check`** (new 2026-08-02, PM product-vision M6). CLI/CI-level precondition
  verification: confirm a SHA-bound `REVIEW:PASS <sha>` comment exists **at the current head** and CI
  is green before the merger persona may merge — refuse naming the failed precondition, and never
  treat a label as an input. This is the half of 2.2 that needs no identity work, and it composes
  directly with the shipped `strip-stale-verdict` Action (P1.4) and signets, so it can ship
  independently of the identity fork below. Converts "the merger *verifying* the verdict" from
  discipline into mechanism — the exact gap class Barony exists to close, and one the launch FAQ
  already concedes is open.

> **Open decision — identity sequencing (2026-08-02, deliberately unresolved).** Verified per-persona
> identity (a GitHub App per persona + signed commits; unlocks 2.2's credential half, `baron join`,
> and provable two-party review) drew two opposed recommendations from the product-vision reviews.
> The **architect** says pull it to *first*, ahead of even 2.0: it is the precondition that converts
> branch protection, signets, and the audit's attribution claim from convention into fact. The **PM**
> says *design now, build the day adopter #1 adds a second operator*: with zero external adopters,
> building identity infrastructure ahead of proven need is speculative platform work, and it is not
> on the critical path for 2.0/2.1/2.7/2.8. Both are internally consistent; they differ on tolerance
> for building ahead of demand. Full argument each way:
> `projects/AgentBootstrapNasikoMix/2026-08-02-synthesis-plan.md` §4. **Not self-decided**, per this
> file's own rule — propose to the owner before starting the build. Design work is safe either way.

## P3 — Productization + dogfood

- [ ] **3.1 — Barony governs Barony** — `baron init` on this repo so the framework dogfoods its own
  multi-persona fleet (today it's hand-built solo: 20/20 commits owner). Strongest possible case study.
- [ ] **3.2 — Fleet-health as a capability** — stall detection + the metrics the pilot proved out
  (mutation-kill rate, claim-drift/PR with direction, **reviewer escape rate**, intervention tax) →
  the Workstream-D paid observability anchor. Reference impl: badminton `fleet-runner/` (metrics-report,
  detect_stalls).
- [ ] **3.3 — Governed-memory evaluation harness** — establish labeled fixtures and a reproducible
  baseline before selecting a semantic-memory backend. Cover propagation precision/recall, duplicate
  suppression, schema/path/status accuracy, retrieval Recall@k/MRR, source-citation accuracy,
  freshness/supersession, and human intervention tax. Compare: git+markdown baseline; hook-assisted
  propagation; semantic retrieval; hooks+semantic retrieval. Include routine commit, release,
  accepted/proposed/parked/superseded ADR, thesis-changing finding, duplicate event, and bad/missing
  source-SHA cases. Separate from 3.2: fleet health measures the team; this measures durable project
  knowledge.
- [ ] **3.4 — Pluggable knowledge substrate + Cognee spike** — define the backend contract first,
  then evaluate Cognee both as (a) a rebuildable semantic projection over git+markdown and (b) a
  candidate authoritative knowledge source where its durability, concurrency, provenance, export,
  and recovery properties meet Barony's governance requirements. The contract must cover stable IDs,
  append/update/supersede, queries, citations to original evidence, transactions/idempotency,
  namespace isolation, export/rebuild, retention, and health. Initial adapter is read-only indexing of
  ADRs/decisions/findings/handoffs/curated status; exclude raw transcripts. **Default remains
  git+markdown until 3.3 shows material retrieval or scale benefit and the Cognee-authoritative mode
  proves equivalent auditability, portability, disaster recovery, and human inspectability.** Every
  retrieval result must carry an authoritative source ID/version (path+commit SHA for Git). Exit:
  classify the Cognee adapter as supported projection, supported source, experimental, or rejected.

## Carried from STATUS.md (in-flight, keep visible)
- [ ] Phase-gate audit — re-run `multi-agent-audit` against the pilot with guard/lock topology.
- [ ] Merger precondition verification + guard coverage growth (`docs/BACKLOG.md`).
- [ ] pydantic-ai adapter field validation.

---

*When you complete a P-item or hit a milestone: update `STATUS.md`, and drop a `barony:` handoff into
the vault (`_handoff/tasks/` for FYI, `_handoff/decisions/` if it needs the owner) so Iris reconciles it
into the cross-project record. Direction questions → propose to the owner, don't self-decide.*
