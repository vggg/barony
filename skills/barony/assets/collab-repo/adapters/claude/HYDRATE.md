# HYDRATE - Claude Code adapter (Tier 2 + Tier 3)

> **Runtime:** Claude Code (home runtime).
> **What this does:** renders a runtime-neutral `agents/<slug>/persona.yaml` into the
> highest-fidelity shape this Claude session supports:
> - **Tier 3** — a native Claude **subagent** at `.claude/agents/<slug>.md` with an
>   **enforced** tool allow-list (whole-tool denials become real). Analogous to the
>   code-puppy adapter's JSON sub-agent.
> - **Tier 2** — a persona `CLAUDE.md` (persistent session context); capabilities are
>   **instructed**, not enforced. This is the v0.3.x output shape — a project hydrated at
>   Tier 2 is IDENTICAL to what v0.3.x produced by hand.
>
> **Read first:** `canon/PARTICIPATE.md` (capability ladder) and
> `canon/capability-vocab.v1.md` (verb contract + enforceability classes).
>
> **Fallback:** if this adapter is absent, use `adapters/generic/HYDRATE.md` (Tier 1).

---

## Which tier? (resolution)

Tier comes from config, defaulting to `auto`. The config keys live in a **namespaced
adapter block** so the canonical schemas stay runtime-neutral — each adapter owns its own
keys under `adapters.<runtime>`:

| Source | Key | Values |
|---|---|---|
| Project default (`manifest.yaml`) | `adapters.claude.tier` | `auto` \| `2` \| `3` (default `auto`) |
| Per-persona override (`persona.yaml`) | `runtime.adapters.claude.tier` | `auto` \| `2` \| `3` |

**Precedence:** persona override > project default > `auto`.

**`auto` self-assessment** — you, the hydrating agent, decide in-context. Render **Tier 3**
only if ALL of these hold; otherwise render **Tier 2**:

1. You can create AND read back a file under `<code_repo>/.claude/agents/` (write access there).
2. This session actually exposes Claude's subagent mechanism — i.e. subagents are usable
   here, not a constrained sub-session / CI shell that can't host them.
3. There is no explicit `claude.tier: 2` override (project or persona).

> An explicit `tier: 2` or `tier: 3` always wins over `auto`. If `tier: 3` is set but this
> session can't host subagents (checks 1–2 fail), do NOT emit a dead subagent file: fall back
> to Tier 2 and report the downgrade with one line of reasoning. Graceful degradation is the
> rule (PARTICIPATE.md) — Tier 2 always works; Tier 3 is the upgrade where supported.

---

## Enforcement boundary

| Capability class | Tier 2 (`CLAUDE.md`) | Tier 3 (subagent) |
|---|---|---|
| **Whole-tool** (e.g. deny all writes / all shell) | instructed | **ENFORCED** via the `tools:` allow-list — omit the tool and the action is impossible |
| **Sub-tool** (e.g. allow `open_pr`, deny `merge_pr` — both via `Bash`) | instructed — **enforced when the `baron guard` hook is wired** (step 3c) | same: instructed, upgraded to enforced by the `baron guard` hook |

Tier 3 closes the gap the v1.0 Claude adapter left open (ADR §10.5 / §10.8): whole-tool
denials become real, matching the contract the code-puppy adapter delivers. Sub-tool denials
are instruction-only by default at BOTH tiers — **do not oversell them** (see
`canon/capability-vocab.v1.md` enforceability classes; `docs/LEARNINGS.md` L3: instruction-only
guardrails still add real value, but say honestly what is enforced vs. instructed). The
`baron guard` PreToolUse hook (step 3c, baron ADR-004) upgrades FIVE of the sub-tool denials
(`push_main`, `force_push`, `merge_pr`, `write_path` scoping, `edit_other_personas`) from
instructed to deterministically ENFORCED — but only when baron is installed on the machine
running the session; without it the hook degrades to a non-blocking error and those denials
are instructed again. `open_pr` / `run_tests` denials stay instruction-only (guard does not
parse for them).

---

## Capability map (v1, normalized)

Claude tool names are PascalCase. Build the **minimal** `tools` allow-list — include a tool
only if at least one allowed verb needs it. One row per verb of the frozen v1 vocabulary
(`canon/capability-vocab.v1.md`); **Grants** is the runtime-neutral category the verb needs
(`read` | `write` | `shell`); **Deny enforcement** is what a *denial* of the verb gets at this
adapter's highest tier (Tier 3 — at Tier 2 everything is instructed).

<!-- capability-map:v1 — machine-readable; parsed by tests/bi_runtime_accept.py.
     Keep exactly one row per v1 verb; keep the column order. -->

