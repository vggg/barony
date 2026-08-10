# Decisions for review — the ops-plane hardening consolidation

**Date:** 2026-08-09 · **Branch:** `harden/ops-plane` · **Suite:** 386 passing (base was 148)
· **Merged:** 5 of 6 workstreams

Read this file first. It is ordered by *what needs you*, not by what shipped.

- **§A — needs your call before this can merge.** Four decisions. Two are blocking.
- **§B — made during implementation, reversible.** You can wave these through.
- **§C — made during implementation, one-way doors.** Worth a read even if you agree.
- **§D — what did not merge, and why.**
- **§E — what is NOT verified.** The honest bounds.

Throughout: **enforced** means baron mechanises it, **instructed** means a persona is told
and nothing checks. ADR-002/ADR-008 forbid blurring those, and this file tries hard not to.

---

## §A. Decisions that need you

### D1 — BLOCKING. Three workstreams each built an observation plane. Pick one.

> **DECIDED 2026-08-09 — the semantics half is settled and implemented.** The owner took the
> recommendation at the bottom of this section: keep ADR-013's transport, port ADR-014's
> `Decision.adjudicated` and its `enforced` / `unevaluated` label onto it. That landed as
> **[ADR-018](adr/ADR-018-adjudicated-enforcement-on-the-event.md)** on `harden/d1-semantics`;
> ADR-013 §9.1 is rewritten from defect to resolution and both measured defects flip under
> test. `instructed` and `not-applicable` are gone from the event field; the vocabulary is
> exactly `enforced` | `unevaluated` | `unknown`.
>
> **What is still open under D1** — merge work, not a product call: retire `telemetry.py`,
> and re-merge the producer-independent half of `harden/otel`
> (`ingest_otel.py`'s `partition_guard_records` and ADR-014 §9.1). D4 (sink on by default)
> is also still open and should stay behind this.
>
> The rest of this section is the analysis that produced the decision. It is left intact.

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

### D2 — BLOCKING, and carried over. Cognee: projection, or authoritative source?

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

### D4 — Should the observation plane be on by default? (Recommend: no, but decide knowingly)

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
straight default-flip call, still unsigned.

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

## §D. What did not merge

### `harden/otel` — NOT MERGED. Aborted cleanly; `harden/ops-plane` left green.

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
- ADR-014 §4.2 and §9.1, and the `Decision.adjudicated` reasoning D1 recommends adopting.
  **Still pending** — producer-side, blocked on D1.

**Deliberately NOT ported:** `harden/otel`'s `guard_enforcement_class` aggregate. Counting
`baron.enforcement` while D1 is open would publish a `measured` number over a field this
very document says is wrong in both directions. ADR-021 §5.

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
<<<<<<< HEAD
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

## Appendix — what merged, in order

| # | Branch | ADR | Suite after |
|---|---|---|---|
| 1 | `harden/hooks` | ADR-012 | 208 |
| 2 | `harden/events` | ADR-013 | 256 |
| — | `harden/otel` | ADR-014 | *aborted, see §D* |
| 3 | `harden/cognee` | ADR-015 | 286 |
| 4 | `harden/rules` | ADR-016 | 348 |
| 5 | `harden/evalgaps` | ADR-017 | 386 |

Baseline `harden/ops-plane` was **148**. No test was deleted at any merge; four were
corrected, each with the reason recorded in the merge commit and in the affected ADR.

**Checked end to end outside pytest**, because the merges were the risk:

- One session's deny + allow + `SessionStart` + `PostToolUse` + `SessionEnd` produced five
  rows sharing **one** trace id in **one** wire shape, with no `tool_response` content on any
  row, and the real `ingest_otel.record_from_flat` parsed all five unchanged.
- A project scaffolded by the merged `baron init` emits all five hook blocks (session events
  correctly matcher-less) and passes `baron doctor` 8/8, with the enforcement and fail-closed
  probes spawning the real executable the hook names.
