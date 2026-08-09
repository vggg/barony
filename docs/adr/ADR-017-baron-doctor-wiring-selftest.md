---
created: 2026-08-09
accepted: 2026-08-09
type: decision
status: accepted
adr: 017
project: barony
related:
  - "[[docs/adr/ADR-004-baron-guard-enforcement]]"
  - "[[docs/adr/ADR-006-baron-init-template-packaging]]"
  - "[[docs/adr/ADR-008-ways-of-working-2026-07-31]]"
---

# ADR-017: `baron doctor` — enforcement wiring is verified, and its absence is loud

| Field | Value |
|---|---|
| **Status** | Accepted (2026-08-09) |
| **Date** | 2026-08-09 |
| **Authors** | Vikram + Claude |
| **Supersedes** | — (extends ADR-004; closes the highest-value open item in the guard-hardening roadmap) |
| **Evidence base** | badminton-analyzer 2026-07-22 (15 PRs merged under a persona denied `merge_pr`, because the hook was never installed); the 2026-08-01 source-level validation; the 2026-08-08 hands-on run |
| **Decision owner** | Vikram |

## 1. The failure this closes

ADR-004 shipped deterministic enforcement. The badminton-analyzer incident is
the proof that shipping a mechanism is not the same as having it. Fifteen PRs
were merged by a persona whose `merge_pr` denial was believed enforced. Nothing
had failed. `baron guard` had simply never been wired into
`.claude/settings.json`, so the denial degraded — exactly as designed, exactly
as documented, and **completely silently** — back to persona text.

That is the residual of FM4, and the 2026-08-01 source-level validation named it
precisely: the guard is a real deterministic guard for recognised direct ops, and
"the residual risk is that **silence**." An absent guard and a guard that never
had to fire produce identical evidence: nothing.

`roadmap.md` § *`baron guard` hardening* carries it as the first checkbox and
labels it "Highest-value item":

> `[ ]` **Guard self-test that fails LOUDLY when the hook/executable is missing** —
> closes the silent-degradation gap (the real FM4 residual).

## 2. Decision

Ship `baron doctor` (`cli/src/baron/doctor.py`): a **read-only** self-test of the
guard's wiring in a given project directory that exits **nonzero on any FAIL**.
Nine checks, each with a status and — when it failed — a remedy line:

| # | id | What it proves | On failure |
|---|---|---|---|
| 1 | `cli-on-path` | the executable the hook names resolves and `--version` runs | FAIL |
| 2 | `hook-configured` | project `.claude/settings.json` wires a PreToolUse hook invoking `baron guard` | FAIL |
| 3 | `hook-matcher` | that hook's matcher selects **every** governed tool (`Bash`, `Edit`, `Write`, `NotebookEdit`) | FAIL |
| 4 | `persona-file` | the persona the hook names exists and `load_persona()` parses it | FAIL |
| 5 | `rules-artifact` | `rules.load_rules()` succeeds at a supported `rules_version` | FAIL |
| 6 | `enforcement-path` | a synthetic denial through `guard.process()` really returns exit 2 **in this install** | FAIL |
| 7 | `fail-closed` | malformed hook stdin also returns exit 2 (ADR-004 §2.3) | FAIL |
| 8 | `override-env` | `BARON_GUARD_OVERRIDE` is not sitting exported in this environment | FAIL |
| 9 | `override-log` | the evidence sink is writable and not gitignored | **INFO only** |

