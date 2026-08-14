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

- [x] **2.1 — `baron decision`** — the FM6/D57 mechanism: a ratified decision must *reconcile the
  work-pull surfaces it contradicts* (park/close contradicting epics, update direction doc, broadcast),
  not just append to `decisions/`. This is the "next thing to extend on" (owner, 2026-07-31). Start with
  a design ADR.
  *(Design ADR: [ADR-009](docs/adr/ADR-009-baron-decision-reconciliation.md), status **proposed / parked**.
  Owner 2026-08-02: `park_label` read-side change **accepted**; **P2.3 first**; **first cut = `park`
  only**. SHIPPED in CLI 0.8.0 — reconcile/check, the marker block, `manifest.backlog.park_label`
  (schema v1.3), and park-exclusion in all five `check_backlog` renderers. Q3/Q4 took the proposed
  defaults (not capability-gated; block-less legacy decisions are green, not nagged).
  `supersedes` / `broadcast` / `direction_doc` remain designed and unbuilt.)*
- [ ] **2.2 — Deterministic enforcement** (already load-bearing in the roadmap, ADR-004 territory):
  per-runtime hook/ToolGuard interceptors so a denied capability is *impossible*, not requested.
  Driver: FM4 — a dev persona merged ~15 PRs despite `merge_pr` denied in its own config, then refused
  identically. Non-deterministic denial is the sharpest enforcement evidence.
- [x] **2.3 — `baron validate` spec↔runtime drift** — a persona declared in `persona.yaml` but absent
  from the registered runtime agents is a validate-time error (this exact gap forced a wrong-persona
  cron on the pilot).
  *(Shipped in `barony` 0.7.0, owner-prioritised 2026-08-02. `cli/src/baron/drift.py`. NOTE the
  check keys off `manifest.personas`, not `agents/*/persona.yaml` — the manifest is the roster.
  Signal is **partial registration**, so Tier-1/Tier-2/fresh-scaffold projects stay silent;
  claude + code-puppy registries; `--no-runtime-drift` opts out. Verified against the real pilot
  repo (reports terrence + carson) and against a fresh scaffold (clean).)*
