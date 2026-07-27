# HYDRATE — code-puppy adapter

> **Runtime:** code-puppy (Claude-backed coding agent; the runtime behind `list_agents` /
> `invoke_agent`).
> **What this does:** turns a runtime-neutral `agents/<persona>/persona.yaml` into a live,
> project-scoped code-puppy **JSON sub-agent** + its slash command, honoring the persona's
> capabilities at the highest fidelity code-puppy supports.
>
> **Tier:** "Tier 2.75" — native sub-agents with **enforced whole-tool allow-listing**;
> sub-tool denials (e.g. allow `gh pr create` but deny `gh pr merge`) remain instruction-only.
> See the enforcement boundary below. Do not oversell guardrails the runtime cannot enforce.
>
> **Source of truth:** verified against code-puppy source
> (`code_puppy/agents/json_agent.py`, `code_puppy/tools/__init__.py`, `code_puppy/config.py`)
> and a live `list_agents` + `invoke_agent` round trip. See
> `docs/notes/CORRECTION-wibey-vs-codepuppy.md`.
>
> **Fallback:** if `adapters/code-puppy/` is absent in a project, use
> `adapters/generic/HYDRATE.md`.

---

## Prerequisites

1. Both repos cloned (code + collab) at the paths in `persona.yaml` / project manifest.
2. `gh` CLI authenticated for the persona's GitHub access.
3. Write access to the project's `.code_puppy/agents/` directory (created if absent).

> ⚠️ Path separators differ: **agents/config live under `~/.code_puppy/` (underscore);
> custom commands live under `~/.code-puppy/commands/` (hyphen)**. Project-scoped versions
> are `{repo}/.code_puppy/agents/` and `{repo}/.agents/commands/` respectively.

---

## Enforcement boundary (READ THIS — verified finding)

code-puppy enforces capabilities through the agent JSON's `tools` **list**.
`JSONAgent.get_available_tools()` filters the requested tools against the live
`TOOL_REGISTRY` — **only listed tools are registered for the agent.** This is real but
**partial**:

| Capability class | Enforced? | How |
|---|---|---|
| **Whole-tool** (deny all file writes → omit write tools) | ✅ YES, hard | leave the tool out of `tools` |
| **Sub-tool** (allow `open_pr` but deny `merge_pr` — both via `agent_run_shell_command`) | ❌ NO | instruction in `system_prompt` only |

> Unlike Wibey, code-puppy's `model` field **is applied** (pins the agent's model). There is
> no `permissionMode` field.

**Every hydrated agent therefore gets BOTH layers:**
1. A minimal `tools` allow-list (the enforced layer).
2. A "What never happens" block inside `system_prompt` (the instructed layer for sub-tool
   denials).

---

## Capability map (v1, normalized)

Translate `persona.yaml` `capabilities.allow` into the **minimal** `tools` list. Include a
tool only if at least one allowed verb needs it. One row per verb of the frozen v1 vocabulary
(`canon/capability-vocab.v1.md`); **Grants** is the runtime-neutral category the verb needs
(`read` | `write` | `shell`); **Deny enforcement** is what a *denial* of the verb gets on this
runtime. Every persona additionally gets `agent_share_your_reasoning` (narration; harmless,
recommended — not tied to a verb).

<!-- capability-map:v1 — machine-readable; parsed by tests/bi_runtime_accept.py.
     Keep exactly one row per v1 verb; keep the column order. -->

| Verb | Class | Grants | Runtime tools | Deny enforcement |
|---|---|---|---|---|
| `read_code` | whole-tool | read | `read_file`, `list_files`, `grep` | enforced |
| `read_collab` | whole-tool | read | `read_file`, `list_files`, `grep` | enforced |
| `write_code` | whole-tool | write | `create_file`, `replace_in_file`, `delete_snippet` | enforced |
| `write_path` | sub-tool | write | `create_file`, `replace_in_file` | instructed |
| `open_pr` | sub-tool | shell | `agent_run_shell_command` | instructed |
| `run_tests` | sub-tool | shell | `agent_run_shell_command` | instructed |
| `merge_pr` | sub-tool | shell | `agent_run_shell_command` | instructed |
| `push_main` | sub-tool | shell | `agent_run_shell_command` | instructed |
| `force_push` | sub-tool | shell | `agent_run_shell_command` | instructed |
| `edit_other_personas` | sub-tool | write | `create_file`, `replace_in_file` | instructed |

