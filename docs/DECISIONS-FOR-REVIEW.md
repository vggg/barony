# Decisions for review — the ops-plane hardening consolidation

**Date:** 2026-08-09 · **Revised:** 2026-08-10 · **Branch:** `harden/ops-plane`
· **Suite:** cli **424 passing** (base was 148) · audit skill **265 checks, 0 fail**
· repo lint PASS · bi-runtime acceptance PASS
· **Merged:** 9 workstreams; `harden/otel` retired, not merged (see §D)

Read this file first. It is ordered by *what needs you*, not by what shipped.

> **2026-08-10 — ALL FOUR DECISIONS ARE NOW SIGNED.** D1 and D3 were resolved on 2026-08-09.
> **D2** is resolved by [ADR-022](adr/ADR-022-substrate-invariant-amended-default-not-only.md),
> which **amends product-vision invariant #1**: git + markdown is now the *default* substrate
> rather than the only one, bounded by "governance state stays complete in git". **D4** is
> resolved as *decided, not deferred*: the shipped sink default stays `null`. **F3** is
> resolved: ADR-014's transport is **retired** (recorded in
> [ADR-014](adr/ADR-014-guard-telemetry.md); nothing deleted, nothing merged). Nothing in §A
> is waiting on you. §E (what is NOT verified) and §F1/F2/F4 are unchanged and still open.

- **§A — decisions.** Four. **All four are now RESOLVED** — D1 and D3 on 2026-08-09, **D2 and
  D4 on 2026-08-10.**
- **§B — made during implementation, reversible.** You can wave these through.
- **§C — made during implementation, one-way doors.** Worth a read even if you agree.
- **§D — what did not merge, and why.**
- **§E — what is NOT verified.** The honest bounds.
- **§F — follow-ups identified in this pass and deliberately NOT done.**

Throughout: **enforced** means baron mechanises it, **instructed** means a persona is told
and nothing checks. ADR-002/ADR-008 forbid blurring those, and this file tries hard not to.

### What changed since the last revision of this file

| | Then | Now |
|---|---|---|
| **D1** semantics | BLOCKING, unresolved | **RESOLVED** — ADR-018, both measured defects flip |
| **D1** ingester half | recommended, unmerged | **RESOLVED** — ADR-021 merged |
| **D1** `telemetry.py` | to retire | **RESOLVED 2026-08-10** — retired, ADR-014 · F3 closed |
| **D3** read-verb label | untickable, 1 of 4 adapters measured | **RESOLVED** — ADR-020, 4 of 4 measured |
| **D2** Cognee | BLOCKING | **RESOLVED 2026-08-10** — ADR-022 amends invariant #1; Cognee answered **(a)** |
| **D4** default-on | open, blocked behind D1 | **RESOLVED 2026-08-10** — stays OFF, decided not deferred |
| runtime neutrality | asserted | **measured** — ADR-019, second producer |

---

## §A. Decisions

**All four are resolved — read them for what was decided and on what evidence, not for an
action.** D1 and D3 were signed 2026-08-09 and are implemented; D2 and D4 were signed
2026-08-10 and neither carries a code change.

### D1 — RESOLVED 2026-08-09. Three workstreams each built an observation plane.

> **DECIDED AND IMPLEMENTED.** The owner took the recommendation at the bottom of this
> section: keep ADR-013's transport, port ADR-014's `Decision.adjudicated` and its
> `enforced` / `unevaluated` label onto it. Both halves have now landed.
>
> **What was decided.** `baron.enforcement` on an EVENT is a **per-call observation** — did a
> capability adjudicate *this* call? — derived from an explicit `Decision.adjudicated` flag,
> never from the rules artifact's static `detection` field. The event vocabulary is exactly
> **`enforced` | `unevaluated` | `unknown`**. `instructed` is removed from the event field: it
> is a static posture property of (persona, verb, runtime), it asserts a control the guard
> cannot measure, and it now lives only on the posture surface (`baron rules list`, D3).
> `not-applicable` is removed, subsumed by `unevaluated`. `unknown` is kept for the
> broken-rules-artifact case, because refusing to guess is what the rest of the codebase does.
>
> **On what evidence.** The two rows this file published as a MEASURED DEFECT were re-measured
> against the merged code, on real emitted output rather than unit tests alone — the audit
> skill's `baron_events.jsonl` fixture is the verbatim output of a real `baron guard` run:
>
> | call | was | is now | why |
> |---|---|---|---|
> | `Write ../../../outside.md` | `enforced` | **`unevaluated`** | structural refusal; no capability adjudicated it. The over-count is gone. |
> | `Write src/x.py`, persona holds `write_code` | `not-applicable` | **`enforced`** | a real persona-dependent adjudication — a persona lacking `write_code` is denied the identical call. The under-count is gone. |
>
> Both are asserted by tests, and the second asserts *both halves* of persona-dependence.
> `guard._enforcement(verbs)` is deleted and a test asserts the symbol stays gone.
>
> **Where.** [ADR-018](adr/ADR-018-adjudicated-enforcement-on-the-event.md) (semantics, from
> `harden/d1-semantics`); [ADR-021](adr/ADR-021-audit-ingester-partitions-observation-rows.md)
> (the ingester half — `partition_guard_records` is **merged**, from `harden/d5-ingest`);
> [ADR-019](adr/ADR-019-runtime-neutral-event-plane.md) (the plane is now *measured*
> runtime-neutral by a second real producer, not asserted). ADR-013 §9.1 is rewritten from
> defect to resolution, keeping the measurement table with a was/is-now column.
>
> **The caveat that survives, and matters to any consumer.** `unevaluated` rows still carry a
> non-empty `baron.capability.verb`, and `enforced` rows may carry an empty one. So
> `baron.enforcement` is the field to read; **the verb tuple is not a proxy for it**, and any
> aggregation must filter on `enforcement == "enforced"` *before* it groups by verb. This is
> documented in `events.py`, ADR-018 §5, ADR-013 §9.1 and STATUS.md, and made executable by a
> test that emits two real rows carrying `write_path` — one adjudicated, one structural — and
> asserts naive count 2 vs correct count 1.
>
> **~~What is still open under D1~~ — CLOSED 2026-08-10.** The last item was **retire
> `telemetry.py`**, and the owner has: it is **retired**, recorded in
> [ADR-014](adr/ADR-014-guard-telemetry.md). Because it was never merged, retiring it is a
> **recording** action — no deletion, no revert, no code change, and `harden/otel` stays
> intact as history. See §D and F3.
>
> The rest of this section is the analysis that produced the decision. It is left intact, and
> its "NOT merged" / "currently-merged" statements should be read as **historical**.

