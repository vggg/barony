---
created: 2026-08-09
accepted: 2026-08-09
type: decision
status: accepted
decided_by: Vikram
adr: 016
project: barony
related:
  - "[[docs/adr/ADR-003-baron-cli]]"
  - "[[docs/adr/ADR-004-baron-guard-enforcement]]"
  - "[[docs/adr/ADR-008-ways-of-working-2026-07-31]]"
---

# ADR-016: externalizable capability rules, step 1 — the rule-list representation and the `baron rules` surface

| Field | Value |
|---|---|
| **Status** | Accepted (2026-08-09) |
| **Date** | 2026-08-09 |
| **Authors** | Vikram + Claude |
| **Extends** | [ADR-004](ADR-004-baron-guard-enforcement.md) §2.2 and addendum §4.1 (the rules artifact) |
| **Answers** | `docs/BACKLOG.md` § *Considered directions → User-extensible guard rules* (2026-07-28) — the **cheap** half, in two steps, of which this is step 1 |
| **Does NOT decide** | Whether projects may define their own verbs (§6.1), or the project-rules loader's precedence semantics (§5) |
| **Superseded in part** | §4.1's *round-3 correction* — "pydantic-ai measured, the other kits unmeasured" — by [ADR-020](ADR-020-read-verb-posture-measured-on-four-adapters.md) (2026-08-09). The printed label is unchanged; its basis is now four measured adapters. Marked inline in §4.1 and §8. |
| **Revised** | 2026-08-09 (round 2) — §3.2, §4.1 and §7 corrected after review. Three claims in the first draft overstated what was mechanised: the closed-matcher refusal was unreachable from document input, `read_code`/`read_collab` were labelled `enforced` on the strength of an adapter behaviour that does not exist, and §7 counted two new document-reachable refusals where there was one. Corrections are marked inline. |

## 1. Summary

Teams want project-specific guard rules without forking baron. The blocker was
never the loader — the rule table has been externalized data since v1.6.0
(`cli/src/baron/data/capability-rules.v1.yaml`). The blocker was the *parsed
representation*: `rules.CapabilityRules` was a flat record with one field per
built-in rule (`push_force_flags`, `push_force_verb`, `gh_pr_merge_subcommand`,
`universal_write_components`, …). A structure with a fixed field per rule
cannot hold an **additional** rule. No amount of loader work makes extension
possible until that changes.

This ADR decides two things and deliberately defers a third:

1. **`CapabilityRules` becomes a rule LIST** — `command_rules: tuple[CommandRule, ...]`
   and `path_rules: tuple[PathRule, ...]`, each rule carrying a stable `id`, a
   `matcher` from a closed set, a `verb`, and a `source` provenance tag. Every
   pre-existing flat name survives as a derived read-only property with the
   identical name and type. The parser reads rule ids and command-rule matchers
   **from the document** and refuses any key or rule it does not implement
   (§3.2).
2. **A `baron rules` command surface** — `list`, `validate`, `diff`, `explain`.
   Diagnostic and read-only. `explain` is a *dry run of the real decision*: it
   calls `guard.evaluate_bash` / `guard.evaluate_write`, so it cannot drift from
   what the hook does.
3. **The project-level rules loader is NOT built here** (§5). It is a set of
   one-way doors that need their own ADR and their own owner decision.

Nothing about the frozen 10-verb vocabulary changes. `rules_version`
negotiation stays exact-match refusal. Conservative-deny and fail-closed are
untouched.

## 2. Context

`docs/BACKLOG.md` (2026-07-28, from the launch Q&A with a staff/SRE reviewer)
already scoped this correctly:

> **Cheap (natural next step):** a project-level `.baron/rules.*` … that guard
> loads *in addition to* the packaged rules, for the **existing modalities** …
> The rules are already externalized data; this is mostly a loader + merge + a
> precedence/validation story, no new detection code. Keep the honesty label:
> user rules are still `enforced` only for the shapes guard can mechanically check.

What that entry missed is that "mostly a loader" is false while the parsed form
is a flat record. Concretely: to add one more `gh` subcommand rule you would
have to add a `gh_release_delete_subcommand` field and a
`gh_release_delete_verb` field, and teach `guard.py` to read them. The data was
external; the *shape* was not extensible.

