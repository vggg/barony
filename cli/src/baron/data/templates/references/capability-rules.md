# Capability Enforcement Rules — the machine-readable artifact

> **The single source for verb→enforcement rules is the versioned artifact**
> **`cli/src/baron/data/capability-rules.v1.yaml`** (shipped as `baron` package data,
> loaded via `importlib.resources` — `baron.rules.load_rules()`). Adapters and other
> consumers MUST consume it; they MUST NOT restate the patterns. This page is the prose
> contract *about* the artifact, not a second copy of its content.

## What the artifact contains

For each of the frozen 10 verbs (`capability-vocab.v1.md` — the vocabulary itself is
unchanged by this artifact):

- **Command detection rules** — how shell commands map to verbs: `git push` targeting the
  default branch (and `git merge` while on it) → `push_main`; force flags / `+refspec` →
  `force_push`; `gh pr merge` → `merge_pr`. Including the exact flag lists, the value-taking
  options that must be skipped during parsing, and the fallback default-branch names.
- **File-operation scoping semantics** — the write-path precedence order: universal write
  zones (`_handoff/`) → own-vs-other persona spec dirs (`edit_other_personas`) → denied
  `write_path` scopes (always block) → `write_code` (general writes) → allowed `write_path`
  scopes (conservative default: deny).
- **Ambiguity policy** — `conservative-deny`: an unresolvable target is treated as the
  enforcement-relevant verb and denied for personas lacking it, with the inference named in
  the denial reason (ADR-004 §2.2).
- **Per-rule notes** — the honest scope of each rule, including which verbs are deliberately
  NOT parsed (`open_pr`, `run_tests` — instruction-only by design).

`rules_version: 1` is the schema version; a consumer must refuse a version it does not
understand rather than silently mis-enforce.

## Known consumers

