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

> **2026-08-02 — reconciled against five independent reviews** (research/architect/PM scope-
> discipline pass + architect/PM product-vision pass, vault
> `projects/AgentBootstrapNasikoMix/2026-08-02-synthesis-plan.md`). Two changes below (2.2 reframed,
> 2.4 demoted); one new top-priority item (2.0); three new items (2.6–2.8); one open decision logged,
> not resolved (identity sequencing, see the callout after 2.8).

- [ ] **2.0 — Guard self-test: fail LOUD when the hook/executable is missing.** Converged
  highest-priority item across all five 2026-08-01 reviews ("highest-value item in the whole
  roadmap" — PM; "do immediately, no dependencies" — architect). Closes the real residual of FM4:
  the guard itself is a real deterministic block for recognized ops, but its *absence* is silent —
  that's how ~15 PRs merged past a denied `merge_pr`. Ship alongside: enforcement-strength labels
  (`enforced` / `enforced-with-baron` / `instructed`) surfaced in every generated persona + audit
  report, and an explicit fail-open/fail-closed policy (currently undefined). Detail: roadmap.md
  § `baron guard` hardening.
- [~] **2.1 — `baron decision`** — the FM6/D57 mechanism: a ratified decision must *reconcile the
  work-pull surfaces it contradicts* (park/close contradicting epics, update direction doc, broadcast),
  not just append to `decisions/`. This is the "next thing to extend on" (owner, 2026-07-31). Start with
  a design ADR.
  *(Design ADR: [ADR-009](docs/adr/ADR-009-baron-decision-reconciliation.md), status **proposed / parked**.
  Owner 2026-08-02: `park_label` read-side change **accepted**; **P2.3 first**. P2.3 shipped 0.7.0 —
  this is now unblocked. Q1/Q3/Q4 still open — pick this up next. **2026-08-02: the PM product-vision
  review independently promotes this from "wedge item #6" to mandatory/signature — no competitor in
  any segment has decision durability, and D57 is "the pilot's most expensive failure." Bound the
  mutation half per the architect review (F5): prefer reporting the reconciliation obligation over
  actively mutating the backlog; do GitHub honestly, report other trackers `unverifiable` rather than
  building a multi-backend adapter matrix.**)*
- [ ] **2.2 — Platform-enforced merge gate** (reframed 2026-08-02 — was "Deterministic enforcement").
  **Cut the "make the denied call impossible / generalize the interceptor across the vocab" ambition**
  — converged finding across research + architect scope reviews: that is the sandbox/authorization
  category `baron guard`'s own positioning disclaims ("not a security boundary"), a static shell
  parser can't win that arms race (`bash -c` bypass, documented in `guard.py`'s own docstring), and
  OS/container sandboxing + GitHub branch protection already own hard denial for free. **What survives:**
  `baron platform apply` provisions branch-protection rulesets + required checks from the manifest; a
  `signet-verify` Action re-derives the reviewer's SHA-bound verdict as a required status; the merger
  persona's `merge_pr` becomes real because *only its App credential can merge*. This closes the
  enforcement story honestly — `guard` stays the cooperating-agent nudge, the platform gate is where
  anything irreversible actually gets stopped. **Depends on identity** (see the open-decision callout
  below) for the credential half; the ruleset-generator + verify-Action half can be designed now.
  FM4 stays the driver evidence.
- [x] **2.3 — `baron validate` spec↔runtime drift** — a persona declared in `persona.yaml` but absent
  from the registered runtime agents is a validate-time error (this exact gap forced a wrong-persona
  cron on the pilot).
  *(Shipped in `barony` 0.7.0, owner-prioritised 2026-08-02. `cli/src/baron/drift.py`. NOTE the
  check keys off `manifest.personas`, not `agents/*/persona.yaml` — the manifest is the roster.
  Signal is **partial registration**, so Tier-1/Tier-2/fresh-scaffold projects stay silent;
  claude + code-puppy registries; `--no-runtime-drift` opts out. Verified against the real pilot
  repo (reports terrence + carson) and against a fresh scaffold (clean).)*
- [ ] **2.4 — `baron promote`** — **demote from product roadmap (2026-08-02).** Both the research
  scope-review (#9) and the PM scope-review (finding #3) independently conclude this solves the
  *maintainer's own* template-sync chore, not an adopter's problem — "internal tooling wearing a
  product-feature costume." Keep as a script/Makefile target; do not build it as a governed `baron`
  subcommand or keep it on the public roadmap. (P1 remains the manual precedent for the fold-in
  itself, which stays real and necessary — only the mechanized-command *product feature* is cut.)
- [~] **2.5 — `baron notify` — wake/nudge idle agents** (fixes FM1/FM5: agents are poll-only, nothing
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
  *(Design ADR drafted: [ADR-010](docs/adr/ADR-010-baron-notify-wake.md), status **proposed**.
  **BLOCKED on owner review** — §8 has five questions; the headline one is that the design DROPS the
  proposed `_mailbox/` surface because `_handoff/` already is it. No code until answered.)*

## P3 — Productization + dogfood

- [ ] **3.1 — Barony governs Barony** — `baron init` on this repo so the framework dogfoods its own
  multi-persona fleet (today it's hand-built solo: 20/20 commits owner). Strongest possible case study.
- [ ] **3.2 — Fleet-health as a capability** — stall detection + the metrics the pilot proved out
  (mutation-kill rate, claim-drift/PR with direction, **reviewer escape rate**, intervention tax) →
  the Workstream-D paid observability anchor. Reference impl: badminton `fleet-runner/` (metrics-report,
  detect_stalls).

## Carried from STATUS.md (in-flight, keep visible)
- [ ] Phase-gate audit — re-run `multi-agent-audit` against the pilot with guard/lock topology.
- [ ] Merger precondition verification + guard coverage growth (`docs/BACKLOG.md`).
- [ ] pydantic-ai adapter field validation.

---

*When you complete a P-item or hit a milestone: update `STATUS.md`, and drop a `barony:` handoff into
the vault (`_handoff/tasks/` for FYI, `_handoff/decisions/` if it needs the owner) so Iris reconciles it
into the cross-project record. Direction questions → propose to the owner, don't self-decide.*