**This is the big one, and it is why `harden/otel` is not merged.**

`harden/hooks`, `harden/events` and `harden/otel` were developed in parallel and each shipped
a producer for *the same* stream of guard evidence, with *incompatible* wire shapes. They
were each verified green **in isolation**. At most one can exist.

| | ADR-012 (`hooks`) | ADR-013 (`events`) — **MERGED** | ADR-014 (`otel`) — **NOT merged** |
|---|---|---|---|
| API | `emit(kind, attrs, *, trace_id)` | `emit(Event, cwd)` | `telemetry.active()` + `_emit_span` |
| span name | `guard.allow` / `guard.deny` | `guard.decision` + `baron.outcome` | `baron.guard.evaluate` |
| verbs key | `baron.verbs` | `baron.capability.verb` (comma-joined) | `baron.capability.verbs` (list) |
| `baron.enforcement` | — | `enforced` / `instructed` / `not-applicable` / `unknown` | `enforced` / `unevaluated` |
| output | — | `.baron/events/*.jsonl` | `.baron/telemetry/*.jsonl` |
| sink plugin | — | `baron.sinks`, 2 built-ins **registered** | `baron.sinks`, group declared, built-ins **not** registered |
| env | `BARON_EVENTS_SINK` | `BARON_EVENTS_SINK` | `BARON_TELEMETRY` |

**I merged ADR-013's shape and reconciled ADR-012 onto it.** That was a defensible merge
resolution rather than an architecture call, because ADR-012 §4 *itself* said the row format
belongs to `baron.events` and only guessed the signature while that module was unlanded. Its
own merge canary (`test_real_event_plane_matches_the_producer_contract`) fired exactly as
designed and caught the divergence. Guard now reaches the plane through one late-bound
adapter; `guard.EVENT_KINDS` is test-required to equal `events.KNOWN_KINDS`.

**ADR-014 is a different matter and I did not merge it.** Reconciling it means choosing
between two contradictory *published* definitions of `baron.enforcement`, which is a product
claim, not a conflict resolution. `git merge --abort`; `harden/ops-plane` left green.

#### The part you should not skip: ADR-014 is right, and what I merged has the bug it fixes

I measured this against the merged code rather than taking either ADR's word (recorded in
ADR-013 §9.1):

| call | emitted `baron.enforcement` | reality |
|---|---|---|
| `Write ../../../outside.md` | **`enforced`** | Structural refusal — path escapes the repo root. **No capability adjudicated it**; every persona is denied identically. **Over-counts.** |
| `Write src/x.py`, persona holds `write_code` | **`not-applicable`** | A real, persona-dependent adjudication — a persona lacking `write_code` is denied here. **Under-counts.** |

So the currently-merged `baron.enforcement` books structural refusals as capability
enforcement and misses genuine capability allows. That is precisely the over-claim ADR-002
and ADR-008 exist to prevent, sitting in merged code. ADR-014's `Decision.adjudicated` flag —
set explicitly at each return site, meaning "a rule matched **and** the outcome turned on the
acting persona" — is the correct basis, and its author reached it by measuring a defect too.

One ADR-014 criticism does **not** bite today: it argues emitting `instructed` asserts a
control never measured. True in principle, unreachable in practice — every verb guard can
attach to a `Decision` has `detection: command|file-op`, so `instructed` never appears on a
real row. It becomes reachable the moment guard parses for `open_pr` or `run_tests`.

**Recommendation.** Keep ADR-013's transport (the `Event` shape, the `baron.sinks` plugin,
the gitignored stream, the fail-open asymmetry — all sound and all merged) and port ADR-014's
`adjudicated` flag and its `enforced`/`unevaluated` label onto it. Retire `telemetry.py`.
Then re-merge the genuinely valuable, producer-independent half of `harden/otel`:
`ingest_otel.py`'s `partition_guard_records` (guard rows must not fabricate sessions — its
author measured the contamination: `session_duration_p50` moved 600.0 → 300.297 and the agent
roster gained two fake personas) and ADR-014 §9.1.

