# barony — git-native governance for teams of AI coding agents

> Install `barony`, run `baron` (or `barony` — both work), import `baron`.
> Part of **Barony** —
> [github.com/vggg/barony](https://github.com/vggg/barony) — where the full
> framework, concepts, and adapters live. This page is the CLI reference.

`baron` is **Barony**'s CLI. It
turns the multi-agent coordination *conventions* that
Barony emits into *mechanisms*: a small CLI that scaffolds new projects
(`baron init`), validates the canonical specs, reports clone/branch/ledger
divergence, and performs the race-prone record-keeping operations
(finding/decision numbering, handoff lifecycle) safely.

**Design principle (ADR-003, `../docs/adr/ADR-003-baron-cli.md`): the
markdown/git substrate IS the database.** baron is a disciplined reader/writer
over the same human-legible collab-repo files the personas use
(`manifest.yaml`, `persona.yaml`, `findings/index.md`, `decisions/index.md`,
`_handoff/*.md`, `wiki/status.md`). It never introduces another store, and every
file it writes remains fully human/agent-legible.

Dependencies: **typer + pyyaml only**. `git` is driven via subprocess. `gh` is an
accepted prerequisite for forge features only (`baron lock`) — everything else
below works without `gh` installed. The pydantic-ai runtime adapter is an
**optional extra** (`barony[pydantic-ai]`, pinned) — see `baron hydrate` below.

## Install

Live on PyPI (distribution name `barony`, console script `baron`):

```bash
uv tool install barony                  # installs the `baron` console script
uv tool install 'barony[pydantic-ai]'   # + the pydantic-ai runtime adapter
# or:
pip install barony
baron --version
```

From a clone (development):

```bash
uv run --project cli baron --help       # run without installing
uv tool install ./cli                   # install the local copy
```

## Quickstart

Verified end-to-end from a `pip install barony`:

```bash
# a code repo to govern (skip if you already have one):
mkdir gardenkit && git -C gardenkit init -b main -q && \
  git -C gardenkit commit --allow-empty -m "init" -q

baron init gardenkit --dir gardenkit-collab --code-repo ./gardenkit \
  --personas dev:fern,dev:moss,librarian:iris
cd gardenkit-collab
baron validate .          # 0 errors
baron status              # green when fresh
baron finding new --title "First finding" --author fern --no-push
HANDOFF=$(baron handoff create --for moss --from fern --title "Review the seam")
baron handoff close "$HANDOFF" --note "Done, see F1."
baron index               # regenerates _handoff/README.md — commit it
baron worktree add fern   # worktree of ./gardenkit — ../gardenkit-worktrees/fern
```

## Commands

### `baron init <project-name>` (ADR-006)

The deterministic, non-conversational scaffold — the mechanical subset of the
skill's `ORCHESTRATE.md` recipe.

```bash
baron init gardenkit --dir gardenkit-collab --code-repo ./gardenkit \
  --personas dev:fern,dev:moss,librarian:iris --runtime claude
```

Flags: `--dir` (default `./<project-name>`), `--code-repo` (local path or git
URL, recorded in `manifest.yaml` with a relative path + `workspace.worktrees_root`),
`--personas archetype:slug,...` (archetypes: `dev`, `librarian`,
`autonomous-event`, `autonomous-cron`, `reviewer`, `merger`; a librarian is
appended when missing), `--runtime claude|generic|pydantic-ai|code-puppy`,
`--no-git`. Refuses a non-empty target directory.

Emits the canonical layout — `CONVENTIONS.md`/`COORDINATION.md` (filled),
`manifest.yaml`, `canon/` + `adapters/` copied verbatim from the **packaged
templates** (vendored from `skills/barony/assets/collab-repo/` per ADR-006;
drift-guarded byte-for-byte by `tests/test_template_sync.py`), hydrated
`agents/<slug>/persona.yaml` (identity `<slug>@<project>.local`, commit prefix,
routing label; generic edit-me scope), a genesis handoff, `findings/index.md` +
`decisions/index.md` ledger headers, the wiki stub, the lock-guard and
strip-stale-verdict CI templates, and a per-persona **runtime kit** under
`agents/<slug>/runtime/`:

| `--runtime` | Kit contents |
|---|---|
| `claude` (default) | Tier-2 persona `CLAUDE.md` + `.claude/settings.json` wiring the `baron guard` PreToolUse hook |
| `generic`, `code-puppy` | Tier-1 `AGENTS.md` (instruction-only; code-puppy's documented fallback) |
| `pydantic-ai` | `agent_setup.py` bootstrap (running it needs `barony[pydantic-ai]`) |

The scaffold must pass `baron validate` with zero errors before init reports
success; then `git init -b main` + a first commit of exactly the files written
(never `git add -A`), unless `--no-git`. Dates come from the injectable clock.
Persona scope prose, `AGENT.md` manuals, and Tier-3 hydration (Claude
subagents, code-puppy JSON agents) stay on the conversational path — init
prints the pointers instead of pretending.

### `baron validate [PATH]` (M1)

Validate `persona.yaml` / `manifest.yaml` — a single file, or every one
discovered under `PATH`. Schemas are declarative Python data
(`src/baron/schemas.py`) formalized from the prose specs in
`../skills/barony/references/`; the FROZEN 10-verb capability
vocabulary is embedded and drift-guarded by a test that re-parses
`capability-vocab.v1.md`.

Checks: YAML parse, missing/unknown fields, types, verbs outside the vocabulary,
allow/deny overlap (including `write_path` scope overlap), unfilled
`{{PLACEHOLDER}}` tokens.

**Template rule:** directory discovery skips files whose path contains a
template marker directory (`assets/collab-repo/` or `legacy/`) — emit-time
templates legitimately carry placeholders and often aren't valid YAML at all.
Fixture paths (`tests/examples/`) are validated but exempt from the placeholder
check only. An explicitly named file is always validated.

**Spec↔runtime drift (P2.3, since 0.7.0).** When you validate a directory
holding `manifest.yaml`, baron also compares the declared personas against the
agent registry of every runtime the manifest declares under `adapters`:

| Runtime | Registry checked |
|---|---|
| `claude` | `.claude/agents/<slug>.md` — collab root, each `repos[].path`, then `~/` |
| `code-puppy` | `.code_puppy/agents/<slug>.json` (note the underscore) |
| `pydantic-ai`, `generic` | none — hydration is in-process / Tier-1 prose, so there is nothing to inspect |

**The signal is PARTIAL registration, not absence.** If some declared personas
are registered and others are not, the project demonstrably hydrates agents on
this runtime, so the gaps are real drift and each is an **ERROR**: work routed to
a missing persona does not fail loudly — it runs as whatever agent the runtime
*does* have, with the wrong identity, commit prefix and capability set. That is
how a cron ran under the wrong persona on the pilot.

**That evidence must be repo-scoped.** A `~/.claude/agents` entry named after one
of your personas proves nothing about *this* project — the directory is shared
machine-wide, and `dev`/`librarian` are the `baron init` defaults, so collisions
are common. A user-level file can still *satisfy* a persona (with a scope
warning); it can never establish that the project hydrates agents at all.

**All-or-nothing is silent**, because zero registered agents is *correct* in three
legitimate cases: a Tier-2 Claude project (`HYDRATE.md` says at Tier 2 "do NOT
emit a dead subagent file"), a freshly scaffolded project (Tier-3 hydration is
conversational — ADR-006 §3), and any Tier-1 runtime. **`tier: auto` is not sidestepped — it is treated as Tier 3 and that is a
judgement call**, stated here rather than buried: under `auto`, HYDRATE.md allows
per-persona, per-session degradation to Tier 2, so a persistent partial registry
*could* be legitimate degradation rather than drift. baron cannot tell them apart
statically. It errors, and the message names the escape hatch: declare
`runtime.adapters.claude.tier: 2` in that persona's `persona.yaml` and the check
honours it. **Weigh that before reaching for it:** the override is permanent and
locks the persona out of Tier 3 (`HYDRATE.md` makes `auto`→Tier 3 conditional on
its absence), so its whole-tool denials drop from *enforced* to *instruction-only*
— while the ambiguity it silences is only per-session. Suppressing a warning
should not quietly cost you enforcement. Explicit `tier: 2` — at project or
persona level — is skipped outright.

Registration is matched by the filename the adapter writes **and** by a `name:`
frontmatter match, since that is what Claude actually keys a subagent on.

Only runtimes the manifest **explicitly declares** are checked, so a stray
registry cannot fail a project that does not hydrate agents. A persona resolving
*only* via the user-level `~/` registry warns: that directory is shared across
every project on the machine, so a same-named agent from elsewhere would satisfy
the check.

**Honest limits.** A project with exactly one persona cannot produce a partial
state, so a single unregistered persona is invisible; and if *every* persona
drifted at once that reads as "not hydrated" and stays silent. The pilot shape —
some registered, some not — is what this catches.

**On CI:** the Claude registry is repo-scoped and *travels with the clone*
(`HYDRATE.md` step 3a), so a committed `.claude/agents/` **is** present in CI —
by design. A partially-registered project therefore fails CI, which is the
intended behaviour, not an accident. `--no-runtime-drift` opts out where that is
unwanted. (`baron init` passes it for its own self-check: init validates the spec
it wrote, not the environment around it.)

Exit 0 = no errors (warnings allowed) / 1 = errors. `--json` for machines.

```bash
baron validate tests/examples/tess/persona.yaml
baron validate . --json
baron validate . --no-runtime-drift   # spec conformance only
```

### `baron status [--fetch] [--sla N] [--json]` (M2)

Run from a collab repo (or `--collab PATH`). Reads `manifest.yaml` — including
the optional `workspace.clones` / `workspace.worktrees_root` fields (see
`../skills/barony/references/manifest.schema.md`) — and
reports, with severity:

| Check | Severity | Meaning |
|---|---|---|
| `ahead` | red | commits never pushed to origin (stranded work) |
| `behind` | red | origin commits never pulled (stale canonical clone) |
| `unmerged-branch` | red | local branch not merged to origin default, with last-commit age |
| `handoff-overdue` | red | `status: open` handoff older than the SLA (default 14 days) |
| `dirty` | warn | uncommitted paths |
| `ledger-stale` | warn | newest F/D entry date older than the newest `docs/`/`src/` commit in the code repo (**heuristic**, labeled as such) |
| `wiki-stale` | warn | `wiki/status.md` `updated:` older than the newest finding entry |

Use `--fetch` to refresh each working copy's origin refs first — without it,
remote-side divergence (the `behind` class) is invisible. Exit 0 = green
(warnings allowed) / 1 = any red (CI-usable).

### `baron finding new` / `baron decision new` (M3)

```bash
baron finding new --title "Tracker-gated recall" --author carson
baron decision new --title "Adopt fps-aware segmentation" --author terrence --body-file body.md
```

Parses the index for the max ID (both `### F<N>` headings and `| F<N> |` table
rows), allocates the next, appends a house-style entry
(`### F<N> — <title> (<date>, <author>)`), commits, and pushes. **On push
rejection** (someone else claimed the number first): roll back, `pull --rebase`,
re-parse, renumber, retry — bounded (`--retries`, default 3). git's push
atomicity is the lock; there is no other store. `--no-push` for offline work.
Dates come from a single injectable clock (`src/baron/clock.py`).

**`--author` vs git author (allocator vs proposer).** `--author` sets only the
**ledger attribution** — the name written into the entry heading (`### F<N> —
<title> (<date>, <author>)`). It is independent of the **git author identity**
that signs the commit (set per-repo via `git config user.name/user.email`, per
each persona's `identity` block). They can legitimately differ: a librarian may
*allocate* a finding **for** a write_path-restricted reviewer — `--author rex`
records rex as the proposer while the commit is authored by the librarian who
holds the write scope. Attribution (who reasoned it) and authorship (who
committed it) are separate on purpose.

### `baron handoff create|close|list` (M3)

```bash
baron handoff create --for tess --from rex --title "Review the seam" --priority high
baron handoff create --for tess --from rex --title "Big review" --body-file review.md
baron handoff close _handoff/2026-07-22-review-the-seam.md --note "Done, see F9." --as tess
baron handoff list --open
```

`create` writes `_handoff/YYYY-MM-DD-<slug>.md` with the standard frontmatter
(`created` / `status: open` / `for` / `from` / `priority`); `--body-file` drops a
prepared body under the frontmatter (parity with `finding`/`decision`, no
`--no-commit` + manual-append dance). `close` flips `status` to `done`, adds a
`closed:` date and an optional blockquote note, then `git mv`s the file to
`_handoff/archive/YYYY/` — **archive, never delete**, with history preserved.
`--as <slug>` attributes the close commit as `<slug>:` (default `baron:`).
Status edits are textual so prose is never reflowed.

### `baron index` (M3)

Regenerates a marker-delimited summary block (`BEGIN/END BARON INDEX` HTML
comments) in `_handoff/README.md` (creating it if absent): open/done/archived
counts plus a table of open handoffs (file, for, from, age). Also verifies
finding/decision numbering: duplicates are errors (exit 1); gaps and
out-of-order headings are **report-only** warnings — baron never renumbers
history.

### `baron guard --persona-file <persona.yaml>` (M4)

Deterministic capability enforcement as a **Claude Code PreToolUse hook**
(ADR-004). Implements the documented hooks contract
(https://code.claude.com/docs/en/hooks — the canonical target of the old
docs.anthropic.com hooks URL): reads the hook JSON from stdin (`tool_name`,
`tool_input`, `cwd`), maps the call to the frozen v1 capability verbs, and
either stays silent (exit 0 — the normal permission flow applies) or blocks
(exit 2 with the reason on stderr, which the contract feeds to the model).
`--persona-file` may also come from env `BARON_PERSONA_FILE`.

What it decides:

- **Bash** — `git push` targeting the default branch → `push_main`;
  `--force`/`-f`/`--force-with-lease`/`+refspec` → `force_push`;
  `gh pr merge` → `merge_pr`; `git merge` while ON the default branch →
  `push_main`. Parsing is **conservative**: an undeterminable push target
  (e.g. bare `git push` outside a repo) is treated as the enforcement-relevant
  verb and denied for personas lacking it, with stderr naming the inference;
  personas holding the verb always pass. Non-git/gh commands pass — guard
  governs capability verbs, not general shell.
- **Edit / Write / NotebookEdit** — `_handoff/` is universally writable;
  `agents/<other-slug>/` needs `edit_other_personas` (a persona's own
  `agents/<slug>/` dir is its own surface); denied `write_path` scopes always
  block; otherwise `write_code` grants the write, and without it only the
  persona's declared `write_path` scopes remain.
- **Unknown tools** — pass (a capability gate, not an allowlist).

**Policy source (since v0.3.0):** guard's rule table — the command patterns and
file-op scoping semantics above, plus the conservative-deny ambiguity policy —
is NOT hardcoded: it lives in the versioned artifact
`src/baron/data/capability-rules.v1.yaml` (package data, loaded by
`src/baron/rules.py`; `rules_version: 1`). It is THE single source for
enforcement rules; the pydantic-ai adapter below consumes the same table, so
decisions are identical across runtimes. A missing/unsupported artifact fails
CLOSED. Prose contract:
`../skills/barony/references/capability-rules.md`.

**Fail-closed but not brick:** unreadable persona file / malformed stdin →
DENY with actionable stderr. Escape hatch: `BARON_GUARD_OVERRIDE=<reason>`
allows the call BUT appends timestamp/tool/target/reason to
`.baron/guard-override.log` — a **tracked** file (deliberately not gitignored:
overrides are visible in diffs); each override is expected to become a
`_handoff/`. Wire-up (`.claude/settings.json`, matcher
`Bash|Edit|Write|NotebookEdit`): the Claude adapter's HYDRATE.md step 3c emits
it. Without baron installed the hook fails non-blocking and denials degrade to
instructed — honest degradation, never a bricked session.

### `baron lock claim|release|list` (M5)

PR-as-lock (ADR-002 §3), replacing the race-prone markdown LOCK-commit
protocol — **the open PR is the lock**, the forge's PR list is the only state.

```bash
baron lock claim contracts/models.py --reason "tightening the stage protocol"
baron lock list
baron lock release contracts/models.py
```

`claim` creates branch `lock/<slug>` with one empty commit (via
`git commit-tree` — the local checkout is never touched; the empty commit is
load-bearing, GitHub refuses a PR whose head equals its base), opens a draft
PR titled `lock: <path>` labeled `lock:<path>` with the reason in the body,
and **refuses if an open lock PR for the path exists** (showing the holder).
`release` closes the lock PR and deletes the branch. `list` prints
path/holder/age/PR#. Requires `gh` (raises a clean `ForgeUnavailable`
otherwise); all forge calls go through the Forge Protocol, so tests run
against a fake. The CI side is the emitted
`.github/workflows/lock-guard.yml` template (bash + `gh`), which fails any
*other* PR touching a locked path.

### `baron worktree add|list|remove|prune|repair` (M6 tooling)

The branch-per-persona worktree topology (ADR-003 §2.7): one shared object
store, worktrees under the manifest's `workspace.worktrees_root`.

```bash
baron worktree add fern --collab .        # <worktrees_root>/fern on branch persona/fern
baron worktree add fern --repo ../code --root ../worktrees   # explicit paths
baron worktree list
baron worktree remove fern [--force]
baron worktree prune [--dry-run]          # clear stale registrations
baron worktree repair [<path>...]         # fix links after a move
```

`add` creates `<root>/<persona>` on branch `persona/<persona>` (created from
the default branch if missing; an existing branch is reused). Defaults resolve
from the manifest (`workspace.worktrees_root`, `repos[role=code]`); `--root` /
`--repo` override. `list` shows each worktree's branch with ahead/behind vs
the default branch. `remove` refuses while the worktree is dirty or its branch
holds unmerged commits unless `--force` — and NEVER deletes the
`persona/<persona>` branch (removing a working copy must not destroy history).

`prune` and `repair` are the *repair* pair for when a worktree directory is
moved or deleted **outside** baron (git leaves a stale entry in
`.git/worktrees/`). `prune` wraps `git worktree prune` (`--dry-run` → `-n`,
reports what would go and changes nothing) to clear registrations whose
directory is gone; `repair` wraps `git worktree repair` to re-point the admin
links after a worktree (or the main repo) was moved — pass the new path(s), or
none to repair all. Both are **non-destructive to committed work**: they only
touch `.git/worktrees/` admin state, never a branch or its history. `repair`
needs git >= 2.30; both give a clean error on an old git or a non-repo path.
The `--repo` default resolves from the manifest like the other worktree
commands.
`baron status` sweeps worktrees like clones (each reports its checked-out
HEAD's divergence; the repo-wide branch sweep runs once, on the shared repo).
Converting an existing clone-per-persona workspace:
`../docs/worktree-migration.md`.

### `baron waiver add|list` + `.baron-waivers.yaml`

Deliberately-parked `baron status` reds, with mandatory expiry.

```bash
baron waiver add "clone:rex *" --reason "kept for the vNext experiment" \
  --handoff _handoff/2026-07-23-parked-branch.md --expires 2026-08-15
baron waiver list
```

`.baron-waivers.yaml` (collab root, human-legible, baron-managed via `waiver
add`) holds `{subject, reason, handoff, expires}` entries; `subject` is an
fnmatch pattern on the status SUBJECT column. A matching, unexpired waiver
downgrades a red to warn with `(waived: <reason>)` appended — parked work
stays visible, just not alarm-red. **Expiry keeps waivers honest:** an expired
waiver stops matching (the red resurfaces) and is itself reported as an
`expired-waiver` warn; malformed entries are reported, never silently dropped.

### `baron session start|end` — session ritual primitives (optional) (ADR-007)

Thin, **opt-in** helpers that mechanize ONLY the git/markdown *bookkeeping* of
the session ritual. They do **not** run an agent, make no model calls, and have
no runtime coupling — orchestration is the runtime's job
([ADR-007](../docs/adr/ADR-007-session-boundary.md)). They are **not** new
capability verbs (the frozen 10 stay frozen); they are composable commands built
by reusing `baron status` / `baron index` / `baron handoff` / `gitutil`. Nothing
in baron requires them — interactive sessions and every command above work
unchanged.

```bash
baron session start --collab . --persona fern           # session-open brief
baron session start --collab . --persona fern --sync    # + git pull --ff-only the working copies
baron session end   --collab . --persona fern           # session-close bookkeeping
```

- **`start [--persona SLUG] [--sync] [--json]`** — session-open, read-mostly.
  With `--sync`, `git pull --ff-only` each manifest working copy (never merges,
  never force-pulls; non-fast-forwards are reported — repos with no `origin` are
  skipped). Without `--sync` no pull happens (default off — it is an honest git
  mutation). Then surfaces, for the persona (else all): OPEN handoffs addressed
  to them, the `CONVENTIONS.md`/`COORDINATION.md` pointer, and the manifest
  backlog location. Plain-text brief or `--json`. Exit 0.
- **`end [--persona SLUG] [--json]`** — session-close. Regenerates the handoff
  index (`baron index` logic); commits any dirty coordination artifacts
  (`_handoff/`, `findings/`, `decisions/`, `wiki/`) — staged **by path, never
  `git add -A`** — with the persona's `commit_prefix` when `--persona` resolves
  one (the same attribution `baron handoff close --as` uses), else `baron:`;
  skips cleanly when nothing is outstanding; then prints a `baron status`
  summary. Exit 0 green / 1 if status finds red (CI-usable).

**Three composition points** (the boundary is the same in all three — bookkeeping
only): a **human** runs them between turns; a **driver/CI** wraps them around a
headless run; a **runtime adapter** may expose them as a capability/hook (a
pydantic-ai capability, a Claude Code session hook, a cron driver). Barony ships
only the runtime-neutral CLI — those wrappers are build-on-demand, not shipped.

### `baron hydrate pydantic-ai --persona-file F [--out agent_setup.py]`

Emit a ready-to-edit bootstrap script hydrating one persona onto
**pydantic-ai** (the fourth runtime adapter,
`../skills/barony/assets/collab-repo/adapters/pydantic-ai/HYDRATE.md`).

```bash
baron hydrate pydantic-ai --persona-file agents/fern/persona.yaml --out agent_setup.py
```

The emitted script imports `baron.runtimes.pydantic_ai.build_agent` and
carries a model placeholder (`"test"` — pydantic-ai's offline TestModel —
until you pick a real model). Emission needs only baron; **running** it needs
the optional extra:

```bash
pip install 'barony[pydantic-ai]'   # pins pydantic-ai-harness>=0.10,<0.11
                                       #      + pydantic-ai-slim>=2.14.1,<3
```

`build_agent(persona_file, collab_root=None, model=...)` returns a live
`pydantic_ai.Agent`: instructions composed from the persona spec; harness
`FileSystem` scoped per write verbs (natively read-only when the persona holds
no write verb); harness `Shell` only when a shell-granting verb is allowed
(with test runners denied when `run_tests` is denied); and an in-process guard
capability (`before_tool_execute` + `ModelRetry` veto — the documented
interception seam) consuming the same `capability-rules.v1.yaml` as
`baron guard`, which makes the five guard-covered sub-tool denials natively
**enforced** on this runtime. Without the extra, importing
`baron.runtimes.pydantic_ai` raises a clean ImportError with these install
instructions. Verified against pydantic-ai-harness 0.10.0 +
pydantic-ai-slim 2.16.0 (2026-07-23).

## Forges

`src/baron/forge/` holds a small `Protocol` (`base.py`) with one built-in
implementation, GitHub via `gh` subprocess (`github.py`) — first consumed by
`baron lock` (M5: `create_branch`, label-aware `open_pr`/`list_open_prs`,
`close_pr`). Other forges are plugins discovered through the `baron.forges`
entry-point group; GitLab is backlog — design sketch in `../docs/BACKLOG.md`.

## Development

```bash
uv run --project cli pytest cli/tests    # from the repo root
```

The suite includes the capability-vocabulary drift guard, the ritual-token
cross-renderer guard (every `RITUAL_TOKENS` entry must render real prose in BOTH
code renderers — the `baron init` kits and the pydantic-ai hydrator; the three
adapters' `HYDRATE.md` prose surfaces stay ungated, see `../docs/BACKLOG.md`), a
synthetic divergent git topology reproducing the 2026-07-22 triple-stranding
incident classes, the ledger push-rejection race test, subprocess-driven guard
hook tests (synthetic PreToolUse JSON on stdin), a recorded fake forge for the
lock lifecycle, a real two-persona worktree fixture, the waiver
downgrade/expiry cases, the
capability-rules artifact tests (packaged + versioned, verb set ≡ the frozen
vocabulary, guard-consumes-the-data mutation test), and the pydantic-ai
adapter tests (offline TestModel/FunctionModel: capability omission, write
scoping, a scripted-and-vetoed `git push origin main`, the clean import-error
path), the `baron init` acceptance tests (layout + self-validation via the real
schemas + runtime kits + the non-empty-dir refusal), and the template drift
guard (`test_template_sync.py`: the vendored `src/baron/data/templates/` must
stay byte-identical to `skills/barony/assets/collab-repo/` — re-vendor with
`python cli/scripts/sync_templates.py`). The dev dependency group repeats the
pydantic-ai extra's pins so those tests run for real.
