# Using with code-puppy

New to Barony? Read [`docs/user-guide.md`](docs/user-guide.md) first — it covers
what Barony is, the enforced-vs-instructed distinction, and the whole loop. This
page is the code-puppy-specific delta.

This repo is packaged as a **Claude Code** plugin/skill (`skills/barony/SKILL.md`,
`.claude-plugin/`). **code-puppy does not auto-discover that skill format** — if you point
code-puppy at this repo and ask it to "use the skill", it will look for its own skill registry
and report that it can't find a `SKILL.md` it understands.

That's expected, and it doesn't matter: the runtime-agnostic design means you don't need the
skill wrapper. The instructions are plain markdown any runtime can read, and the `baron` CLI
is runtime-neutral Python.

> Native code-puppy skill packaging is tracked as a follow-up. Until then, use `baron init`
> (below) or invoke the neutral files by path.

## What enforcement you actually get here

Read this before anything else, because the tier numbers are easy to misread.

| | On code-puppy | Where it comes from |
|---|---|---|
| **Whole-tool denials** (deny all writes → omit the write tools) | **enforced**, hard | the agent JSON's `tools` allow-list — `JSONAgent.get_available_tools()` registers only listed tools |
| **Sub-tool denials** (allow `open_pr`, deny `merge_pr` — both ride `agent_run_shell_command`) | **instructed** | `system_prompt` prose; nothing checks |
| **`baron guard`** | **does not run** | guard is a Claude Code PreToolUse hook. code-puppy has no pre-tool seam, so it is deliberately absent from `guard.KNOWN_RUNTIMES` — it emits nothing rather than post-hoc rows implying an adjudication that never happened |

That is the "Tier 2.75" the adapter labels itself: a real allow-list, and a partial one. It
does not round up to 3.

**And the enforced half is not what `baron init` gives you.** `baron init --runtime
code-puppy` emits a **Tier-1 `AGENTS.md`** — instruction-only, nothing enforced:

```console
$ baron init pupkit --dir pupkit-collab --personas dev:scout --runtime code-puppy
scaffolded pupkit at …/pupkit-collab (33 files)
personas: scout (dev), librarian (librarian) · runtime kit: code-puppy

$ find pupkit-collab/agents -type f
pupkit-collab/agents/librarian/persona.yaml
pupkit-collab/agents/librarian/runtime/AGENTS.md
pupkit-collab/agents/librarian/runtime/README.md
pupkit-collab/agents/scout/persona.yaml
pupkit-collab/agents/scout/runtime/AGENTS.md
pupkit-collab/agents/scout/runtime/README.md
```

The kit says so itself: *"Everything in this file is instruction-only (Tier 1) — nothing is
enforced."* Reaching 2.75 means writing `{repo}/.code_puppy/agents/<slug>.json` with a minimal
`tools` list, which is an **in-session** step from
`adapters/code-puppy/HYDRATE.md`. baron never generates it; the tool-omission tests
(`test_adapter_omission.py`) exist precisely to keep that claim honest.

## Two ways in

### A. `baron init` — deterministic, fastest

```bash
pip install barony    # or: uv tool install barony

baron init myproject --dir myproject-collab --code-repo ../myproject \
  --personas dev:scout,librarian:iris --runtime code-puppy
cd myproject-collab
baron validate .
baron status
```

Then start code-puppy **from the collab repo root** (see *Why* below) and hand it:

> Hydrate each persona in `agents/` onto this runtime by following
> `adapters/code-puppy/HYDRATE.md`. Use `canon/capability-vocab.v1.md`,
> `canon/persona.schema.md` and `canon/manifest.schema.md` as the canonical contract.
> Each persona's `persona.yaml` is the machine truth — the `AGENTS.md` in
> `agents/<slug>/runtime/` is derived from it.

That step is what writes the enforced `tools` allow-list.

**Then turn on drift detection, which `init` does not do for you.** With
`--runtime code-puppy`, `baron init` writes **no `adapters:` block** into
`manifest.yaml`, and `baron validate` only checks runtimes the manifest explicitly
declares. Add it by hand:

```yaml
# manifest.yaml
adapters:
  code-puppy: {}
```

Now `baron validate` compares your roster against `.code_puppy/agents/<slug>.json`
and catches the persona you forgot to hydrate:

```console
$ baron validate .
ERROR   manifest.yaml: [runtime-drift] code-puppy: persona 'librarian' is declared in
manifest.personas but has no agent registered, while 1/2 sibling personas are registered
in this project's own repo (scout) — so this project DOES hydrate agents here and
'librarian' was missed. Work routed to it will silently run as some other agent: wrong
identity, wrong commit prefix, wrong capabilities. …
3 file(s) checked: 1 error(s), 0 warning(s)
```

The signal is **partial** registration — zero registered agents is legitimate (Tier 1, or a
freshly scaffolded project), so it stays silent there rather than crying wolf.

### B. The conversational path

```bash
git clone https://github.com/vggg/barony
cd <your-collab-repo>          # start code-puppy FROM the project root (see Why below)
```

