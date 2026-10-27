# STATUS — Barony

Tracks current progress and deferred candidates. Update on every PR that ships a step (per
`CONTRIBUTING.md`). Full release history lives in `CHANGELOG.md`; the v0→v1 migration story
lives in [`docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md`](docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md).
Every ADR, its status and its supersession relationships are indexed at
[`docs/adr/README.md`](docs/adr/README.md).

> **CONSOLIDATION IN REVIEW (2026-08-09; decisions signed 2026-08-10).** `harden/ops-plane`
> merges nine hardening workstreams; a tenth (`harden/otel`) is NOT merged because it is a
> second, incompatible observation plane — and its transport is now **retired**
> ([ADR-014](docs/adr/ADR-014-guard-telemetry.md); branch kept as history, nothing deleted).
> **All four §A owner decisions are signed, and so is the one follow-up that was also an
> owner call (F3).** D1 and D3 on 2026-08-09; D2, D4 and F3 on 2026-08-10: the substrate
> invariant is **amended** ([ADR-022](docs/adr/ADR-022-substrate-invariant-amended-default-not-only.md)),
> the shipped sink default **stays off** ([ADR-013 §7.1](docs/adr/ADR-013-observation-plane-events-and-sinks.md)),
> and ADR-014's transport is retired. **None of those three changed code** — which is the
> point of recording them: a default nobody signed and a default somebody signed look
> identical in a diff. Start at
> [`docs/DECISIONS-FOR-REVIEW.md`](docs/DECISIONS-FOR-REVIEW.md); what remains open is §E
> (what is NOT verified) and §F1/F2/F4.
>
> **What §E still says, because a green test suite invites the wrong inference.**
> Updated 2026-08-14 by [ADR-034](docs/adr/ADR-034-deterministic-capability-enforcement.md):
> the `bash -c '...'` bypass is **narrowed, not closed** — one level of recursion,
> with `python -c`/`eval`/base64/script files deliberately still open. A test that
> drives a real Claude Code process now **exists** but is opt-in, advisory and
> **has not yet been run**, so "enforcement is proven by wiring, not invocation"
> still stands as the published claim. `.baron-rules.yaml` is still parsed-but-never-
> activated (the loader is deferred; the path is now fenced). `baron doctor` reads
> project-level settings only. Runtime neutrality is measured with **two** producers,
> not three. **G1 is unchanged**: an unwired hook is still zero enforcement — the
> layer that would have softened that (`permissions.deny`) was deliberately **not**
> built (OD-2).

## Shipped (unreleased) — P2.2 deterministic enforcement: denial becomes structural (plugin 1.20.0 / CLI 0.18.0, `rules_version` 1 → **2**, [ADR-034](docs/adr/ADR-034-deterministic-capability-enforcement.md))

The backlog's P2.2. **G5**, found by the ADR-034 sweep in merged code: the enforcement
configuration was inside the agent's own blast radius. `evaluate_write` made a persona's own
`agents/<slug>/` always writable and `.claude/settings.json` was an ordinary path, while the
hook re-reads `--persona-file` on *every* invocation — so a persona could **grant itself a
denied verb, or unwire the hook, in one edit**, and the next tool call was adjudicated
against the document it had just written. Every other layer was conditional on that.

**Three layers, not the four the ADR proposed** — see the honest accounting below.

- **L0 — the policy is out of the governed party's reach** (`file_ops.protected_config`,
  `.protected_spec_file`, `.own_spec_dir`). A **structural** refusal at `evaluate_write`
  step 0.5, modelled on the step-0 path escape: no verb unlocks it, so `adjudicated=False`
  and the event reads `unevaluated` ([ADR-018](docs/adr/ADR-018-adjudicated-enforcement-on-the-event.md) §2).
  Fenced: every persona's `persona.yaml` (own included, and including for a holder of
  `edit_other_personas`), the acting persona's own `agents/<slug>/**` entirely,
  `.claude/settings.json{,.local}`, `.baron-waivers.yaml`, `.baron-rules.yaml`,
  `.barony/allowed_signers`. (Those three are `baron rules` **rule ids**, not YAML keys — the corresponding `file_ops:` keys in the artifact are `protected_config_paths`, `protected_spec_files` and `protect_own_spec_dir`.) **A capability change is now a PR a human merges — for
  everyone, always, including the owner working solo.** That friction is the point.
- **L2 — the wrapper class narrowed** (`commands.wrappers`). One level of recursion into
  `bash -c '<payload>'` and the other shell forms, through the **same evaluators** — not a
  second parser. Uninspectable payloads get the artifact's conservative-deny **narrowed to
  `merge_pr`/`push_main`/`force_push`**, so the false-positive cost lands only on personas
  that deny those anyway.
- **L3 — the platform layer, reported and never configured** (`baron doctor` check 10,
  INFO). Branch protection and per-persona push credentials are what could actually make an
  irreversible action impossible, and they are **not baron's** ([ADR-007](docs/adr/ADR-007-session-boundary.md)).
  The networked half is opt-in (`BARON_DOCTOR_PLATFORM=1`) so doctor's exit code stays
  reproducible offline. It also states the ADR-033 §5 distinction rather than blurring it:
  per-persona *signing* keys are not per-persona *push authority*.
- **Proof by invocation — the opt-in tier.** A `PATH`-shimmed `git`/`gh` sentinel drives a
  real `claude -p` in a scaffolded temp repo and asserts the denied operation **did not
  run**. Its negative control is load-bearing: the same prompt runs first against a persona
  that *grants* the verb and the sentinel must appear, or the run reports **INCONCLUSIVE**,
  never PASS — a model that simply declines is FM4's exact shape.

**Honest status of that tier, stated because an advisory gate presented as a gate is this
repo's named failure (OD-3):** it is **opt-in, excluded from default CI, and ADVISORY**. An
INCONCLUSIVE or failing run **does not block a release**. As of this writing it **has not
been run** — the instrument landed, the measurement is still owed. Its harness (shims,
scaffold, kit install) *is* covered in the default job by `test_live_harness.py`, precisely
because a silently-broken shim would make the live test report a false green.

**What did NOT improve.** **G1 is unchanged** — an unwired hook is still zero enforcement.
The layer that would have degraded that to "weaker but non-zero" was `baron init` emitting
`permissions.deny`, and the owner **declined it** (OD-2 = NO): it publishes a
stronger-*looking* posture still evadable by `bash -c`, and not over-claiming is the
differentiator. `test_adapter_omission.py` and the ADR-020 measurement are therefore
untouched. **G3 unchanged** (loader still deferred). **G4 conditionally moved** (instrument
exists; measurement owed).

**Bounds that survive all of it.** A hostile workspace still wins: `~/.claude/settings.json`
is outside the repo root and invisible to L0 and to doctor, and a shell redirect is neither
a write-tool call nor a capability verb — both pinned by tests rather than only written
down. `python -c`/`eval`/base64/script files remain uninspected. Credentials are not
revoked. Positioning is unchanged: **a deterministic policy guard at the agent-tool
interface for cooperating agents, not a security boundary.**

Tests: `cli/tests/test_guard_l0.py` (16), `test_guard_wrappers.py` (31 — half of them
pinning what still gets through), `test_live_harness.py` (5), plus doctor/rules/pydantic-ai
updates. 806 pass, live tier deselected.

> **Reading the "Shipped (unreleased)" sections below (2026-08-14).** Every one of them is
> merged on `main` and none of them was tagged — they accumulated between v1.10.0 and now.
> They are **all** contents of the prepared **v1.19.0** release (see the Shipped table and
> `CHANGELOG.md`); the headings are left as written rather than retitled in bulk, because
> the version markers inside each one (`plugin 1.1x.0 / CLI 0.1x.0`) are what a reader
> chasing a specific `pip install` needs. "Unreleased" here means *not yet tagged*, not
> *not yet merged*.

