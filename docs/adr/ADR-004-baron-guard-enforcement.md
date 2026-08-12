---
created: 2026-07-23
accepted: 2026-07-23
type: decision
status: accepted
decided_by: Vikram
adr: 004
project: barony
related:
  - "[[docs/adr/ADR-002-ways-of-working-2026-07]]"
  - "[[docs/adr/ADR-003-baron-cli]]"
---

# ADR-004: `baron guard` — sub-tool capability denials become enforceable (hook-based)

| Field | Value |
|---|---|
| **Status** | Accepted (2026-07-23) |
| **Date** | 2026-07-23 |
| **Authors** | Vikram + Claude |
| **Supersedes** | — (extends ADR-002/ADR-003; changes one claim ADR-001's adapters made) |
| **Evidence base** | GardenTwin audit operational fidelity 0.53; the enforceability-class split in `capability-vocab.v1.md` |
| **Decision owner** | Vikram |

## 1. Why this is its own ADR

M4's mechanics would fit an ADR-003 addendum, but M4 changes a **contract** the framework
has stated since v1.0: the enforceability classes in `capability-vocab.v1.md` say sub-tool
denials (`push_main`, `merge_pr`, `force_push`, path-scoped writes,
`edit_other_personas`) are *instruction-only* wherever the parent tool is granted, and
every adapter's honesty boundary ("do not oversell") is built on that. `baron guard` moves
five of those denials to a third enforcement tier that the two-value
enforced/instructed split cannot express. A change to the framework's central honesty
claim deserves its own decision record, not a paragraph in a CLI milestone ADR.

## 2. Decision

Ship `baron guard` (baron M4): a **Claude Code PreToolUse hook** that deterministically
evaluates each `Bash` / `Edit` / `Write` / `NotebookEdit` call against the acting
persona's `persona.yaml` BEFORE the tool runs.

### §2.1 — Implemented against the documented hooks contract

Contract source: https://code.claude.com/docs/en/hooks (the canonical target that
https://docs.anthropic.com/en/docs/claude-code/hooks redirects to; fetched 2026-07-23).
Facts baron implements against: the hook receives one JSON object on stdin
(`tool_name`, `tool_input` — `command` for Bash, `file_path`/`notebook_path` for the
write tools — plus `cwd`); **exit 2 blocks the call and feeds stderr to the model**;
exit 0 with no stdout defers to the normal permission flow; other exit codes are
non-blocking errors. A JSON `hookSpecificOutput.permissionDecision` (allow/deny/ask)
form also exists; baron uses the exit-code form because it also covers the fail-closed
error paths, and baron never needs `"allow"` — emitting it would bypass the user's own
permission prompts. The guard only ever objects (exit 2) or stays silent (exit 0).

### §2.2 — Scope: five verbs, conservative parsing, not a sandbox

Guard maps tool calls to the frozen v1 verbs it can decide deterministically:
`push_main` (push refspecs targeting the default branch; `git merge` while on it),
`force_push` (`--force`/`-f`/`--force-with-lease`/`+refspec`), `merge_pr`
(`gh pr merge`), `write_path` scoping and `edit_other_personas` (write-tool paths).
On ambiguity (e.g. bare `git push` whose target branch cannot be resolved) it assumes
the enforcement-relevant verb and denies personas that lack it, with stderr naming the
inference; personas holding the verb always pass. Non-git/gh shell and unknown tools
always pass — guard is a capability gate, not an allowlist (that remains the Tier-3
subagent's job) and not an adversarial sandbox (creative shell can evade static
parsing; the target failure class is the honest mistake, which is also what the field
evidence shows — every ADR-002 incident was a persona forgetting its lane, not gaming it).
`open_pr`/`run_tests` denials stay instruction-only: guard does not parse for them.

### §2.3 — Fail-closed, with a logged escape hatch

Internal errors (unreadable persona file, malformed stdin) DENY with actionable stderr —
a broken guard must not silently become no guard. The escape hatch
`BARON_GUARD_OVERRIDE=<reason>` allows the call BUT appends
timestamp/tool/target/reason to `.baron/guard-override.log` — a **tracked** file,
deliberately not gitignored: overrides must be visible in diffs, and each is expected to
be turned into a `_handoff/`. Fail-closed but not brick.

### §2.4 — The new enforcement tier is named, exactly

The Claude adapter's capability map now claims, for the five guard-covered sub-tool rows,
the exact string **`enforced-with-baron (instructed otherwise)`** — and
`tests/bi_runtime_accept.py` accepts only that form, only on sub-tool rows, only for the
claude adapter. The qualifier is the honesty boundary carried into the claim itself:
without baron installed the hook command fails as a non-blocking error and the denial
degrades to instructed (worse-is-visible, never worse-is-broken). code-puppy and generic
adapters are unchanged.

## 3. Consequences

- Positive: the enforcement-theater finding (operational fidelity 0.53) gets a mechanism
  at the exact layer it failed — rules that no longer depend on the session re-reading
  prose. Deny surfaces the reason to the model, which can then route the work correctly.
- Negative / costs: Claude-Code-only (hooks are a runtime feature; other runtimes keep
  instructed sub-tool denials until they grow an equivalent seam); shell parsing is
  conservative and will occasionally deny a legitimate exotic command (the override path
  is the pressure valve, and it leaves a record); the guard adds a subprocess to every
  matched tool call.
- The capability vocabulary is untouched — the verbs and their *classes* are unchanged;
  what changed is what the Claude adapter can honestly claim about denial enforcement.

## 4. Addendum (2026-07-23, v1.6.0): the rules artifact + the pydantic-ai adapter

### §4.1 — The rule table is externalized as versioned package data

Guard's policy — the §2.2 command patterns, the write-tool scoping semantics, the
conservative-deny ambiguity rule — moves out of `guard.py` into a machine-readable
artifact, **`cli/src/baron/data/capability-rules.v1.yaml`** (`rules_version: 1`), loaded
via `importlib.resources` (`baron.rules.load_rules()`). `guard.py` keeps the *mechanics*
(shell splitting, refspec resolution, branch lookups, the hook I/O contract); every
pattern constant comes from the artifact. Behavior is identical — the guard test suite
passed unchanged across the refactor — and a missing/unparseable/unsupported-version
artifact fails CLOSED, consistent with §2.3.

**Placement rationale (why baron package data, not the collab-repo template or the skill
references):** the rules are only meaningful to something that *enforces* them; every
current enforcer (this hook, the pydantic-ai hydrator below) already ships in baron, so
packaging the rules as baron data versions the policy in lock-step with the code that
interprets it. A copy emitted into each collab repo would be one more artifact to drift
(the F4 lesson), and runtimes without baron get nothing from a rules file they have no
interpreter for — they keep instruction-only sub-tool denials exactly as before. The
prose contract for consumers lives in the skill
(`references/capability-rules.md`); the vocabulary itself stays frozen and separate.

### §4.2 — pydantic-ai: the first adapter with natively-`enforced` sub-tool denials

The new pydantic-ai runtime adapter (`adapters/pydantic-ai/HYDRATE.md`; hydrator
`baron.runtimes.pydantic_ai.build_agent`, extra `barony[pydantic-ai]` pinned to the
verified `pydantic-ai-harness>=0.10,<0.11` + `pydantic-ai-slim>=2.14.1,<3`) enforces the
same five sub-tool denials through the runtime's documented in-process interception seam:
a capability's `before_tool_execute` hook, where raising `ModelRetry` skips execution and
feeds the reason to the model. The guard capability evaluates every shell command and
file write through `baron.guard`'s evaluators — the SAME rules artifact — so decisions
are identical across runtimes by construction. Implemented against the stable documented
capability/hook interface only; deliberately NOT against any third-party guard add-on
package.

Consequence for §2.4's tier naming: this adapter's sub-tool rows claim plain
**`enforced`**, unqualified — the qualifier exists on Claude because the external hook
degrades to instructed when baron is missing on the machine; in-process interception
cannot be absent from an agent built via `build_agent` (an agent built WITHOUT the
hydrator is simply not this adapter's product — Tier-1 rules apply).
`tests/bi_runtime_accept.py` encodes both allowances per-adapter and TIGHTENS the old
rule: guard-enforcement claims (either form) are accepted only on the five
rules-covered verbs — never on `open_pr`/`run_tests` rows. The whole-tool story is
unchanged: capability omission (no shell verbs → no Shell capability; no write verbs →
a natively read-only FileSystem via `protected_patterns`).

**Fit-analysis divergences found against the real APIs (recorded per the honesty rule):**
the harness `FileSystem` has no `readonly` flag — native read-only is expressed as
`protected_patterns=['*', '**/*']` (protected paths reject writes, verified); the harness
`Shell` documents no per-command callback — interception lives at the pydantic-ai
capability layer (`before_tool_execute`), not inside Shell; and `TestModel` cannot script
specific tool arguments, so the blocked-push acceptance test drives a real run through
`FunctionModel` (equally offline) and unit-tests the interceptor directly.

## 5. Extended by ADR-012 (2026-08-09): hook coverage beyond PreToolUse

[ADR-012](ADR-012-hook-coverage-and-evidence-capture.md) widens `baron guard` from *the
PreToolUse hook* to *the hook*, dispatching internally on `hook_event_name`. Nothing in
§2 changes:

- **§2.1 is unchanged.** The exit-code form still applies, guard still never emits `allow`,
  and the enforcement path still reads `tool_name`/`tool_input`/`cwd`. ADR-012 only adds a
  branch *before* it, on a field ADR-004 did not read.
- **§2.2 is unchanged.** Still five verbs, still `PreToolUse`-only. The new handlers enforce
  nothing; `enforced-with-baron (instructed otherwise)` still describes exactly those five.
- **§2.3 is unchanged and now pinned.** Fail-closed on the enforcement path stands. Empty
  and malformed stdin both denying was previously an observed consequence of sharing one
  `JSONDecodeError` path; ADR-012 gives it a test, because §2.3 states it as policy.

The one thing ADR-012 adds that §2.3 does not cover: the **new** evidence paths fail
**open**, deliberately, because a fail-closed telemetry hook on `SessionStart` bricks a
session from a place nothing inside the session can reach. That asymmetry is ADR-012 §3.