Then tell code-puppy:

> Read these files from the cloned repo, in order, then follow them to bootstrap a new
> collab project:
> 1. `barony/skills/barony/assets/collab-repo/START.md`
> 2. `barony/skills/barony/assets/collab-repo/ORCHESTRATE.md`
> 3. `barony/skills/barony/assets/collab-repo/adapters/code-puppy/HYDRATE.md`
>
> Use the schemas in `barony/skills/barony/references/`
> (`capability-vocab.v1.md`, `persona.schema.md`, `manifest.schema.md`) as the canonical contract.

code-puppy reads those, identifies its runtime as `code-puppy`, routes (new dir → `ORCHESTRATE`),
and hydrates each persona via the adapter — no skill discovery needed. This path keeps the
judgment work `baron init` skips: real scope prose and roster design.

## Key file map

| Purpose | Path (under repo root) |
|---|---|
| Front door / router | `skills/barony/assets/collab-repo/START.md` |
| Role 1 — bootstrap a new project | `skills/barony/assets/collab-repo/ORCHESTRATE.md` |
| Role 2 — join an existing project | `skills/barony/assets/collab-repo/PARTICIPATE.md` |
| code-puppy adapter | `skills/barony/assets/collab-repo/adapters/code-puppy/HYDRATE.md` |
| Capability vocabulary (frozen v1) | `skills/barony/references/capability-vocab.v1.md` |
| Persona schema | `skills/barony/references/persona.schema.md` |
| Manifest schema | `skills/barony/references/manifest.schema.md` |

In a scaffolded project these are copied in under `canon/` and `adapters/`, so a joiner needs
only the collab repo.

## Why start the session from the project root

code-puppy discovers project-scoped sub-agents relative to its working directory. If you launch
the session somewhere else, the personas it hydrates won't be found. `cd` into the collab repo
root (your project's `paths.root`) **before** starting code-puppy. (This is `START.md` Step 3.)

Path quirk to expect: **agents live under `.code_puppy/` (underscore); custom commands live
under `.agents/commands/`** — and `baron validate`'s drift check looks in
`.code_puppy/agents/`, so that is the one that has to be right.

## What you'll be asked for

- Project name + one-line description
- Code repo URL + collab repo URL (remote-collab needs both as real repos)
- Backlog source — a `backlog.md` file in the collab repo, or an issue tracker
- Persona roster — at least one `dev` persona (think one per collaborator role)

## Joining an existing project (other collaborators)

Same idea, different recipe: clone the collab repo, start code-puppy from its root, and ask it
to read `canon/START.md` → `canon/PARTICIPATE.md` → `adapters/code-puppy/HYDRATE.md`. Claim a
persona, set your git identity, and validate with a "hello" PR.

## Which `baron` commands are worth running here

Everything except the guard surface, which is Claude-Code-shaped:

| Command | On code-puppy |
|---|---|
| `baron init` / `validate` / `status` / `index` | fully useful — runtime-neutral |
| `baron finding` / `decision` / `handoff` / `export` / `worktree` / `waiver` | fully useful |
| `baron rules list` / `rules explain` | useful as **documentation of the policy**, but note `explain` describes what `baron guard` *would* decide — and guard does not run here |
| `baron guard` | not applicable — no pre-tool seam to hook |
| `baron doctor` | not applicable — it self-tests a Claude Code `.claude/settings.json` PreToolUse hook. On code-puppy the equivalent check is `baron validate .` with `adapters.code-puppy` declared, which catches unhydrated personas |

## "Vault commit" / `/vc` on code-puppy

`/vc` ("vault commit") is a **Claude Code slash command** (`skills/barony/assets/commands/vc.md`).
code-puppy has no command by that name, so saying "vault commit" or `/vc` to a code-puppy agent
does nothing — it doesn't understand it. There are two ways to get the same behavior:

**Option A — use the emitted per-persona command (if your project was hydrated).**
The code-puppy adapter's HYDRATE recipe writes a project-scoped command at
`{code_repo_root}/.agents/commands/vc-<slug>.md` (e.g. `vc-scout.md`). If your runtime's
customizable-commands plugin is active, invoke it as `/vc-<slug>`. Note this comes from the
in-session hydration, not from `baron init`.

**Option B — just describe the workflow (always works).**
Tell the agent in plain language:

> Commit my changes the "vault commit" way: run `git status --short` (never `git add -A`), stage
> only the intended files, commit with message `<commit_prefix> <op> | <description>` (my prefix
> is `<your-prefix>:`), push the current branch (never force-push, never push to main directly),
> and for substantive changes open a PR instead. `_handoff/` files may be direct-pushed.

Both produce the canonical `<persona>: <op> | <description>` commit + push that `/vc` does on
Claude Code. The workflow is what matters, not the slash command — code-puppy executes the steps
directly.

Note that "never force-push, never push to main" is **instructed** on this runtime. On Claude
Code the same two sentences are backed by `baron guard`; here nothing checks them.