> **ADR ratifications, 2026-08-14.** The owner accepted **[ADR-028](docs/adr/ADR-028-mechanized-merge-gate.md)**
> (mechanized merge gate) and **[ADR-030](docs/adr/ADR-030-observer-archetype.md)** (the
> `observer` archetype). Both shipped while still marked *proposed* — live on `main` since
> CLI 0.11.0 and 0.13.0 — so this changes the **record**, not the behavior, and neither ADR
> was rewritten. ADR-028 §4's account of the attribution hole stands exactly as written: it
> is the reasoning ADR-033 was built on, and an ADR that edits away its admitted gaps is
> worth less than one that leaves them visible.
>
> **Still shipping in v1.19.0 while proposed:** [ADR-031](docs/adr/ADR-031-governed-memory-eval-harness.md)
> (`baron memeval`) and [ADR-015](docs/adr/ADR-015-baron-export.md) (`baron export`). Two
> records remain ahead of their signatures, not zero — worth saying plainly, because
> "ratified two" reads like "closed the gap" and it did not.

## Shipped (unreleased) — the signed-verdict default is keyed to reviewer enrollment (plugin 1.19.0 / CLI 0.18.0, [ADR-033 §7 Q1](docs/adr/ADR-033-signed-review-verdicts.md) RESOLVED)

**Owner decision, 2026-08-14: APPROVED — default-ON once a reviewer persona is enrolled,
warn-only before enrollment.** ADR-033 shipped `--require-signed-verdict` off and left the
trigger to the owner; none of its three candidates (a manifest field, a flag day, `baron
doctor` readiness) was chosen. Enrollment is the trigger because it is the fact that
decides whether a signature was *possible*: before a reviewer's key is in
`.barony/allowed_signers`, nothing could have signed, so refusing would punish a project
for a capability it does not have. After it, the project opted in — by an **owner-merged**
commit, which is what makes this a default somebody signed (ADR-013 §7.1).

- `merge.resolve_signed_posture()` reads enrollment **at HEAD**, never the worktree — else
  any persona could flip the fleet's merge posture by editing a file it already controls.
- Both halves required: an enrolled key **and** an `archetype: reviewer` persona behind it.
- `--require-signed-verdict` / `--no-require-signed-verdict` override in both directions.
- The posture and its trigger print in the `verdict_signed` detail line on every run.

**Bound, unchanged:** enforcing that a signature is *present* does not make the verdict
*correct* (ADR-024's escape-rate axis), a hostile workspace holding the reviewer's key can
still sign anything, and this is still the evidence half of the autonomous merger, not the
authority half. There is still no `baron merge do`.

## Shipped (unreleased) — docs coverage becomes a pipeline step (`tests/check_docs_coverage.py`)

`CONTRIBUTING.md`'s "docs land with code" rule was prose from 2026-06-03 to 2026-08-14, so
it held as well as whoever remembered it. CI now warns when a PR changes `cli/` or
`skills/` but touches neither `CHANGELOG.md` nor `docs/`.

**Advisory on purpose, and it says so everywhere it appears.** It sees that a file changed,
not that the change describes what shipped; its false positives (refactors, test-only
fixes) are legitimate. A gate that cries wolf teaches people to click past it. `--strict`
is the one-line escalation to make once there is evidence the warning is being ignored
rather than answered. `CLAUDE.md`'s release workflow additionally gates on
`docs/product-overview.md` and `docs/capability-value-map.md` being reviewed, and now
records the owner-only PyPI publish step.

## Shipped (unreleased) — signed review verdicts (plugin 1.17.0 / CLI 0.17.0, [ADR-033](docs/adr/ADR-033-signed-review-verdicts.md), supersedes [ADR-028](docs/adr/ADR-028-mechanized-merge-gate.md) §7 Q4)

The reviewer SSH-signs its verdict into `.barony/verdicts/`, and `baron merge check`'s new
**`verdict_signed`** precondition verifies it offline against `.barony/allowed_signers`. Four legs:
the signature verifies; the **signed content** binds (repo, PR, sha) so a valid signature cannot be
replayed by copying the file; the signer is a `reviewer`-archetype persona; and the signer is **not
the persona that signed the head commit**. **Reviewer≠author is now a property of the repo**, not a
rule in a persona file.

New: `baron review sign`, `baron review verify`, `--require-signed-verdict`, `--code-repo`. Built on
ADR-027 §2.3 — no new key, no new registry, no new trust root. The PR comment is demoted to an index
(the ADR-008 §1 move, one level up).

Posture follows ADR-027 §7.3: an invalid signature always refuses; a missing one warns by default
and refuses under `--require-signed-verdict`, because turning absence into a refusal is a fleet-wide
breaking change that should be signed rather than defaulted. *(Amended 2026-08-14: the owner signed
it — a missing signature now refuses once a reviewer persona is enrolled, warn-only before. See the
§7 Q1 section at the top of this file.)*

**What it does NOT do — the sentence most likely to be misread.** It closes the **evidence** half of
the autonomous merger, not the **authority** half: merging still means acting under the owner's
token, so `baron merge check` stays owner-in-the-loop and there is still no `baron merge do`
(ADR-033 §5). Nor does it defend against a hostile workspace, or make a verdict *correct*.

Tests: `cli/tests/test_signed_verdict.py` (23), real `ssh-keygen` + real git signing.

## Shipped (unreleased) — identity onboarding commands (plugin 1.14.0 / CLI 0.14.0, [ADR-027 §7.5](docs/adr/ADR-027-agent-identity.md) amended)

## Shipped (unreleased) — identity onboarding commands (plugin 1.15.0 / CLI 0.15.0, [ADR-027 §7.5](docs/adr/ADR-027-agent-identity.md) amended)

`baron identity register | enroll | protect` mechanize the three owner steps of
`docs/runbooks/identity-signing.md` — register a persona's public key as a GitHub **signing**
key, open the `.barony/allowed_signers` enrollment PR, and create the `main` ruleset (signed
commits + required `verify-identity` + code-owner review, rebase-merge excluded).

**The trust boundary is unchanged, and that is the load-bearing claim.** All three are
**dry-run by default** — they print the exact `gh` argv and payload and exit; `--apply` is the
only thing that executes. All three run under the operator's existing `gh auth`: baron accepts,
reads, stores and prints **no token**, so no forge credential is introduced (ADR-027 §2 holds).
`enroll` opens the **request** and stops — there is no `--merge` flag, because a persona that
could approve its own enrollment could mint peers (§7.2). `register`/`protect` remain owner
actions; `baron identity init` is still the only agent-run step.

Tests: `cli/tests/test_onboard.py` (24), all against a recording fake — nothing reaches a live
account, by design rather than by mocking discipline.

## Shipped (unreleased) — P3.3 `baron memeval`: the governed-memory eval harness (plugin 1.14.0 / CLI 0.14.0)

[ADR-031](docs/adr/ADR-031-governed-memory-eval-harness.md). `baron memeval --fixtures
evals/governed-memory` materializes a labeled corpus into a throwaway git repo, walks it with
the **existing** `baron export` producer, and scores each approach on all eight metric families
3.3 names. The fixture set covers 3.3's case list (routine commit, release,
accepted/proposed/parked/superseded ADR, thesis-changing finding, duplicate event,
bad/missing source SHA) and a test fails if a case goes missing. No new dependency.

**Baseline numbers, 22 citable records, k=5** — measured, reproducible, and *on fixtures*:

