---
created: 2026-08-09
accepted: 2026-08-09
type: decision
status: accepted
adr: 018
project: barony
related:
  - "[[docs/adr/ADR-002-ways-of-working-2026-07]]"
  - "[[docs/adr/ADR-006-baron-init-template-packaging]]"
  - "[[docs/adr/ADR-008-ways-of-working-2026-07-31]]"
  - "[[docs/adr/ADR-016-externalizable-capability-rules]]"
---

# ADR-018: the read-verb posture label rests on four measured adapters

| Field | Value |
|---|---|
| **Status** | Accepted (2026-08-09) |
| **Date** | 2026-08-09 |
| **Authors** | Vikram + Claude |
| **Supersedes** | ADR-016 §4.1's *round-3 correction* (the "one measured, three unmeasured" scoping) |
| **Implements** | The owner's D3 decision — see `docs/DECISIONS-FOR-REVIEW.md` §A/D3 and ADR-016 §8 D-1 |
| **Decision owner** | Vikram |

## 1. Summary

`baron rules list` prints `instructed` for `read_code` and `read_collab`. That
label was correct and its **basis was not**: one adapter (`pydantic-ai`) was
measured and the label spoke for four. This ADR supplies the missing three
measurements and rebuilds the published caveat on top of all four, so the claim
and its evidence are the same size.

Nothing about the printed label changes. What changes is what stands behind it.

## 2. The defect in the round-3 wording

Round 2 of ADR-016 wrote "no adapter baron ships does" — a property of four
adapters asserted from one instrumented test. Round 3 caught that and narrowed
it honestly: pydantic-ai measured, `claude` and `code-puppy` **unmeasured**,
`generic` not mentioned at all. That was the right call at the time and it is
also a stopping point, not a resting place:

- `baron rules list` has one label per verb, not one per adapter. A label
  derived from one adapter still *speaks for* four the moment it is printed.
- "Unmeasured" is an honest word that decays. It reads as "someone will get to
  it", and five reviews of this project have shown that nobody does unless a
  test fails when they don't.
- ADR-016 §8 itself named the fix — option **(c)**, instrument all four — and
  declined it as "a larger piece of work than this ADR". That estimate assumed
  the work was symmetric with the pydantic-ai measurement. It is not (§3).

## 3. The asymmetry that makes this cheap

Proving the **presence** of enforcement requires a live runtime: you have to
watch a real tool call be refused, which for `claude` and `code-puppy` means
driving a real agent process — the same thing `docs/DECISIONS-FOR-REVIEW.md` §E.1
records as not done anywhere in this project.

Proving the **absence of a baron-emitted mechanism** is static. Enumerate every
artifact `baron init` writes into a runtime kit and show that none of them is a
construct a runtime reads as a tool allow/deny list. No runtime required.

For the read verbs the answer is negative on all four adapters, so the cheap
direction is the one that was needed. That is why option (c) was mis-costed.

## 4. Decision — one measurement per shipped adapter

`baron.rules.READ_VERB_MEASUREMENTS` maps each adapter to the evidence and the
test that produces it. `LABEL_CAVEAT` is **built from that dict**, so the
published caveat cannot drift from the measurements behind it.

| Adapter | Measurement | Kind |
|---|---|---|
| `pydantic-ai` | The emitted `agent_setup.py` builds `FileSystem` unconditionally; `read_file`/`list_directory`/`search_files` survive a `read_code` denial, and the in-process guard vetoes none of them. | **Live** — `test_pydantic_ai.py::test_denying_read_code_does_not_omit_read_tools` (pre-existing; untouched) |
| `claude` | The kit's only machine-readable artifact is `.claude/settings.json`. Every key at every depth is hook wiring; no `permissions`, `allowedTools` or `disallowedTools`, and no `.claude/agents/<slug>.md` subagent anywhere — including at repo level. | **Static emission** — `test_adapter_omission.py` |
| `code-puppy` | The kit is `README.md` + `AGENTS.md`, both prose. code-puppy's real enforcement surface is the agent JSON's `tools` list (`JSONAgent.get_available_tools()` filters against `TOOL_REGISTRY`); baron emits no JSON at all for this runtime. | **Static emission** — `test_adapter_omission.py` |
| `generic` | Tier 1 has no allow-list surface to emit into; its own HYDRATE.md says "It emits no ENFORCED artifact". The kit is prose. | **Static emission** — `test_adapter_omission.py` |

