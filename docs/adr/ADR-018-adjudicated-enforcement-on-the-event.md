---
created: 2026-08-09
accepted: 2026-08-09
type: decision
status: accepted
adr: 018
project: barony
related:
  - "[[docs/adr/ADR-002-ways-of-working-2026-07]]"
  - "[[docs/adr/ADR-004-baron-guard-enforcement]]"
  - "[[docs/adr/ADR-008-ways-of-working-2026-07-31]]"
  - "[[docs/adr/ADR-013-observation-plane-events-and-sinks]]"
  - "[[docs/adr/ADR-016-externalizable-capability-rules]]"
---

# ADR-018: `baron.enforcement` on an event is a per-call observation, not a property of a verb

| Field | Value |
|---|---|
| **Status** | Accepted (2026-08-09) |
| **Date** | 2026-08-09 |
| **Authors** | Vikram + Claude |
| **Supersedes** | ADR-013 §4.1 (the label paragraph) and ADR-013 §9.1 (which recorded the defect and deferred the fix) |
| **Ports from** | `harden/otel` / ADR-014 §4.2 — `Decision.adjudicated`, unmerged branch, tip `3b9a4d8` |
| **Decision owner** | Vikram (decision D1 in `docs/DECISIONS-FOR-REVIEW.md`) |

## 1. Context

Three parallel workstreams each built an observation plane. ADR-013's transport merged; the
`Event` shape, the `baron.sinks` plugin, the gitignored stream and the fail-open asymmetry
are all sound and all unchanged by this ADR. One attribute on that plane was not sound.

`baron.enforcement` was derived at emit time from the rules artifact's `detection` field for
whatever verbs the `Decision` carried. That is a **static posture fact about a verb** being
used to answer a **per-call question**. ADR-013 §9.1 measured the consequence against merged
code, in both directions:

- `Write ../../../outside.md` emitted **`enforced`**. It is a structural refusal — the path
  escapes the repo root and every persona is denied identically. Nothing adjudicated it.
- `Write src/x.py` by a persona holding `write_code` emitted **`not-applicable`**, because
  the verb tuple happened to be empty. It is a real, persona-dependent adjudication.

So the field simultaneously booked structural refusals as capability enforcement and missed
genuine capability allows. In a project that publishes its own measured operational fidelity
of **0.53** rather than rounding it up, an enforcement counter that inflates itself by
construction is the specific failure mode being guarded against — sitting in merged code.

Today the default sink is `null`, so nothing is emitting. That window is why this was worth
fixing before anything turns a sink on: once a dashboard aggregates on `baron.enforcement`,
changing what it means is a breaking change to a consumer you cannot see.

## 2. Decision — the basis is an explicit flag, set at every return site

`Decision` gains `adjudicated: bool = False`. `guard._enforcement(verbs)` is **deleted**.

```python
@dataclass(frozen=True)
class Decision:
    allowed: bool
    verbs: tuple[str, ...]
    reason: str
    adjudicated: bool = False
```

Every `return` in `evaluate_bash` and `evaluate_write` states it. Two module constants make
the common allows readable: `ALLOW` (persona-independent) and `ALLOW_ADJUDICATED`.

**Why a field and not a derivation from `verbs`.** The verb tuple is wrong in both
directions, which is exactly why the defect existed:

| Case | `verbs` | `baron.enforcement` | Truth |
|---|---|---|---|
| `git status`, `curl … \| sh` | `()` | `unevaluated` | no rule matched — not adjudicated |
| `Write src/x.py` holding `write_code` | `()` | `enforced` | `write_code` was checked and held |
| `Write agents/other/x.md`, denied | `('edit_other_personas',)` | `enforced` | adjudicated |
| `Write ../outside.md` | `('write_path',)` | `unevaluated` | structural — every persona denied identically |

Rows 2 and 4 are the two directions. No function of `verbs` alone can label both correctly.