| approach | prop. P / R | dup suppr. | schema / path / status | R@5 | MRR | fresh | cite | tax |
|---|---|---|---|---|---|---|---|---|
| `git-markdown` | 66.7 / 75.0 | 50.0 | 0.0 / 100 / 50.0 | 76.0 | 81.2 | 100 | 100 | 33.3 |
| `hooks` | 100 / 100 | 100 | 100 / 100 / 100 | 76.0 | 81.2 | 100 | 100 | 6.7 |
| `semantic`, `hooks+semantic` | **NOT MEASURED** — no retriever registered; the harness estimates nothing it did not measure | | | | | | | |

**The finding, and it is not the expected one.** On the flagship fixture — this repo's own
2026-08-04 identity incident — the lexical baseline retrieves **every in-corpus gold record,
first at rank 1**. Its only miss is the survey note, which `baron export` never walks. The
binding constraint on this corpus is **coverage, not ranking**, which argues 3.4's first move
is widening what gets exported (curated status; research notes outside the four corpora)
rather than adding embeddings to the same 22 records. A second measured cost: one labeled
query is unanswerable because its answer sits in an uncommitted file — the ADR-015 citation
gate, priced instead of assumed.

**Honest bounds** (ADR-031 §4, and printed in the output as `honesty_bound`): this measures
fixtures, not a live repository or a running fleet. The `hooks` row is partly definitional —
its rule table mechanizes the same policy the gold labels come from, so read its duplicate
suppression and bad-SHA columns and discount the rest. 22 records is a small corpus and small
corpora flatter literal search; the vocabulary-mismatch probe (Q2) failed to defeat term
overlap and is reported as measured rather than corrected by rewriting the corpus. No latency
or scale metric is collected, so 3.4's "or scale benefit" clause is untouched.

**Still deliberately not built, asserted by test:** no knowledge backend, no `baron.knowledge`
entry-point group, no vendor named or run, no new runtime dependency. The seam for the two
semantic approaches is an in-process dict (`memeval.RETRIEVERS`), not an entry-point group —
ADR-015 §4's rule is not repealed by shipping 3.3.

## Shipped (unreleased) — the prior-art gate: `baron adr check` (plugin 1.12.0 / CLI 0.12.0, [ADR-029](docs/adr/ADR-029-prior-art-gate.md))

**Accepted 2026-08-14.** Barony's own thesis (*instructed → enforced*) applied to its own
governance process, on a first-party incident: an ADR-027 session re-derived an identity design
a **2026-08-04 vault spike had already decided against**. The prior art was written down and
findable; nothing in the ADR path ever asked whether it had been consulted.

Two rules — **(a) one canonical home** (a decision is canonical only once promoted to an
accepted ADR here; vault notes are inputs) and **(b) a recorded prior-art sweep** on every ADR
reaching `status: accepted`. Rule (b) is mechanized: **`baron adr check [docs/adr]` is
fail-closed** — missing/malformed block, empty `searched:`, a required corpus unsearched, an
omitted `hits:` key, or a malformed hit all exit **1**. Rule (a) is instructed, and §6 says so.

Landed with it: `docs/adr/ADR-TEMPLATE.md` + the emitted `decisions/ADR-TEMPLATE.md` (so
`baron init` scaffolds the section), step 0 of the `CONVENTIONS.md` decision/ADR-intake rule,
the `COORDINATION.md` ADR rules, `baron adr scaffold`, 40 tests, and a **CI step gating this
repo's own `docs/adr/`** — ADR-029 included, gated by its own rule rather than grandfathered.

**Honest bound (in the record, the README, and the templates):** the gate enforces that a
search was **recorded**, not that it was **thorough**. Recall quality is a separate axis — the
P3.3/P3.4 memory work. It converts "I forgot to check" from silent to blocked, and no more.

**Residual owner-decision points (§8):** ADR-027/028 sit on unmerged branches dated 2026-08-14,
so the gate binds them on merge and each needs a block added (alternative: `--since 2026-08-15`,
which would also exempt ADR-029 from its own rule); whether `vault` is the right *default*
required corpus for emitted projects; whether `status: proposed` should be gated too.

Related, still open: the Irisidian **claims ladder** (2026-08-05) is the other convention
awaiting template promotion — ADR-023 §8 Q2 named a combined `ways-of-working-2026-08` ADR as
the likely host. **This ADR did not absorb it**: the claims ladder is a separate promotion with
its own evidence, and bundling it would have made one decision out of two. The scope call
remains the owner's.
## Shipped (unreleased) — the merge gate: `baron merge check` (CLI 0.11.0, [ADR-028](docs/adr/ADR-028-mechanized-merge-gate.md) ACCEPTED 2026-08-14)

[ADR-028](docs/adr/ADR-028-mechanized-merge-gate.md). P1.3 hardened the `__MERGER__`
templates in **prose**; this moves the checkable half into code. `baron merge check <pr>`
scores four preconditions against one PR snapshot — `pr_open`, `verdict_at_head`
(`reviewed-sha == head`, exact, never prefix-matched), `no_changes_requested`, `ci_green` —
and exits 1 with the failing precondition, a stable reason slug and the sha it checked.
Fail-closed with **no amber**: pending CI, absent CI, an all-skipped check set, an
unrecognized check state, a missing verdict, an unreachable forge — all REFUSE; unreached
preconditions are reported FAILED rather than skipped. Review-state **labels are collected
and printed as ignored, never scored**, in both directions (ADR-008 §1). Wired into the
`__MERGER__` persona template (`persona.yaml` + `AGENT.md`) and
`COORDINATION.md § Review and merge`. 41 new tests: the pass path plus every refusal path.