There is also no way today to ask baron what it enforces. `baron guard` only
answers one question, one call at a time, over stdin, with an exit code. There
is no `list`, no `validate`, no `explain`. Every audit of what is actually
mechanised has been done by reading YAML by hand — and the project's own
measured operational fidelity of 0.53 says hand-reading is not good enough.

## 3. Decision — the rule-list representation

### 3.1 Shape

```python
@dataclass(frozen=True)
class CommandRule:
    id: str                      # "git.push.force_flags" — the public handle
    program: str                 # "git" | "gh"
    subcommand: tuple[str, ...]  # ("push",) / ("pr", "merge")
    matcher: str                 # one of COMMAND_MATCHERS (closed set)
    verb: str                    # the capability verb a match implies
    flags / flag_prefixes / prefix / fallback_branches   # matcher parameters
    source: str = "builtin"

@dataclass(frozen=True)
class PathRule:
    id: str
    matcher: str                 # one of PATH_MATCHERS (closed set)
    components: tuple[str, ...]
    verb: str = ""               # "" when a match needs no verb
    source: str = "builtin"
```

The eight built-in rules are
`git.push.force_flags`, `git.push.plus_refspec`, `git.push.all_branches`,
`git.push.default_branch_target`, `git.merge.on_default_branch`, `gh.pr_merge`,
`file_ops.universal_write`, `file_ops.spec_dir`.

### 3.2 The matcher set is CLOSED, and the document names its matcher

`flag_present`, `refspec_prefix`, `refspec_default_branch`,
`current_branch_is_default`, `subcommand_present` (command rules);
`universal_write`, `spec_dir` (path rules). Adding a matcher (file size, time
window, rate limit, anything semantic) is new detection code in `guard.py`,
gated on observed need per vocabulary design rule 4 — this is the closed half
of the BACKLOG's cheap/expensive split made mechanical.

**Command rules carry `matcher` in the document.** Each rule in
`capability-rules.v1.yaml` states the matcher it is checked with, and the
parser validates it two ways:

1. it must be in the closed set — otherwise no consumer can enforce it, and
   accepting it would print an `enforced` label over nothing;
2. it must be *the matcher guard actually implements for that rule id* — a
   document that says `force_flags` is matched by `subcommand_present` is
   describing a check nobody performs, which is the same lie one layer down.

The field is **optional but authoritative**: absent, the rule gets guard's
matcher (so a v1 document written before this change still parses identically,
and the grammar did not break under a fixed version number); present, it is
validated, never trusted.

**Rule ids come from the document too** — a rule's id is its position,
`commands.git.push.rules.<key>` → `git.push.<key>`. The parser enumerates the
keys the document actually carries and refuses any it does not implement (§5.4
applied to the artifact itself), so the id space is closed by the same
mechanism that closes the rule set.

**Honest limit.** Path-rule matchers are **not** document-supplied. `file_ops`
is a flat block (`universal_write_components`, `spec_dir_component`) whose keys
name the scoping semantics directly; there is nowhere for a document to state a
matcher and so nothing for it to get wrong. The closed-set check over
`PATH_MATCHERS` is therefore a developer-edit guard, and is labelled as one in
the code rather than counted as document validation.

*Round-2 correction.* As first shipped, `matcher` and `id` were hardcoded in
the parser and the closed-set check was unreachable from any document — it
could only fire against a developer edit to the builtin table. The claim
"a rule naming a matcher outside the set is refused at parse time" was true of
the code path and false of the user-facing behaviour. It is now true of both,
and `test_unrecognised_document_content_is_refused_not_ignored` exercises it
from document input.

Contrast with the event-`kind` decision taken elsewhere in this hardening round
(open dotted string): that is an OBSERVATION namespace where an unrecognised
value costs nothing. This is an ENFORCEMENT contract where an unrecognised
value means mis-enforcement. Different invariant, opposite answer.

### 3.3 Behaviour preservation is the acceptance criterion

`guard.py` and `runtimes/pydantic_ai.py` are **byte-identical** across this
change — that is the proof, not a claim about it. Every name they read
(`push_force_flags`, `push_value_options`, `gh_pr_merge_verb`,
`universal_write_components`, `spec_dir_component`, …) is now a `@property`
over the rule list with the same type. `test_legacy_accessors_are_behaviour_preserving`
pins all fifteen against hand-transcribed pre-refactor literals — deliberately
literals, because re-deriving them from the artifact would test the loader
against itself.