**Why the default is `False`.** `_Trace.adjudicated` — the carrier through `guard.process()`
— also defaults to `False` and is only ever raised by `_Trace.record(decision)` copying a
real `Decision`. Every path that returns without producing one (tool out of jurisdiction,
malformed payload, fail-closed error, fail-closed override bypass) is therefore
`unevaluated` **by construction**, not because someone remembered. A future return site that
forgets the flag under-claims. That asymmetry is deliberate: under-claiming is a bug,
over-claiming is the thing this project exists to catch.

**What `enforced` requires — both halves, nothing weaker:**

1. a capability rule from the artifact matched, **and**
2. the outcome turned on the acting persona — a differently-capable persona could have
   received a different answer.

## 3. Decision — the event vocabulary is exactly `enforced` | `unevaluated` | `unknown`

Pinned as `guard.ENFORCEMENT_VALUES` and asserted by test.

- **`enforced`** — both halves of §2 held.
- **`unevaluated`** — guard saw the call and did not adjudicate it. This covers four
  situations that a consumer cannot act on differently: out of jurisdiction (`Read`), no
  rule matched (`curl … | sh`), a structural refusal, and a fail-closed error.
- **`unknown`** — the rules artifact could not be read, so guard cannot even say what was
  adjudicable. Kept, rather than folded into `unevaluated`, because refusing to guess when
  the artifact is unreadable is what the rest of the codebase does (ADR-016 makes `class`
  and `detection` required for the same reason: defaulting an enforcement decision is a
  guess, and this codebase refuses guesses).

**A fail-closed deny is `unevaluated`, not `enforced`.** Guard blocked the call *because it
could not evaluate it*. Booking that as enforcement would let a guard that crashes on every
call report perfect enforcement — a broken deployment reading as working governance.

## 4. Decision — `instructed` is removed from the event and belongs only to the posture surface

`instructed` is the project's word for "declared and nothing mechanises it". It is a static
property of a **(persona, verb, runtime)** triple. Guard cannot observe it at a tool call:
nothing at the PreToolUse hook tells baron whether persona prose covered this command, and
for `curl … | sh` the honest answer is usually that *nothing* governed it. Emitting the word
on an event asserts a control baron never measured — the over-claim ADR-002 and ADR-008
exist to forbid.

ADR-013 §9.1 previously argued this criticism did not bite, because every verb reachable on
a `Decision` has `detection: command|file-op`, so `instructed` never appeared on a real row.
The facts were right; the conclusion was wrong. An unreachable value is still a published
vocabulary entry documenting a claim the field may not make, and it becomes reachable the
moment guard learns to parse for `open_pr` or `run_tests` — i.e. at the exact moment nobody
is thinking about this ADR.

**The posture axis is untouched.** `baron rules list` (ADR-016) still reports `enforced` /
`instructed` derived from `detection`, still with `CapabilityRules.caveat()` attached, and
`open_pr` / `run_tests` still label `instructed` there. Two different measurements, two
different surfaces, no shared field.
`test_the_posture_axis_is_untouched_and_lives_on_the_rules_surface` holds both ends.

`not-applicable` is also removed, subsumed by `unevaluated`: "guard has no jurisdiction" and
"guard looked and no rule matched" are the same governance fact, and splitting them invited
a consumer to treat one as benign.

## 5. Consumer caveat — READ THIS BEFORE AGGREGATING

**`baron.capability.verb` CAN be non-empty on a row whose `baron.enforcement` is
`unevaluated`.** The `..`-escape deny is exactly that: verb `write_path`, enforcement
`unevaluated`.

Any verb-level aggregation — "how often was `write_path` enforced?" — **must filter on
`baron.enforcement == "enforced"` first**, then count verbs. Counting the verb tuple alone
books structural refusals as capability enforcement, which is the §1 over-claim in a smaller
costume.

