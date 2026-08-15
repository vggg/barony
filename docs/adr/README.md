# ADR index

Every architecture decision record in this repo, with its status, and — where one exists —
the ADR that superseded or amended it. Statuses here are copied from each ADR's own header;
if the two ever disagree, the ADR is right and this file is stale.

**Start elsewhere for the current review.** [`../DECISIONS-FOR-REVIEW.md`](../DECISIONS-FOR-REVIEW.md)
is the consolidation document for the 2026-08 ops-plane pass: §A carries the four owner
decisions (all resolved), §E carries the bounds that are *not* verified, §F carries the
follow-ups deliberately not done. This index is a map, not a summary.

## The records

| # | Title | Status | Relationships |
|---|---|---|---|
| [001](ADR-001-runtime-agnostic-multi-agent-bootstrap.md) | Runtime-agnostic multi-agent project bootstrap & participation | Accepted 2026-05-30 | The founding record. §7's open questions are dispositioned in-place (2026-08-10). |
| [002](ADR-002-ways-of-working-2026-07.md) | July-2026 ways of working | Accepted 2026-07-22 | Extended by ADR-008 (same promotion mechanism). |
| [003](ADR-003-baron-cli.md) | `baron` — coordination conventions become mechanisms | Accepted 2026-07-22 | §2.1 (the name) refined by ADR-005. §2.2 (the git/markdown substrate) **scoped** by ADR-022. |
| [004](ADR-004-baron-guard-enforcement.md) | `baron guard` — sub-tool capability denials become enforceable | Accepted 2026-07-23 | Extended by ADR-012 (hook coverage), ADR-016 (rules artifact), ADR-017 (`baron doctor`). |
| [005](ADR-005-naming.md) | The name — **Barony** / `baron` | Accepted 2026-07-27 | Extends ADR-003 §2.1. |
| [006](ADR-006-baron-init-template-packaging.md) | `baron init` — the deterministic scaffold and template packaging | Accepted 2026-07-27 | Extends ADR-003. |
| [007](ADR-007-session-boundary.md) | The session boundary — Barony does not own the agent loop | Accepted 2026-07-28 | Resolves the `docs/BACKLOG.md` "`baron run` driver — decision pending" fork. |
| [008](ADR-008-ways-of-working-2026-07-31.md) | July-31-2026 ways of working — verdict/label split, decision reconciliation | Accepted 2026-07-31 | Extends ADR-002. §4 is mechanized (as a design) by ADR-009. |
| [009](ADR-009-baron-decision-reconciliation.md) | `baron decision` — a ratified decision reaches the work-pull surfaces | **Proposed / parked** (partial owner review 2026-08-02) | Mechanizes ADR-008 §4. Design only, no code on this branch. Q1/Q3/Q4 genuinely open — see §10. |
| 010 | *(reserved — `baron notify`, the wake mechanism)* | **Not on this branch** | Lives on the unmerged `p2-5-baron-notify` branch, PR #29. The number is reserved and not reused. |
| 011 | *(reserved — agent identity at spawn)* | **Proposed, never merged · SUPERSEDED by [ADR-027](ADR-027-agent-identity.md) (2026-08-14)** | Lived on the unmerged `adr-011-agent-identity` branch, PR #32 (opened 2026-08-04). Same problem, same 2026-08-04 spike, **same mechanism** as ADR-027 — re-derived ten days later without either citing the other. ADR-027 carries the owner's acceptance and the code, and dispositions ADR-011's five blocking questions in its §9. **PR #32 closed as superseded**; the number is reserved and not reused. |
| [012](ADR-012-hook-coverage-and-evidence-capture.md) | Claude Code hook coverage — one enforcing hook, four observing ones | Accepted 2026-08-09 | §4's provisional producer signature **superseded in part by ADR-013 §2**; `baron.hook_event` **superseded by ADR-019**. Both marked inline. |
| [013](ADR-013-observation-plane-events-and-sinks.md) | Observation plane — events, sinks, and the enforcement/evidence asymmetry | Accepted 2026-08-09 | §4.1's label paragraph and §9.1's defect **superseded by ADR-018**. §7.1 records the D4 sink-default decision (2026-08-10). |
| [014](ADR-014-guard-telemetry.md) | Guard-decision telemetry — adopted in part; its transport is retired | **Adopted in part 2026-08-09 · transport RETIRED 2026-08-10** | **Status record only.** The 435-line original was never merged and lives at `harden/otel:docs/adr/ADR-014-guard-telemetry.md`. Its analysis landed as ADR-018 (§4.2) and ADR-021 (§9.1); its transport is retired. **Not rejected** — see §2. |
| [015](ADR-015-baron-export.md) | `baron export` — the governed corpus as citable records | **Proposed** (2026-08-09) | Code shipped while the record is still unsigned. (It was *the only* such ADR when this row was written; 028 and 030 later joined it and were **ratified 2026-08-14**, leaving this and 031 as the two that ship in v1.19.0 still proposed.) §4.1's blocking question is **answered by ADR-022**; §4.2 still withholds the knowledge adapter. |
| [016](ADR-016-externalizable-capability-rules.md) | Externalizable capability rules, step 1 — rule list + the `baron rules` surface | Accepted 2026-08-09 | §4.1's round-3 "one measured, three unmeasured" scoping **superseded by ADR-020**. §5/§6's one-way doors are still undecided and need their own ADR. |
| [017](ADR-017-baron-doctor-wiring-selftest.md) | `baron doctor` — enforcement wiring is verified, and its absence is loud | Accepted 2026-08-09 | Extends ADR-004. Closes the `docs/BACKLOG.md` hook-install-verification item. |
| [018](ADR-018-adjudicated-enforcement-on-the-event.md) | `baron.enforcement` on an event is a per-call observation | Accepted 2026-08-09 | **Supersedes** ADR-013 §4.1 and §9.1. **Ports** `Decision.adjudicated` from ADR-014 §4.2. Implements owner decision D1 (semantics half). |
| [019](ADR-019-runtime-neutral-event-plane.md) | The observation plane is runtime-neutral — a second producer proves it | Accepted 2026-08-09 | **Supersedes** ADR-012 §4's `baron.hook_event` (renamed to `baron.trigger`, no alias). Builds on ADR-018. |
| [020](ADR-020-read-verb-posture-measured-on-four-adapters.md) | The read-verb posture label rests on four measured adapters | Accepted 2026-08-09 | **Supersedes** ADR-016 §4.1's round-3 correction. Implements owner decision D3. |
| [021](ADR-021-audit-ingester-partitions-observation-rows.md) | baron's own evidence is not agent activity — the ingester partitions it out | Accepted 2026-08-09 | **Ports** ADR-014 §9.1 / `partition_guard_records`, re-measured against the merged producer. Implements the ingester half of D1. Scope is `skills/multi-agent-audit/` only. |
| [022](ADR-022-substrate-invariant-amended-default-not-only.md) | git + markdown is the DEFAULT substrate — and governance state stays complete in git | **Accepted 2026-08-10** | **Amends product-vision invariant #1.** Scopes ADR-003 §2.2 and ADR-009 §3; resolves ADR-015 §4.1 and owner decision D2. No code change. |
| [023](ADR-023-reserved-filenames.md) | The emitted config filenames are governed artifact types | Accepted 2026-08-12 | Names the emit-time filenames as artifacts with owners, not incidental strings. |
| [024](ADR-024-fleet-health.md) | `baron health` — a fleet-health surface from the substrate, not a bespoke script | Accepted 2026-08-13 | Sits BESIDE `baron status` and calls into it. §5 states the honest bound: it measures what was emitted. Goes portfolio-wide under ADR-025. |
| [025](ADR-025-coordination-monorepo.md) | The coordination monorepo — projects as subdirs, the portfolio as a `_meta` project | Accepted 2026-08-13 | A **topology**, not a new tier: `baron init --layout monorepo` + `baron add-project`. Per-project-repo stays the default (§7 Q4). Extends ADR-006; routes the ADR-010 wake per subdir. |
| [026](ADR-026-persona-sidecar.md) | The persona sidecar — a persona as a deployable unit | Accepted 2026-08-13 | `baron sidecar run` + an emitted `agents/<slug>/sidecar.sh`. ADR-007 holds: the runtime invocation stays project-owned. |
| [027](ADR-027-agent-identity.md) | Agent identity — per-persona SSH signing keys enrolled in the repo | Accepted 2026-08-14 | Promotes the 2026-08-04 vault spike. `baron identity init` / `baron verify identity`; `.barony/allowed_signers` is the registry, CODEOWNERS the human gate. Agents still push under the OWNER's forge identity — attribution is the KEY. **Supersedes ADR-026 §6 Q4** and **ADR-011** (PR #32 — the same design, re-derived; closed as superseded, see §9). |
| [028](ADR-028-mechanized-merge-gate.md) | `baron merge check` — the merge decision becomes a fail-closed gate | Accepted 2026-08-14 | Mechanizes ADR-002 §4 + ADR-008 §1/§3. Bounded by ADR-007 (checks, never merges). §4 **corrected at integration**: ADR-027 (SSH signing) does **not** unblock the autonomous merger — it attributes commits, and a verdict is a PR comment. §7 Q4 carries the real blocker. |
| [029](ADR-029-prior-art-gate.md) | The prior-art gate — one canonical home, and a recorded sweep before acceptance | Accepted 2026-08-14 | Joins the ways-of-working family (002 → 008 → 023). Extends ADR-009 / the `CONVENTIONS.md` decision-intake rule one step earlier. Mechanized by `baron adr check`, which gates **this directory in CI**. |
| [030](ADR-030-observer-archetype.md) | The `observer` archetype — a strictly read-only watcher with one zone | Accepted 2026-08-14 | Sixth shipped archetype. Deploys per ADR-026; reads the ADR-013 plane and ADR-024 health; read-only-ness rests on the write side because ADR-020 makes the read verbs `instructed`. 027/028 are claimed by in-flight PRs #47/#46. |
| [031](ADR-031-governed-memory-eval-harness.md) | The governed-memory evaluation harness — measure first, then choose a backend | **Proposed** (2026-08-14) | `baron memeval` over labeled fixtures; P3.3, the gate on P3.4. Consumes ADR-015's walker. §4 states the honest bound (fixtures, not a live audit); §5 lists what it does NOT authorise. Renumbered 028 → 031 at integration: 028 landed as the merge gate. |
| [032](ADR-032-export-reach-monorepo-and-widened-corpus.md) | `baron export` reaches the whole estate — the monorepo walk, and the widened corpus | Accepted 2026-08-14 | Owner decision #5. Fixes the root-level silent zero (same class as ADR-025 §6.8) and widens the corpus to six kinds — `status` + `note` — **supersedes ADR-015 §7**'s "curated status is not exported" deferral. Acts on ADR-031's measured finding that the miss was coverage, not ranking. |
| [033](ADR-033-signed-review-verdicts.md) | Signed review verdicts — the merge gate proves WHO approved | Accepted 2026-08-14 | **Supersedes ADR-028 §7 Q4** (route 2: the in-repo signed artifact). Builds entirely on ADR-027 §2.3 — same registry, same trust root, no new key. Closes the EVIDENCE half of the autonomous merger; the authority half (acting under the owner's token) is untouched — see §5. |
| [034](ADR-034-deterministic-capability-enforcement.md) | Deterministic capability enforcement — denial becomes structural, and is proved by invocation | **Accepted** (2026-08-14) | The P2.2 design record, driven by FM4. Extends ADR-004. Names a new finding (**G5**) with no prior art in either corpus: a persona's own `persona.yaml` and `.claude/settings.json` were writable by the persona they govern, so any denial could be undone in one edit. Ratified with **three** layers, not four: L0 makes the config paths a structural refusal (broadened past §4.1 — see §4.1a), L2 recurses one level into `bash -c`, L3 is reported and never configured. **L1 (`permissions.deny`) was declined (OD-2)** — it would publish a stronger-looking posture `bash -c` still evades — so the ADR-020 measurement **stands** and **G1 is unchanged**. The proof-by-invocation tier is opt-in and **advisory**. `rules_version` 1 → 2. |

## Where the owner decisions landed

`docs/DECISIONS-FOR-REVIEW.md` §A carries four decisions plus one follow-up (F3) that was
also an owner call. All five are resolved; none of D2, D4 or F3 carried a code change.

| Decision | Resolved by | Date |
|---|---|---|
| **D1** — what `baron.enforcement` means on an event | [ADR-018](ADR-018-adjudicated-enforcement-on-the-event.md) (semantics) + [ADR-021](ADR-021-audit-ingester-partitions-observation-rows.md) (ingester) | 2026-08-09 |
| **D2** — is a semantic-memory backend a projection or an authority? | [ADR-022](ADR-022-substrate-invariant-amended-default-not-only.md) — answer (a), and invariant #1 amended | 2026-08-10 |
| **D3** — `baron rules list` reports *less* enforcement than it used to | [ADR-020](ADR-020-read-verb-posture-measured-on-four-adapters.md) | 2026-08-09 |
| **D4** — should sinks be on by default? | [ADR-013 §7.1](ADR-013-observation-plane-events-and-sinks.md) — no, and that is a decision rather than a deferral | 2026-08-10 |
| **F3** — ADR-014's producer transport | [ADR-014](ADR-014-guard-telemetry.md) — retired; a recording action, nothing deleted | 2026-08-10 |

## Numbering

ADR numbers are never reused. Two are absent from this directory on purpose:

- **010** was claimed by a branch that is still unmerged (PR #29). ADR-013's header carries
  the same note.
- **011** was claimed by PR #32 and is **superseded by [ADR-027](ADR-027-agent-identity.md)** —
  the two are the same design, re-derived ten days apart from the same 2026-08-04 spike,
  neither citing the other. PR #32 is closed; ADR-011 was never merged and its number is not
  reused. **This is the exact failure ADR-029 exists to catch**, and it is recorded here
  rather than quietly dropped.
- Anyone opening a new ADR should start at **035** (034 is claimed by the P2.2 enforcement
  record, now accepted) — and **check the branches, not just this
  directory**: a number free here may already be taken in flight. The 011/027 re-derivation
  is the reason that sentence is in this file. `baron adr check` gates the *records*; it
  cannot see a number claimed on a branch.
- **031** was claimed **three** times in flight, and the collision was resolved twice. The
  governed-memory eval harness took it first (renumbered 028 → 031, below) and **landed** as
  [ADR-031](ADR-031-governed-memory-eval-harness.md). Signed review verdicts, written against
  031 on a parallel branch while that one was unmerged, renumbered to
  **[033](ADR-033-signed-review-verdicts.md)** at integration; `baron export`'s widened reach,
  written on a third branch, had already taken **032**. Recorded here rather than silently
  renamed — same failure mode as 011/027 and 028, caught at integration and costing only two
  renames. The next free number is **035**.
- **028** was claimed twice in flight. It landed as the mechanized merge gate; the
  governed-memory eval harness, written against 028 on a parallel branch, renumbered to
  **031** at integration. Same failure mode as 011/027, caught earlier and costing only a
  rename. The in-flight collision remains a fixture in `evals/governed-memory/`.
- Three workstreams of the ops-plane consolidation each independently wrote an `ADR-018`.
  The number stayed with `harden/d1-semantics` because ADR-019 was already written against
  it by number; the other two were renumbered **020** and **021**. Only identifiers changed
  — see `../DECISIONS-FOR-REVIEW.md` § *Appendix*.

## Two house conventions worth knowing before editing an ADR

1. **Text under a banner reading "the original framing, which the decision was made against,
   follows" is quarantined and preserved deliberately.** It records what a decision was
   decided *against*. Do not rewrite it to match the outcome; annotate above it instead. The
   same applies to struck-through paragraphs kept under a `SUPERSEDED BY` note — ADR-013
   §4.1 is the worked example.
2. **A superseded relationship is stated in both directions.** The superseding ADR names
   what it supersedes in its header; the superseded section carries an inline note pointing
   forward. One direction alone leaves a reader who arrives from the wrong end with stale
   text and no signal.