> **The bound, stated where it cannot be missed** (ADR-028 §4, and printed on every run).
> The gate is identity-*independent* to build and test — it is pure preconditions. **Live
> autonomous merging is not.** Under one shared forge account baron can verify that a
> `REVIEW:PASS` exists at the current head but **cannot verify who posted it** — the dev
> whose code is under review can post its own, and the gate correctly returns 0. So the
> command **verifies and reports; it never merges** (there is no `baron merge do`, per
> ADR-007), and merging stays **owner-in-the-loop** until per-persona forge identity
> (ADR-027) is deployed. `--verdict-author <login>` ships now — useless under one account,
> load-bearing the moment identities exist.
>
> Two of the merger's four preconditions remain unmechanized on purpose: **record
> obligations** (needs a materiality judgement) and **hot-file collisions** (mechanizable —
> the next increment; `baron lock list` is today's answer). Exit 0 means "1 and 2 hold",
> never "merge it", and the command's own output says so.

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

> **Release-tagging gap (noticed 2026-07-31) — CLOSED 2026-08-14.** The gap was real: the
> tag / `gh release create` steps had not run since v1.3.0. They were caught up in a batch
> on **2026-08-02** (v1.4.0 → v1.9.0, all six releases created that afternoon) and
> **v1.10.0** on 2026-08-09, so the newest tag on `origin` is **v1.10.0**, not v1.3.0.
> Everything after it — plugin 1.11.0 → 1.19.0, CLI 0.10.0 → 0.18.0 — is cut as
> **v1.19.0**; see `CHANGELOG.md`.
>
> The lesson that outlived the gap: **the tag is the only record a stranger can check.**
> A CHANGELOG section describing a version nobody can `pip install` or `git checkout` is a
> claim, not evidence. The release-gate checklist in `CLAUDE.md` now includes verifying the
> Shipped table against `git tag` rather than against the CHANGELOG.

## Shipped (unreleased) — `baron export` reaches the whole estate (plugin 1.16.0 / CLI 0.16.0, [ADR-032](docs/adr/ADR-032-export-reach-monorepo-and-widened-corpus.md))

Owner decision #5. Two fixes to the export's **reach**, both about what the walker can see.

**The monorepo silent zero.** At an ADR-025 coordination-monorepo root `baron export` walked
no project subdir and printed `no records`, while per-project runs returned real counts
(measured on a two-project fixture: **0 at the root, 2 + 2 in the subdirs**). Same
silent-false-zero class as the [ADR-025 §6.8](docs/adr/ADR-025-coordination-monorepo.md)
health bug just fixed, and the exact instance §6.3's generalisation predicted. Now
`collect_portfolio()` walks the `.baron-monorepo.yaml` registry and aggregates, keeping the
**same payload shape** so `jq '.records[]'` does not fork per topology. Per-project provenance
rides on each record (`project`) and on `projects[]`; unregistered subdirs are reported, not
swept in; one unwalkable project no longer zeroes the portfolio. The primary key became
`(project, kind, id)` — the old `(kind, id)` would have called the second project's `ADR-001`
a duplicate and dropped its whole corpus, trading a silent zero for a silent halving.

**The widened corpus, behind `--wide`.** `status` (`wiki/status.md`, `STATUS.md`) and `note`
(`wiki/`, `docs/notes/`, retargetable via `--note-dir`) join the four ledgers — six kinds
available, four by default (`DEFAULT_KINDS == LEDGER_KINDS`). **ADR-032 §3.1 was amended at
integration** to make them opt-in: as written they were on by default, decided while ADR-031
was unmerged and the export had no consumer in the tree. It has one now — `baron memeval`
calls `collect()` with no kinds — and on the integrated stack a six-kind default moved its
pinned numbers (MRR 81.2 → 68.8, citation 100 → 94.4) and failed three `test_memeval.py`
assertions while delivering no ceiling gain. The capability ships whole behind one flag. This
**supersedes [ADR-015](docs/adr/ADR-015-baron-export.md) §7**'s "curated status is not
exported — deferred rather than guessed at" and closes 3.4's own corpus list. It acts on
**[ADR-031](docs/adr/ADR-031-governed-memory-eval-harness.md) (P3.3)**'s measured finding that the retrieval miss was **coverage, not
ranking**: the lexical baseline already retrieved the flagship gold record at rank 1, and its
only miss was a `wiki/` research note the exporter never walked. The citation gate is not
relaxed for the new kinds — an untracked note is skipped and named exactly like an untracked
handoff.

**Measured against the P3.3 fixtures, under `--wide`** (ADR-031 has since merged, so this is
now directly reproducible — but it also needs §4.3's two harness fixes, which are a follow-up
on `main`; without them `--wide` measures 84.4 / 76.0 / 68.8 / 94.4): 22 → 23 records, retrieval
ceiling **84.4% → 87.5%**, R@5 **76.0 → 79.2**, and the flagship query's permanently
unreachable gold record becomes reachable (`unreachable: []`). **MRR fell 81.2 → 75.0** —
reported rather than suppressed: widening a 22-record corpus adds competition, and the note
that closes one query's gap crowds another's top slot. Whether a semantic layer recovers
precision-at-1 *while keeping* the coverage is now a well-posed question for P3.4, which it
was not before.

> **Two items this hands to `main`** (ADR-032 §4.3), now that ADR-031 has merged and they are
> the prerequisite for ever flipping the default. ADR-031's harness hardcodes its
> producer's vocabulary in two places — the gold label `wiki:research-agent-identity-lightweight`
> (the shipped record is `note:wiki/research-agent-identity-lightweight`) and
> `_citation_holds`'s closed kind allowlist `("adr", "handoff")`. Run unmodified against a
> six-kind export they report a producer *improvement* as a regression (MRR 68.8, citation
> 94.4) — measured, which is why the default was amended to four. Both are one-line fixes.

**Still deliberately not built:** no semantic backend, no `baron.knowledge` entry-point group,
no vendor, no new dependency. ADR-015 §4.2 / ADR-022 §5.1 are untouched and their three guard
tests stay green and unrelaxed.

## Shipped (unreleased) — P3.4 (partial) `baron export`: citable records

[ADR-015](docs/adr/ADR-015-baron-export.md). `baron export [--kind …] [--json]` walks
`docs/adr/`, `decisions/index.md`, `findings/index.md` and `_handoff/**` into flat records
carrying `{id, kind, title, path, commit_sha, status, body, links, meta}`. **The citation gate
is the substance:** a source that is untracked or dirty is skipped and named rather than
emitted with a SHA that resolves but returns different text, so `git show <sha>:<path>` always
reproduces a record's bytes. That discharges 3.4's "every retrieval result must carry
path + commit SHA" independently of any backend. Measured: 284 records out of
`baddie-analyzer-collab` (62 decisions / 62 findings / 160 handoffs), all 284 citations
verified by byte-equality (`git show <sha>:<path>` vs disk, 0 mismatches). No new dependency;
still typer + pyyaml.

**Deliberately not shipped:** the backend contract interface, a `baron.knowledge` entry-point
group, and any semantic-memory adapter — 3.4 is gated on 3.3 (**shipped 2026-08-14**, ADR-031;
the gate now exists and 3.4 has to pass it), and an
entry-point group with no consumer is unretractable public API (ADR-015 §4). **Nothing about
the candidate vendor was run** — public docs read, no ingest, no retrieval, no measurement.

> **~~OWNER DECISION OUTSTANDING~~ — RESOLVED 2026-08-10
> ([ADR-022](docs/adr/ADR-022-substrate-invariant-amended-default-not-only.md)).** Semantic
> memory is a **rebuildable projection** — answer (a). The *authoritative* mode is refused.
> **Product-vision invariant #1 was amended in the process:** git + markdown is now the
> **DEFAULT** substrate and plugins may extend it to other suitable platforms, **bounded** by
> *governance state stays complete in git* — "who may do what", "who did what" and "what is
> true now" stay answerable from the repo alone; a plugin may be authoritative for derived or
> auxiliary domains, never for authority, evidence or the ledger. **Nothing is authorised to
> be built:** no adapter, no `baron.knowledge` entry-point group (its test stays green), 3.4
> still gated on 3.3, and still nothing about the vendor has been run.
## Shipped (unreleased) — `baron doctor`, the guard wiring self-test ([ADR-017](docs/adr/ADR-017-baron-doctor-wiring-selftest.md))

Closes the first and highest-value checkbox of the `baron guard` hardening list from the
2026-08-01 source-level validation. The badminton-analyzer incident merged 15 PRs under a
persona denied `merge_pr`, and nothing had failed — the hook had never been wired into
`.claude/settings.json`, so the denial degraded to persona text **silently**. `baron doctor`
runs nine read-only checks (executable resolves · PreToolUse hook present · matcher covers
every governed tool · persona parses · rules artifact loads · **a synthetic denial fed to the
executable the hook names really exits 2** · malformed stdin fails closed per ADR-004 §2.3 ·
`BARON_GUARD_OVERRIDE` not exported · override log writable, INFO-only) and **exits 1 on any
FAIL**, each with a remedy line. `--json` for CI and audit reports.

**Honesty boundary, printed on every run including green ones:** doctor verifies **WIRING,
not invocation**. It proves the install *can* enforce; it cannot observe whether Claude Code
actually ran the hook, because nothing outside the runtime can. Implying otherwise would
manufacture the same false confidence that produced the badminton merges. Two scoped
non-goals, both deliberate: evidence checks are INFO and never FAIL (enforcement is
fail-closed, evidence is fail-open), and only project-level settings are read — a hook wired
in `~/.claude/settings.json` reads as FAIL, because a verdict that depends on the developer's
home directory is not a property of the repo.

**Two narrower bounds, also in the output** (ADR-017 §3.2a, §3.5). Checks 6–7 *spawn the
hook's own command* — `uv run`-style wrapper prefixes included — instead of calling the
`baron` module doctor imported: a project wired to a stale or hand-rolled `baron` is the
badminton shape, and an in-process probe is blind to it by construction. Where the hook names
no resolvable executable doctor falls back in-process and says so, and that PASS is scoped to
the library rather than to the hook's command (`probe_mode` in `--json`). And a *bare*
executable name is resolved against **doctor's** PATH, not the runtime's, so `cli-on-path`
for that shape is a property of the invoking shell — the same non-reproducibility that keeps
`~/.claude/settings.json` out of scope.

## Documented (unreleased) — 2026-08-08 evaluation close-out, no code change

Two "gaps" from the 2026-08-08 Barony/Nasiko evaluation were already decided; the deliverable
was recording that honestly rather than re-deriving them (the note's own CORRECTIONS block
¶2 names re-derivation as its documented failure mode).

- **Fail-open vs fail-closed on hook failure** — settled since **ADR-004 §2.3** and
  implemented in `guard.process()`'s two DENY paths. No new ADR. The 2026-08-08 hands-on run
  measured it empirically; it is now pinned per-install by doctor's `fail-closed` check and by
  `test_doctor.py::test_fail_closed_policy_is_pinned_adr_004_s2_3`.
- **`open_pr` / `run_tests` denial parsing** — remains DEFERRED as of 2026-08-09 with no
  observed-need evidence anywhere in the repo or the evaluation (vocabulary design rule 4;
  ADR-004 §2.2). Still deferred, still pinned by
  `test_rules.py::test_open_pr_and_run_tests_stay_unparsed_deferred`. (`rules_version` moved
  to **2** on 2026-08-14 for ADR-034's L0 fences and wrapper recursion — neither touches
  these two verbs; the deferral is a statement about DETECTION, not about the integer.)
- **Lock soft-timeout sweep** — still open and correctly so: folding locks into `baron status`
  crosses the recorded "status reads local git state only, never the forge" deferral, so it
  needs its own ADR first. Shape recorded in `docs/BACKLOG.md`.

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

## Shipped (unreleased) — the coordination monorepo (ADR-025)

`baron init --layout monorepo` + `baron add-project <name>`, per
[ADR-025](docs/adr/ADR-025-coordination-monorepo.md) and its §7 owner answers. A second
**topology**, not a new tier: one collab repo whose projects are subdirs, each an ordinary
Barony project. **Per-project-repo remains the default** (Q4) — a monorepo cannot grant
per-project access, and that is a blocker for the multi-tenant case, so isolation stays the
thing you get without asking.

The portfolio tier is itself a project: the `_meta` subdir, no code repo, work items are the
cross-project decisions. `baron status` / `baron health` go portfolio-wide at the root and are
unchanged inside a project; `baron validate .` already recursed and now also **warns on a
manifest-carrying subdir the marker does not list**, because a portfolio read would otherwise
skip it silently. The wake carries `project` and the root's gate `cd`s into that subdir (Q2) —
`paths:` cannot scope a `repository_dispatch`, so the `cd` is the scoping; authorization is
unchanged and still reads the committed handoff, never the payload. Identity survives as
`<slug>@<project>.local` (Q3).

**Three design calls the ADR left open, made here and recorded in `monorepo.py`:** the root
marker is a *file* (`.baron-monorepo.yaml`) rather than a root manifest, since the root is not
itself a project; **subdir name and project name are separate fields** so the `_meta` subdir can
carry the project name `meta` (that name becomes a hostname); and the registry is *declared and
discovered*, so an unregistered subdir is reported rather than silently included or ignored.
The control-plane pilot is the natural first `_meta` — not built here.

**Dogfood-hardened 2026-08-14 ([ADR-025 §6](docs/adr/ADR-025-coordination-monorepo.md)).**
`fleet-coordination` was stood up for real, with Barony grafted in as its first non-`_meta`
project. It found six defects, two of them critical, and both criticals **failed silently
upward**: `add-project --code-repo <url>` emitted a path that resolved back to the project
subdir, so `baron status` reported a code repo **green** that had never been cloned; and no
`notify:` block was emitted at all, so a grafted project could never be woken and the manifest
gave no hint why. Fixed, with `baron adopt-project` added as the migration path that
`add-project` structurally could not be.

The generalisation worth keeping: none of the six argue against projects-as-subdirs. Every one
is code written when *the collab repo* and *the git repo* were the same directory, run where
they are not. §2's "a monorepo subdir is an ordinary Barony project" holds for the **data** and
fails for anything that shells out to git or assumes its own nesting depth — so that is now the
audit boundary for the next command that goes portfolio-wide.

**Stage 2 found one more by applying that boundary — fixed ([ADR-025 §6.8](docs/adr/ADR-025-coordination-monorepo.md)).**
`baron health` **wrote** verdicts to the
git top-level (where the disk sink puts the plane) and **read** them from a `.baron/events` join
onto the project subdir. Measured in the dogfood: `verdict.read(<root>)` → 1 row,
`verdict.read(<root>/barony)` → 0. So an approved verdict sat on disk while health printed `0
verdict(s)`, reassured that a project recording no verdicts shows a clean board, and advised
enabling a sink already enabled — a false green of the same class as the `--code-repo` aliasing
bug, invisible in single-project layouts because there the collab dir *is* the git top-level.
Write and read now share one resolution (`sinks.disk.events_dir`); the portfolio rollup reads
the shared plane **once** rather than once per project (which would have replaced the false zero
with an N× false total); and the report names the plane it read, so a zero is attributable.
ADR-024 §5's honest bound is untouched — health still measures what was **emitted**; this was
about reading what was.

**Still open — persona-name collisions (ADR-025 §6.7).** Default slugs
(`dev`/`reviewer`/`merger`/`librarian`) collide when two projects share one monorepo clone and
a runtime resolves personas globally. Deferred to its own ADR/PR: the fix spans the persona
spec, all four adapters and the drift checker. Workaround: per-project slugs.

## Shipped (unreleased) — the persona sidecar (ADR-026, launcher form)

`baron sidecar run <persona>` plus a per-persona `agents/<slug>/sidecar.sh` emitted by
`baron init` — [ADR-026](docs/adr/ADR-026-persona-sidecar.md)'s launcher half, which the owner
chose over containers-first ("the cheap proof"). One cycle is sync → sweep → invoke → land,
composed from `baron session start --sync` and `baron session end` rather than new machinery;
the badminton `fleet-runner`, generalised and emitted.

**Two things carried over from the hand-built runner deliberately.** The **idle guard** — no
addressed handoff and no labelled backlog item means the runtime is never invoked — because the
runner's cheapest win was not waking a model for nothing. And **the model invocation is the
project's**: `--cmd` / `$BARON_SIDECAR_CMD` / the emitted script supply it, and a cycle without
one is a usage error, never a default. ADR-007 is visible in the surface, not just the prose.

`runtime.trigger` decides the loop form (§6 Q2): `interactive` refuses `--watch` (that loop is
the human's session), `event` is spawned by the ADR-010 wake, `cron` is scheduler-driven or
self-paced. A watching sidecar re-reads git as truth every cycle — stateless per task, so
audit-by-diff survives a process that outlives one unit of work (§4). Containers stay deferred
per the ADR. The per-persona signing keys its identity answer (§6 Q4) waited on are **no longer
deferred** — see the next section; §6 Q4 is superseded by ADR-027.

## Shipped (unreleased) — agent identity (ADR-027, plugin 1.11.0 / CLI 0.10.0)

Per-persona **SSH signing keys**, generated at spawn, enrolled once into an in-repo
`.barony/allowed_signers` file, verified offline with `git verify-commit` —
[ADR-027](docs/adr/ADR-027-agent-identity.md), promoting the 2026-08-04 vault spike whose
trigger was an un-onboarded Codex agent committing to `main` under the owner's identity.

`baron identity init` generates the key, configures repo-local git signing, emits an enrollment
**request**, and **refuses to let the persona work** (exit 1) until the owner has merged that
request at HEAD. `baron verify identity` is the CI gate: signature ↔ trust status `G` ↔ the
three-way cross-check (signer principal ↔ claimed persona ↔ `persona.yaml` registry entry),
which closes the `from:` misattribution class as well as the anonymous-commit class. `baron init`
scaffolds the registry, `.github/CODEOWNERS` and `verify-identity.yml`. Handoffs and findings get
detached `ssh-keygen -Y sign` signatures; an unverifiable one is **refused and recorded as a
finding** at ingest.

**Agents still push under the owner's forge identity** — attribution is the KEY, not an account.
No per-persona PATs, machine accounts or GitHub Apps: the spike surveyed and rejected both for
this problem (a separate, heavyweight *authorization* question).

**Not done, and it is the owner's to do** (`docs/runbooks/identity-signing.md`): registering each
public key as a signing key on the GitHub account, the `main` ruleset (require PR + the
`verify-identity` check + signed commits, and **no rebase-merge** — it adds head-branch commits
to the base unverified), and filling `CODEOWNERS`. Until then `.barony/allowed_signers` is empty,
which is fail-closed, and nothing verifies.

**Honest bound**, in the ADR and in every command's output: attribution among **cooperating**
agents. The private key is unencrypted in the agent's workspace, so this does not defend against
a hostile actor with write access there — the same bound as `baron guard`.

**Residual owner decisions surfaced rather than assumed** (ADR-027 §7): key location under
containers, whether enrollment may ever be delegated to a trusted persona (shipped human-only),
whether a missing handoff signature should refuse (shipped off), and whether `baron guard` should
refuse for an unenrolled persona at every tool call rather than only at spawn.

## Shipped (unreleased) — P2.1 `baron decision` (park only, CLI 0.8.0)

`baron decision reconcile --park` / `baron decision check`, per
[ADR-009](docs/adr/ADR-009-baron-decision-reconciliation.md) with the owner's scope call
(2026-08-02: `park` alone — the obligation that caused FM6). Obligations live in a
marker-delimited block inside the decision's own `decisions/index.md` entry; a park discharges
only when an agent's backlog query stops returning the item (closed/absent, or labelled **and**
declared via the new `manifest.backlog.park_label`, schema v1.3). "Labelled and commented" is
explicitly not enough — that is the state D57 recorded for the epic it left open. All five
`check_backlog` renderers now exclude parked items. `supersedes` / `broadcast` /
`direction_doc` remain designed and unbuilt.

## Superseded by the above — P2.1 `baron decision` design
## Accepted, not yet implemented — P2.5 `baron notify` design

[ADR-010](docs/adr/ADR-010-baron-notify-wake.md) (**accepted with changes**, Vikram 2026-08-02 — no
code yet) designs the FM1/FM5 wake mechanism. Key call: **no new mailbox** — `_handoff/` already is
the delivery surface, so `baron notify` is an ordinary handoff plus a `repository_dispatch`,
**ordered** — commit, push, then dispatch, and no dispatch if the push fails. A failed *dispatch*
still leaves a pushed message that arrives on the next spawn; the converse does not hold, which is
why the order is load-bearing. ADR-007 boundary held: baron fires the event; the spawn lives in a
project-owned workflow slot. Loop-safety guards specified up front.

**All eight §8 questions are answered and recorded verbatim in the ADR**; implementation is
unblocked. The owner's substantive departures from the draft: the pilot's 15-minute cron drops to
hourly/daily as a **slow backstop** rather than being retired (§5.3's silent-no-op paths — missing
PAT, missing workflow, rate limit — are real, so something must still catch a wake that never
fired), and a **manifest allowlist** gates who may fire a wake — enforced **in the workflow**, in the
collab repo, against the **committed handoff** rather than the dispatch payload (2026-08-04): a
payload is written by whoever fires it, and `github.actor` cannot tell personas apart under the
single-account constraint. A two-job gate/spawn split keeps a refused wake to one short job
(§5.5). Dropping the mailbox stands;
adversarial review upheld it independently. Sequencing answer was "build everything, sequenced by
dependency," so this no longer competes with P2.2 / P2.4 / P3.1 for a slot.

## Shipped (unreleased) — observation plane: `baron.events` + `baron.sinks` (ADR-013)

One `Event` shape for guard verdicts, session boundaries, ledger writes, decisions and tool
outcomes, plus a three-member `Sink` Protocol and the `baron.sinks` entry-point group
(mirroring `baron.forges`). Built-ins: `null` (**the default** — baron writes nothing unless
`BARON_EVENTS_SINK` says so) and `disk` (append-only, date-rotated JSONL under
`.baron/events/`, stdlib `json` only per ADR-003).

**Honest bounds, stated up front.** Enforcement stays fail-CLOSED; emission is deliberately
fail-OPEN and silent, because a full disk inside a PreToolUse hook would otherwise meet
guard's fail-closed policy and deny every tool call. Events are **observation, never
enforcement** — nothing on this path can change a verdict, and a test pins both guard exit
codes with `events.emit` raising. `.baron/events/` is gitignored while
`.baron/guard-override.log` stays **tracked**: overrides are evidence, events are telemetry.
No OpenTelemetry dependency — the row shape is what `ingest_otel.py` already parses, verified
by a test that re-derives its key lists. That compatibility needed a consumer-side fix to be
safe: the shared join keys made an older ingester read baron's evidence as agent activity, so
ingester v1.1 partitions baron rows out of the activity plane before sessions are built
(ADR-021, with the measured contamination). Anything reading `.baron/events/` should check
`telemetry_metrics_version`.

Only **one** call site is wired (guard's verdict path); ledger, session and decision have the
contract available and adopt it on their own schedule. The `events:` manifest block is
declared in the schema (canon v1.3) so it does not warn, but **no command reads it** —
wiring it means measuring a manifest parse on guard's per-tool-call hot path, which is a
follow-up with its own ADR.

**`baron.enforcement` was measurably wrong and is now fixed
([ADR-018](docs/adr/ADR-018-adjudicated-enforcement-on-the-event.md)).** It derived its value
from the rules artifact's `detection` field, which describes a *verb* rather than *this
evaluation*: a `..`-escape deny read `enforced` (structural — every persona refused
identically) and a `write_code` allow read `not-applicable` (a real persona-dependent
adjudication). It is now a per-call observation read off an explicit `Decision.adjudicated`
flag set at all eleven return sites, with the vocabulary `enforced` | `unevaluated` |
`unknown`. `instructed` was removed from the event — it asserts a control a PreToolUse hook
cannot measure — and is **unchanged** on the posture surface (`baron rules list`). **Consumer
caveat:** `baron.capability.verb` can be non-empty on an `unevaluated` row, so verb-level
aggregation must filter on `baron.enforcement == "enforced"` first.

## Shipped (unreleased) — the plane is measured runtime-neutral ([ADR-019](docs/adr/ADR-019-runtime-neutral-event-plane.md))

The event vocabulary was runtime-neutral by design from the start, which makes neutrality an
intention rather than a fact while only one runtime writes to it. It is now a measurement:
the pydantic-ai adapter's in-process `before_tool_execute` seam is a **second producer** on
the same plane, reaching it through one public function (`guard.observe_decision`) and reusing
ADR-018's `adjudicated` semantics verbatim. Driven with the same persona and the same command,
the two runtimes append to the *same* log file and their rows differ in exactly four
attributes — `baron.runtime`, `baron.trigger`, `tool.name` and `session.id`; verdict, verb,
enforcement label, actor and subject are identical.

**Honest bound, and it is the whole point of the number.** Two producers falsifies "the plane
is Claude-Code-shaped". It is **not** proof the shape fits every runtime. **code-puppy has no
pre-tool seam**, so it emits nothing and is deliberately absent from `guard.KNOWN_RUNTIMES` —
a post-hoc producer would put rows on the plane implying an adjudication that never happened.
`test_known_runtimes_is_the_landed_set_and_code_puppy_is_absent` pins the tuple so it grows
with a landed adapter and never with an intention.

**Breaking change, taken knowingly:** `baron.hook_event` is renamed `baron.trigger` **with no
alias**. Accepted on the same grounds as ADR-018's label change — the default sink is `null`
and no consumer exists — and that argument expires the moment the default flips.

## Shipped (unreleased) — read-verb posture on four measured adapters ([ADR-020](docs/adr/ADR-020-read-verb-posture-measured-on-four-adapters.md))

Owner decision **D3**, executed. `baron rules list` prints `instructed` for `read_code` and
`read_collab`; **the printed label does not change here — its basis does.** It previously
rested on one instrumented adapter (`pydantic-ai`) and spoke for four. All four now carry a
measurement: `claude`, `code-puppy` and `generic` statically (an A/B on two persona specs
identical but for the two read verbs, asserting every machine-readable artifact is
byte-identical across the pair), `pydantic-ai` on its pre-existing live gate. All four are
negative, so `enforced` was not honestly restorable.

**The bound is exact and travels with the label** (`rules.LABEL_CAVEAT` is built from
`rules.READ_VERB_MEASUREMENTS`, so it cannot drift from the evidence): *baron emits no
mechanism capable of omitting the read tools* — **not** *the runtime cannot enforce them*.
A hand-written `permissions.deny`, or the Tier-3 subagent the `claude` / `code-puppy`
HYDRATE.md recipes tell a human to author, does enforce them, and is outside what
`baron rules list` speaks for. That divergence is recorded in ADR-020 §7 rather than papered
over by editing one table to match the other. Adding a fifth adapter **breaks the label's
basis until it is measured** — asserted by test, which is the anti-drift lock prose could not
provide.

## Shipped (unreleased) — the audit ingester partitions baron's own evidence ([ADR-021](docs/adr/ADR-021-audit-ingester-partitions-observation-rows.md))

`skills/multi-agent-audit/` only; no change to `cli/src/baron/`, because the wire shape is
right and the consumer was wrong. Baron's guard rows share join keys (`agent.name`,
`tool.name`, `session.id`) with agent-activity spans by design, so an older ingester read
baron's *evidence* as agent *activity*. Ingester v1.1 splits guard rows out on the
`baron.outcome` attribute before sessions are built. Measured contamination when a baron
export is paired with `flat_spans.jsonl`: `session_duration_p50_s` 600.0→300.444,
`tool_calls_total` 1→12, the agent roster polluted with two fake personas plus a literal
`unknown`, and `human_turns_total` downgraded `measured`→`inferred`.

**Verified by reverting the fix, not by assertion:** `return records, baron` reverts the
partition and only the partition, and the suite completes with **45 failed checks** — a count
stable across the branch while the denominator grew. The audit skill's tests are also now in
CI, which they never were. Bound: verified against fixtures, **not against a live audit** — no
end-to-end run over a real project's `.baron/events/` exists, because the default sink is
`null` and no project is emitting yet.

## Shipped (unreleased) — externalizable capability rules, step 1 (ADR-016)

The enabling refactor for project-level custom guard rules, plus the audit surface.
`rules.CapabilityRules` was a flat record with one field per built-in rule, which
**structurally cannot hold an additional rule** — so the BACKLOG's "mostly a loader" was
wrong about the blocker. It is now a rule LIST (`CommandRule`/`PathRule`, stable ids, a
**closed** matcher set that refuses an unenforceable rule at parse time, `source`
provenance), with every legacy accessor preserved as a derived property; `guard.py` and
`runtimes/pydantic_ai.py` are **byte-identical** across the change. New
`baron rules list|validate|diff|explain` (all `--json`): `list` labels enforcement in three
honest states (`guard` / `adapter-dependent` / `instructed`) of which only `guard` earns
the word `enforced` — `read_code` and `read_collab` are `adapter-dependent` and label
`instructed`, because the shipped pydantic-ai adapter builds `FileSystem` unconditionally
and a test that hydrates a persona denying `read_code` measures the read tools still
present — and, since **ADR-020**, because the `claude`, `code-puppy` and `generic` kits
emit nothing a runtime reads as a tool allow/deny list either, one static emission
measurement each. Four adapters, four measurements; `rules.READ_VERB_MEASUREMENTS` must
cover `scaffold.ADAPTERS` or the label's basis fails a test. The bound is exact: **baron
emits no mechanism**, not that a runtime cannot enforce these verbs.
`explain` is a dry run of the real evaluators with a test pinning its verdict to
`guard.evaluate_bash`'s `Decision`. The parser refuses unrecognised document content
(unknown rule, unknown key, unknown or wrong matcher, missing built-in rule) rather than
ignoring it.

**Not shipped:** the `.baron/rules.yaml` loader. `validate --file` parses a candidate but
does not activate it — baron still loads packaged rules only. The one-way doors
(add-only/deny-only precedence, supported ranges on both artifacts, refuse-don't-ignore,
cache safety, the `.baron/` vs root-config convention collision) and the separable
project-defined-verbs question are recorded in ADR-016 §5–§6 for their own ADR.

## Shipped — ADR-023 reserved filenames (template promotion)

[ADR-023](docs/adr/ADR-023-reserved-filenames.md) (**accepted 2026-08-12**, no code) promotes a rule about
the framework's own emitted namespace: the config filenames `baron init` writes are governed
artifact types, and a reserved name is scoped to its emitted location — in particular **no
vault-root `COORDINATION.md`**. Driver: a 2026-08-12 Irisidian incident where a prose briefing
at a vault root would have outranked `CONVENTIONS.md` by position alone.

Both owner decisions are **resolved 2026-08-12**:

**(1) The promotion is accepted**, on a **single-incident evidence base** — thinner than ADR-002's
or ADR-008's pilot runs, and argued structurally (`baron init` creates the namespace, so exposure
is universal) rather than statistically. Applied to `skills/barony/assets/collab-repo/CONVENTIONS.md`
and the vendored `cli/src/baron/data/templates/` copy; drift guard green.