One internal API did change: `dataclasses.replace(rules, push_force_verb=...)`
no longer works, because those are properties now. Mutation goes through the
rule list instead. Only tests did that; the new form is the more honest one
anyway (rules are data, so mutate the datum).

### 3.4 `SPEC_DIR_VERB`

The v1 artifact carries `file_ops.spec_dir_component: "agents"` but not the
verb that gates another persona's spec dir; `guard.py` names
`edit_other_personas` literally. Rather than change the artifact (a
`rules_version` bump for no behavioural gain), the constant lives in
`rules.py`, the `PathRule` carries it, and `test_spec_dir_verb_matches_the_literal_guard_uses`
asserts the pair agrees. Moving it into the artifact is a v2 change.

### 3.5 Verb-entry VALUES are validated, not just keys

`class` and `detection` are drawn from closed sets (`whole-tool | sub-tool`,
`none | command | file-op`), both are **required**, and `detection` is
cross-checked against what guard implements — symmetrically, so neither
over-claiming nor under-declaring parses.

The reasoning is the same one §3.2 applies to `matcher`, and the omission was an
inconsistency rather than a considered exception: these two fields *route
enforcement*. `detection` is what `label()` turns into the word `enforced`, and
`class` picks the `adapter-dependent` branch. A closed set on `matcher` but free
text on the two fields that decide what baron claims to enforce protects the
less important surface. Requiring them rather than defaulting follows: a missing
`detection` would silently mean "guard checks nothing", and defaulting an
enforcement decision is a guess of exactly the kind this parser exists to refuse.

The cross-check needs the verbs table *and* both rule lists, so it runs last in
`_parse`, after `_parse_command_rules`. `FILE_OP_CHAIN_VERBS` (`write_code`,
`write_path`) mirrors the write-path precedence chain in `guard.evaluate_write`,
which decides those two verbs as a whole rather than through a named `PathRule`;
it is a hardcoded mirror of guard's behaviour and would need updating if that
chain grows.

## 4. Decision — the `baron rules` surface

| Command | What it does | Exit codes |
|---|---|---|
| `rules list [--json] [--file]` | The verb table: class, detection modality, enforcement, label, and the rule ids that can imply each verb | 0, or 2 if the artifact is refused |
| `rules validate [--file] [--json]` | Parse + report the negotiation and integrity checks | 0 clean / 1 a check failed / 2 refused |
| `rules diff --file <candidate> [--json]` | Join a candidate document against the packaged artifact on **rule id and verb id** | 0 identical / 1 differs / 2 refused |
| `rules explain <target> --persona-file <p> [--write] [--cwd] [--json]` | What guard would decide for one call, and why | 0 would pass / 1 would be DENIED / 2 guard could not evaluate |

### 4.1 Three-state enforcement, but only ONE of them is `enforced`

The house rule is that enforcement is honestly labelled. `rules list` reports
three states for *who could* enforce a verb:

- **`guard`** — guard mechanically checks it (`detection` is `command` or `file-op`).
- **`adapter-dependent`** — guard does NOT parse for it, but the class is
  whole-tool, so a runtime with a tool allow-list *could* enforce it by omitting
  the tool. Whether any adapter does is a property of that adapter, not of this
  table.
- **`instructed`** — nothing checks it. `open_pr` and `run_tests`, by design.

**`label` says `enforced` only for `guard`.** `adapter-dependent` labels
`instructed`, because no *measured* enforcement backs it.

*Round-4 correction — SUPERSEDED by ADR-020: the claim now rests on four
measurements.* Round 2 wrote "no adapter baron ships does", asserting a property
of every adapter from a single instrumented test. Round 3 narrowed that
honestly: only **pydantic-ai** was measured, and the `claude` / `code-puppy`
kits were called **unmeasured**. That scoping is now **obsolete**. ADR-020
measured the other three by the cheap direction — proving the *absence* of a
baron-emitted enforcement mechanism is static (inspect what `baron init`
generates), where proving *presence* would need a live runtime — and found the
answer negative on all four:

| Adapter | Measurement |
|---|---|
| `pydantic-ai` | the emitted bootstrap builds `FileSystem` unconditionally; the read tools survive a `read_code` denial (live) |
| `claude` | the only machine-readable artifact, `.claude/settings.json`, is hook wiring: no `permissions` / `allowedTools` / `disallowedTools`, no `.claude/agents/` subagent (static) |
| `code-puppy` | the kit is prose only; the agent JSON that *is* code-puppy's enforcement surface is hand-authored in-session, never emitted (static) |
| `generic` | Tier 1 has no allow-list surface to emit into (static) |