**Reversible?** The transport, yes. The **published label semantics**, effectively no — once
someone's dashboard aggregates on `baron.enforcement`, changing what it means is a breaking
change to a consumer you cannot see. Decide before anyone turns a sink on. Today the default
sink is `null`, so nothing is emitting yet. **That window is why this is worth doing now.**

---

### D2 — RESOLVED 2026-08-10. The substrate invariant is AMENDED. Cognee is answered **(a)**.

> **DECIDED — and this is a product-vision change, not a disposition of work already done.**
> Recorded in **[ADR-022](adr/ADR-022-substrate-invariant-amended-default-not-only.md)**, the
> most consequential item of this pass.
>
> **Product-vision invariant #1 is amended.**
>
> | | |
> |---|---|
> | **From** | git + markdown **IS** the substrate. |
> | **To** | git + markdown is the **DEFAULT** substrate. Plugins may extend it to other suitable platforms. |
>
> **The bound, which is the load-bearing half.** Governance state stays **COMPLETE IN GIT**.
> *"Who may do what"*, *"who did what"* and *"what is true now"* must remain answerable from
> the repository **alone**. A plugin may be authoritative for **derived or auxiliary** domains
> — semantic search, embeddings, cross-project recall — and **never** for **authority,
> evidence, or the ledger**.
>
> **Why the bound, argued rather than asserted (ADR-022 §3).** The product's audit claim is
> *governance you can verify by reading a diff*. That holds only while the repo is complete.
> If a plugin holds authoritative governance state, a capability grant stops appearing in a
> PR, the auditor needs credentials rather than a `git clone`, and the failure is silent — a
> stale index does not announce itself. The claim degrades from **"read the diff"** to
> **"trust the index"**, which is a different product. A project that publishes its own
> measured fidelity of 0.53 rather than rounding up should not ship a headline claim that can
> only be taken on trust. **The amendment must not be read as permission for that.**
>
> **The test that makes the bound checkable** (ADR-022 §2): delete every plugin, clone fresh,
> ask the three questions. If an answer is lost or now needs a second system, the plugin was
> holding governance state and is forbidden. If only *speed of finding it* is lost, it is
> permitted.
>
> **Cognee is answered (a): a rebuildable projection.** Mode (b) — "it holds things the repo
> does not" — is authority-bearing by construction and is **refused on the merits**. The
> amendment *permits* a plugin to be authoritative for auxiliary domains; it does **not** make
> Cognee authoritative for anything, and it **mandates building nothing**. 3.4 is still gated
> on 3.3, which does not exist. **Nothing about the vendor has been run** (ADR-015 §6) and
> this decision adds no measurement.
>
> **Still NOT published: the `baron.knowledge` entry-point group.** There is no consumer, and
> the group is public API that cannot be retracted.
> `test_no_knowledge_entry_point_group_was_published` **stays green and is not relaxed** — it
> protects a different rule (no group without a consumer) that this decision does not touch.
>
> **What this reverses, and what it does not** (ADR-022 §6). `docs/BACKLOG.md` records that
> five prior reviews cut this surface, and ADR-015 §4 cut it a sixth. **Those cuts stand.**
> What was cut was *building it now*, on sequencing and evidence grounds. What is amended is
> *what would be permissible if the demand and the measurement arrived*. This changes the
> answer to **"may we ever?"**, not to **"may we now?"** — and "may we now?" is still no.
>
> The analysis the decision was made against follows, unedited.

Unchanged from the 2026-08-04 reconciliation and from ADR-015 §4.1. Still not mine to answer.

- **(a)** Semantic memory is a **rebuildable projection** over git + markdown. Blow it away,
  rebuild from the repo, lose nothing.
- **(b)** It is an **authoritative knowledge source** — it holds things the repo does not.

**(b) contradicts product-vision invariant #1** (git + markdown is the substrate). The
workstream's recommendation, and mine, is **(a)**.

What shipped is only the safe half: `baron export --json`, emitting the governed corpus as
citable records with a commit SHA on every one. **No adapter, no `baron.knowledge`
entry-point group, no vendor name anywhere under `cli/src/baron/`** — a test enforces all
three. `docs/BACKLOG.md` records that five prior reviews already cut this surface once.

**Reversible?** The export, yes. Publishing a `baron.knowledge` entry-point group, no —
that is public API you cannot retract. Do not create it until there is a consumer.

> **Post-decision note on reversibility.** The *wording* stays reversible while no plugin
> exists — re-tightening costs a follow-up ADR. **Anything built under the amendment is not.**
> Once a plugin ships and downstream repos depend on it, the permission has consumers and the
> bound is the only thing between the audit claim and "trust the index". Defend the bound in
> review, every time — not the amendment.

---

### D3 — DECIDED 2026-08-09. `baron rules list` reports *less* enforcement than it used to (ADR-016 §8 D-1)

**Approved. ADR-016 §8 D-1 is ticked, on a basis the original framing did not
have: four measured adapters, not one measurement generalised to four.**
Recorded in **ADR-020**; the round-3 "three of four are unmeasured" scoping is
retired, not carried alongside. The printed label is unchanged (`instructed`);
what changed is that the evidence is now the same size as the claim, and a fifth
adapter breaks the basis until it is measured. The honest bound is published
with the label: *baron emits no mechanism capable of omitting the read tools* —
**not** *the runtime cannot enforce them*. The original text, which the decision
was made against, follows.