**(2) §4.3, the precedence inversion — resolved as (a) refined by (c).** The emitted order stands
(`CONVENTIONS → COORDINATION → AGENT.md`); the **Irisidian vault inverted its chain to match**, and
**both** documents gained the axis that was the real defect: *constraints resolve most-general-wins;
operational detail resolves most-specific-wins.* Rationale: the two orders disagreed most sharply on
the **per-agent file**, and every agent's write zone includes its own workspace — so the vault's
order let a file an agent edits itself outrank the never-list and the claims ladder. Field survey:
both live scaffolded repos carry the template's order verbatim and **no persona `AGENT.md` overrides
a `CONVENTIONS.md` rule**, so nothing downstream depended on the vault's order.

**This reversed rev. 1** of the ADR, which recommended the opposite; the reversal is recorded inline
at §4.3 rather than quietly edited.

**Lint enforcement remains deferred, not rejected (§5)** — the one open lever if a second collision
happens despite the prose rule.

**Residual risk, stated not closed:** in the Irisidian vault, workspace `CLAUDE.md` moved from
**first to last**. The survey covered the collab repos, not every workspace `CLAUDE.md` on the
machine; any agent that was relying on its own workspace file to override a vault rule has lost that
ability — which is the intent, but it was not exhaustively verified as unused.

