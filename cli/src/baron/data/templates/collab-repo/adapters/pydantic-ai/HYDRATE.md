# HYDRATE — pydantic-ai adapter (in-process, code-defined personas)

> **Runtime:** [pydantic-ai](https://pydantic.dev/docs/ai/overview/) + the official
> capability library [pydantic-ai-harness](https://pydantic.dev/docs/ai/harness/)
> (`Agent`, `FileSystem`, `Shell`, `RepoContext`).
> **What this does:** turns a runtime-neutral `agents/<slug>/persona.yaml` into a live
> `pydantic_ai.Agent` — instructions from the persona spec, a minimal capability set
> (whole-tool denials = capability omission), and an **in-process tool-interception guard**
> that consumes baron's `capability-rules.v1.yaml` so sub-tool denials are vetoed before
> the tool executes.
>
> **Tier:** 3 — and uniquely, **sub-tool denials are natively `enforced` here**: because
> hydration happens in-process, every tool call passes through a capability hook
> (`AbstractCapability.before_tool_execute`; raising `ModelRetry` vetoes the call — the
> documented interception seam) *whenever the agent is built with `build_agent`*. No
> external hook wiring, no separate install step to degrade without.
>
> **Verified against:** `pydantic-ai-harness 0.10.0` / `pydantic-ai-slim 2.14.1–2.19.x`
> (the pinned extra range; harness is 0.x — minor releases may break, hence the pin).
> **Source of truth:** the working hydrator `cli/src/baron/runtimes/pydantic_ai.py` in the
> bootstrap repo — install with `pip install 'barony[pydantic-ai]'`.
>
> **Read first:** `canon/PARTICIPATE.md` (capability ladder) and
> `canon/capability-vocab.v1.md` (verb contract + enforceability classes).
>
> **Fallback:** if this adapter is absent, use `adapters/generic/HYDRATE.md` (Tier 1).

---

## Prerequisites

1. Both repos cloned (code + collab) at the paths in the project manifest.
2. Python ≥ 3.10 with the extra installed: `pip install 'barony[pydantic-ai]'`
   (pins `pydantic-ai-harness>=0.10,<0.11` + `pydantic-ai-slim>=2.14.1,<3`).
3. A model key for the model you pass to `build_agent` — or none: the built-in `'test'`
   model (`TestModel`) runs fully offline for smoke checks.

---

## Enforcement boundary (READ THIS — the adapter's distinction)

pydantic-ai personas run **in-process**: the hydrator both *assembles* the capability set
and *intercepts* every tool call, which moves the enforcement line compared to the other
Tier-3 adapters:

| Capability class | Enforced? | How |
|---|---|---|
| **Whole-tool** (no shell verbs → no shell at all) | ✅ YES, hard | the harness capability is simply **omitted** from `Agent(capabilities=[...])` — the tools do not exist for the model |
| **Sub-tool** (allow `open_pr`, deny `push_main` — both via `run_command`) | ✅ YES, for the five guard-covered verbs | the guard capability's `before_tool_execute` hook evaluates the call against `capability-rules.v1.yaml` and raises `ModelRetry` (veto + reason fed to the model) BEFORE execution |

Honesty boundary, unchanged in spirit: this is deterministic enforcement of the
honest-mistake class, not an adversarial sandbox (the harness itself calls its shell
controls "best-effort" — OS-level isolation is the stricter tool). `open_pr` / `run_tests`
denials stay **instructed** (the rules artifact deliberately defines no detection for them;
ADR-004 §2.2) — though a denied `run_tests` additionally seeds the Shell capability's
`denied_commands` with common test runners. And the guard only guards agents built through
`build_agent`: hand-rolling an `Agent` without the guard capability is Tier-1 territory.

**Evidence, on the same plane as Claude Code (ADR-019).** The guard capability is also an
event *producer*: every adjudicated call emits one `guard.decision` row into
`.baron/events/` in the same wire shape the Claude Code hook writes, tagged
`baron.runtime="pydantic-ai"` and `baron.trigger="before_tool_execute"`. `baron.enforcement`
is read off the guard's own `Decision.adjudicated` (ADR-018) — never re-derived from the
rules artifact — so a row that says `enforced` means a capability rule matched *and* the
outcome turned on this persona. Read tools emit nothing, mirroring `Read`/`Grep` under
PreToolUse. **Nothing is written unless an operator sets `BARON_EVENTS_SINK`** (default
`null`), and emission is fail-OPEN: a broken sink can never turn a deny into an allow.
Two honest bounds: there is no in-process `BARON_GUARD_OVERRIDE` path, so this runtime emits
no `guard.override` rows (zero overrides here means "no mechanism", not "no overrides"), and
`baron.trigger` values are runtime-native, so cross-runtime aggregation must group by
`baron.runtime` first.

**Known bypass — command-string wrappers.** The guard's static parser inspects each
top-level subcommand's tokens; it does NOT recurse into an interpreter invoked with an
inline program string, so `bash -c '...'`, `sh -c "..."`, and `python3 -c '...'` run their
payload uninspected — a `git push origin main` hidden inside `bash -c` is not caught. This
in-process Shell narrows (not closes) that class: it denies redirect/pipe operators
(`>`, `>>`, `|`) so a payload can't redirect out of root, and a test-only persona's shell is
allowlisted to test runners. Where the boundary must hold against a wrapper, use OS-level
isolation.

---

## Capability map (v1, normalized)

Tool names are the harness capabilities' snake_case tools (`FileSystem`, `Shell`). Build
the **minimal** capability set — include a capability only if at least one allowed verb
needs it. One row per verb of the frozen v1 vocabulary
(`canon/capability-vocab.v1.md`); **Grants** is the runtime-neutral category the verb needs
(`read` | `write` | `shell`); **Deny enforcement** is what a *denial* of the verb gets on
this runtime via `build_agent`.

<!-- capability-map:v1 — machine-readable; parsed by tests/bi_runtime_accept.py.
     Keep exactly one row per v1 verb; keep the column order. -->

| Verb | Class | Grants | Runtime tools | Deny enforcement |
|---|---|---|---|---|
| `read_code` | whole-tool | read | `read_file`, `list_directory`, `search_files`, `find_files` | enforced |
| `read_collab` | whole-tool | read | `read_file`, `list_directory`, `search_files`, `find_files` | enforced |
| `write_code` | whole-tool | write | `write_file`, `edit_file`, `create_directory` | enforced |
| `write_path` | sub-tool | write | `write_file`, `edit_file` | enforced |
| `open_pr` | sub-tool | shell | `run_command` | instructed |
| `run_tests` | sub-tool | shell | `run_command` | instructed |
| `merge_pr` | sub-tool | shell | `run_command` | enforced |
| `push_main` | sub-tool | shell | `run_command` | enforced |
| `force_push` | sub-tool | shell | `run_command` | enforced |
| `edit_other_personas` | sub-tool | write | `write_file`, `edit_file` | enforced |

> "Deny enforcement: enforced" on the whole-tool rows is only real when NO allowed verb
> grants the same category — capability omission is the mechanism. Denying `write_code`
> while allowing `write_path` keeps `FileSystem` write tools present; that denial is then
> enforced by the guard's path scoping instead (sub-tool row), and a persona with NO write
> verbs at all gets a natively read-only `FileSystem`
> (`protected_patterns=['*', '**/*']` — writes are rejected by the harness itself).
>
> The sub-tool `enforced` rows are enforced by in-process interception consuming
> `capability-rules.v1.yaml` (see `canon/capability-rules.md` in the skill references) —
> the SAME rule table `baron guard` uses on Claude Code, hence identical decisions.
> `open_pr`/`run_tests` rows stay `instructed` because the rules artifact defines no
> detection for them. State it exactly this way; do not oversell.

---

## Steps

### 1. Install the extra + read the persona spec

```bash
pip install 'barony[pydantic-ai]'
```

Read `agents/<slug>/persona.yaml`. Everything below is derived from it — the hydrator does
this for you.

### 2. Build the agent with the hydrator

```python
from pathlib import Path

from baron.runtimes.pydantic_ai import build_agent

agent = build_agent(
    Path("agents/<slug>/persona.yaml"),
    collab_root=Path("."),                 # the persona's working-copy root
    model="anthropic:claude-sonnet-4-6",   # or "test" for an offline smoke run
)
result = agent.run_sync("Introduce yourself and recite your guardrails.")
```

What `build_agent` assembles:

- **Instructions** — identity (git author/email/prefix/label), scope summary + focus,
  session ritual, "What you may do" / "What never happens" imperative lines. Same shape as
  the other adapters' persona bodies.
- **`FileSystem(root_dir=<collab_root>)`** — omitted read scoping is not needed (reads are
  always granted in practice); personas with NO write verbs get
  `protected_patterns=['*', '**/*']` (natively read-only).
- **`Shell(cwd=<collab_root>, denied_operators=['>', '>>', '|'])`** — ONLY when at least
  one shell-granting verb is allowed. A persona whose ONLY shell need is `run_tests` (a
  reviewer shape: allows `run_tests`, no dev write verbs) gets an **allowlisted** shell
  restricted to test runners (`pytest`/`py.test`/`tox`/`nox`/`unittest`/`coverage`) so it
  cannot `curl`/`rm`/arbitrary `git push`; a broader (dev) shell stays general but blocks
  redirect/pipe operators so a `>` can't write out of root behind the guard's back. A denied
  `run_tests` seeds `denied_commands` with common test runners. (`python -m pytest` /
  `make test` are intentionally NOT allowlisted — the harness matches the executable name,
  so allowing `python`/`make` would re-open a general-purpose runner; invoke the runner
  directly.)
- **`RepoContext(workspace_dir=<collab_root>)`** — added when a `collab_root` is passed, to
  auto-load `CLAUDE.md`/`AGENTS.md` from the working copy (additive; falls back cleanly if
  the installed harness lacks the capability).
- **The baron guard capability** — `before_tool_execute` maps `run_command` commands and
  `write_file`/`edit_file`/`create_directory` paths to capability verbs via
  `capability-rules.v1.yaml` and vetoes denials with `ModelRetry` (reason fed to the model,
  mirroring the Claude hook's exit-2 stderr).

### 3. Or scaffold a bootstrap script

```bash
baron hydrate pydantic-ai --persona-file agents/<slug>/persona.yaml --out agent_setup.py
```

Emits a ready-to-edit `agent_setup.py` (imports `build_agent`, model placeholder). The
emission itself needs only baron; *running* the script needs the extra.

### 4. Verify (exit check)

- `build_agent(...)` constructs without error and `agent.run_sync(...)` with `model="test"`
  completes offline.
- A persona with no shell verbs has NO `Shell` capability (ask it to run a command — the
  tool does not exist).
- A guarded denial actually vetoes: scripted attempt at `git push origin main` for a
  persona denying `push_main` is refused with the guard's reason (the bootstrap repo's
  `cli/tests/test_pydantic_ai.py` automates exactly this).
- Every `deny` verb appears in the instructions' "What never happens" block.

---

## Composing the session ritual (optional)

`build_agent` gives you the *enforcement* half of a persona; the git/markdown
*bookkeeping* half of the session ritual (sync working copies, surface open
handoffs, regenerate the handoff index, commit coordination artifacts, run a
divergence check) is exposed as two thin, opt-in CLI primitives —
`baron session start` and `baron session end` (ADR-007). A pydantic-ai
user or driver MAY compose them around a run:

```bash
baron session start --collab . --persona <slug> --sync   # before the run
# ... agent.run_sync(...) ...
baron session end   --collab . --persona <slug>          # after the run (exit 1 = red status)
```

…or wrap them in a `DynamicWorkflow` step / a capability that shells out to them.
**Barony ships the runtime-neutral CLI, not the wrapper** — the primitives do NO
agent loop and NO model calls (that stays your job / pydantic-ai's), so the
wrapper is build-on-demand. They are not new capability verbs; the frozen
vocabulary is untouched.

---

## Notes / limitations

- **In-process only.** The guarantees hold for agents built via `build_agent`. This adapter
  does not (cannot) constrain a developer who constructs `Agent` by hand.
- **`RepoContext()` layering:** `build_agent` wires `RepoContext(workspace_dir=<collab_root>)`
  when a `collab_root` is passed, auto-loading `CLAUDE.md`/`AGENTS.md` from the working copy
  (e.g. a Tier-1-emitted `AGENTS.md`, `adapters/generic/HYDRATE.md` step 3). It stays
  additive — the persona is already injected as instructions — and degrades cleanly if the
  installed harness lacks the capability.
- **Version pin honesty:** the harness is 0.x and states that minor releases may break; the
  extra pins `<0.11`. Re-verify the capability hook seam on any pin bump.
- `runtime.model_hint` from `persona.yaml` is honored as the default model when the caller
  does not pass one explicitly.