Left **untickable by me on purpose**; its author flagged it the same way.

`read_code` and `read_collab` currently print `enforced`. That is **measurably wrong**: guard
does not parse for them, and the one adapter that was actually instrumented (pydantic-ai)
builds `FileSystem` unconditionally — a test hydrates a persona denying `read_code` and
measures the read tools still present. Narrowing them to `instructed` changes user-visible
output and the `label` field in `--json` for 2 of 10 verbs.

It is a **correction, not a regression**. But "we now report less enforcement than we used
to" is a product claim you should make knowingly rather than absorb from a merge.

Note the honest bound the author took: only pydantic-ai was measured. The `claude` and
`code-puppy` kits are prompt/config templates whose tool exposure belongs to the host
runtime and is **unmeasured** — they are not evidence for either label. The alternative
branch (instrument all four adapters and possibly restore `enforced` honestly) was costed
and declined as too expensive for this pass.

> **Update (ADR-020).** That last sentence was the mis-costing. The branch was taken and it
> was cheap, because the direction that was needed is the *negative* one: proving baron
> emits no enforcement mechanism is a static inspection of what `baron init` generates,
> where proving one exists would need a live runtime. All four adapters now carry a
> measurement (`claude`, `code-puppy`, `generic` static; `pydantic-ai` keeps its live gate)
> and all four are negative, so `enforced` was not honestly restorable. The `claude` and
> `code-puppy` HYDRATE.md Tier-3 tables still print `enforced` for the read verbs and are
> **not wrong** — they describe an artifact a human hand-authors from the recipe, which
> baron never generates. Recorded as a known divergence in ADR-020 §7 rather than papered
> over by editing one table to match the other.

**Reversible?** Yes — it is a label, and the machinery to flip it is a data change.

---

### D4 — RESOLVED 2026-08-10. Sinks stay OFF by default. Decided, not deferred.

> **DECIDED.** The shipped default remains **`BARON_EVENTS_SINK=null`**. Recorded in
> [ADR-013 §7.1](adr/ADR-013-observation-plane-events-and-sinks.md).
>
> **This is a decision, not a deferral, and there is NO CODE CHANGE** — the current default is
> already correct, so the signature is the whole of the change. Saying so explicitly matters:
> a default left alone because nobody signed it and a default left alone because someone did
> look identical in the diff and are not the same fact.
>
> **The reasoning that survives.** Downstream repos should not start writing to disk because
> they upgraded. Enabling telemetry is an operator's act, not a consequence of installing a
> governance tool — and a freshly generated repo behaves identically with the four new hook
> blocks wired, which is what made the scaffold change safe to land in the first place.
>
> **The cost, stated plainly and not buried.** The **0.53 operational-fidelity measurement
> that motivated this entire workstream still has no data**, and will keep having none until
> someone sets the variable. That cost is not reduced by this decision; it is accepted by it.
> A framework whose own telemetry is off by default measures itself as often as anyone
> remembers to.
>
> **What closes the gap instead.** The owner intends to enable sinks in his **own** projects
> to generate that data. **The shipped default is a separate question from his local one** —
> and it is deliberately answered separately, because "the author runs it hot" is not a reason
> to make every downstream repo run it hot. The measurement will come from opted-in projects,
> which is also the only population where the numbers mean anything.
>
> **The F3 interlock.** The hazard recorded below — that turning sinks on with two transports
> live forks the schema in downstream repos — is now **moot**, because F3 retires the second
> transport (ADR-014 §4.1). **The two decisions interlock:** F3 removes the fork, and D4 keeps
> the no-consumer window open regardless. Neither depends on the other, and both point the
> same way.
>
> The original framing, which the decision was made against, follows.

Every merged plane defaults to `BARON_EVENTS_SINK=null`. Baron writes nothing unless an
operator opts in, which is why the scaffold change was safe to land: a freshly generated repo
behaves identically with the four new hook blocks wired.

The cost is that **the 0.53 operational-fidelity measurement that motivated all of this still
has no data**, and will keep having none until someone sets an environment variable. A
framework whose own telemetry is off by default measures itself as often as anyone remembers
to.

I did **not** change the default. Flipping it is one line, but it means baron writes to disk
in every downstream repo by default, and that deserves your signature, not mine.

**Reversible?** Yes, trivially — but note that D1 should be settled *first*: turning sinks on
before the `baron.enforcement` semantics are fixed starts accumulating rows with the labelling
defect baked in. **Update 2026-08-09:** that precondition is met (ADR-018). This is now a
straight default-flip call, still unsigned. **Update 2026-08-10: signed — the default stays
`null`.** Still reversible; flipping it later remains one line plus an ADR.

---

## §B. Reversible decisions made during implementation

