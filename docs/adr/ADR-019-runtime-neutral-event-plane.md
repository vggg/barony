---
created: 2026-08-09
accepted: 2026-08-09
type: decision
status: accepted
adr: 019
project: barony
related:
  - "[[docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap]]"
  - "[[docs/adr/ADR-012-hook-coverage-and-evidence-capture]]"
  - "[[docs/adr/ADR-013-observation-plane-events-and-sinks]]"
  - "[[docs/adr/ADR-018-adjudicated-enforcement-on-the-event]]"
---

# ADR-019: The observation plane is runtime-neutral — and a second producer proves it

| Field | Value |
|---|---|
| **Status** | Accepted (2026-08-09) |
| **Date** | 2026-08-09 |
| **Authors** | Vikram + Claude |
| **Supersedes** | ADR-012 §4's `baron.hook_event` attribute (renamed, no alias) |
| **Builds on** | ADR-018 (`Decision.adjudicated`), unchanged and reused verbatim |
| **Decision owner** | Vikram (raised while closing D1 in `docs/DECISIONS-FOR-REVIEW.md`) |

## 1. Context

ADR-001's whole premise is that the canonical layer is runtime-neutral and each runtime
adapts to it. The observation plane ADR-013 landed was built inside a Claude Code
workstream, and it *looks* neutral: `events.KNOWN_KINDS` is `guard.decision`,
`session.start`, `tool.post`, … — not a Claude name among them — while
`guard.KNOWN_HOOK_EVENTS` holds Claude Code 2.1.226's 31 hook names behind a dispatch
table. The layering is right.

Two things were not.

**(1) One Claude Code concept sat on the neutral wire.** Every evidence row carried
`baron.hook_event`, whose value is a Claude Code hook name, with `PreToolUse` as its
default. Read from a stream that one day carries two runtimes, the key asks a question
only one runtime can answer. Its default was worse than merely Claude-shaped: evidence
handlers are never invoked for `PreToolUse` (ADR-012 §2 routes that to enforcement), so a
payload naming no event was stamped with the one trigger that function cannot be called
for — an unreachable default that was also wrong.

**(2) Neutrality was asserted, never shown.** Exactly one producer had ever written a row.
Nothing distinguished "this plane is runtime-neutral" from "this plane has one producer
and that producer is Claude Code". `docs/BACKLOG.md` said so plainly: *"Other runtimes have
no evidence seam. The pydantic-ai adapter enforces in-process but emits nothing; the event
stream is Claude-Code-only today, exactly as enforcement was before v1.6.0."*

That is the same shape of claim ADR-018 had just finished removing from
`baron.enforcement` — a property asserted rather than measured — one level up.

## 2. Decision — every row says WHICH runtime produced it

New attribute `baron.runtime`, on every guard-sourced row: `"claude-code"`,
`"pydantic-ai"`, or `"unknown"`. The landed set is pinned as `guard.KNOWN_RUNTIMES`.

This is the attribute the plane needed before it could honestly be called neutral. Without
it a merged stream is unpartitionable, and — worse for a project that publishes a fidelity
number — a consumer cannot tell **"pydantic-ai never denied anything"** from
**"pydantic-ai never ran"**. Both look like an absence of rows.

**The default is `unknown`, not `claude-code`.** `_Trace.runtime` defaults to
`RUNTIME_UNKNOWN` and `guard.process()` — which *is* the Claude Code producer — states its
identity explicitly. A producer that forgets is therefore *unattributed*, never
*mis-attributed*. Same rule, same reasoning, as ADR-018's `adjudicated` default: the
failure mode a governance stream can live with is under-claiming.

## 3. Decision — `baron.hook_event` becomes `baron.trigger`: neutral key, native value

The three options considered, and why the middle one:

| Option | Verdict |
|---|---|
| **(a) Keep it Claude-scoped, document it.** Emit `baron.hook_event` only from the Claude producer; other runtimes omit it. | **Rejected.** It leaves the plane's fixed vocabulary containing one runtime's word, and a second producer with a seam name has nowhere neutral to put it — so it invents `baron.pydantic_seam` and the wire forks per runtime. Documentation does not stop that; a key does. |
| **(b) Rename to `baron.trigger`, value stays runtime-native.** | **CHOSEN.** |
| **(c) Normalise the values too** — map `PreToolUse` and `before_tool_execute` onto a baron vocabulary like `pre-tool`. | **Rejected.** It puts a translation nobody can verify between the reader and the name the runtime actually uses in its own docs and logs. When the row and the runtime's documentation disagree, the analyst is stuck. Neutrality is owed by the *schema*, not by flattening what each runtime calls its own seam. And baron would then be maintaining a mapping table that must be right for runtimes it has never run. |