| Verb | Class | Grants | Runtime tools | Deny enforcement |
|---|---|---|---|---|
| `read_code` | whole-tool | read | `Read`, `Grep`, `Glob` | enforced |
| `read_collab` | whole-tool | read | `Read`, `Grep`, `Glob` | enforced |
| `write_code` | whole-tool | write | `Write`, `Edit` | enforced |
| `write_path` | sub-tool | write | `Write`, `Edit` | enforced-with-baron (instructed otherwise) |
| `open_pr` | sub-tool | shell | `Bash` | instructed |
| `run_tests` | sub-tool | shell | `Bash` | instructed |
| `merge_pr` | sub-tool | shell | `Bash` | enforced-with-baron (instructed otherwise) |
| `push_main` | sub-tool | shell | `Bash` | enforced-with-baron (instructed otherwise) |
| `force_push` | sub-tool | shell | `Bash` | enforced-with-baron (instructed otherwise) |
| `edit_other_personas` | sub-tool | write | `Write`, `Edit` | enforced-with-baron (instructed otherwise) |

> "Deny enforcement: enforced" is only real when NO allowed verb grants the same category —
> whole-tool enforcement works by omitting the tool entirely. Denying `write_code` while
> allowing `write_path` leaves `Write`/`Edit` granted, so that denial degrades to instructed
> (rendered in the body). This is the honesty boundary; do not oversell it.
>
> "**enforced-with-baron (instructed otherwise)**" (the exact qualified form
> `tests/bi_runtime_accept.py` accepts) means: the denial is deterministically enforced by
> the `baron guard` PreToolUse hook when step 3c is wired AND baron is installed on the
> session's machine; without baron the hook command fails as a NON-blocking error (per the
> hooks contract, https://code.claude.com/docs/en/hooks) and the denial degrades to the
> instructed layer. `open_pr`/`run_tests` denials are not guard-parsed and stay instructed.

**Whole-tool denials:** if NO allowed verb needs a tool, it MUST be absent — the runtime
hard-denies it. A read-only persona (e.g. a reviewer/librarian variant with no
write/shell-granting verbs allowed) gets `tools: Read, Grep, Glob` — `Write`/`Edit`/`Bash`
are absent and genuinely unavailable.

**Sub-tool denials** (`merge_pr`, `push_main`, `force_push`, denied `write_path` scopes,
`edit_other_personas`): the parent tool (`Bash` / `Write`) is needed for allowed ops, so
render these into the body's "What never happens" block.

> At **Tier 2** none of this is allow-listed; the same verbs render only as prose (the
> "What you may do" / "What never happens" sections of the persona `CLAUDE.md`).

---

## Steps

### 1. Read the inputs
- `manifest.yaml` (repos, paths, backlog, owner, `adapters.claude.tier`).
- `agents/<slug>/persona.yaml` (the persona; `runtime.adapters.claude.tier` override if set).
- Resolve workspace paths from `manifest.paths` (RELATIVE; never bake absolute home paths — F7).

### 2. Resolve the tier
Apply precedence (persona override > project default > `auto`) and run the `auto`
self-assessment if unresolved. Record the chosen tier + a one-line reason.

### 3a. Tier 3 — write the Claude subagent
Write to `<code_repo>/.claude/agents/<slug>.md` (project-scoped → travels with the repo;
already present on re-clone, so failover = re-clone, no re-hydration unless `persona.yaml`
changed). Schema: YAML frontmatter (`name`, `description`, `tools`) + the system-prompt body.

```markdown
---
name: <slug>
description: <Persona> — <archetype> for <project>. Use when work is routed to the <slug> persona (label agent-<slug>) or the user asks <Persona> to act.
tools: <minimal allow-list from the mapping above, comma-separated>
# model: <persona runtime.model_hint, if set; else omit to inherit the session default>
---
You are <Persona>, the <archetype> persona for <project>.

<scope.summary>

## Identity
- Git author: <git_name> / <git_email>
- Commit prefix: <commit_prefix>
- Routing label: <routing_label>
Before committing, set per-repo git config:
  git config user.name "<git_name>"
  git config user.email "<git_email>"

## Scope
- <scope.focus[0]>
- <scope.focus[1]>
- ...

## Session-start ritual (every session, in order)
<render session_ritual — see step 4>

## What you may do
<one line per capabilities.allow verb, human-phrased>

## What never happens (sub-tool guardrails — self-enforced; the `tools:` allow-list already hard-blocks the rest)
<one imperative line per capabilities.deny verb>
- Never git add -A / git add . (stage only intended files; avoids leaking secrets).

## Commit workflow
Use the `/vc` command to stage, commit (prefix "<commit_prefix>"), and push per the project's
conventions. `_handoff/` files may be direct-pushed; substantive changes go via PR.
```