| # | Decision | Alternative rejected |
|---|---|---|
| B1 | Event `kind` is an **open dotted string** with a documented registry + pinning test, no runtime warning. | Closed enum. Rejected: the vocabulary is frozen because it is an *enforcement* contract where ambiguity means mis-enforcement; this is *observation*, where an unknown kind costs one `grep`. A warning would fire on every third-party event and train people to ignore guard's stderr — the channel carrying the actual denial message. What is frozen instead is the `baron.` **attribute-key** namespace, since that is what `ingest_otel.py` parses. |
| B2 | Evidence records the **presence** of `tool_response`, never its content. `UserPromptSubmit` deliberately not wired at all. | Recording responses. Rejected: they carry file bodies and stdout; a stream accumulating them is an exfiltration surface, not telemetry. **Verified empirically** — a `PostToolUse` payload containing `SECRET` produced a row with no trace of it. |
| B3 | `BARON_EVENTS_DEBUG=1` is the opt-in diagnostic; emission failures are otherwise **silent**. | Warn on stderr. Rejected: guard's stderr is fed to the **model** on exit 2, so noise there degrades the denial message. |
| B4 | `baron doctor`'s `KNOWN_WRAPPERS` is a hand-written allowlist of 13 launchers (`uv`, `uvx`, `poetry`, `pipx`, …). | Auto-detection. An unlisted launcher is still probed as written, just never *described* as a wrapper. Adding one is a one-line change; nothing depends on the list being complete. |
| B5 | Guard emits on **allows as well as denies**. | Denials only. A stream recording only denials cannot answer "how often did the boundary hold?" — the question the 0.53 measurement needed. |
| B6 | `test_no_new_entry_point_group_was_published` narrowed to `test_no_knowledge_entry_point_group_was_published`. | Deleting it. It asserted `groups == ["baron.forges"]`, which ADR-013's legitimate `baron.sinks` broke. ADR-015 §4's actual rule is "no group **without a consumer**"; `baron.sinks` ships two. Now asserts no `baron.knowledge`, no vendor-named group, and an **allowlist** so a third unreviewed group still fails. |
| B7 | The `baron doctor` instruction in `HYDRATE.md` promoted to its own **step 3e**. | Leaving it where the union put it — mid-step-3d, under a heading about non-blocking evidence hooks, while doctor checks the blocking enforcement hook. |

---

## §C. One-way (or sticky) doors already walked through

| # | Decision | Why it is sticky |
|---|---|---|
| C1 | **The `Sink` Protocol is final at three members** (`name`, `emit`, `close`). | `@runtime_checkable` makes `isinstance` test method *presence*, so adding a fourth member would retroactively invalidate every third-party sink. Optional capabilities are duck-typed instead: `flush()` for batching sinks, `bind(cwd)` for repo-writing ones. `bind()` is an admitted wart — a documented optional method exactly one built-in implements — costed in ADR-013 §10. An ABC would have allowed safe additions; consistency with the established `baron.forges` pattern was judged worth more. |
| C2 | **No `opentelemetry-api` in baron core. Ever.** | ADR-003 pins baron to typer + pyyaml, and guard is a cold Python start on *every tool call*. **Verified, not assumed**: the five top-level row keys are each the first entry of `ingest_otel.py`'s flat key lists, and I ran the real `record_from_flat` over real emitted rows — it parsed all five with zero code changes. The entire consumer-side value of OTel costs a ~40-line stdlib writer. A live exporter belongs out-of-tree under `baron.sinks`. |
| C3 | **Only `PreToolUse` may exit 2.** | A blocked `SessionStart` or `Stop` is **unrecoverable from inside the session** — the session is bricked from a place nothing inside it can reach. `test_only_pretooluse_can_block` parametrizes all 30 other events with one payload carrying a force-push to main, a write to `/etc/passwd`, and a `..` escape *simultaneously*, asserting exit 0 and empty stderr for each. Preconditions belong in `baron doctor`, not a session-start hook. |
| C4 | **Enforcement fails CLOSED; evidence fails OPEN — asymmetric and silent.** | Without it, a full disk inside a PreToolUse hook meets guard's fail-closed policy and denies *every* tool call: a session bricked by a logging destination. Locked by `test_sink_failure_does_not_change_guard_exit_code`. |
| C5 | **The event stream is gitignored; `.baron/guard-override.log` stays TRACKED.** | The `.gitignore` the disk sink writes contains `*` and lives **inside** `.baron/events/`, deliberately *not* at `.baron/` level — an ignore there would silently un-track the override log in every downstream repo, removing a governance property that already exists. Overrides are a handful of deliberate human acts (evidence, belongs in the diff); events are one row per tool call (telemetry, belongs on local disk). |
| C6 | **`class` and `detection` are now REQUIRED in the rules artifact**, and consistency is checked **symmetrically**. | Previously-parseable documents become invalid. Over-claiming (`detection: command` with no rule bound) and under-declaring (a rule binds a verb whose entry says `none`) are both refused. Defaulting an enforcement decision is a guess, and this parser exists to refuse guesses — but the under-declare direction is stricter than was asked for. |
| C7 | **`baron doctor` spawns the executable the hook NAMES**; in-process is a labelled fallback forbidden from claiming anything about the hook's command. | Changes what a green doctor *means*. This is the fix for a **reproduced** bug: a scaffolded project whose hook invoked a fake `baron` that answered `--version` but exited 0 on `guard` used to report 8 pass / exit 0. It now reports 6 pass / 2 fail / exit 1 and names the fake binary. Cost: any exit code other than 2 is a FAIL, so a wrapper whose environment cannot be materialised offline will FAIL — justified because in that state the hook genuinely does not block. First thing to revisit if it proves noisy. |
| C8 | **`--allow-dirty` covers modified *tracked* sources only**; untracked sources are skipped unconditionally, so `commit_sha` is never empty. | Behaviour change vs the workstream's round 1 (nothing downstream can depend on it — never merged or released). Preserves the format invariant the CHANGELOG advertises and makes `--allow-dirty` honestly mean "modified too", not "uncited too". |