`baron.rules.READ_VERB_MEASUREMENTS` holds one entry per shipped adapter and
`LABEL_CAVEAT` is built from it, so a fifth adapter breaks the label's basis
until someone measures it. The label is unchanged; the *reason* is no longer
"unmeasured" but "baron emits no mechanism", with the bound stated explicitly —
that is a claim about what baron ships, **not** a claim that a runtime cannot
enforce these verbs. See ADR-020 §4.2 and §7.

*Round-2 correction — this ADR previously got this wrong.* The third state was
called `tool-omission` and `label` collapsed it to `enforced`, so
`baron rules list` claimed `read_code` and `read_collab` were enforced. They are
not. The pydantic-ai adapter baron ships constructs `FileSystem`
unconditionally (`# FileSystem: always present (reads)`) and
`BaronGuardCapability.check` returns `None` for every read tool, so a persona
that *denies* `read_code` still gets `read_file`, `list_directory`,
`search_files`, `find_files` and `file_info`. The claim was reasoning from the
vocabulary's enforceability *class* — what a runtime could in principle do —
and printing it as a fact about what baron does. That is exactly the failure
mode ADR-002 exists to prevent, and the project's measured 0.53 operational
fidelity is what it looks like at scale.

The fix is not just a renamed constant. The label is now **gated by a
measurement**: `test_denying_read_code_does_not_omit_read_tools` hydrates a
persona denying `read_code` through `pydantic_ai.plan()`, asserts the read tools
are present on the toolset and that the in-process guard vetoes none of them,
and *then* asserts the label is `instructed`. If an adapter ever does omit read
tools, that assertion fails first and the label follows it — never the reverse.
(ADR-020 adds three sibling measurements on the same persona fixture, one per
remaining adapter; the gate above is unchanged.)
*Round-3 correction — that test was circular.*
`test_only_guard_checked_verbs_are_labelled_enforced` derived the expected label
from `detection`, the very field under test, and only ran against
`load_rules()`. It therefore restated the document back to itself: a document
declaring `detection: command` for `read_code` satisfied it while
`baron rules list` printed `enforced` for a verb nothing checks. It is replaced
by two non-circular tests plus a parser change:

- `test_enforcement_claims_are_pinned_to_a_literal_table` — `EXPECTED_CLAIMS`
  states the `(class, detection, enforcement, label)` tuple for all ten verbs as
  **literals**. Changing what baron claims to enforce now shows up as a diff in
  review.
- `test_every_enforced_verb_is_backed_by_a_real_check` — asks whether a rule (or
  the file-op chain) could actually fire, not what the document says.
- and `_check_detection_consistency` makes the decoupling **unrepresentable from
  document input**, which is the durable fix: the state the circular test failed
  to catch can no longer be parsed at all.

The qualifier travels in the **JSON payload**, not only the human table: a
top-level `label_caveat` plus a per-row `caveat` on the affected verbs. Machine
consumers are the ones most likely to trust `label` unread, and a footer printed
by the text renderer never reaches them.

### 4.2 `explain` reuses the real evaluators

`explain` calls `guard.evaluate_bash` / `guard.evaluate_write` directly.
`test_rules_explain_matches_guard_evaluate_bash_exactly` asserts the JSON
verdict equals the `Decision` the evaluator returns for the same input, so a
second implementation cannot creep in. This is the diagnostic seam a future
`baron doctor` and any future extension both need.

**Honest limit, stated in `--help`:** `candidate_rules` lists the rules that
*can* imply a verb, not the single rule instance that matched. Guard's own
`reason` string names the concrete inference ("force flag `--force`");
re-deriving the exact matched rule in the CLI would mean a second parser that
could drift from the first, which is precisely the failure this project keeps
finding.

### 4.3 `validate --file` does not activate anything

`baron rules validate --file X` and `baron rules diff --file X` parse X. They
do **not** load it into guard. Nothing outside the packaged artifact is
consumed by any enforcer. This is stated in the sub-app help, in both commands'
`--help`, in `rules.py`'s module docstring, and pinned by
`test_guard_reads_packaged_data_only`.