> "Deny enforcement: enforced" is only real when NO allowed verb grants the same category —
> whole-tool enforcement works by omitting the tool entirely. Denying `write_code` while
> allowing `write_path` leaves the write tools granted, so that denial degrades to
> instructed. Same honesty boundary as the enforcement table above.
>
> v1 note: path-scoped writes are the parametric `write_path: [findings, _handoff, ...]` verb
> (replaces v0's `write_findings`/`write_handoff`). The allowed scopes are rendered into the
> persona body; denied scopes (e.g. `write_path: [wiki]`) become "what never happens" lines.

Optional, add only if the persona's scope needs it: `ask_user_question` (interactive
clarification), `list_agents`/`invoke_agent` (orchestrator personas only),
`activate_skill`/`list_or_search_skills` (skill-using personas).

> Avoid the deprecated `edit_file` — it auto-expands to
> `create_file, replace_in_file, delete_snippet`. List those explicitly instead.

**Whole-tool denials:** if NO allowed verb needs a tool, it MUST be absent. A read-only
persona (e.g. Librarian) with no `write_*`/`open_pr`/`run_tests` verbs gets
`["read_file","list_files","grep","agent_share_your_reasoning"]` — write + shell tools are
hard-denied and the runtime enforces it.

**Sub-tool denials** (`merge_pr`, `push_main`, `force_push`, `write_wiki`,
`edit_other_personas`): the parent tool (`agent_run_shell_command` / write tools) is needed
for allowed ops, so render these into the `system_prompt` "What never happens" block.

---

## Steps

### 1. Read the persona spec
Read `agents/<persona>/persona.yaml`. Extract: `persona`, `slug`, `archetype`, `identity`,
`capabilities.allow`, `capabilities.deny`, `scope`, `session_ritual`, and optional
`runtime.model_hint`.

### 2. Compute the `tools` list
Union the tools required by every verb in `capabilities.allow` (table above), add
`agent_share_your_reasoning`, deduplicate. This is the enforced layer.

### 3. Build the `system_prompt`
Assemble a single string (or list of strings) with these sections, filling persona values:

```
You are <Persona>, the <archetype> persona for <PROJECT_NAME>.

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
<render session_ritual — see Ritual rendering below>

## What you may do
<one line per capabilities.allow verb, human-phrased>

## What never happens (guardrails — self-enforced; the runtime cannot hard-stop these)
<one imperative line per capabilities.deny verb>
- Never git add -A / git add . (stage only intended files; avoids leaking secrets).

## Commit workflow
Use the /vc-<slug> command to stage, commit (prefix "<commit_prefix>"), and push per the
project's conventions. _handoff/ files may be direct-pushed; substantive changes go via PR.
```

### 4. Render the session ritual (v1 tokens; RELATIVE paths — F7 fix)
> Resolve every path RELATIVE to `manifest.paths.root` (default = collab repo root). NEVER
> bake absolute home-dir paths into the agent body — that breaks portability/failover
> (Phase 2 F7). Resolve `check_backlog` against `manifest.backlog` (Phase 2 F8).

| Token (v1) | Rendered step |
|---|---|
| `sync_repos` | for each repo in `manifest.repos` with a `remote`: `git -C <repo.path> pull` (relative path). Local-only repos (no remote): skip. |
| `read_conventions` | Read `<collab.path>/CONVENTIONS.md` and `<collab.path>/COORDINATION.md` |
| `check_handoffs` | `grep -rl "^for: <Persona>\|^for: all" <collab.path>/_handoff/ \| xargs grep -l "^status: open"` |
| `check_backlog` | if `manifest.backlog.source == file`: read `<collab.path>/<backlog.location>`. If `github_issues`: `gh issue list --state open --label <routing_label> --repo <backlog.location>`. If `jira`: query per project config. |

> Legacy note: v0 used `pull_both_repos` (transport-coupled, two hardcoded repos). v1 uses
> `sync_repos` over `manifest.repos` so local-only and N-repo projects both work.