---

## §D. What did not merge — RESOLVED 2026-08-10

### `harden/otel` — NOT MERGED, and now RETIRED. Aborted cleanly; `harden/ops-plane` left green.

> **RESOLVED 2026-08-10 — the owner's call is in.** ADR-014's producer transport is
> **retired**; the branch is kept as history; an out-of-tree plugin over the existing
> `baron.sinks` group is the future path for a live OTel exporter. Recorded in
> **[ADR-014](adr/ADR-014-guard-telemetry.md)**, which is a **status record** on the reserved
> number — the 435-line ADR itself was never merged and still lives at
> `harden/otel:docs/adr/ADR-014-guard-telemetry.md`.
>
> **"Retired" is a RECORDING action here, not a deletion.** `telemetry.py` was never merged,
> so there is nothing to remove: **no deletion, no revert, no code change, suite unchanged at
> 424.** `harden/otel` is **NOT deleted** and nothing further is merged from it — both
> producer-independent halves already landed (`Decision.adjudicated` → ADR-018,
> `partition_guard_records` → ADR-021).
>
> **Not "rejected", and the distinction is the point.** ADR-014's analysis was **correct and
> was ADOPTED in part** — ADR-018 cites it as *"the correct basis"* and ports
> `Decision.adjudicated` from it essentially unchanged. **Its TRANSPORT is what is retired.**
> Recording it as rejected would misstate a history that is checkable, and would lose the more
> useful fact: the branch that lost the merge was the branch that was right about the label.
> ADR-014 §12.2 had itself named this outcome as the correct resolution.
>
> **Forward path.** A live OTel exporter belongs **out-of-tree**, registered over the
> **existing** `baron.sinks` entry-point group — no new group needed. ADR-014 §3 / one-way door
> **C2** already forbids `opentelemetry-api` in baron core; **that stands, and this decision is
> consistent with it** rather than an exception to it. The plugin carries its own dependency.
> Nothing is authorised or planned.
>
> The analysis this decision was made against follows, unedited.

**Why:** see **D1**. It is a second, complete, incompatible observation plane —
`telemetry.py` with its own `Sink` Protocol, its own `baron.sinks` entry-point group
declaration, and its own producer wired into `guard.process()`. It collides with the merged
ADR-013 plane on the module, the entry-point group, the env vars, the on-disk location, the
span name, and — the part that actually matters — the meaning of `baron.enforcement`.

Merging it would have meant inventing a unified schema and discarding one workstream's
verified test suite (`test_telemetry.py`, 668 lines) on my own authority. That is an
architecture decision with an ADR attached, not a conflict resolution, so I stopped.

**Nothing is lost.** The branch is intact at `harden/otel` (3 commits, tip `3b9a4d8`). Its
consumer-side work is producer-independent and should be re-merged once D1 is settled:

- ~~`ingest_otel.py`'s `partition_guard_records`~~ — **PORTED 2026-08-09, ADR-021.** Split
  out before `build_sessions`, keyed on the `baron.outcome` attribute rather than a span
  name, and generalised to all six ADR-013 kinds. Re-measured against the *merged* producer
  rather than carried over: it is worse here, because ADR-013 also puts `tool.name` on every
  row. Nine activity metrics move when a baron export is paired with `flat_spans.jsonl` —
  `session_duration_p50_s` 600.0→300.444, `tool_calls_total` 1→12, roster polluted with two
  personas plus a literal `unknown`, `human_turns_total` downgraded `measured`→`inferred`.
  ADR-021 §2 has the full table.
- ~~`test_no_contamination_from_paired_export`~~ — **PORTED.** Re-verified the same way its
  author did, by reverting the fix — and the two possible reverts are kept apart, because
  conflating them is what made an earlier draft of ADR-021 §4 wrong. `return records,
  baron` reverts the partition **and only** the partition: the suite completes with **45
  failed checks**, a count stable across every commit on this branch while the denominator
  grows (45 of 230 at `4a85a49`, 45 of 247 at `30a1002`, 45 of 263 now). `return records,
  []` *additionally* blinds the
  guard-decision axis, and that second mutation — not the partition revert — is what
  crashes `test_baron_guard_metrics` with an `AttributeError` after 17 failed checks, since
  `guard_decisions` degrades to a `not measurable` string the test then sums. Run on its
  own, the contamination test fails 34 of its own checks under either. ADR-021 §4 tabulates
  both. The audit skill's tests are also now in CI, which they never were.
- ~~ADR-014 §4.2 and §9.1, and the `Decision.adjudicated` reasoning D1 recommends adopting.~~
  — **PORTED 2026-08-09, ADR-018.** `Decision.adjudicated` is set explicitly at all eleven
  return sites in `evaluate_bash` / `evaluate_write`, defaulting `False` on the trace so that
  every path returning without a real `Decision` (out-of-jurisdiction tool, malformed
  payload, fail-closed error, override bypass) is `unevaluated` **by construction** rather
  than by remembering to say so. Ported, not redesigned.

