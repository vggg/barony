---
created: 2026-08-10
accepted: 2026-08-10
type: decision
status: accepted
decided_by: Vikram
adr: 022
project: barony
related:
  - "[[docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap]]"
  - "[[docs/adr/ADR-003-baron-cli]]"
  - "[[docs/adr/ADR-013-observation-plane-events-and-sinks]]"
  - "[[docs/adr/ADR-015-baron-export]]"
---

# ADR-022: git + markdown is the DEFAULT substrate, not the only one — and governance state stays complete in git

| Field | Value |
|---|---|
| **Status** | **Accepted (2026-08-10)** — a product-vision amendment, signed by the owner |
| **Date** | 2026-08-10 |
| **Authors** | Vikram (decision) + Claude (record) |
| **Scope** | Product-vision **invariant #1**. Amends the wording; adds a normative bound. **No code change.** |
| **Resolves** | `DECISIONS-FOR-REVIEW.md` **D2** · [ADR-015](ADR-015-baron-export.md) §4.1 · `AGENT-TASKS.md` 3.4 · the 2026-08-04 Codex reconciliation, item C |
| **Decision owner** | Vikram |

> **This is the most consequential item in the 2026-08-10 pass.** The other two decisions of
> that pass ([ADR-014](ADR-014-guard-telemetry.md) transport retirement; sinks stay off by
> default) are dispositions of work already done. This one changes what Barony *is allowed to
> become*.

## 1. The amendment

Product-vision invariant #1, **as it stood**:

> The repo is the only source of truth. Any hosted surface is a cache, rebuildable from
> `git clone`. `cat` always works; the product is never on the read path.
>
> — quoted in ADR-015 §4.1, `AGENT-TASKS.md` 3.4, `STATUS.md`, and shorthanded throughout as
> *"git + markdown **IS** the substrate"*.

Product-vision invariant #1, **as amended**:

> **git + markdown is the DEFAULT substrate. Plugins may extend it to other suitable
> platforms.**
>
> **The bound: governance state stays COMPLETE IN GIT.** *"Who may do what"*, *"who did
> what"*, and *"what is true now"* must remain answerable from the repository **alone**. A
> plugin may be authoritative for **derived or auxiliary** domains — semantic search,
> embeddings, cross-project recall — and **never** for **authority, evidence, or the
> ledger**. `cat` always works for governance; the product is never on the read path for it.

The first sentence is the loosening the owner asked for. The second paragraph is the bound,
and it is not decorative — it is the load-bearing half, and §3 argues why rather than
asserting it.

## 2. What "complete in git" means, operationally

Three questions define the boundary. Each must be answerable by a person with nothing but a
`git clone` and a text editor — **no credentials, no running service, no index.**

| Question | Answered today by | Class |
|---|---|---|
| **Who may do what?** | `agents/<name>/persona.yaml`, the capability rules artifact, `capability-vocab.v1.md` | **authority** |
| **Who did what?** | git history, `decisions/index.md`, `findings/index.md`, `_handoff/**`, `.baron/guard-override.log` (tracked on purpose, ADR-013 §5) | **evidence** |
| **What is true now?** | `docs/adr/*.md`, `wiki/status.md`, the ledger indexes, `manifest.yaml` | **the ledger** |

**The deletion test.** Delete every plugin and every hosted surface, clone the repo fresh, and
ask the three questions. If any answer is lost, degraded, or now requires a second system, the
plugin was holding governance state and the amendment forbids it. If every answer survives
intact and the only thing lost is *speed of finding it*, the plugin was auxiliary and the
amendment permits it.

That is the whole rule. It is deliberately a test a reviewer can run, not a taxonomy a
reviewer has to interpret.

### 2.1 Permitted and forbidden, concretely

| A plugin **may** be authoritative for | A plugin **may never** be authoritative for |
|---|---|
| Semantic / vector retrieval over the governed corpus | Persona capability grants and denials |
| Embeddings, rerankers, similarity indexes | The capability rules artifact, or any rule guard adjudicates against |
| Cross-project recall and roll-ups spanning many collab repos | The decision, finding, ADR or handoff ledgers |
| Summaries, digests, and derived dashboards | The guard override log, or any record of an adjudication |
| Caches of anything above | Lock, session or merge state that a review depends on |