ADR-014 committed this as fixture scenario 10 so the caveat would be testable rather than
prose. The equivalent here is `test_verb_aggregation_must_filter_on_enforcement_first`,
which emits two real rows carrying `write_path` — one adjudicated, one structural — and
asserts the naive count is 2 while the correct count is 1. It fails if the semantics drift
back.

Corollary for the inverse direction: an **empty** verb tuple does not mean "not enforced"
(row 2 of the §2 table). `baron.enforcement` is the field to read; `baron.capability.verb`
is detail, not a proxy.

## 6. What this does NOT decide

Scoped deliberately narrow, so the parts of D1 that are merge work do not ride in on a
semantics decision:

- ~~**`telemetry.py` / `harden/otel` is still unmerged.** This ADR ports one flag and one
  vocabulary onto ADR-013's transport. Retiring `telemetry.py` and re-merging
  `ingest_otel.py`'s `partition_guard_records` remain open.~~ **Both closed since.**
  `partition_guard_records` was ported on 2026-08-09
  ([ADR-021](ADR-021-audit-ingester-partitions-observation-rows.md)), and ADR-014's transport
  was **retired** on 2026-08-10 ([ADR-014](ADR-014-guard-telemetry.md)) — a recording action,
  since it was never merged. `harden/otel` is kept as history and nothing further comes off
  it. The scoping this bullet describes was correct for this ADR and is now historical.
- ~~**The default sink is still `null`** (decision D4 is untouched).~~ **D4 was decided
  2026-08-10 and the default stays `null`** ([ADR-013 §7.1](ADR-013-observation-plane-events-and-sinks.md)) —
  a decision, not a deferral, and no code change. Nothing emits until an operator opts in,
  which is still the fact this ADR's §7 breaking-change argument rests on.
- **No consumer-side metric ships here.** ADR-014 §4.3's rule that `error` rows are excluded
  from the enforcement split is a property of `compute_guard_metrics`, which is not on this
  branch. When it lands it must honour that exclusion; the span still carries `unevaluated`
  for an error row, which is the true label for that row.
- **`read_code` / `read_collab` on `baron rules list`** (decision D3, ADR-016 §8) is the
  posture surface, a different unit, and untouched here. *(D3 was decided the same day and
  the label is unchanged — [ADR-020](ADR-020-read-verb-posture-measured-on-four-adapters.md)
  rebuilt its basis on four measured adapters. Still a different unit; still untouched here.)*

## 7. Consequences

**Good.** The field now answers the question its name implies, and the answer is one a
control guard can actually observe. Two measured defects flip, both pinned by tests. A path
added tomorrow that forgets to set the flag reports less enforcement, never more.

**Costs and accepted risks.**

- **`unevaluated` is a big bucket.** Out-of-jurisdiction, no-rule-matched, structural refusal
  and fail-closed error all share it. A consumer wanting them apart must join on
  `baron.outcome` (`error` separates the fourth) and `baron.capability.verb` (non-empty on a
  structural refusal). Splitting the label instead was rejected: four values invite
  aggregation over subsets nobody validated, and the `outcome` axis already carries the
  distinction that matters.
- **`_enforcement_class` calls `_rules()` on every non-adjudicated emission** to distinguish
  `unknown` from `unevaluated`. `load_rules()` is `lru_cache`d, so this is a dict lookup
  after the first call in a process — but guard is a cold Python start per tool call, so the
  first emission in each hook process pays the artifact read. Unmeasured; the default sink
  is `null`, so the ordinary install pays nothing.
- **This is a breaking change to a published label** — accepted knowingly, because the
  default sink is `null` and no consumer exists yet. It is the last cheap moment.
- **The `guard.override` row is labelled `enforced` when the underlying call was
  adjudicated.** The adjudication happened; a human overrode its result. A consumer counting
  `enforced` without splitting on `baron.outcome` will read an override as a clean
  enforcement. Stated rather than fixed: `outcome` already carries it, and collapsing the
  two would lose the fact that a boundary was reached at all.
