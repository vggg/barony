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
   identical name and type.
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

### 3.2 The matcher set is CLOSED

`flag_present`, `refspec_prefix`, `refspec_default_branch`,
`current_branch_is_default`, `subcommand_present`, `universal_write`,
`spec_dir`. A rule naming a matcher outside the set is **refused at parse
time**, because it is a rule no consumer can honestly enforce — accepting it
would print an `enforced` label over nothing. This is the closed half of the
BACKLOG's cheap/expensive split made mechanical: adding a matcher (file size,
time window, rate limit, anything semantic) is new detection code in
`guard.py`, gated on observed need per vocabulary design rule 4.

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

## 4. Decision — the `baron rules` surface

| Command | What it does | Exit codes |
|---|---|---|
| `rules list [--json] [--file]` | The verb table: class, detection modality, enforcement, label, and the rule ids that can imply each verb | 0, or 2 if the artifact is refused |
| `rules validate [--file] [--json]` | Parse + report the negotiation and integrity checks | 0 clean / 1 a check failed / 2 refused |
| `rules diff --file <candidate> [--json]` | Join a candidate document against the packaged artifact on rule id | 0 identical / 1 differs / 2 refused |
| `rules explain <target> --persona-file <p> [--write] [--cwd] [--json]` | What guard would decide for one call, and why | 0 would pass / 1 would be DENIED / 2 guard could not evaluate |

### 4.1 Three-state enforcement labelling, not two

The house rule is that enforcement is honestly labelled. Two states are not
enough to be honest here, so `rules list` reports three:

- **`guard`** — guard mechanically checks it (`detection` is `command` or `file-op`).
- **`tool-omission`** — guard does NOT parse for it, but the class is
  whole-tool, so a runtime with a tool allow-list enforces it by omitting the
  tool. That is the *adapter's* enforcement, not guard's, and it is only real
  on a runtime that has an allow-list. The table prints that caveat as a footer.
- **`instructed`** — nothing checks it. `open_pr` and `run_tests`, by design.

`label` collapses the first two to `enforced` for the callers that want a
binary, but `enforcement` is the field to trust.

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
- `diff` gives a project a way to see exactly how a candidate rules document
  departs from the shipped one — the review surface the loader will need.
- Two new parse-time refusals that did not exist: unknown `vocabulary`, and
  duplicate rule id. Both are fail-closed, consistent with ADR-004 §2.3.

**Costs and limits.**
- `rules.py` more than tripled in size (160 → 526 lines) for zero behaviour
  change. That is the price of a shape that can grow; it is paid once.
- Each legacy accessor is now a dict lookup rather than an attribute read.
  Guard calls a handful per token over an eight-entry index; not measurable
  against the subprocess spawn the hook already costs.
- `explain`'s rule attribution is by verb, not by matched instance (§4.2).
- `rules list` shows no rule ids for `write_code` / `write_path`: those are
  decided by the whole file-op precedence chain in `guard.py`, not by one named
  rule. The `notes` field carries the explanation; the table does not.
- Still nothing loads a project rules file. A team that wants a custom rule
  today still cannot have one. This ADR unblocks that; it does not deliver it.

## 8. Decision record

- [ ] Approved as written
- [ ] Approved with changes
- [ ] Needs revision
- [ ] Rejected

**Owner sign-off pending (Vikram).** The code ships ahead of sign-off because
§3 is behaviour-preserving (guard byte-identical, all pre-existing tests green)
and §4 is a purely additive read-only surface — neither is a one-way door. The
one-way doors are all in §5 and §6, and none of them is taken here.