### 5. Write the project-scoped agent JSON
Write to `{code_repo_root}/.code_puppy/agents/<slug>.json` (project scope → travels with the
repo, overrides user agents on name collision → satisfies portability/failover). Schema
(required: `name`, `description`, `system_prompt`, `tools`):

```json
{
  "name": "<slug>",
  "display_name": "<Persona> <emoji> (<archetype>)",
  "description": "<Persona> — <archetype> for <PROJECT_NAME>. Invoke when work is routed to the <slug> persona (label agent-<slug>) or the user asks <Persona> to act.",
  "system_prompt": "<assembled in step 3>",
  "tools": ["<computed in step 2>"],
  "model": "<optional: persona.yaml runtime.model_hint, else omit for global default>",
  "user_prompt": "<optional opening question, e.g. 'Which module should I work on?'>"
}
```

Do NOT add marketplace metadata (`id`, `tags`, `version`, `owner_*`, etc.) — those are
injected on marketplace upload, not needed for a locally authored project agent.

### 6. Emit the slash command (the `/vc` analog)
Write `{code_repo_root}/.agents/commands/vc-<slug>.md` (project scope, VCS-shareable; the
`.agents/commands/` dir is scanned by code-puppy's customizable-commands plugin):

```markdown
---
name: vc-<slug>
description: Stage, commit, and push <Persona>'s changes using prefix "<commit_prefix>".
---
# Repo Commit — <Persona>
1. `git status --short` — show what will be staged. Never `git add -A`/`.` (avoids secrets).
2. Stage only the intended files (print the list).
3. Commit with message: `<commit_prefix> <op> | <short description>`.
4. Push the current branch (NEVER force-push; NEVER push to main directly).
5. For substantive changes, open a PR; `_handoff/` files may be direct-pushed per CONVENTIONS.
```

### 7. Verify
- `list_agents` includes `<slug>` (project agent discovered). ← the real proof.
- Optional: `invoke_agent("<slug>", "identify yourself + list your guardrails")` and confirm
  it recites identity + denies correctly.
- JSON sanity: all four required fields present; `tools` is a list; every tool name is in the
  live registry (`read_file`, `create_file`, `agent_run_shell_command`, etc.).
- Minimality: no tool present that no allowed verb requires.
- Every `deny` verb appears in the `system_prompt` "What never happens" block.

---

## Worked example — the `tess` acceptance fixture (test-coverage dev) [VERIFIED LIVE]

Input: the dev fixture at `tests/examples/tess/persona.yaml` in the skill repo (allow:
read_code, read_collab, write_code, `write_path: [findings, _handoff]`, open_pr, run_tests).

Computed `tools` =
`["read_file","list_files","grep","create_file","replace_in_file","delete_snippet","agent_run_shell_command","agent_share_your_reasoning"]`
(read_* → read_file/list_files/grep; write_* → create_file/replace_in_file/delete_snippet;
open_pr/run_tests → agent_run_shell_command; + narration).

Whole-tool denials: none possible — the fixture needs shell + write, so merge_pr/push_main/etc.
are rendered as `system_prompt` instructions. (Dev personas gain the LEAST Tier enforcement; a
read-only Librarian gains the MOST.)

Output files:
- `{code_repo_root}/.code_puppy/agents/tess.json`
- `{code_repo_root}/.agents/commands/vc-tess.md`

**Proven:** dropped into `.code_puppy/agents/`, `list_agents` showed the persona
(`test-coverage dev`); `invoke_agent` had it recite identity + all guardrails.

---

## Notes / limitations (carry to Phase 3)

- Dev personas gain the LEAST from enforcement (need shell + write). Read-only personas gain
  the MOST (deny write + shell outright; runtime truly blocks them).
- `model` IS applied in code-puppy (can pin per persona) — unlike Wibey.
- Native `scheduler_*` tools exist → autonomous-cron personas may be achievable on code-puppy
  without external cron. Revisit post-1.0 (ADR §7.1).
- Project-scoped agent JSON means failover = re-clone; the agent file is already there. No
  re-hydration unless `persona.yaml` changed.
- Path gotcha: `~/.code_puppy/agents/` (underscore) vs `~/.code-puppy/commands/` (hyphen).