Related open item: the Irisidian **claims ladder** (2026-08-05) is a *second* convention still
awaiting template promotion. The two could land as one `ways-of-working-2026-08` ADR in the
ADR-002/008 family — deliberately not bundled here (ADR-023 §8 Q2), since that is a scope call
for the owner.


## Parked after owner review — P2.1 `baron decision` design

[ADR-009](docs/adr/ADR-009-baron-decision-reconciliation.md) (**proposed**, no code) designs the
FM6/D57 mechanism ADR-008 §4 named: a ratified decision must reach the work-pull surfaces, not
just `decisions/`. Boundary held from ADR-007 — baron never infers *what* a decision
contradicts; the surfaces are declared input and baron verifies **discharge**. `baron status`
gains a `decision-unreconciled` red. **Owner review 2026-08-02:** the `park_label` read-side
change is **accepted** (§3.2 stands — a park discharges only when an agent's backlog query stops
returning the item), and **P2.3 is built first** (smaller, no schema change). Q1/Q3/Q4 stay open;
this is parked, not rejected.

> **Currency 2026-08-10.** P2.3 shipped (barony 0.7.0, below), so the *sequencing* condition
> is discharged. What holds this is Q1, Q3 and Q4 — three owner answers, not build work. The
> distinction matters for anyone reading the queue: this is no longer "waiting its turn".

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
  mechanisms. **Two preconditions changed in the 2026-08 pass and both matter to whoever runs
  it:** the ingester no longer counts baron's own evidence as agent activity
  ([ADR-021](docs/adr/ADR-021-audit-ingester-partitions-observation-rows.md)), so a paired
  export is now safe — and the sink default is `null` by signed decision, so **the pilot
  emits no rows until an operator turns sinks on**. Run it without that and the number moves
  for no measured reason.