`--json` emits the same report machine-readably (for CI, and for the audit
skill's report generation).

## 3. The load-bearing choices

### §3.1 — Doctor verifies WIRING, not invocation. It says so, every run.

This is the decision that makes the rest safe to ship. Doctor can prove that
this installation **can** enforce. It cannot observe whether Claude Code
actually executed the hook on any real tool call — nothing outside the runtime
can see that. A command that implied otherwise would manufacture exactly the
false confidence that produced the badminton merges, which is a worse outcome
than not shipping it.

So the caveat is not a footnote in the docs. It is printed on **every** run
(green included), it is a field in the `--json` payload
(`"verifies": "wiring"`, `"caveat": …`), and a test greps for it. Read a green
doctor as "correctly wired", never as "enforcement happened".

### §3.2 — Check 6 uses a SYNTHETIC persona, not the project's

The temptation is to feed a denial the project's real persona would refuse. That
would test the project's capability grants, not the mechanism: a project whose
personas grant everything would produce a vacuous PASS, and a merger persona
holding `merge_pr` would produce a false FAIL.

Check 6 therefore writes a throwaway persona with no write capability into a
temp dir and asserts a `Write` outside every scope exits 2. That is a property
of the **installed guard**, independent of the project. It runs entirely offline
and touches no git state.

A subtlety worth naming: `guard.process()` is itself fail-closed via a bare
`except Exception`, so a totally broken guard would still exit 2. Check 6
therefore also rejects a 2 that arrived through the internal-error path — "a
guard that denies everything by crashing is not enforcement, it is an outage
that happens to look safe."

### §3.3 — Probes neutralise `BARON_GUARD_OVERRIDE`; its being set is its own FAIL

An exported `BARON_GUARD_OVERRIDE` allows every denial (logging each). Left in
place during checks 6 and 7, it would make both measure the escape hatch instead
of the mechanism. The probes pop it for the duration and restore it after.

Its presence is not swallowed, though — check 8 FAILs on it. The hatch is
designed for one deliberate command; exported for a session it is
indistinguishable from having no guard, and that deserves the same volume as a
missing hook.

### §3.4 — Evidence checks are INFO, never FAIL (the asymmetry with enforcement)

Enforcement is fail-CLOSED (ADR-004 §2.3). Evidence is fail-OPEN. A guard whose
enforcement works but whose audit trail cannot be written must still enforce, so
reporting a sink problem as an enforcement failure would invert the priority and
train people to ignore doctor's exit code.

Check 9 is therefore INFO whatever it finds — including the case where
`.baron/guard-override.log` has been gitignored, which does remove the
governance property ADR-004 §2.3 relies on. Doctor says so loudly in the detail
and still exits 0 on it alone.

*Forward note:* when an events/telemetry sink lands (the ops-plane events
workstream), it gets a check here on the same rule — INFO, never FAIL, same
rationale. Check 9 is the pattern, not a special case.

### §3.5 — Project-level settings only; user-level is out of scope and admitted

Claude Code merges `.claude/settings.json`, `.claude/settings.local.json`, and
the machine-global `~/.claude/settings.json`. Doctor inspects the two
project-level files only.

Checking the home directory would make doctor's verdict depend on the developer's
machine rather than on the repo under test — the verdict would not be
reproducible, and CI would disagree with the laptop. The cost is a false FAIL for
someone who wired the hook globally; the remedy line names that case explicitly
rather than leaving it to be discovered.

### §3.6 — Matcher coverage is read permissively (`re.search`)

Claude Code matchers are regexes. Doctor reports a tool uncovered only when no
matcher `re.search`-matches it, which is the permissive reading — so
`"Edit|Write"` counts as covering `NotebookEdit`. Being wrongly loud about a
correct matcher is its own honesty failure, and doctor's whole value is that
people believe it when it shouts. An invalid regex covers nothing rather than
crashing the run.

### §3.7 — Un-copied runtime kits get a named remedy

`baron init` generates the wiring at `agents/<slug>/runtime/.claude/settings.json`
and HYDRATE.md instructs copying it to where the runtime reads it. Skipping that
copy *is* the badminton shape. When doctor finds no hook but does find an
un-copied kit, the remedy names the kit path, names the incident, and gives the
`cp -R`.

## 4. What this does NOT do

- It does not observe hook invocation (§3.1). Nothing in this repo can.
- It does not check `~/.claude/settings.json` (§3.5).
- It does not verify Tier-3 subagent allow-lists — those are a different
  enforcement tier with a different failure mode.
- It does not run against a live forge, make network calls, or mutate anything.
  `baron doctor` is read-only and offline; the only writes are to a
  `tempfile.TemporaryDirectory` for check 6's probe persona.
- It does not replace `baron validate` (schema correctness) or `baron status`
  (divergence). Doctor answers one question: *is enforcement actually plugged
  in here?*

## 5. Consequences

- A project can be asked, mechanically and in CI, whether it is enforced. The
  honest answer stops depending on someone remembering.
- The 0.53-fidelity culture gains a measurement point: `baron doctor --json` is
  the input an audit report needs to distinguish `enforced-with-baron` from
  `instructed` per project, rather than assuming the former because a persona
  file says so.
- Cost: doctor spawns one subprocess (`<exe> --version`) and does one temp-dir
  write per run. Both are bounded and offline.