| Consumer | How it uses the rules |
|---|---|
| `baron guard` (Claude Code PreToolUse hook, ADR-004) | Loads the artifact for all command patterns and file-op scoping; supplies only the parsing mechanics + hook I/O. |
| pydantic-ai runtime adapter (`baron.runtimes.pydantic_ai`) | In-process tool interception consumes the same evaluation (via `baron.guard`), so shell + write vetoes follow the identical rule table. |
| Future runtime adapters | Same rule: load the artifact (directly, or through `baron.guard`'s evaluators); never re-hardcode a pattern. |

## Why it lives in the baron package (placement rationale)

Recorded in the ADR-004 addendum (§4.1): the rules are only meaningful to something that
*enforces* them, every current enforcer already depends on baron, and packaging them as
baron data versions the policy in lock-step with the mechanics that interpret it — a copy
in the collab-repo template would be one more artifact that can drift. Runtimes without
baron keep instruction-only sub-tool denials, exactly as before.

## Inspecting the rules — `baron rules` (ADR-016)

The artifact is auditable from the command line; you should not have to read the YAML to
know what is enforced.

| Command | What it answers |
|---|---|
| `baron rules list [--json]` | The verb table: class, detection modality, **enforcement**, label, and the rule ids that can imply each verb. |
| `baron rules validate [--file F] [--json]` | Does this artifact parse, negotiate, and hold together? Exit 0 clean / 1 a check failed / **2 refused outright**. |
| `baron rules diff --file F [--json]` | How does a candidate document depart from the packaged one? Joined on **rule id and verb id** (`rules_changed`, `verbs_changed`). Exit 0 identical / 1 differs / 2 refused. |
| `baron rules explain <cmd\|path> --persona-file P [--write] [--json]` | What would guard decide for this one call, and why? Exit 0 would-pass / 1 would-be-DENIED / 2 could not evaluate. |

`explain` calls `guard.evaluate_bash` / `guard.evaluate_write` — it is a dry run of the
real decision, not a second implementation, and a test pins its verdict to the evaluator's
`Decision`. It reports the rules that *can* imply each verb, not the single rule instance
that matched; guard's own `reason` names the concrete inference.

**Enforcement is reported in three states — but only one of them is `enforced`**
(the ADR-002/ADR-008 honesty rule):

| State | Meaning | `label` |
|---|---|---|
| `guard` | guard mechanically checks it (`detection` is `command` or `file-op`) | `enforced` |
| `adapter-dependent` | guard does NOT parse for it; the class is whole-tool, so a runtime with a tool allow-list *could* enforce it by omitting the tool — but **baron emits no such mechanism**, measured once per shipped adapter | `instructed` |
| `instructed` | nothing checks it (`open_pr`, `run_tests`, by design) | `instructed` |

`read_code` and `read_collab` are the `adapter-dependent` pair. The pydantic-ai adapter
constructs `FileSystem` unconditionally, so a persona that *denies* `read_code` still gets
`read_file` / `list_directory` / `search_files`. Calling that "enforced by tool omission"
would be a claim about what a runtime could in principle do, printed as a fact about what
baron does — so it labels `instructed`, and a test that hydrates such a persona and
inspects the toolset is what gates the label.

*Scope of that claim (ADR-018):* all **four** shipped adapters are measured, one measurement
each. pydantic-ai is measured live (above). `claude`, `code-puppy` and `generic` are measured
by **static emission**: the kit `baron init` generates is inspected for any construct a
runtime reads as a tool allow/deny list, and there is none — `claude` emits only hook wiring
in `.claude/settings.json` (no `permissions`, no `allowedTools`/`disallowedTools`, no
`.claude/agents/` subagent), and the other two emit no machine-readable artifact at all.

*The bound, which is exact:* the measured claim is **baron emits no mechanism** capable of
omitting the read tools — **not** that a runtime cannot enforce them. A hand-written
`permissions.deny`, or the Tier-3 subagent with a minimal `tools:` allow-list that
`adapters/claude/HYDRATE.md` and `adapters/code-puppy/HYDRATE.md` describe, *does* enforce
them. Those HYDRATE tables print `enforced` for the read verbs and are right about the
artifact a human hand-authors from the recipe; `baron rules list` speaks for what baron
ships. An instruction someone may or may not follow is what `instructed` means.

`--json` carries the qualifier in the payload (`label_caveat` at the top level, `caveat` on
each affected verb), not only in the table footer.

**Refuse, don't ignore — values as well as keys.** The parser enumerates what a document
actually carries and refuses anything it does not implement:

- an unrecognised **key** (top level, `verbs.<verb>`, `commands.*`, `file_ops`);
- a **rule** this baron does not implement, a missing built-in rule, or a rule missing a
  required parameter;
- an unknown **`matcher`**, or one other than the matcher guard implements for that rule.
  Each command rule states its `matcher` in the document; the field is optional but
  authoritative — absent it defaults to guard's, present it is validated, never trusted;
- an unknown or missing **`class`** (`whole-tool | sub-tool`) or **`detection`**
  (`none | command | file-op`). Both are required: they route enforcement, and defaulting
  an enforcement decision is a guess;
- a **`detection` that misdescribes what guard implements**, in either direction —
  `command` with no rule binding the verb (which would print `enforced` for a verb nothing
  checks), or `none` where a rule does bind it (an artifact under-reporting its own code).

Silently dropping an unrecognised rule is the worst failure mode an enforcement artifact
has: the document says a thing is blocked and nothing blocks it. Accepting a bad *value* is
the second worst, and is how a document can claim enforcement that does not exist.

## Project-level custom rules — NOT loaded (yet)

`baron rules validate --file` and `diff --file` will parse a candidate rules document, but
**validating a file does not activate it**. Every enforcer loads the PACKAGED artifact
only: there is no `.baron/rules.yaml` discovery, no merge, no precedence.

ADR-016 §3 landed the enabling change — the parsed rules are now a *list* of typed rules
(`CommandRule` / `PathRule`, each with a stable `id`, a `matcher` from a **closed** set, a
`verb`, and a `source`), so an additional rule is representable at all; the previous flat
field-per-rule record structurally could not hold one. ADR-016 §5 records why the loader
itself is deferred and the one-way doors it must settle first: add-only/deny-only (project
rules may never grant), never new verbs, explicit supported version ranges on *both*
artifacts, refuse-don't-ignore on a malformed project file (matching guard's fail-closed
policy, deliberately unlike `.baron-waivers.yaml`'s soft-fail), `load_rules()` cache safety
once it becomes path-dependent, and the `.baron/` (machine state) vs root-level
`.baron-waivers.yaml` (human config) convention collision.

## Change discipline

- The **vocabulary** stays frozen (`capability-vocab.v1.md` governs verbs and classes).
  Project-defined verbs are a separate, unmade decision (ADR-016 §6.1) — custom rules for
  *existing* verbs need no vocabulary change and are the 90% case.
- The **matcher set is closed**: `flag_present`, `refspec_prefix`,
  `refspec_default_branch`, `current_branch_is_default`, `subcommand_present`,
  `universal_write`, `spec_dir`. A rule naming anything else is refused at parse time,
  because it is a rule no consumer can honestly enforce. Adding a matcher (file size, time
  windows, rate limits, anything semantic) is new detection code in `guard.py`, gated on
  observed need.
- Rule changes (new patterns, changed flag lists) bump `rules_version` and get a note in the
  artifact header; `cli/tests/test_rules.py` asserts the verb set still matches the frozen
  vocabulary exactly and that guard actually consumes the packaged data.
- `rules_version` and `vocabulary` are negotiated by **exact match**. A consumer refuses
  what it does not understand rather than mis-enforcing it; guard turns that refusal into a
  fail-closed DENY.