**What is left of `harden/otel` after those three ports: its transport.** `telemetry.py`,
`test_telemetry.py` (668 lines), the `BARON_TELEMETRY` env var and the `.baron/telemetry/`
location. ~~That is the piece D1 still lists as open, and it is the owner's call (§F).~~
**RETIRED 2026-08-10 — ADR-014. Kept on the branch as history; nothing deleted.**

**Deliberately NOT ported:** `harden/otel`'s `guard_enforcement_class` aggregate. **Note the
reason changed at consolidation.** It was withheld because `baron.enforcement` was wrong in
both directions; that is fixed (ADR-018). It stays out because an honest aggregate must
filter on `enforcement == "enforced"` **before** grouping — an `unevaluated` row still
carries a non-empty verb — and that filter is un-built with no consumer asking for it. It is
now a **gap, not a blocker**. ADR-021 §5.

---

## §E. What is NOT verified

Stated plainly, because a green suite invites the wrong inference.

1. **No test drives a real Claude Code process against a scaffolded repo.** `baron doctor`
   is the nearest thing, and it verifies **wiring, not invocation** — it proves the install
   *can* enforce, never that enforcement *happened*. Nothing outside the runtime can observe
   that.
2. ~~**`baron.enforcement` is known-wrong in two directions** (D1, ADR-013 §9.1).~~ **Fixed
   2026-08-09 (ADR-018).** Both defects flip under test. The honest remaining bound: the
   label is verified against baron's *own* evaluator, which is the only thing that can
   observe it — no test proves a real Claude Code session produced the row, and item 1 above
   is why. `unevaluated` is also a wide bucket (out-of-jurisdiction, no-rule-matched,
   structural refusal, fail-closed error all share it); splitting them requires joining on
   `baron.outcome` and `baron.capability.verb`.
3. **No adapter's read-tool exposure is verified against a live runtime** (D3, ADR-020).
   All four are now measured, but only `pydantic-ai`'s measurement runs the emitted kit;
   the other three are static — they prove **baron emits no mechanism** capable of
   omitting read tools, which is the claim `baron rules list` makes, and nothing more.
   What a `claude` or `code-puppy` session actually exposes belongs to the host runtime
   and is unobservable from here (same bound as item 1). *This replaces the earlier
   "three of four adapters are unmeasured", which is obsolete.*
4. **The evidence-handler tests use a contract double's writer, not `baron.sinks.disk`.** The
   double was rewritten onto the real signature and re-exports the real `Event`,
   `KNOWN_KINDS` and `FIXED_ATTR_KEYS`, so it cannot drift silently — but real-sink behaviour
   is covered separately (`test_sinks.py`, and the ADR-013 section of `test_guard.py`).
5. **`baron doctor` reads project-level settings only.** A hook wired in
   `~/.claude/settings.json` is invisible to it, and a bare executable name resolves against
   *doctor's* `PATH`, not the runtime's. Both bounds are printed on every run. Note this
   bites the **default** wiring: `baron init` generates a bare `baron guard --persona-file …`.
6. **`.baron/rules.yaml` does not exist.** `baron rules validate --file` parses a candidate
   but **does not activate it** — baron still loads packaged rules only. The one-way doors
   for the loader (add-only/deny-only, never grants, never new verbs, supported-version
   ranges on *both* artifacts, malformed-file-must-REFUSE, and the `.baron/` machine-state
   vs root `.baron-waivers.yaml` human-config convention collision) are recorded in ADR-016
   §5–§6 for their own ADR.
7. **The known guard bypass is unchanged.** `bash -c '...'` and friends run their payload
   uninspected. Documented in `guard.py`'s module docstring; not a regression, not fixed here.
8. **Runtime neutrality is proved with TWO producers, not three** (ADR-019, added
   2026-08-09). pydantic-ai now emits into the same plane in the same wire shape, and the
   two producers' rows for one governance fact differ in exactly four attributes — that is
   a measurement, and it does falsify "the plane is Claude-Code-shaped". It is **not** proof
   the shape fits every runtime. **code-puppy has no pre-tool seam**, so it emits nothing
   and is deliberately absent from `guard.KNOWN_RUNTIMES`; inventing a post-hoc producer
   would put rows on the plane implying an adjudication that never happened. Also note
   `baron.hook_event` was **renamed to `baron.trigger` with no alias** — a second breaking
   change to a published attribute, taken in the same "default sink is `null`, no consumer
   exists" window as ADR-018, and the argument expires the moment D4 flips.
9. **The audit ingester's baron partition is verified against fixtures, not a live audit**
   (ADR-021). `baron_events.jsonl` is real `baron guard` output, and the contamination test
   is verified to fail when the partition is reverted (`return records, baron`: 45 failed
   checks) — but no end-to-end audit has been run over
   a real project's `.baron/events/` directory, because the default sink is `null` and no
   project is emitting yet. The partition predicate also assumes no non-baron producer emits
   a `baron.outcome` attribute; that is an assumption about a namespace, not a measurement.

---

## §F. Identified in this pass, deliberately NOT done

Named here so they are choices on the record rather than things nobody noticed.