## 5. Deferred — the project-level rules loader (`.baron/rules.yaml`)

Not built here. The refactor makes it a small follow-up; what makes it *not*
this PR is that it is a bundle of one-way doors, each of which needs an owner
decision and its own ADR. Recording the positions so the next round does not
re-derive them:

- **§5.1 Add-only, deny-only.** Project rules may only *add* denials. They may
  never grant a capability and never narrow a built-in denial. A rules file
  that can weaken enforcement is a rules file that becomes an attack surface
  and a support burden. Built-in deny always wins.
- **§5.2 Never new verbs.** See §6.1.
- **§5.3 Explicit min/max on BOTH artifacts.** Negotiation today is exact-match
  on one artifact (`SUPPORTED_RULES_VERSION`, `SUPPORTED_VOCABULARY`).
  A scheme spanning two independently versioned documents is a compatibility
  contract that cannot be tightened later; the supported range for each side
  must be written down before the first project file exists in the wild.
- **§5.4 A malformed project file REFUSES, it does not get ignored.** This
  matches the measured fail-closed hook policy: guard turns a `RulesError` into
  an exit-2 DENY. Note this is deliberately *unlike* `.baron-waivers.yaml`,
  which soft-fails and reports problems — waivers relax a report, rules decide
  an enforcement.
- **§5.5 Cache safety.** `load_rules()` is `lru_cache(1)` over packaged data and
  takes no arguments precisely so the process-global cache is correct. The
  moment it becomes path-dependent the cache key must include the path, and the
  pydantic-ai in-process adapter (long-lived process, potentially several
  collab roots) is the case that will find the bug.
- **§5.6 Settle the filesystem convention.** `.baron/` currently holds
  machine-written state (`guard-override.log`); human-authored config sits at
  the repo root (`.baron-waivers.yaml`). A human-authored `.baron/rules.yaml`
  straddles both conventions. Pick one and say why, in that ADR.

## 6. What was explicitly NOT decided

### 6.1 Project-defined verbs — a CRITICAL DECISION, not taken

Letting a project add a verb breaks the frozen-vocabulary invariant asserted in
two places (`cli/tests/test_schemas.py` re-derives the verb set from
`skills/barony/references/capability-vocab.v1.md` and asserts `len == 10`;
`cli/tests/test_rules.py` asserts `set(loaded.verbs) == set(CAPABILITY_VERBS)`).
It is also *separable*: custom rules for existing verbs need no vocabulary
change at all, and that is the 90% case ("also block `gh release delete`" is
`merge_pr`-shaped, not a new intent). This ADR does the separable half. If
project-defined verbs are ever wanted, they get their own ADR arguing the
vocabulary change on its merits — not smuggled in as a side effect of a loader.

### 6.2 New detection modalities

File size, time windows, rate limits, semantic constraints. Each is a new
matcher plus new code in `guard.py`. Gated on observed need. The closed matcher
set (§3.2) is what keeps this decision explicit instead of accidental.

## 7. Consequences

**Good.**
- An additional rule is now *representable*. The loader is a small follow-up
  rather than a refactor-plus-loader.
- `baron rules list` / `validate` make the enforcement surface auditable from
  the command line instead of by reading YAML. `explain` makes a single guard
  decision inspectable without constructing a hook payload by hand.
- `diff` gives a project a way to see how a candidate rules document departs
  from the shipped one — the review surface the loader will need. It joins on
  **rule id and verb id**; the verb-entry join (`verbs_changed`) was added in
  round 3 and the limits are recorded under *Costs* below.