So: the KEY is neutral and shared, the VALUE is deliberately the runtime's own name, and
`baron.trigger` is **only meaningful read together with `baron.runtime`**. That pairing is
stated in `events.py`'s reserved-key list, which is where a consumer looks.

**No alias, no deprecation window.** `baron.hook_event` is gone, not carried alongside.
Two names for one fact is the cost, and the benefit would be compatibility for a consumer
that does not exist: the default sink is `null` (D4 unsigned), nothing has ever emitted in
anger, and ADR-018 took exactly this "last cheap moment" reasoning three commits ago for a
label with more downstream weight. `test_baron_hook_event_is_gone_from_the_wire` pins it.

The Claude-side fallback is also fixed: `baron.trigger` falls back to `""` — the honest
"the producer did not say" — instead of the unreachable-and-wrong `PreToolUse`.

## 4. Decision — one producer seam, `guard.observe_decision`, and it is public

`_Trace` stops being "what one *PreToolUse* evaluation observed" and becomes "what one
*capability evaluation* observed". The new public function:

```python
guard.observe_decision(
    decision,            # a real Decision, or None for "reached no verdict"
    *, runtime, trigger, tool, subject, outcome,
    actor="unknown", session_id="", cwd=None, reason="", error="",
    kind="guard.decision",
)
```

**Why the `Decision` is a parameter and not re-derived inside.** ADR-018 made
`baron.enforcement` readable off `Decision.adjudicated` and nothing else. Keeping that
property under a *public* API means the API must offer no other route to the label: there
is no `enforcement=` argument, and nothing is inferred from `outcome`, `verbs` or
`subject`. A caller passing `None` gets `unevaluated` even while asserting a deny — pinned
by `test_the_seam_cannot_be_talked_into_claiming_enforcement`. **The only way to put
`enforced` on the wire is to hand over a decision that earned it.**

Emission stays one-way and fail-OPEN (ADR-013 C4): `observe_decision` never raises and
returns nothing, so no adapter can accidentally make an enforcement outcome depend on a
sink.

## 5. Decision — pydantic-ai becomes a real second producer, and that is the evidence

`BaronGuardCapability.before_tool_execute` — the seam that already vetoes calls in-process
— now emits `guard.decision` through `observe_decision`, tagged
`baron.runtime="pydantic-ai"` / `baron.trigger="before_tool_execute"`.

ADR-001 §4.5 accepts an adapter on evidence from a real runtime. So the test that carries
the claim drives a **real `Agent.run_sync`** (offline `FunctionModel`) through pydantic-ai's
own model loop and capability dispatch, and then reads the file the **real `DiskSink`**
wrote. Not baron calling itself.

What the port had to preserve, and does:

- **`check()` could not carry it.** It returned `str | None`, which collapses "allowed" and
  "no jurisdiction" into the same `None`. Emission needs them apart, because
  out-of-jurisdiction must emit *nothing*. Hence `decide() -> Decision | None`, with
  `check()` kept as a thin predicate over it (its callers and tests are unchanged).
- **Two deliberate silences, both mirroring the hook.** Read tools (`read_file`,
  `list_directory`, `search_files`) emit no row, exactly as `Read`/`Grep` emit none under
  PreToolUse — one row per read would bury the verdicts and inflate any denominator
  computed over `guard.decision`. And a broken sink cannot stop the veto.
- **Correlation by the same derivation.** `guard._trace_id(session_id)`, where the session
  id is pydantic-ai's `conversation_id` (a conversation spans several `Agent.run` calls —
  the same granularity as a Claude Code session), falling back to `run_id`. Neither
  present → `""` → no fabricated shared trace, the rule `_trace_id` already stated.

**The measured result**, and the reason this ADR claims neutrality rather than asserting
it: driven with the same persona and the same command, the two producers append to the
**same** `.baron/events/` file, and the two rows differ in exactly four attributes —
`baron.runtime`, `baron.trigger`, `tool.name` (the runtimes name their own tools: `Bash`
vs `run_command`) and `session.id`. Verdict, verb, enforcement label, actor, subject and
reason are byte-identical. `test_two_producers_one_stream_one_wire_shape` asserts the
difference set exactly, so a future divergence in either direction fails.

ADR-018's two measured defects were also re-checked *on the new producer*, not inherited:
the `..`-escape structural refusal reads `unevaluated` with a non-empty verb tuple, and the
`write_code` allow reads `enforced` with an empty one.

### How a THIRD runtime registers its seam

Three steps, no new machinery, and step 1 is allowed to end the process:

1. **Find the runtime's own pre-execution seam** — a point where it can still veto a tool
   call. If it has none, **stop and say so.** Do not emit from a post-hoc hook and file the
   rows as enforcement evidence.