| # | Follow-up | Why not now | Cost if deferred |
|---|---|---|---|
| F1 | **The per-runtime capability matrix.** `baron rules list` prints one label per verb, but the honest answer is a **4 adapters × 10 verbs** grid: `write_code` is mechanised on Claude Code via the PreToolUse hook and in-process on pydantic-ai, and is prose-only on code-puppy and generic. One flat column cannot say that. The `(adapter, verb)`-keyed harness that ADR-020 needed to answer D3 (`cli/tests/omission.py`) is already shaped for it — it was built keyed on the pair for exactly this reason. | It is a **user-visible output redesign** (a table, a `--json` schema change, and a decision about what to print when a repo has several adapters hydrated), not a measurement gap. Doing it inside a consolidation pass would smuggle a product decision through a merge — the thing D1 exists to prevent. | Low and shrinking. The harness is the expensive half and it is merged and under test. |
| F2 | **Delivery-verified `instructed`, via the ritual-fence technique.** Today `instructed` means "baron emitted the sentence into the kit" — verified at *emission*, never at *receipt*. Nothing checks that the persona's runtime actually loaded the file, so a silently-ignored `AGENTS.md` is indistinguishable from a heeded one. The ritual-fence technique (make the agent echo a token it can only have obtained by reading the instruction) would upgrade this from emitted to **delivered**. | It needs a live runtime in CI, which §E item 1 records as the standing bound of this whole project. It is also a **new claim class** — "delivered" is neither `enforced` nor `instructed` — and deserves its own ADR and its own vocabulary decision, not a quiet third value. | Medium. This is the honest ceiling on the `instructed` label, and the 0.53 fidelity number lives here. |
| ~~F3~~ | ~~**ADR-014's producer transport — `telemetry.py` — is still unmerged and still the owner's call.**~~ **RESOLVED 2026-08-10 — [ADR-014](adr/ADR-014-guard-telemetry.md).** The transport is **RETIRED**: `telemetry.py`, `test_telemetry.py` (668 lines), `BARON_TELEMETRY`, `.baron/telemetry/`. A **recording** action — none of it was ever merged, so nothing is deleted, `harden/otel` stays intact as history, and the suite is unchanged at 424. ADR-014's *analysis* was adopted in part (ADR-018 cites it as "the correct basis"); only the transport is retired, and it is **not** recorded as rejected. | Decided. The alternative was keeping two transports, which forks the schema downstream the moment sinks are on. ADR-014 §3 / C2 forbids `opentelemetry-api` in core — that stands — so the forward path for a live OTel exporter is **out-of-tree over the existing `baron.sinks` group**. Nothing is authorised or planned. | **Discharged.** The rising cost was contingent on D4 flipping; D4 was decided the same day to stay OFF, and retiring the second transport moots the fork independently. The two decisions interlock. |
| F4 | **No aggregate over `baron.enforcement` in the audit skill.** Now un-built rather than blocked — see §D. | Needs the `enforcement == "enforced"` filter applied before grouping, and no consumer has asked. | Low. |

**Bounds this pass did NOT move**, restated so §F is not mistaken for a clean sweep: §E items
1 (no live-runtime test), 5 (`baron doctor` is project-scoped), 6 (`.baron/rules.yaml` is
parsed but never activated) and 7 (the `bash -c` guard bypass) are all unchanged.

---

## Appendix — what merged, in order

| # | Branch | ADR | cli suite after |
|---|---|---|---|
| 1 | `harden/hooks` | ADR-012 | 208 |
| 2 | `harden/events` | ADR-013 | 256 |
| — | `harden/otel` | ADR-014 | *not merged; transport **RETIRED** 2026-08-10, analysis adopted in part — see §D + F3* |
| 3 | `harden/cognee` | ADR-015 | 286 |
| 4 | `harden/rules` | ADR-016 | 348 |
| 5 | `harden/evalgaps` | ADR-017 | 386 |
| 6 | `harden/d1-semantics` | **ADR-018** | 397 |
| 7 | `harden/d1-neutrality` | **ADR-019** | 417 |
| 8 | `harden/d3-posture` | **ADR-020** *(claimed 018)* | 424 |
| 9 | `harden/d5-ingest` | **ADR-021** *(claimed 018)* | 424 *(skill-only; 265 skill checks)* |

**ADR numbering at consolidation.** Workstreams 6, 8 and 9 each independently wrote an
`ADR-018`. The number stayed with **d1-semantics**, because ADR-019 was already written
against it by number and it is the decision the other two reference. The other two were
renumbered **020** and **021**; only identifiers changed, no content.

**Suite counts.** cli `pytest`: **148 → 424**. Audit skill (`test_ingest_otel.py`, stdlib,
now in CI): **265 checks, 0 fail**. `tests/lint_repo.py` and `tests/bi_runtime_accept.py`
both PASS. No test was deleted at any merge in this pass; one was **flipped** — the check
that asserted the pre-ADR-018 enforcement defect as current truth now asserts the fix, which
is what its own comment said should happen.

Baseline `harden/ops-plane` was **148**. No test was deleted at any merge; four were
corrected, each with the reason recorded in the merge commit and in the affected ADR.

**Checked end to end outside pytest**, because the merges were the risk:

- One session's deny + allow + `SessionStart` + `PostToolUse` + `SessionEnd` produced five
  rows sharing **one** trace id in **one** wire shape, with no `tool_response` content on any
  row, and the real `ingest_otel.record_from_flat` parsed all five unchanged.
- A project scaffolded by the merged `baron init` emits all five hook blocks (session events
  correctly matcher-less) and passes `baron doctor` 8/8, with the enforcement and fail-closed
  probes spawning the real executable the hook names.
