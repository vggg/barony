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
- [ ] **1.2 — Fold the FEEDBACK-SWEEP step-0 `reviewed-sha == head` check into the dev persona
  template** (`agents/__DEV__/persona.yaml`). Source: badminton dev `CLAUDE.md` FEEDBACK SWEEP step 0.
- [ ] **1.3 — Encode SHA-bound verdict discipline in the reviewer + merger templates**
  (`agents/__REVIEWER__/`, `agents/__MERGER__/persona.yaml`) — verdict = comment bound to a head SHA;
  never GitHub-approve; merger verifies `reviewed-sha == head` before merge.
- [ ] **1.4 — Ship `strip-stale-verdict` as a scaffolded workflow** in the template (`baron init` emits
  a `.github/workflows/strip-stale-verdict.yml` that removes `reviewed-approved` + `changes-requested`
  on `synchronize`). Reference impl: badminton `fleet-runner/strip-stale-approval.yml`.
- [ ] **1.5 — ADR "ways-of-working 2026-07-31"** documenting the fold-in (follows ADR-002). One PR can
  bundle 1.1–1.5 or split; ADR lands with the templates.

## P2 — New capabilities surfaced by the pilot (the probe items)

*Each is a candidate net-new differentiator — several may be things no competitor has. Probe/scope
with the owner before large builds: `…/probe-findings-to-capabilities.md`.*

- [ ] **2.1 — `baron decision`** — the FM6/D57 mechanism: a ratified decision must *reconcile the
  work-pull surfaces it contradicts* (park/close contradicting epics, update direction doc, broadcast),
  not just append to `decisions/`. This is the "next thing to extend on" (owner, 2026-07-31). Start with
  a design ADR.
- [ ] **2.2 — Deterministic enforcement** (already load-bearing in the roadmap, ADR-004 territory):
  per-runtime hook/ToolGuard interceptors so a denied capability is *impossible*, not requested.
  Driver: FM4 — a dev persona merged ~15 PRs despite `merge_pr` denied in its own config, then refused
  identically. Non-deterministic denial is the sharpest enforcement evidence.
- [ ] **2.3 — `baron validate` spec↔runtime drift** — a persona declared in `persona.yaml` but absent
  from the registered runtime agents is a validate-time error (this exact gap forced a wrong-persona
  cron on the pilot).
- [ ] **2.4 — `baron promote`** — mechanize the pilot→canonical upstream path (P1 is the manual version
  of this; #2.4 makes it a governed operation so learnings don't stay trapped downstream).
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
