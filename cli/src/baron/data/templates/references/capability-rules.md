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

## Change discipline

- The **vocabulary** stays frozen (`capability-vocab.v1.md` governs verbs and classes).
- Rule changes (new patterns, changed flag lists) bump `rules_version` and get a note in the
  artifact header; `cli/tests/test_rules.py` asserts the verb set still matches the frozen
  vocabulary exactly and that guard actually consumes the packaged data.