The `tools:` line is the **enforced** layer; the "What never happens" block is the
**instructed** layer for sub-tool denials. (Mirror of the code-puppy two-layer contract.)

> **`AGENTS.md` note:** `CLAUDE.md` remains this adapter's NATIVE context file — Claude Code
> auto-loads it, and nothing here changes. Emitting an `AGENTS.md` alongside it (the generic
> adapter's step-3 template, `adapters/generic/HYDRATE.md`) is **optional and additive**:
> useful when the same working copy is also visited by AGENTS.md-aware runtimes
> (pydantic-ai-harness `RepoContext()`, etc.), redundant otherwise. If you emit both, both
> are DERIVED from `persona.yaml` — regenerate together, never hand-edit either.

### 3b. Tier 2 — write the persona `CLAUDE.md`
Write to the persona's workspace as `CLAUDE.md` (Claude auto-loads it as session context).
Mirror the v0.3.x `__DEV__/AGENT.md` shape, with YAML frontmatter + these sections:

- **Frontmatter:** `persona`, `slug`, `archetype`, `status: active`, `created`.
- **Title + intro:** "You are <persona>, a <archetype> persona for <project>."
- **Identity table:** slug, git author, git email, commit prefix (`<slug>:`), routing label
  (`agent-<slug>`), plus the `git config` snippet.
- **Workspaces table:** each repo from `manifest.repos` with its relative path + access.
- **Scope:** `scope.summary` + `scope.focus` bullets.
- **Session-start ritual:** render `session_ritual` tokens (step 4).
- **Working rules:** branch `<slug>/<issue>-<slug>`, commit `<slug>: <type> | <desc>`, PR body.
- **What you may do:** from `capabilities.allow`.
- **What never happens:** from `capabilities.deny` (+ standard: force-push, git add -A).

All capabilities here are INSTRUCTED — no tool allow-list is applied at this tier
(step 3c upgrades the five guard-covered sub-tool denials when wired).

### 3c. BOTH tiers — wire the `baron guard` PreToolUse hook

Emit (or merge into) `<code_repo>/.claude/settings.json` a hooks block wiring Claude Code's
PreToolUse event to `baron guard`, per the documented hooks contract
(https://code.claude.com/docs/en/hooks — stdin carries `tool_name`/`tool_input`/`cwd`;
exit 2 blocks the call with stderr fed to the model; exit 0 with no output defers to the
normal permission flow):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "baron guard --persona-file \"${CLAUDE_PROJECT_DIR}/<relative path to agents/<slug>/persona.yaml>\"",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

Resolve the persona-file path RELATIVE to the code repo (F7 — e.g.
`${CLAUDE_PROJECT_DIR}/../<collab-dir>/agents/<slug>/persona.yaml`); never bake an absolute
home path. If `.claude/settings.json` already exists, MERGE the hooks block — do not clobber
other settings.

**Honest note (say this to the user when hydrating):** this upgrades the five guard-covered
sub-tool denials (`push_main`, `force_push`, `merge_pr`, `write_path` scopes,
`edit_other_personas`) from *instructed* to **ENFORCED** — deterministically, before the tool
runs — **when baron is installed** (`uv tool install <bootstrap-repo>/cli`). When baron is
NOT installed, the hook command fails with a non-blocking error (the hooks contract runs the
tool anyway on exit codes other than 0/2), so the session degrades exactly to the instructed
behavior above — worse-is-visible, never worse-is-broken. Overrides
(`BARON_GUARD_OVERRIDE=<reason>`) are allowed-but-logged to the tracked
`.baron/guard-override.log`; each one is expected to become a `_handoff/`.

### 3d. BOTH tiers — wire the evidence hooks (non-blocking; baron ADR-012)

The **same** `baron guard` command, on four more events. Guard dispatches internally on
`hook_event_name`; there is no second binary and no second config to keep in sync.

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash|Edit|Write|NotebookEdit",
        "hooks": [{ "type": "command", "command": "<same command as 3c>", "timeout": 5 }]
      }
    ],
    "PostToolUseFailure": [
      {
        "matcher": "Bash|Edit|Write|NotebookEdit",
        "hooks": [{ "type": "command", "command": "<same command as 3c>", "timeout": 5 }]
      }
    ],
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "<same command as 3c>", "timeout": 5 }] }
    ],
    "SessionEnd": [
      { "hooks": [{ "type": "command", "command": "<same command as 3c>", "timeout": 5 }] }
    ]
  }
}
```

`SessionStart` / `SessionEnd` take **no matcher** — those events carry no tool name, so a
matcher would silently never fire. Use the *same* relative persona path as 3c.

**What these do and, more importantly, do not do.** They are **EVIDENCE ONLY**: each one
emits a structured event (`session.start`, `session.end`, `tool.post`, `tool.failure`) and
always exits 0. They enforce nothing, and they are structurally incapable of blocking —
only `PreToolUse` (step 3c) can ever exit 2. This is deliberate: a hook that blocks
`SessionStart` or `Stop` cannot be un-blocked from *inside* the session, so a bad evidence
path would brick the agent rather than correct it. Preconditions belong in `baron doctor`,
not here.

**Fail-open, unlike 3c.** Enforcement fails CLOSED (a guard that cannot decide denies);
evidence fails OPEN and silently (an event sink that cannot write must not take the session
with it). Set `BARON_EVENTS_DEBUG=1` to see emission failures on stderr.

**Default is off, so wiring this changes nothing yet.** The event plane's default sink is
null: with 3d wired and no `BARON_EVENTS_SINK` set, the session behaves exactly as it did
with 3c alone. Wire it now so enabling telemetry later is one environment variable rather
than a re-hydration of every persona kit.

`Stop` and `SubagentStop` are also handled by `baron guard` (they map to `session.end`) but
are **not** wired by default — `Stop` fires on every turn and its only distinctive power is
blocking, which this design refuses. Any other Claude Code hook event routed here is inert:
guard exits 0 and emits nothing.

### 4. Render the session ritual (v1 tokens, relative paths)
Used by both tiers (in the subagent body at Tier 3, in `CLAUDE.md` at Tier 2).

<!-- ritual-map:v1 — machine-readable; parsed by tests/bi_runtime_accept.py.
     One entry per token in the CANON's session-ritual table
     (references/persona.schema.md). baron.schemas.RITUAL_TOKENS is joined to that
     table by cli/tests/test_schemas.py::test_ritual_tokens_match_the_canon. The parser is shape-tolerant
     (pipe table OR bullet list); entries are read ONLY between this marker and the
     closing fence below, so prose bullets outside it are not miscounted as
     declarations. Adding a ritual token without
     adding it here fails the acceptance harness — that gap shipped once (ADR-008 §2). -->

| Token | Rendered step |
|---|---|
| `sync_repos` | `git -C <repo.path> pull` for each repo with a remote (relative paths) |
| `read_conventions` | Read `<collab.path>/CONVENTIONS.md` + `COORDINATION.md` |
| `check_handoffs` | `grep -rl "^for: <Persona>\|^for: all" <collab.path>/_handoff/ \| xargs grep -l "^status: open"` |
| `check_review_feedback` | `gh pr list --author @me --state open --json number,headRefOid`; for each, read the latest verdict comment (`gh pr view <n> --json comments`) and act only where the verdict's SHA == `headRefOid`. Never act on a review-state label alone. |
| `check_backlog` | resolve `manifest.backlog`: file read, or `gh issue list --label agent-<slug>` |

<!-- /ritual-map:v1 -->

### 5. Emit the `/vc` command
Write `.claude/commands/vc.md` mirroring the v0.3.x command: frontmatter
(`description`, `allowed-tools: Bash, Read`, `argument-hint`), the stage-thoughtfully rule
(never `git add -A`), the `<prefix> <operation> | <description>` convention, commit+push,
verify-the-push, and the hard rules (no force-push/amend/rebase on main; never commit `.env`).
The same command serves both tiers; the Tier-3 subagent body points at it.

### 6. Derive `AGENT.md` (optional, for collab repo)
The collab repo's `agents/<slug>/AGENT.md` is the human-readable manual, DERIVED from
`persona.yaml` (yaml canonical — F4). For Claude, the operative file is the subagent
(Tier 3) or the persona `CLAUDE.md` (Tier 2); `AGENT.md` may mirror it for cross-runtime
readability.

### 7. Verify (exit check)

**Both tiers:**
- Identity (git author/email/prefix/label) matches `persona.yaml`.
- Every `deny` verb appears under "What never happens."
- `.claude/commands/vc.md` exists.
- `.claude/settings.json` carries the PreToolUse → `baron guard` hook (step 3c) with the
  persona-file path resolving; state honestly whether baron is installed (enforced) or not
  (instructed until it is).

**Tier 3:**
- `.claude/agents/<slug>.md` exists with frontmatter (`name`, `description`, `tools`) + body.
- `tools` is MINIMAL: every listed tool is required by an allowed verb; no extras.
- Whole-tool denials honored: the tool for any denied whole-tool capability is ABSENT.
- (Optional, the real proof) the subagent is discoverable/invocable in this session; ask it to
  recite its identity + guardrails.

**Tier 2:**
- Persona `CLAUDE.md` exists with frontmatter + all sections.
- Diff against a v0.3.x hand-authored example: structurally equivalent.