Every entry in the left column shares one property: **it is rebuildable from the repo, and a
divergence between it and the repo is by definition a bug in the plugin.** Every entry in the
right column shares the opposite one — the repo would be the thing that had to be corrected.

Note what the left column is *not* restricted to. It is not "read-only mirrors". A plugin may
be genuinely **authoritative** for a derived domain — it may own the embedding model, the
chunking, the ranking, and the answer to "what is semantically nearest" — because none of
those are governance facts. What it may not own is a governance fact.

## 3. Why the bound exists — the argument, not the assertion

Barony's audit claim, stated plainly, is: **governance you can verify by reading a diff.** Not
"governance you can query". Not "governance the tool reports as green". A reviewer opens a
pull request, reads the changed lines, and sees who gained a capability, which decision was
ratified, which finding changed the thesis. That claim is why the guard is auditable at all
(ADR-004), why the override log is tracked while the event stream is gitignored (ADR-013 §5),
and why `baron` is a reader/writer over files rather than a service (ADR-003 §2.2).

**That claim holds only while the repository is complete.** The moment a plugin is
authoritative for any governance fact, the following things stop being true, in order:

1. **The diff stops being sufficient.** A capability grant that lives in an index does not
   appear in a PR. A reviewer who reads the whole diff and approves it has approved something
   that no longer describes the system. The review ritual survives in form and dies in
   substance — which is the exact failure class this project already paid for once, when the
   badminton-analyzer incident merged 15 PRs under a persona denied `merge_pr` and *nothing
   failed* because the enforcement had silently degraded to text (ADR-017).
2. **The auditor needs standing to audit.** Today an auditor needs `git clone`. Under an
   authoritative plugin they need credentials to a third-party service, network reachability,
   and a version of the index contemporaneous with the commit they are auditing. Governance
   whose verification requires the vendor's cooperation is not verifiable governance.
3. **The failure is silent.** A stale index does not announce itself. A lost index does not
   announce itself. A repo missing a file announces itself the instant anyone opens it. This
   asymmetry is the reason to prefer the repo even where the index is more capable.
4. **The claim degrades from "read the diff" to "trust the index".** Those are different
   products. The first is checkable by an adversary; the second is checkable only by its
   operator. Barony publishes its own measured operational fidelity of **0.53** rather than
   rounding it up precisely because it does not want claims that can only be taken on trust.
   An authoritative governance plugin would make the project's headline claim exactly that
   kind of claim.

There is also a disaster-recovery consequence, which matters less rhetorically and more in
practice: `git clone` is the recovery story. It is the *only* recovery story that has been
tested, because it is the one that runs on every machine every day. An authoritative index
introduces a second recovery story that nobody has ever exercised, and introduces it at the
layer whose whole purpose is to be trustworthy.

**The amendment must not be readable as permission for any of that.** A future reader who
takes "plugins may extend the substrate" as licence to move capability grants into a
knowledge store has misread this ADR, and §2's deletion test is the sentence to hand them.

### 3.1 What the amendment actually buys

Stated honestly, because a loosening that buys nothing should not have been made:

- Retrieval at scale. `grep` plus a human-curated wiki is the current answer and it does not
  survive cross-project scale — `docs/BACKLOG.md` § *Centralized cross-project memory
  substrate* already names indexing / semantic search as the gap.
- Cross-project recall, which is structurally out of reach for a per-repo substrate: no
  amount of git discipline inside one collab repo answers a question spanning twelve.
- A place to put per-agent memory that is neither in-process-and-private (what runtimes ship)
  nor hand-curated (what the vault pattern does today).

None of these are governance facts. That is not a coincidence — it is the reason the bound
costs nothing to hold.

## 4. This resolves D2. The Cognee question is answered **(a)**.

`AGENT-TASKS.md` 3.4 asked whether a semantic-memory backend is **(a)** a rebuildable
projection over git + markdown, or **(b)** a candidate *authoritative* knowledge source
holding things the repo does not.