- [x] **Claude Code hook coverage** ([ADR-012](docs/adr/ADR-012-hook-coverage-and-evidence-capture.md))
  — `baron guard` dispatches on `hook_event_name`: `PreToolUse` enforces (unchanged,
  fail-closed), four more events capture evidence (fail-open, structurally unable to block),
  everything else is inert. Correlates by `session_id`. *(At authoring time the event plane
  was an unlanded parallel workstream and this was contract-tested against a double. The
  plane has since landed: the merge canary `test_real_event_plane_matches_the_producer_contract`
  stopped skipping and **caught the divergence it was built for** — ADR-013's `Event` shape
  is authoritative and guard's `emit_event()` is a thin adapter onto it. The double was
  rewritten onto the real signature and re-exports the real `Event` / `KNOWN_KINDS` /
  `FIXED_ATTR_KEYS`, so it cannot drift silently again. What is still true: the producer
  tests use the double's writer rather than `baron.sinks.disk` — real-sink behaviour is
  covered separately by `test_sinks.py`.)*
- [ ] **Merger precondition verification** + guard coverage growth — `docs/BACKLOG.md`.
- [ ] **pydantic-ai adapter field validation** — the adapter is test-proven offline
  (v1.6.0); running a real persona on a real project on this runtime is the ADR-001
  acceptance bar for any adapter — `docs/BACKLOG.md`.