- [ ] **2.4 — `baron promote`** — mechanize the pilot→canonical upstream path (P1 is the manual version
  of this; #2.4 makes it a governed operation so learnings don't stay trapped downstream).
- [~] **2.5 — `baron notify` — wake/nudge idle agents** (fixes FM1/FM5: agents are poll-only, nothing
  wakes the responsible agent when a verdict or handoff lands; today a human is the message bus).
  Researched 2026-07-31 — external survey confirms **no agent framework wakes a cold headless agent**
  (that's a *platform* capability; A2A wakes the orchestrator, not the worker; MCP is orthogonal).
  **Design — two layers, most designs conflate them:** (a) **delivery** and (b) **wake** — a
  `repository_dispatch` GitHub Actions event that *spawns* a fresh headless persona. Laptop-off
  durable; no bespoke server; on-brand git-native. Adopt A2A *vocabulary* as the interop north-star
  only; reserve Temporal signals for true sub-second mid-run steering. Detail: vault
  `projects/AgentBootstrapNasikoMix/research-a2a-wake-nudge.md` + `research-agent-messaging.md` (FM1/FM5).
  *(Design ADR: [ADR-010](docs/adr/ADR-010-baron-notify-wake.md) — **ACCEPTED with changes, Vikram
  2026-08-02**; all eight §8 questions answered and recorded verbatim in the ADR. Unblocked: build.
  The headline change is that the design **drops the proposed `_mailbox/<persona>/` surface** —
  `_handoff/` already is the delivery layer, and adversarial review supplied the stronger argument
  (it already carries `priority:`). Other owner answers: the pilot's 15-minute cron drops to
  hourly/daily as a **slow backstop** rather than being retired, because §5.3's silent-no-op paths
  (missing PAT, missing workflow, rate limit) are real and something must still catch a wake that
  never fired; `--max-depth 2` enforced in **both** CLI and workflow; repo-event triggers are **out**
  of the first cut; the handoff-filename disagreement is **its own change**, not smuggled in here;
  duplicate-notify **reuses the existing handoff and wakes only**.)*
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
  - **SHIPPED 2026-08-14 ([ADR-031](docs/adr/ADR-031-governed-memory-eval-harness.md)):**
    `baron memeval --fixtures evals/governed-memory`. Labeled fixtures cover the full case
    list (asserted by test), all eight metric families are computed, and two of the four
    approaches are **measured** — `git-markdown` and `hooks`. The two semantic approaches are
    declared and report `NOT MEASURED`; the seam is an in-process dict, deliberately not an
    entry-point group. Numbers and honest bounds in `STATUS.md`.
  - **The gate result 3.4 has to act on:** on the flagship fixture the lexical baseline
    retrieves every *in-corpus* gold record at rank 1 and misses only a document
    `baron export` does not walk. On this corpus the constraint is **coverage, not ranking** —
    so widen the export (curated status, research notes outside the four corpora) before
    reaching for embeddings, and expect a semantic layer over the same records to win little.
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
  - **PRODUCER WIDENED, 2026-08-14 ([ADR-032](docs/adr/ADR-032-export-reach-monorepo-and-widened-corpus.md), owner decision #5):**
    acting on ADR-031 (P3.3)'s measured finding that the retrieval miss was **coverage,
    not ranking**, `baron export` now reaches (a) every project subdir of an ADR-025 coordination
    monorepo — it previously reported **0 records** at the root — and (b) under `--wide`, two more
    corpora, `status` and `note`, which completes this task's own "ADRs/decisions/findings/handoffs/**curated
    status**" list and supersedes ADR-015 §7's deferral. The widened corpus is **opt-in** (ADR-032
    §3.1, amended at integration): a six-kind default measurably regressed `baron memeval`'s pinned
    ADR-031 numbers, so the capability ships behind a flag and flipping the default waits on §4.3's
    two harness fixes. Measured on the P3.3 fixtures: retrieval
    ceiling 84.4% → 87.5%, R@5 76.0 → 79.2, flagship query's unreachable gold record now reachable;
    MRR 81.2 → 75.0 (a widened small corpus adds competition — reported, not suppressed). **The
    backend half is untouched and still gated**: no `baron.knowledge` group, no vendor, no
    adapter. The next question is now well-posed — does a semantic layer recover precision-at-1
    while keeping the coverage?
  - **PARTIAL, 2026-08-09 ([ADR-015](docs/adr/ADR-015-baron-export.md)):** the *producer* half is
    built and shipped as **`baron export`** — ADRs/decisions/findings/handoffs walked into flat
    records that each carry `path + commit_sha`, with sources that cannot honour that citation
    skipped by name rather than mis-cited. That discharges the "every retrieval result must carry
    an authoritative source ID/version" requirement independently of which backend wins, since it
    is a requirement on the corpus walk, not on the store. **Curated status is still not
    exported** (no schema), and ADRs living in the code repo are out of reach (needs the manifest).
  - **Still NOT built, deliberately:** the backend contract interface, the `baron.knowledge`
    entry-point group, and any vendor adapter. Reasons in ADR-015 §4 — 3.4 is gated on 3.3 (which
    does not exist), and a published entry-point group with no consumer is unretractable public
    API. Tests assert `baron.forges` is still the only group, that runtime deps are still
    typer + pyyaml, and that no vendor name appears under `cli/src/baron/`.
  - **~~BLOCKING OWNER DECISION~~ — RESOLVED 2026-08-10
    ([ADR-022](docs/adr/ADR-022-substrate-invariant-amended-default-not-only.md)).** The owner
    took the second branch of the choice below: **invariant #1 is consciously AMENDED**, and the
    why is recorded. It now reads *git + markdown is the **DEFAULT** substrate; plugins may
    extend it to other suitable platforms* — **bounded** by *governance state stays complete in
    git*: "who may do what", "who did what" and "what is true now" must stay answerable from the
    repository alone, and a plugin may be authoritative for **derived or auxiliary** domains
    (semantic search, embeddings, cross-project recall) and **never** for authority, evidence or
    the ledger. **Mode (b) is answered: refused** — "it holds things the repo does not" is
    authority-bearing by construction. **3.4 is therefore mode (a), a rebuildable projection.**
    Note what did *not* change: **no adapter is authorised**, 3.4 is still gated on 3.3 (which
    does not exist), the `baron.knowledge` entry-point group is still **not** published and its
    test stays green, and nothing about the vendor has been run. The original framing follows.
    - *(original)* Carried from the 2026-08-04 Codex reconciliation, item C:
      mode **(b)** "authoritative knowledge source" contradicts the product vision's invariant #1
      ("the repo is the only source of truth; any hosted surface is a cache, rebuildable from
      `git clone`; `cat` always works"). Either drop mode (b) and keep the substrate a projection,
      or consciously amend invariant #1 and record why. **Recommendation: drop (b).** No adapter
      should be built until this is answered *and* 3.3 exists.
  - **Nothing about the vendor has been run.** Its public docs were read on 2026-08-09; no
    ingest, no retrieval, no measurement. Do not let any surface imply otherwise (ADR-015 §6).

## Carried from STATUS.md (in-flight, keep visible)
- [ ] Phase-gate audit — re-run `multi-agent-audit` against the pilot with guard/lock topology.
  **Note the precondition moved**: the audit ingester now partitions baron's own evidence out
  of the activity plane ([ADR-021](docs/adr/ADR-021-audit-ingester-partitions-observation-rows.md)),
  so a re-run is safe to pair with a baron export — but the **default sink is `null` by
  signed decision** ([ADR-013 §7.1](docs/adr/ADR-013-observation-plane-events-and-sinks.md)),
  so a project produces no `.baron/events/` rows until an operator opts in. Whoever runs this
  has to turn sinks on in the pilot first, or the fidelity number moves for no measured reason.
- [ ] Merger precondition verification + guard coverage growth (`docs/BACKLOG.md`).
- [ ] pydantic-ai adapter field validation. *(The adapter gained an in-process evidence
  producer in [ADR-019](docs/adr/ADR-019-runtime-neutral-event-plane.md); that is a second
  measured producer on the event plane, **not** the ADR-001 acceptance bar. The bar is still
  a real persona on a real project on this runtime, and it has not been run.)*

## Deferred out of the 2026-08 ops-plane consolidation

Recorded in `docs/DECISIONS-FOR-REVIEW.md` §F and carried in `docs/BACKLOG.md` §
*Deferred out of the 2026-08 ops-plane consolidation*, not re-listed here: **F1** the
per-runtime capability matrix (harness already merged; what remains is an output redesign),
**F2** delivery-verified `instructed` via the ritual-fence technique (needs a live runtime in
CI and its own vocabulary decision), **F4** an aggregate over `baron.enforcement` in the audit
skill (un-built, not blocked), and wiring the reserved `events:` manifest node (blocked on
measuring guard's hot path). None is queued. Promote one into P2/P3 only on the owner's call.

---

*When you complete a P-item or hit a milestone: update `STATUS.md`, and drop a `barony:` handoff into
the vault (`_handoff/tasks/` for FYI, `_handoff/decisions/` if it needs the owner) so Iris reconciles it
into the cross-project record. Direction questions → propose to the owner, don't self-decide.*