- New parse-time refusals, all fail-closed and consistent with ADR-004 §2.3.
  Reachable **from document input**, which is the only kind that counts:
  unknown `vocabulary`; a rule the parser does not implement; a key the parser
  does not recognise (top level, `verbs.<verb>`, `commands.*`, `file_ops`); an
  unknown matcher; a matcher other than the one guard implements for that rule;
  a missing built-in rule; a rule missing a required parameter; **an unknown
  `class` or `detection` value; a missing `class` or `detection`; and a
  `detection` that misdescribes what guard implements, in either direction**.
  `test_unrecognised_document_content_is_refused_not_ignored` covers each.

  *Round-3 correction.* The list above previously stopped at "a rule missing a
  required parameter", and so did the parser. Every refusal was over a **key**
  or a **rule slot**; no **value** was validated. Measured consequences, all at
  exit 0 on the shipped `validate`: `detection: banana` passed; `class: banana`
  passed and silently re-routed `enforcement()`; and `read_code` with
  `detection: command` and no rule behind it passed *and made
  `baron rules list` print `LABEL=enforced` for a verb nothing checks*. The
  last one is the exact failure this ADR's §4.1 claims to prevent — an
  enforcement claim with no enforcement — reachable from a one-word document
  edit. `class`/`detection` are now closed sets, both are required rather than
  defaulted (defaulting an enforcement decision is a guess), and
  `_check_detection_consistency` is parser-enforced.

  That consistency check previously existed **only as an assertion in
  `test_rules.py` against the packaged artifact**, which is the wrong place for
  it: `--file` accepts documents, and no document ever reached it. It is
  symmetric on purpose — over-claiming (`detection: command`, no rule)
  manufactures a false assurance, and under-declaring (a rule binds the verb,
  entry says `none`) leaves the artifact misdescribing the code it documents.
  Both are refused.

  *Round-2 correction.* This section previously claimed "two new parse-time
  refusals … unknown `vocabulary`, and duplicate rule id". That was one, not
  two. The duplicate-rule-id check is a `__post_init__` invariant on
  `CapabilityRules` reachable only via `dataclasses.replace()` — ids were
  hardcoded, so no document could produce a duplicate. It is still a real
  invariant (and still tested, by `test_duplicate_rule_ids_are_refused`), but it
  guards the deferred loader and developer edits, not user input. Only the
  unknown-`vocabulary` refusal was document-reachable as shipped.

**Costs and limits.**
- `rules.py` grew from 160 to ~720 lines for zero behaviour change. Roughly
  half of that is the strict document grammar (§3.2) rather than the rule-list
  shape itself. That is the price of a shape that can grow and a parser that
  refuses what it cannot honour; it is paid once.
- Each legacy accessor is now a dict lookup rather than an attribute read.
  Guard calls a handful per token over an eight-entry index; not measurable
  against the subprocess spawn the hook already costs.
- `explain`'s rule attribution is by verb, not by matched instance (§4.2).
- `diff`'s `rules_added` / `rules_removed` **cannot fire from a document**. The
  built-in rule set is closed and every slot is mandatory, so a candidate with
  an extra rule is refused and one with a rule missing is refused too. They
  exist for the deferred loader (§5) and are exercised by unit tests over
  constructed `CapabilityRules` values (`test_diff_rules_detects_an_added_rule`),
  not by a document fixture. The diff computation was extracted to
  `rules.diff_rules()` — a pure function — precisely so those branches are
  testable without a document that cannot exist. This gap is what let the
  round-1 hole survive: every CLI diff fixture was a *string substitution* on
  the packaged artifact, so no test ever added a rule.
- `diff` was blind to **verb entries** until round 3. It joined on rule id
  alone, so a candidate that rewrote `detection`, `class` or `notes` on an
  existing verb diffed as `identical to the packaged artifact` at exit 0 —
  reproduced three ways. Those are the fields that decide whether baron prints
  `enforced`, so the one document edit most worth reviewing was the one the
  review surface could not see. `verbs_changed` now joins on verb id and the
  renderer spells out the resulting `enforcement/label` transition. Unlike
  `rules_added` / `rules_removed` this branch **is** document-reachable, so it
  is covered by document fixtures (`test_rules_diff_reports_a_changed_verb_entry`),
  not constructed values.
- The first `verbs_changed` renderer truncated long values to a fixed prefix,
  which made two different `notes` blocks render as an identical-looking pair.
  Values are now printed in full in a two-line block form.
  `test_rules_diff_does_not_elide_the_difference_it_is_reporting` pins it. A
  diff that hides the diff is worse than no diff.
- **Not every check in `validate` is computed.** `rules_version`, `vocabulary`,
  `matchers known` and `no unrecognised content` are reported as `ok` because
  the parser already refused the alternative at exit 2 — they show *what was
  negotiated*, they do not re-test it. Round 2 got this wrong in a way worth
  recording: `no unrecognised content` was hardcoded `True` while its text
  claimed "every key and rule in the document is one this baron implements",
  and it printed `ok` over a document containing `detection: banana`. The text
  now names exactly what is covered (keys, rule slots, and the enumerated
  values), and the one genuinely derivable claim —
  `detection matches implementation` — is computed from the parsed table
  instead of asserted. A hardcoded check whose prose overstates its coverage is
  precisely the failure mode ADR-002 and ADR-008 exist to prevent, and it got
  past a round of review inside the ADR that forbids it.
