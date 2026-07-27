# Capability Vocabulary v1 (FROZEN)

> The runtime-neutral capability API. Personas declare these abstract verbs in
> `persona.yaml`; each runtime's adapter maps them to concrete tools. **This is a versioned
> contract** - additions bump the minor version; removals/renames bump major.
>
> Status: **v1, FROZEN** (promoted from v0 draft after the Phase 2 dogfood validated the set).
> Provenance: every verb here was coined during Phase 1 adapter work and exercised in the
> Phase 2 dogfood. No speculative verbs (YAGNI - see docs/LEARNINGS.md proven #2).

## Design rules

1. **Intent-level, not tool-level.** `open_pr`, never `gh_pr_create`. The canon says WHAT;
   the adapter decides HOW.
2. **snake_case `verb_noun`.**
3. **A deny is the same verb under `deny:`** - no separate `no_*` verbs.
4. **Additions require observed need.** A verb enters v1.x only when a real persona on a real
   task needed it. (This is why the list is short.)

## Enforceability classes

From the code-puppy spike + dogfood (generalizes to any runtime):

- **whole-tool** - a runtime that allow-lists tools can genuinely ENFORCE this (omit the
  tool -> the action is impossible). Example: deny all writes by omitting write tools.
- **sub-tool** - lives inside a shared tool (shell for git/gh/tests; write tools for
  path-scoped writes). Denial is **instruction-only** when that tool is granted. Proven to
  still add real value (docs/LEARNINGS.md L3).

An adapter MUST enforce whole-tool capabilities via its allow-list where possible, and MUST
render sub-tool denials as explicit instructions in the persona body.

## The v1 verbs

| Verb | Intent | Class | Typical deny? |
|---|---|---|---|
| `read_code` | Read the code repo | whole-tool | - |
| `read_collab` | Read the collab repo | whole-tool | - |
| `write_code` | Create/modify code & tests | whole-tool | - |
| `write_path` | Write to a named path scope (see Q1 resolution) | sub-tool (path) | - |
| `open_pr` | Open a pull request | sub-tool | - |
| `run_tests` | Execute the test/coverage suite | sub-tool | - |
| `merge_pr` | Merge a pull request | sub-tool | usually denied (humans merge) |
| `push_main` | Push directly to the main branch | sub-tool | usually denied (PR only) |
| `force_push` | Force-push | sub-tool | almost always denied |
| `edit_other_personas` | Edit another persona's spec | sub-tool (path) | usually denied |

## Open-question resolutions (the point of Phase 3)

### Q1 - path-scoped writes: collapse to one parametric verb. RESOLVED.
The v0 draft had `write_findings`, `write_handoff`, `write_wiki` as separate verbs. Real use
(Phase 2) showed these are the SAME capability with different path scopes. v1 collapses them
into one parametric verb `write_path: [<scope>...]`:

```yaml
capabilities:
  allow:
    - write_code
    - write_path: [findings, _handoff]   # may write these collab scopes
  deny:
    - write_path: [wiki]                  # may NOT write wiki/
    - merge_pr
    - push_main
    - force_push
```

Rationale: fewer verbs, composable, and the path scope is data not vocabulary. The adapter
renders allowed scopes into the persona body and (where the runtime supports path-scoped
tools) into enforcement. Named convenience scopes: `findings`, `_handoff`, `wiki`, `decisions`.

### Q2 - repo as a separate axis vs per-repo verbs. RESOLVED: keep `code`/`collab` split.
Observed use only ever needed two repos (code, collab) and the read verbs naturally carried
the repo name (`read_code`, `read_collab`). Keeping them explicit is more self-documenting
than a `read(repo)` parametric form, and there are only two. Revisit only if a 3rd repo type
appears.

### Q3 - `run_tests` vs raw shell. RESOLVED: keep `run_tests` as an intent verb.
Never expose "run arbitrary shell" as a capability - that defeats the whole point of
intent-level verbs. `run_tests` says what the persona is allowed to DO; the adapter maps it
to the shell tool. (The persona still needs the shell tool for git/gh, but the *vocabulary*
stays intent-level.)

## Mapping note

The abstract->concrete mapping lives in each adapter's normalized capability map
(`adapters/<runtime>/HYDRATE.md`, `capability-map:v1` marker — one row per verb here;
checked by `tests/bi_runtime_accept.py`). For code-puppy see also
`docs/notes/code-puppy-capability-map.md`. The canon does NOT name runtime tools.

**Enforcement rules note:** the machine-readable verb→enforcement rule table (command
patterns such as "git push to the default branch → `push_main`", write-path scoping
semantics, the conservative-deny ambiguity policy) is a separate versioned artifact,
`cli/src/baron/data/capability-rules.v1.yaml` — see
[`capability-rules.md`](capability-rules.md). Enforcing consumers (baron guard, runtime
adapters) load that artifact; they never restate the patterns. This vocabulary stays
frozen — the artifact maps it, it does not extend it.

## Changelog

- **v1** (Phase 3): promoted from v0 draft. Collapsed path-scoped writes into `write_path`
  (Q1). Kept code/collab read split (Q2). Kept `run_tests` intent verb (Q3). 10 verbs total.