## Shipped

Every row below **v1.19.0** corresponds to a tag that exists on `origin` — verified against
`git tag`, not against the CHANGELOG. The v1.19.0 row is the release this branch prepares;
it becomes true when the owner runs the tag + `gh release create` + `uv publish` steps
(`CLAUDE.md` § Release workflow). Until then it is the only row that is a plan.

| Version | Date | Summary (details in `CHANGELOG.md`) |
|---|---|---|
| **v1.19.0** (prepared, not yet tagged) | 2026-08-14 | **The governance release** — plugin 1.11.0 → 1.19.0, CLI 0.10.0 → 0.18.0 cut as one. Agent identity + SSH signing ([ADR-027](docs/adr/ADR-027-agent-identity.md)) and `baron identity register\|enroll\|protect`; the mechanized merge gate ([ADR-028](docs/adr/ADR-028-mechanized-merge-gate.md)); signed review verdicts ([ADR-033](docs/adr/ADR-033-signed-review-verdicts.md)) **and** its §7 Q1 resolution — enforcement default-ON once a reviewer is enrolled; the prior-art gate ([ADR-029](docs/adr/ADR-029-prior-art-gate.md)); the coordination monorepo ([ADR-025](docs/adr/ADR-025-coordination-monorepo.md)) + `baron adopt-project` + the health-plane fix; the persona sidecar ([ADR-026](docs/adr/ADR-026-persona-sidecar.md)); the `observer` archetype ([ADR-030](docs/adr/ADR-030-observer-archetype.md)); `baron memeval` ([ADR-031](docs/adr/ADR-031-governed-memory-eval-harness.md)); `baron export` monorepo fix + `--wide` ([ADR-032](docs/adr/ADR-032-export-reach-monorepo-and-widened-corpus.md)); the fleet dashboard; the advisory docs-coverage check. |
| **v1.10.0** | 2026-08-09 | Ritual-token coverage gated in the adapters — `ritual-map:v1` across `claude`/`code-puppy`/`generic`, closing the silent-omission gap 1.9.0 left in the three prose surfaces. |
| **v1.9.0** | 2026-08-02 | The pilot-hardening release — 2026-07-31 ways of working ([ADR-008](docs/adr/ADR-008-ways-of-working-2026-07-31.md)): verdict-vs-label, decision reconciliation, `check_review_feedback`, the strip-stale-verdict workflow; plus P2.3 `baron validate` spec↔runtime drift. |
| **CLI 0.5.6** + plugin **1.8.2** (folded into v1.9.0) | 2026-07-28 | Session boundary ([ADR-007](docs/adr/ADR-007-session-boundary.md)) from the pydantic-ai interop eval (enforcement solid, orchestration manual): **no `baron run` driver** — Barony does not own the agent execution loop (orchestration is the runtime's job) — **plus** thin, optional session-ritual bookkeeping primitives `baron session start` (optional `git pull --ff-only`; open handoffs + conventions pointer + backlog location) and `baron session end` (regenerate the handoff index; commit dirty `_handoff/ findings/ decisions/ wiki/` by path with the persona prefix; `baron status` divergence check, exit 1 on red). Bookkeeping only — no agent loop, no model calls; opt-in; not new capability verbs (compose `status`/`handoff`/`indexer`/`gitutil`). pydantic-ai HYDRATE.md gains an optional "composing the session ritual" note (1.8.2; vendored copy re-synced). |
| **CLI 0.5.4–0.5.5** + plugin **1.8.1** (folded into v1.9.0) | 2026-07-28 | **0.5.5:** worktree repair commands (rest of baron M6) — `baron worktree prune [--dry-run]` (wraps `git worktree prune`, clears stale `.git/worktrees/` registrations) + `baron worktree repair [PATH…]` (wraps `git worktree repair`, re-registers a moved worktree/main repo); both admin-only, non-destructive to history. **0.5.4:** interop hardening + backlog burndown from a pydantic-ai dogfood: least-privilege Shell (test-only personas get an allowlisted shell; broad shells deny redirect/pipe operators), guard denies out-of-root writes itself, `RepoContext` wired, `bash -c`/`sh -c` bypass honesty made prominent; `handoff create --body-file`, `handoff close --as`, `BARON_NOW` clock seam, `--author`-vs-git-author docs, version-string fixes. |
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