### 4.1 The experiment, not just the assertion

Each static test is an A/B, not an inspection. Baron is handed two persona specs
that are **identical but for the two read verbs** — one denying them, one
allowing them — and generates a kit from each. Three things are then true:

1. the denial appears in the kit's **prose** ("Never read the code repo.");
2. every **machine-readable** artifact is byte-identical across the pair (modulo
   the persona slug, which is legitimately in the hook's `--persona-file` path);
3. no artifact in either kit is a construct that could omit a read tool.

(2) is the load-bearing one. If nothing baron emits is even a *function* of the
denial, the denial cannot be mechanised by anything baron emits. That is exactly
what `instructed` means, demonstrated rather than argued.

The denying persona is byte-identical to the fixture the pydantic-ai gate test
uses, asserted by `test_the_four_adapters_are_measured_on_the_same_input`. Four
adapters, one input.

### 4.2 The honest bound, and it is in the API

A negative verdict means **baron emits no mechanism**. It does **not** mean the
runtime cannot enforce the verb, and the difference is not pedantry:

- a user who hand-writes `permissions.deny` into `.claude/settings.json` gets
  real whole-tool enforcement;
- `adapters/claude/HYDRATE.md` §3a and `adapters/code-puppy/HYDRATE.md` §2 both
  describe a **Tier-3** path whose `tools:` allow-list omits read tools, and
  both label the read verbs `enforced` in their own tables. Those tables are
  correct *about the artifact the recipe tells a human to hand-author*. Baron
  generates neither — `scaffold.py`'s module docstring already records Tier-3
  hydration as conversational, by design.

So the two surfaces disagree only in appearance. `baron rules list` reports the
posture of **what baron ships**; a HYDRATE.md table reports what the runtime
does **once a human has followed the recipe**. An instruction a human may or may
not follow is the definition of `instructed`, which is why the divergence is not
a bug to fix by editing one of the two tables. It is recorded as a known
divergence in §7 and the caveat states it in the product surface.

### 4.3 What was NOT done

`baron rules list` remains **one label per verb**, not a per-adapter matrix. All
four adapters agree on the read verbs today, so nothing is lost by collapsing
them; the day they disagree, the collapse becomes a lie and §6 is where that
gets settled.

## 5. Decision — the harness, and where the caveat is printed

The three static tests share `cli/tests/omission.py`, which answers one
question: *does adapter X emit a mechanism capable of omitting the tools that
verb Y grants?* It is keyed `(adapter, verb)` because the per-runtime capability
matrix is the planned follow-up and this is slice one — a fourth bespoke test
per verb does not scale to 4 × 10.

Three properties make its **negative** answers worth anything:

- **Refuse, don't ignore.** `KIT_ARTIFACTS` is a closed classification of every
  artifact baron emits per adapter. An artifact the harness has never seen is
  reported as `unclassified` and the assertion helper fails on it *before* it
  looks at mechanisms. A silent pass on an unrecognised artifact is precisely
  how a mechanism would arrive unnoticed. (This is `rules.py`'s parser rule
  applied to emission.)
- **Static inspection refuses to clear executable output.** `agent_setup.py` is
  classified `KIND_CODE`; probing it returns `needs_live_measurement` naming the
  live gate test, and the helper raises rather than returning a clean verdict.
  A harness that quietly cleared pydantic-ai statically would be manufacturing
  the fourth measurement instead of making it.
- **"Nobody looked" cannot read as "nothing found".** An adapter with no
  registered mechanism, no recorded reason there is none, and no live
  measurement would otherwise sail through `probe()` with a clean verdict it did
  nothing to earn. `probe()` refuses to answer for such an adapter, and every
  shipped adapter is asserted accounted for. This is the same distinction the
  label itself is about, applied one level down.
- **It is verified to fail.** `test_the_harness_detects_a_mechanism_when_one_is_present`
  plants each registered mechanism — a `permissions.deny` block, a Tier-3
  subagent file, a code-puppy agent JSON — into a real generated kit and asserts
  the probe fires on each.

**Caveat rendering.** `LABEL_CAVEAT` (the full claim plus all four measurements)
is what the `--json` payload publishes, top-level and per row, unchanged in
kind. The human table prints `LABEL_CAVEAT_SUMMARY` — the same claim and the
same bound, minus the evidence — followed by one `measured — <adapter>: …` line
each. Four measurements inlined into a single paragraph is a wall of text nobody
reads, and an unread caveat is the failure mode the field exists to prevent.
`test_rules_list_table_names_the_honesty_caveat` asserts the summary is a
literal prefix of the full string, so the short form can never become a softer
paraphrase.

## 6. Consequences

- ADR-016 §8 **D-1 is APPROVED**, with the basis recorded as four measured
  adapters rather than one measurement generalised to four. §4.1's round-3
  scoping is superseded, not merely supplemented.
- Adding a fifth adapter **breaks the label's basis** until it is measured:
  `test_the_label_rests_on_one_measurement_per_shipped_adapter` asserts
  `set(rules.READ_VERB_MEASUREMENTS) == set(scaffold.ADAPTERS)`. This is the
  anti-drift lock the round-3 wording structurally could not provide — prose
  saying "the others are unmeasured" fails no test when a sixth adapter lands.
- `DECISIONS-FOR-REVIEW.md` §E.3 ("three of four adapters are unmeasured") is
  retired and replaced with the narrower bound that is actually true.
- The harness reaches into `scaffold._Context` and `scaffold._emit_runtime_kit`.
  This is contained to one function and self-checked: `emit_kit` re-emits an
  init-created persona first and asserts the bytes match `baron init`'s own
  output, so a drifting reconstruction fails loudly instead of quietly measuring
  something baron does not emit. The alternative — a public re-hydration API on
  `scaffold` — is a product surface with its own ADR, and inventing one to
  satisfy a test is the wrong order.
- `CLAUDE_SETTINGS_KEYS` is a closed allowlist of the keys the emitted hook
  wiring uses. **A new hook event added to the scaffold will fail this test**,
  deliberately: whoever widens what baron writes into `settings.json` should
  have to look at whether the new key gates tools.

## 7. Known divergence, recorded rather than resolved

`adapters/claude/HYDRATE.md` and `adapters/code-puppy/HYDRATE.md` print
`enforced` for the read verbs in their Tier-3 verb→tool tables, while
`baron rules list` prints `instructed`. Both are correct about different things
(§4.2): the HYDRATE tables describe a hand-authored artifact, `rules list`
describes what baron ships. They were left alone on purpose — editing them to
say `instructed` would make them *wrong* about Tier 3, and editing `rules list`
to say `enforced` would make baron claim a mechanism it does not emit, which is
the exact failure this project exists to catch.

The durable fix is the per-runtime capability matrix (§5's follow-up): a surface
that can say "instructed as shipped; enforced at Tier 3 once hydrated" without
either table lying. Until it exists, the caveat carries the distinction in prose.

## 8. Decision record

- [x] **Approved as written** — the owner's D3 decision, executed.
- [ ] Approved with changes
- [ ] Needs revision
- [ ] Rejected

Basis: four measured adapters (§4). The scope this replaces — "the one adapter
measured does not; the others are unmeasured" — is obsolete and has been updated
in ADR-016 §4.1 and §8, not left standing alongside it.