**The answer is (a): a rebuildable projection.** Mode **(b)** is refused, and the amendment
does not rescue it — (b) is authority-and-evidence-bearing by construction ("it holds things
the repo does not"), which §2 places in the right-hand column.

Three things this decision is **not**, spelled out because each is an easy misreading:

- It is **not** a decision to build anything. Nothing is authorised here. 3.4 remains gated on
  3.3, the governed-memory evaluation harness, which does not exist.
- It does **not** make Cognee — or any vendor — authoritative for anything. It establishes
  that a plugin *could* be authoritative for an auxiliary domain, which is a statement about
  the shape of the permission, not a grant of it.
- It does **not** change the standing fact that **nothing about the candidate vendor has been
  run**. Public docs were read on 2026-08-09; no ingest, no retrieval, no measurement
  (ADR-015 §6). This ADR adds no measurement and must not be cited as if it did.

## 5. What does NOT change

### 5.1 No `baron.knowledge` entry-point group. Still.

**`cli/tests/test_export.py::test_no_knowledge_entry_point_group_was_published` stays green
and is not to be relaxed.** It is not collateral damage from an unresolved question that this
ADR has now resolved; it protects a different rule, which is untouched: *an entry-point group
name is public API and cannot be retracted, so no group ships without a consumer.*

There is no consumer. 3.3 does not exist, no adapter is built, and no measurement has been
taken. Publishing the group now would trade an irreversible commitment for zero present value
— and it would do it on the strength of a permission, which is the worst possible reason.

The test also asserts no vendor-named group and an allowlist (`baron.forges`, `baron.sinks`),
so a third unreviewed group still fails. That is unchanged too.

### 5.2 The dependency policy and the "files, never endpoints" posture

ADR-003 §2.3 (runtime deps are exactly typer + pyyaml) is untouched. So is
[ADR-014](ADR-014-guard-telemetry.md) §3 / ADR-013 §6 — **no `opentelemetry-api` in baron
core, ever** — and so is `multi-agent-audit/SKILL.md`'s rule that the audit reads *files*,
never endpoints. An extension platform arrives as a separately-distributed plugin over an
existing entry-point group; its dependencies live in the plugin.

### 5.3 `CONTRIBUTING.md`'s "non-git coordination substrates are out of scope"

Unchanged, and consistent. **Coordination *is* governance** in Barony's vocabulary — handoffs,
locks, decisions and reviews are the three questions of §2 in motion. A fundamentally
different *coordination* substrate is still a fork-and-publish-separately proposition. What
the amendment opens is the auxiliary layer beside it, not a replacement beneath it.

### 5.4 `baron export` is the interface, and it was already right

ADR-015 shipped `baron export --json`: the governed corpus as flat records, each carrying
`path + commit_sha`, with any source that cannot honour that citation **skipped by name**
rather than emitted with a SHA that resolves to different bytes. That gate is what makes a
projection auditable — every retrieval result points back at bytes `git show <sha>:<path>`
reproduces. The export was built to be the input either answer consumed, and under answer (a)
it is exactly the right seam. Nothing about it changes.

## 6. What this reverses — and what it does not

`docs/BACKLOG.md` § *Centralized cross-project memory substrate* records that this surface was
**cut once already, after five reviews**, with the disposition *"build only on real demand"*.
ADR-015 §4 cut it a sixth time on sequencing and irreversibility grounds.

**Those cuts stand.** This is the distinction the owner asked to be stated explicitly, and it
is easy to blur:

- **What was cut** was *building the surface now*: no backend contract interface, no
  `baron.knowledge` group, no vendor adapter, no work before 3.3 exists. Every one of those
  reasons was about **sequencing and evidence**, not about the vision forbidding the shape.
  None of them is disturbed here.
- **What is amended** is *what would be permissible if the demand and the measurement
  arrived*. Before today, mode (b) was barred by the vision itself — a future reviewer with
  perfect demand data and a green 3.3 harness would still have had to amend the vision first.
  After today they would not; they would still have to clear the sequencing bar, and they
  would have to stay inside §2's bound.

Put plainly: **this changes the answer to "may we ever?", not the answer to "may we now?".**
The answer to "may we now?" is still no, for the same reasons as before.

The one prior position genuinely **reversed** is the recommendation recorded in ADR-015 §4.1,
`AGENT-TASKS.md` 3.4 and `STATUS.md` — *"amend 3.4 to drop mode (b)"*. Mode (b) is not dropped
from the roadmap's vocabulary; it is **refused on the merits** (§4) under a vision that now
permits the question to be asked. The practical effect on what gets built is identical. The
difference is that the refusal is now a decision with an argument attached, rather than a
constraint inherited from a sentence.

## 7. Where the old wording lived, and what each site now says

Found by grepping for `invariant`, `substrate`, `source of truth` and `product vision` across
the branch — not from memory. Every site is updated in the same commit as this ADR.

| File | Was | Now |
|---|---|---|
| `docs/adr/ADR-015-baron-export.md` §4.1 | "the blocking owner decision"; quotes invariant #1; recommends (a) | **RESOLVED**, quotes the amended invariant, points here |
| `docs/adr/ADR-003-baron-cli.md` §2.2 | "The markdown/git substrate IS the database" | unchanged claim, **scoped** by a pointer here: default substrate, governance complete in git |
| `docs/adr/ADR-013-observation-plane-events-and-sinks.md` §7.1 | — | new: the D4 sink-default decision, which cites this ADR only for the interlock |
| `AGENT-TASKS.md` 3.4 | "BLOCKING OWNER DECISION … or consciously amend invariant #1 and record why" | **RESOLVED** — the amendment is this ADR; (b) refused |
| `STATUS.md` | "OWNER DECISION OUTSTANDING" | **RESOLVED**, points here |
| `README.md` § *What Barony is NOT* | "The markdown/git substrate is the only database" | scoped to governance state, points here |
| `CHANGELOG.md` [Unreleased] | "one decision is still BLOCKING" | **RESOLVED**, points here |
| `docs/DECISIONS-FOR-REVIEW.md` D2 | BLOCKING | **RESOLVED**, points here |
| `docs/BACKLOG.md` § *Centralized cross-project memory substrate* | "build only on real demand" | unchanged verdict, annotated with §6's distinction |

`docs/history.md`'s closing line — *"The substrate never changed: plain markdown + git"* — is
**deliberately left alone.** It is a historical statement about the period it narrates, and it
was true then. Editing history to match a later decision is the thing this project's ledger
conventions exist to prevent.

## 8. Consequences

**Reversible?** The wording, yes — it is a sentence, and re-tightening it costs a follow-up
ADR while no plugin exists. **What is not reversible is anything built under it.** The moment
a plugin ships and downstream repos depend on it, the permission has consumers, and §2's bound
becomes the only thing standing between the product's audit claim and "trust the index". So
the bound is the part to defend in review, every time — not the amendment.

**The near-term consequence is zero.** No code changes, no dependency changes, no entry-point
group, no adapter, nothing built. The suite is unchanged at 424. What changed is that a
question that used to be foreclosed by the vision is now open on the merits, with a published
bound on the answer.

**What a future proposal must show**, so the bar is on the record rather than negotiated later:

1. Real demand, not anticipated demand (`docs/BACKLOG.md`'s existing standard).
2. A 3.3 harness result showing the projection beats the git + markdown baseline on a measured
   axis — the project's own measure-first rule, on the task where that rule is written down.
3. A passing deletion test (§2): delete the plugin, clone fresh, all three questions still
   answered.
4. A consumer that exists, before any entry-point group is published (§5.1).

## 9. Alternatives rejected

| Alternative | Why not |
|---|---|
| **Leave invariant #1 as-is; keep (b) barred by the vision** | It bars the question, not just the answer. Cross-project recall is a real gap the current substrate cannot close at any level of git discipline, and a vision that forecloses it forecloses it silently — the failure would show up as a roadmap item nobody could explain the refusal of. Better to permit the question and publish the bound. |
| **Amend with no bound** — "plugins may extend the substrate", full stop | This is the outcome §3 is written to prevent. Without the bound, the first plausible proposal to move capability state into an index is *compliant*, and the audit claim degrades with nothing to point at. |
| **Bound by vendor or technology** (e.g. "no hosted services", "local only") | Draws the line in the wrong place. The hazard is not where the data lives; it is whether the repo remains complete. A local SQLite index holding capability grants breaks the claim; a hosted vector store holding embeddings does not. |
| **Bound by read/write** — "plugins may read, never write" | Too tight and slightly beside the point. A projection that owns its own chunking, ranking and embeddings *writes* constantly and threatens nothing. The distinction that matters is authoritative-for-what, not read-vs-write. |
| **Defer again, pending 3.3** | The question has been carried since the 2026-08-04 reconciliation and has blocked ADR-015 from moving past *proposed* through two review passes. It is a vision question, not a measurement question — 3.3 would tell us whether semantic retrieval is *good*, never whether an authoritative index is *permissible*. Deferring a vision call behind a measurement it does not depend on is how items become permanent. |
| **Publish `baron.knowledge` now that the direction is settled** | §5.1. Permission is not a consumer, and the group is unretractable. |