2. **Evaluate through `guard.evaluate_bash` / `guard.evaluate_write`**, the same functions
   the Claude hook calls, so the same `capability-rules.v1.yaml` adjudicates and the
   decisions are identical by construction rather than by review.
3. **Call `guard.observe_decision`** with that `Decision`, your runtime id (added to
   `KNOWN_RUNTIMES`), and your runtime's native seam name as `trigger`.

`test_a_third_runtime_needs_only_the_public_seam` executes this recipe literally for an
invented `acme-runner` in a dozen lines, and asserts the resulting row is shape-identical
to the other two. No hook payload, no `hook_event_name`, no subprocess, no stdin JSON.

## 6. What this does NOT decide, and the hole that stays open

**code-puppy has no pre-tool seam, and is deliberately NOT in `KNOWN_RUNTIMES`.**
`docs/BACKLOG.md` has recorded this since ADR-012: code-puppy has no PreToolUse equivalent
today. This ADR does not invent one. Emitting rows from a post-hoc log would put
observations on the plane implying an adjudication that never happened — the ADR-018
over-claim in a new costume, and precisely what a project publishing 0.53 must not do.

So the honest state of the neutrality proof is **two producers, not three**, and the third
is blocked on the runtime rather than on baron. `test_known_runtimes_is_the_landed_set_and_code_puppy_is_absent`
pins the tuple so it grows with a landed adapter and never with an intention. The
`generic` adapter is in the same position for the same reason: no seam, no producer.

Also out of scope, stated so they are not read as done:

- ~~**The `claude` and `code-puppy` kits stay unmeasured** for tool exposure (D3, ADR-016 §8).
  Unrelated axis, unchanged here.~~ **Obsolete as of the same day.**
  [ADR-020](ADR-020-read-verb-posture-measured-on-four-adapters.md) measured all four
  adapters — `claude`, `code-puppy` and `generic` statically, `pydantic-ai` live — and all
  four are negative. The axis is still unrelated to this ADR and still unchanged by it; what
  is no longer true is the word *unmeasured*.
- **The pydantic-ai producer does not honour `BARON_GUARD_OVERRIDE`.** The adapter never
  did — there is no in-process override path — so it emits no `guard.override` rows. A
  consumer comparing override rates across runtimes will read zero for pydantic-ai and must
  not read that as "no overrides happened".
- **The adapter's error policy is unchanged.** A `GuardError` (unreadable rules artifact)
  still propagates out of `before_tool_execute` and aborts the run rather than becoming a
  `ModelRetry`. ADR-019 adds only the observation of it — an `error`-outcome row carrying no
  `Decision`, hence `unevaluated`. Converting it to a veto is a behaviour change to
  enforcement and belongs in its own decision.
- **The default sink is `null`** — and since 2026-08-10 that is a signed decision rather than
  an unexamined default (D4, [ADR-013 §7.1](ADR-013-observation-plane-events-and-sinks.md)).
  Both producers write nothing until an operator opts in. Note the consequence for the
  breaking rename below: the no-consumer window this ADR spent is now held open deliberately,
  not by accident.

## 7. Consequences

**Good.**

- The plane's neutrality is now a measurement (two producers, one file, an exact difference
  set) instead of an architectural intention.
- A consumer can partition a merged stream by producer, and can tell silence from absence.
- Adding a runtime is one public function call, and the honest-label property is enforced
  *by the shape of that function* rather than by the next author reading ADR-018.
- The pydantic-ai adapter stops being enforcement-without-evidence — the gap
  `docs/BACKLOG.md` named.

**Costs and accepted risks.**

- **Breaking rename, no alias.** Any consumer reading `baron.hook_event` breaks. Accepted
  on the same grounds as ADR-018 §7: default sink `null`, no consumer exists, and this is
  the last cheap moment. If a sink is turned on before this lands, the argument expires.
- **Two more attributes on every row.** Guard is a cold Python start per tool call; this is
  two dict entries and two short strings, not a new read. Unmeasured, and stated as such.
- **`baron.trigger` values are not comparable across runtimes.** Deliberate (§3c), and it
  means any cross-runtime aggregation must group by `baron.runtime` first. The same shape
  of caveat as ADR-018 §5, and recorded in the same place — `events.py`'s reserved-key list.
- **`KNOWN_RUNTIMES` is a pinned tuple, so adding a runtime touches core.** Making it an
  entry-point group was rejected: `baron.sinks` earned its group by shipping two consumers
  (ADR-015 §4's rule), and a runtime id is a two-line change, not a plugin surface. Revisit
  when an out-of-tree adapter actually exists.
- **Only the two in-tree runtimes are covered.** Two producers is enough to falsify
  "Claude-Code-shaped"; it is not proof that the shape fits every runtime. The third one to
  try it will find out, and §5's recipe is written so that finding out is cheap.