- `rules list` shows no rule ids for `write_code` / `write_path`: those are
  decided by the whole file-op precedence chain in `guard.py`, not by one named
  rule. The `notes` field carries the explanation; the table does not.
- Still nothing loads a project rules file. A team that wants a custom rule
  today still cannot have one. This ADR unblocks that; it does not deliver it.

## 8. Decision record

- [x] **Approved as written** — Vikram, 2026-08-09, on the D-1 answer below.
- [ ] Approved with changes
- [ ] Needs revision
- [ ] Rejected

**Sign-off complete (Vikram, 2026-08-09). The one blocking item, D-1, is
answered.** The header and frontmatter carry the same status; this box was left
unticked through three rounds and is ticked here so the two surfaces agree.

Most of this ADR shipped ahead of sign-off on the usual grounds: §3 is
behaviour-preserving (`guard.py` and `runtimes/pydantic_ai.py` byte-identical,
all pre-existing tests green) and §4 is a purely additive read-only surface.
Neither is a one-way door; the one-way doors are all in §5 and §6 and none is
taken here. **Those doors are still shut and still need their own ADR** — §8 is
signed, §5/§6 are not decided by it.

**One item was not in that category and needed an explicit answer before merge.
It got one.**

> **D-1 — narrowing `enforced` to guard-checked verbs only (§4.1).** Round 2
> changed what `baron rules list` prints for `read_code` and `read_collab` from
> `enforced` to `instructed`. It is a **user-visible output change**: anyone who
> read the old table was told those verbs were enforced, and anyone parsing
> `--json` for `label` sees a different value for two of ten verbs. The old
> output was wrong — `test_denying_read_code_does_not_omit_read_tools` measures
> the read tools surviving a `read_code` denial — so this is a correction, not a
> regression. But "we now report less enforcement than we used to" is a claim
> about the product that the owner should make knowingly, not one an implementer
> should slip in under a refactor.
>
> Round 3 also narrowed the *reason*: not "no adapter enforces it" but "the one
> adapter measured does not; the other kits are unmeasured". ~~Approving D-1
> approves that scoping too.~~ **That scoping is obsolete — see the basis below.**
>
> - [x] **D-1 approved** — publish the narrowed label
> - [ ] **D-1 rejected** — revert to the previous wording and re-open §4.1
>
> **Approved by Vikram, 2026-08-09. Basis: FOUR MEASURED ADAPTERS.** The
> approval is *not* of the round-3 scoping, which has been retired. Option (c)
> below — "instrument the kits and let the measurement decide per-adapter" —
> was taken, not declined, and it was cheaper than this ADR costed it: proving
> the **absence** of a baron-emitted enforcement mechanism is static (inspect
> what `baron init` generates), while only proving **presence** would have
> needed a live runtime. `pydantic-ai` keeps its live gate; `claude`,
> `code-puppy` and `generic` each gained a static emission measurement. All four
> are negative, so `instructed` stands — now on evidence the same size as the
> claim. Recorded in **ADR-020**; §4.1 above is updated, not merely annotated.
>
> The honest bound travels with the label: the measured claim is *baron emits no
> mechanism capable of omitting the read tools*, **not** *the runtime cannot
> enforce them*. A hand-written `permissions.deny`, or the Tier-3 subagent the
> `claude` and `code-puppy` HYDRATE.md recipes describe, does enforce them and
> is outside what `baron rules list` speaks for (ADR-020 §4.2, §7).
>
> Options if rejected: (a) keep `enforced` and delete the measuring test — not
> tenable under ADR-002; (b) introduce a fourth printed state instead of
> collapsing to `instructed`; (c) instrument the `claude` and `code-puppy` kits
> and let the measurement decide per-adapter. (c) is the only one that could
> honestly restore `enforced` — it was done, and the measurement said no.

*This box was unticked through three rounds of review, deliberately: an
implementer cannot sign off an owner decision about what the product claims. It
is now ticked on the owner's D3 decision, with the basis recorded above rather
than inherited from the round-3 wording.*
