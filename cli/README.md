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

cp -R agents/fern/runtime/.claude ../gardenkit/   # install the guard hook
baron doctor --dir ../gardenkit                   # prove it — exit 1 if it is missing
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
`--wake-allowed <slug>,...`, `--no-git`. Refuses a non-empty target directory,
and a `--code-repo` that aliases the collab repo — whether it resolves to the
collab repo itself, to a path inside it, or to an ancestor of it (which would
nest the collab repo in its own project's code repo).

`manifest.yaml` always carries a `notify:` block, empty unless `--wake-allowed`
names personas. Empty still means **nobody may wake** — ADR-010 §5.5's
fail-closed contract is unchanged — but absent and empty are not the same thing
to a reader: absent is invisible, and a project whose wakes silently never fire
gives you nothing to search for. `--wake-allowed` is the one-flag way to scaffold
a working wake loop, and it rejects a slug that is not a persona of this project
(the gate matches the handoff's `from:`, so an unknown name could never fire).

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

Beside each kit, init emits the persona's **sidecar** —
`agents/<slug>/sidecar.sh`, executable (ADR-026). The kit is what the persona
*is*; the sidecar is how it is *deployed*: a thin launcher over
`baron sidecar run` whose only project-owned part is the runtime invocation
(pre-filled for `--runtime claude`, an empty fill-me slot elsewhere, always
overridable with `$BARON_SIDECAR_CMD`). Its header renders the persona's
`runtime.trigger`, which decides the loop form.

The scaffold must pass `baron validate` with zero errors before init reports
success; then `git init -b main` + a first commit of exactly the files written
(never `git add -A`), unless `--no-git`. Dates come from the injectable clock.
Persona scope prose, `AGENT.md` manuals, and Tier-3 hydration (Claude
subagents, code-puppy JSON agents) stay on the conversational path — init
prints the pointers instead of pretending.

### `baron init --layout monorepo` + `baron add-project <name>` ([ADR-025](../docs/adr/ADR-025-coordination-monorepo.md))

`--layout repo` (the default) is everything above: one collab repo for this
project, which is what buys multi-tenant isolation and an independent lifecycle.
`--layout monorepo` emits the other topology — **one collab repo whose projects
are subdirs** — for a single owner running a portfolio of fleets.

```bash
baron init fleet-coordination --layout monorepo    # root + the `_meta` project
cd fleet-coordination
baron add-project gardenkit --code-repo ../gardenkit --personas dev:fern,librarian:iris
```

```
fleet-coordination/
  .baron-monorepo.yaml     # the root marker + the project registry
  .github/workflows/       # CI owned ONCE (baron-notify routes by project)
  _meta/                   # the portfolio project — no code repo
  gardenkit/               # a project — manifest.yaml agents/ _handoff/ ...
```

`init --layout monorepo` flags add `--first-project` (default `_meta`); `--dir`,
`--personas`, `--runtime` and `--no-git` behave as above and apply to that first
project. **`baron add-project <name>`** grafts a further subdir into an existing
root: `--root` (default `.`), `--project-name` (when the project name must differ
from the subdir), `--code-repo`, `--personas`, `--runtime`, `--wake-allowed`,
`--no-git`. It reuses `init`'s emitters verbatim and refuses cleanly on a
non-monorepo directory, a duplicate, or anything that is not a plain subdir name.
The subdir gets **no `.github/` and no git repo of its own** — both belong to the
root, which is where both commands commit. If a project subdir does carry a
`.github/` (an adopted repo brings one), both commands **warn that it is inert**:
GitHub runs workflows from the repository root only, so a nested one fires never
while reading like working CI.

**`--code-repo` is resolved against the SUBDIR, and refuses to alias the
coordination repo.** A code repo is a separate repo, so it may not be the
monorepo root, live inside it, or contain it — `baron` errors instead of writing
a `repos[].path` that resolves back inside. This matters most for a git URL,
which names no local path: baron assumes the conventional sibling clone, and in a
monorepo the sibling is `../../<name>`, one level further up than in a standalone
collab repo. (The 2026-08-14 dogfood emitted `../<name>`, which pointed at the
project subdir itself; every path existed, so `baron status` reported the code
repo green with nothing cloned.)

### `baron adopt-project <subdir>` — the migration path

`add-project` scaffolds, and refuses a non-empty target — so an existing collab
repo, with its own history, personas and ledgers, had no way into a monorepo.
`adopt-project` registers one that is **already a subdir here**:

```bash
cd fleet-coordination
git subtree add --prefix=gardenkit git@github.com:you/gardenkit-collab.git main
baron adopt-project gardenkit
```

Placing the directory stays git's job — `git subtree add` keeps its history, a
plain `mv` is right when history does not matter, and baron will not guess which
you meant nor re-implement either. It picks up where git leaves off: verify the
subdir is a collab repo, read its project name from its own manifest (never
rewrite it), register it in the marker, re-render the root README, and commit.
Flags: `--root`, `--project-name` (refused if it contradicts the manifest's
`project.name`), `--no-git`. It refuses a subdir that is still its own git repo,
one with no `manifest.yaml`, a duplicate, and a path rather than a plain name.

Two things it deliberately does not do: delete the adopted `.github/` (reported
inert — removing another repo's CI is not a side effect of registering it) and
re-base its `repos[].path`. The collab root moved one level deeper, so a code
repo recorded at `../x` is now at `../../x`; the command's next-steps output says
so, and `baron status` reports it red until you fix it.

Run at the root, `baron status` and `baron health` go **portfolio-wide** (per
project, then a total; `--json` gains `layout`/`projects`/`summary`) and
`baron validate .` names the projects covered and warns on a manifest-carrying
subdir the marker does not list. Run inside a project — monorepo subdir or
standalone collab repo — every command behaves exactly as it always has.

`baron notify` inside a subdir adds `project` to the `repository_dispatch`
payload and does its git work at the root; the root's `baron-notify.yml`
validates that project against the registry and `cd`s into it before resolving
the handoff. Authorization is unchanged — the committed handoff `from:`, never
the payload.

Two shapes worth knowing: the project name is separate from the subdir name
(`_meta`'s project is `meta`, because that name becomes the identity domain
`<slug>@<project>.local`), and a project's `workspace.worktrees_root` resolves to
`../../<project>-worktrees` so worktrees stay a sibling of the monorepo.

**What it costs:** access is all-or-nothing — a monorepo cannot grant per-project
access. That is why this is a mode and not a replacement.

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
(warnings allowed) / 1 = any red (CI-usable). At a coordination-monorepo root
this goes portfolio-wide — see `baron add-project` above.

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

### `baron adr check|scaffold` — the prior-art gate ([ADR-029](../docs/adr/ADR-029-prior-art-gate.md))

```bash
baron adr check docs/adr                        # the gate — exit 1 blocks
baron adr check docs/adr --require repo-adr     # a project with no research vault
baron adr check docs/adr --since 1970-01-01     # audit the WHOLE corpus, not just new records
baron adr scaffold                              # print the section to paste into a new ADR
```

**Fail-closed, not a lint.** An ADR marked `status: accepted` must carry a populated
prior-art block; a missing, malformed, or incomplete one exits **1**. Wire it into CI —
this repo does (`.github/workflows/ci.yml`).

```markdown
## Supersedes / Prior art

<!-- BEGIN BARON PRIOR-ART -->
searched:
  - corpus: repo-adr          # closed vocabulary: repo-adr | repo-decisions | vault | external
    location: docs/adr
    query: "identity, spawn credentials"
    date: 2026-08-14
  - corpus: vault
    location: /Users/vikram/Obsidian/Brain
    query: "agent identity spike"
    date: 2026-08-14
hits: []                      # `[]` means "found nothing" — say it; an omitted key is an ERROR
<!-- END BARON PRIOR-ART -->
```

Each hit carries `ref` plus a `disposition` of `supersedes` / `cites` / `distinct`, and
`distinct` **must** carry a `note` — it is the only disposition that discharges a hit by
assertion. Errors: block missing, block malformed (unclosed marker or bad YAML — *never*
silently rewritten, ADR-003 §2.6), `searched:` empty, an entry missing a known `corpus` /
`query` / ISO `date`, a **required corpus not searched** (default `repo-adr` **and**
`vault`), `hits:` omitted, or a malformed hit. Warnings (do not block): a sweep dated >90
days before acceptance, a block with no prior-art heading, a `supersedes` ref naming an ADR
absent from the directory (legitimate for the reserved-but-unmerged numbers).

**Retrofit.** Only ADRs dated on/after **2026-08-14** are gated; earlier records report
`exempt` — never as *passing* — because failing 26 legacy records on day one is how a gate
teaches people to ignore it (the ADR-009 §10 Q4 call, reapplied).

> **Honest bound.** This enforces that a search was **recorded**, not that it was
> **thorough**. Recall quality is a separate axis (the memory work, AGENT-TASKS P3.3/P3.4).
> It converts *"I forgot to check"* from silent into blocked; it cannot tell you the
> searcher found everything, and a determined author can record a sweep they never ran.

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

### `baron identity init|show|sign` + `baron verify identity` ([ADR-027](../docs/adr/ADR-027-agent-identity.md))

```bash
baron identity init --persona carson       # at spawn — exits 1 until enrolled
baron identity show                        # who is enrolled in this repo
baron handoff sign _handoff/2026-08-14-1200-carson-note.md
baron handoff verify --record-finding      # the librarian's ingest gate
baron verify identity --base origin/main --head HEAD --label agent-carson   # the CI gate
```

Per-persona **SSH signing keys**, generated at spawn, enrolled once into
`.barony/allowed_signers` (a file **in the repo** — a clone is sufficient to verify
anything, offline, forever), verified with `git verify-commit`.

`identity init` generates `~/.barony/keys/<slug>.key` if absent (`$BARON_KEY_DIR`
overrides), configures **repo-local** git (`gpg.format=ssh`, `commit.gpgsign`,
`tag.gpgsign`, the in-repo allowed-signers file, and a distinct
`<slug>@agents.barony.invalid` author email), writes an enrollment **request** into
`.barony/allowed_signers`, and **exits non-zero until that request is merged at HEAD**.
The agent cannot merge it — `.github/CODEOWNERS` is owner-only — and that one human
merge is the trust root. Identity precedes work.

`verify identity` walks `BASE..HEAD` and, per commit, checks the signature against the
in-repo allowlist, that git's trust status is `G`, and the **three-way cross-check**:
signer principal ↔ the persona the commit claims (a `Barony-Persona:` trailer and/or the
PR's `agent-<slug>` routing label, checked independently) ↔ an `agents/<slug>/persona.yaml`
registry entry. Fail-closed. `baron init` emits it as `verify-identity.yml`; **make it a
required status check**, and use squash/merge commits — *rebase-merge* adds head-branch
commits to the base without signature verification.

Handoffs and findings get detached signatures (`ssh-keygen -Y sign` → `<file>.sig`).
`baron handoff verify` and `baron handoff close` refuse an artifact whose signature does
not verify and **record the refusal as a finding** — an attribution failure is evidence,
not something to drop silently. A *missing* signature only warns by default
(ADR-027 §7.3); `--require-signature` makes it a refusal.

**Agents still push under the owner's forge identity.** There are no per-persona tokens,
machine accounts or GitHub Apps anywhere in this — attribution comes from the **key**, and
GitHub allows unlimited signing keys per account. Owner setup:
[`docs/runbooks/identity-signing.md`](../docs/runbooks/identity-signing.md).

**Honest bound:** this establishes attribution among **cooperating** agents. Private keys
sit unencrypted in each agent's workspace, so it does **not** defend against a hostile
actor with write access there — the same bound as `baron guard`.

### `baron index` (M3)

Regenerates a marker-delimited summary block (`BEGIN/END BARON INDEX` HTML
comments) in `_handoff/README.md` (creating it if absent): open/done/archived
counts plus a table of open handoffs (file, for, from, age). Also verifies
finding/decision numbering: duplicates are errors (exit 1); gaps and
out-of-order headings are **report-only** warnings — baron never renumbers
history.

### `baron export [--wide] [--kind K]... [--note-dir D]... [--json]` (P3.4 partial, [ADR-015](../docs/adr/ADR-015-baron-export.md) + [ADR-032](../docs/adr/ADR-032-export-reach-monorepo-and-widened-corpus.md))

The governed corpus as **citable records** — one flat record per artifact, walked
from the same markdown the personas write. **Four kinds by default** — the `adr`,
`decision`, `finding` and `handoff` ledgers. **`--wide` adds two more**: `status`
(`wiki/status.md`, `STATUS.md`) and `note` (`wiki/`, `docs/notes/`), which ADR-032
added after P3.3 measured retrieval and found the binding constraint was
**coverage, not ranking**. They are opt-in rather than default because widening
the corpus moves the record set under every existing consumer (ADR-032 §3.1,
amended); `--kind` selects any of the six explicitly.

```bash
baron export                                                    # table
baron export --json | jq '.records[] | select(.kind=="decision")'
baron export --wide --json                                      # + status and note
baron export --kind adr --kind decision --json                  # subset
baron export --kind note --note-dir research --json             # retarget the note walk
baron export --json | jq -r '.records[] | "\(.id)\t\(.commit_sha)\t\(.path)"'
```

```json
{ "id": "D57", "kind": "decision", "title": "RATIFIED: …",
  "path": "decisions/index.md", "commit_sha": "6bccfba7…", "status": null,
  "body": "**Owner decision (Vikram), ratified 2026-07-31…",
  "links": [{"type": "ref", "target": "ADR-0011"}, {"type": "ref", "target": "D56"}],
  "meta": {"form": "heading"}, "project": "barony" }
```

Nine core fields (`id, kind, title, path, commit_sha, status, body, links,
project`) plus an open, kind-specific `meta`. Primary key is
**`(project, kind, id)`** — two projects in one monorepo legitimately both hold an
`ADR-001`. `path` is **repo-root-relative** so the citation below pastes verbatim;
the envelope's `repo_prefix` recovers the `--collab`-relative form when they differ.

**Run it at a coordination-monorepo root** ([ADR-025](../docs/adr/ADR-025-coordination-monorepo.md))
and it walks every registered project subdir and aggregates — `layout: "monorepo"`,
per-project counts in `projects[]`, each record tagged with its `project`, and
subdirs the marker does not list reported in `unregistered[]` rather than silently
swept in. The record shape is identical in both layouts, so `jq '.records[]'` does
not care which topology produced the payload. Before ADR-032 a root-level run
walked nothing and reported **0 records** while the per-project runs returned real
counts — the same silent-false-zero class as the ADR-025 §6.8 health bug.

**Every record cites a commit that reproduces it.** A source file that is
untracked or has uncommitted edits is **skipped and named** in `skipped[]` — never
emitted with a SHA that resolves but returns different text. So
`git show <commit_sha>:<path>` always returns the exact bytes the record was
parsed from. `--allow-dirty` relaxes that for **modified tracked** sources only,
stamping `meta.dirty` on the affected records; untracked sources stay skipped
under every flag, because `commit_sha` is never empty and a file with no commit
has nothing to cite.

Both real ledger entry-forms parse (`### F40 — title (date, author)` blocks and
bare `| F40 | title |` index rows; the heading wins for the same ID). `status` is
**null for findings and decisions** — the canon gives ledgers no lifecycle field,
and guessing one from prose would be an overclaim. Output is byte-stable across
runs (`age_days` is deliberately dropped). Archived handoffs are **included** by
default (`--no-archived` to drop them) — unlike `baron handoff list`, this is the
history, not the work queue. `--adr-dir` retargets the ADR walk (default
`docs/adr`); ADRs kept in the *code* repo are out of reach for now.

There is **no knowledge backend, no plugin group, and no vendor dependency** here,
and that is deliberate — see [ADR-015](../docs/adr/ADR-015-baron-export.md) §4 for
the sequencing argument and the open owner decision. Exit 0; exit 2 if the collab
path is not a git repo with history (there is no provenance-free mode).

### `baron memeval --fixtures <dir> [--k N] [--approach A]... [--json]` (P3.3, [ADR-031](../docs/adr/ADR-031-governed-memory-eval-harness.md))

The governed-memory evaluation harness — the gate P3.4 has to pass. It
materializes a labeled fixture corpus into a throwaway git repo, walks it with
the same `baron export` producer above, and scores each approach on the metrics
AGENT-TASKS.md 3.3 names.

```bash
baron memeval --fixtures evals/governed-memory
baron memeval --fixtures evals/governed-memory --approach git-markdown --json | jq '.approaches[0].retrieval.per_query'
```

```
corpus  22 citable record(s) at a034318b (adr=6, decision=6, finding=5, handoff=5)
        skipped _handoff/2026-08-13-1700-tess-uncited-draft.md: uncommitted (1 record(s) not citable)
        retrieval ceiling 84.4% — the share of gold answers any strategy could reach

approach          prec   rec   dup schema  path  stat   R@5   MRR fresh  cite   tax
git-markdown      66.7  75.0  50.0    0.0 100.0  50.0  76.0  81.2 100.0 100.0  33.3
hooks            100.0 100.0 100.0  100.0 100.0 100.0  76.0  81.2 100.0 100.0   6.7
semantic         NOT MEASURED — no 'semantic' retriever is registered ...
hooks+semantic   NOT MEASURED — no 'semantic' retriever is registered ...
```

Columns, in order: propagation precision and recall, duplicate suppression,
schema / path / status accuracy of the emitted note, Recall@k, MRR, freshness
(does the *superseding* record outrank the superseded one), source-citation
accuracy (`git show <sha>:<path>` resolves and reproduces), and human
intervention tax (lower is better — the share of events a human has to touch).
A metric with an empty denominator reports `n/a`, never a silent `0`.

**It measures fixtures, not a live repository.** The bound is printed on the
table and carried in the JSON as `honesty_bound`, so quoting the output cannot
drop it. The fixture set — including the flagship 2026-08-04 identity case and
the three fixtures that price the citation gate — is documented in
[`evals/governed-memory/README.md`](../evals/governed-memory/README.md), and the
limits of the `hooks` row (its rule table encodes the same policy the gold labels
do) in [ADR-031](../docs/adr/ADR-031-governed-memory-eval-harness.md) §4.

The two semantic approaches are **declared and unmeasured** — the seam is an
in-process dict (`memeval.RETRIEVERS` / `register_retriever`), deliberately not
an entry-point group, and this command estimates nothing it did not measure. No
backend, no vendor, no new dependency ships with it; `cli/tests/test_memeval.py`
asserts all four. Exit 0; exit 2 if the fixture set cannot be loaded or built.

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
  **Shell wrappers (ADR-034):** guard recurses **one level** into
  `bash -c '<payload>'` (also `sh`/`zsh`/`dash`/`ksh`, optionally behind `env`)
  and re-runs the same evaluators over the payload, so a wrapped `git push
  origin main` is adjudicated. A payload that cannot be tokenised, or one nested
  past the cap, is ambiguous → conservative-deny **narrowed to `merge_pr`,
  `push_main`, `force_push`**. Still uninspected, on purpose: `python -c` and
  other interpreters, `eval`, base64/`printf` indirection, script files,
  `xargs`, raw forge API calls. See the bound below.
- **Edit / Write / NotebookEdit** — **the enforcement configuration is refused
  first, structurally (L0, ADR-034)**: no verb unlocks it and every persona gets
  the same answer. Fenced are every `agents/*/persona.yaml` (own included, and
  including for a holder of `edit_other_personas`), the acting persona's own
  `agents/<slug>/**`, and `.claude/settings.json{,.local}`,
  `.baron-waivers.yaml`, `.baron-rules.yaml`, `.barony/allowed_signers` (matched
  on trailing path components, so the copy inside an emitted runtime kit counts
  too). **Changing a capability set is a PR a human merges — always, including
  solo.** After that: `_handoff/` is universally writable;
  `agents/<other-slug>/` needs `edit_other_personas` for its *non-capability*
  files; denied `write_path` scopes always block; otherwise `write_code` grants
  the write, and without it only the persona's declared `write_path` scopes
  remain.
- **Unknown tools** — pass (a capability gate, not an allowlist).

> **The honest bound, unchanged by any of the above.** L0 governs guard's own
> write-tool seams, not the filesystem: `~/.claude/settings.json` is outside the
> repo root and invisible to guard and to doctor, and a shell redirect
> (`echo … > .claude/settings.json`) is neither a write-tool call nor a
> capability verb. Both are pinned by tests rather than only written down. This
> is **a deterministic policy guard at the agent-tool interface for cooperating
> agents, not a security boundary.** Where the boundary must hold against an
> adversary, use OS-level isolation.

**Policy source (since v0.3.0):** guard's rule table — the command patterns and
file-op scoping semantics above, plus the conservative-deny ambiguity policy —
is NOT hardcoded: it lives in the versioned artifact
`src/baron/data/capability-rules.v1.yaml` (package data, loaded by
`src/baron/rules.py`; `rules_version: 2`). It is THE single source for
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

### `baron rules list|validate|diff|explain` (ADR-016)

The read-only diagnostic surface over the capability-rules artifact. Nothing
here changes enforcement; it makes enforcement *inspectable* instead of
requiring you to read YAML by hand.

```bash
baron rules list                      # the verb table: class, detection, enforcement, label
baron rules list --json               # same, machine-readable
baron rules validate                  # negotiation + integrity checks on the packaged artifact
baron rules validate --file r.yaml    # ...on a candidate document (see the caveat below)
baron rules diff --file r.yaml        # join a candidate against the packaged artifact on rule id
baron rules explain 'git push --force origin main' --persona-file agents/dev/persona.yaml
baron rules explain agents/other/persona.yaml --write --persona-file agents/dev/persona.yaml
```

- **`list`** reports enforcement in **three** states, but only one of them is
  `enforced`: `guard` (guard mechanically checks it → `enforced`),
  `adapter-dependent` (guard does NOT parse for it; a runtime with a tool
  allow-list *could* enforce it by omitting the tool, but **baron emits no such
  mechanism** → `instructed`), `instructed` (nothing checks it — `open_pr`,
  `run_tests`). `read_code` / `read_collab` are the `adapter-dependent` pair,
  measured once per shipped adapter (ADR-020): the pydantic-ai adapter builds
  `FileSystem` unconditionally, so a persona denying `read_code` still gets the
  read tools (`test_denying_read_code_does_not_omit_read_tools`), and the
  `claude`, `code-puppy` and `generic` kits emit nothing a runtime reads as a
  tool allow/deny list (`test_adapter_omission.py`). The bound is exact — baron
  emits no mechanism, **not** that a runtime cannot enforce these verbs: a
  hand-written `permissions.deny`, or the Tier-3 subagent the HYDRATE.md recipes
  describe, does. `--json` carries the qualifier in the payload (`label_caveat`,
  plus `caveat` per affected verb), not just the table footer.
- **`validate`** exits 0 clean, 1 if a check fails, **2 if the document is
  refused outright** — unreadable, not YAML, unknown `rules_version` or
  `vocabulary`, a rule or key this baron does not implement, an unknown matcher
  (or one other than the matcher guard implements for that rule), a missing
  built-in rule, **an unknown `class` or `detection` value, or a `detection`
  that misdescribes what guard implements** (claiming `command` with no rule
  behind it, or `none` where a rule does bind the verb). That refusal is the
  same one guard turns into a fail-closed DENY. Unrecognised content is never
  dropped silently — and that includes values, not just keys.
- **`diff`** exits 0 identical / 1 differs / 2 refused. It joins on **rule id
  and verb id**: `rules_changed` for a rule body, `verbs_changed` for a verb
  entry (`class` / `detection` / `notes`), with the resulting
  enforcement/label change spelled out inline. A candidate carrying a rule this
  baron does not implement is **refused**, not reported as an addition — so
  `identical` can never be printed over content that was discarded.
  *Honest limit:* `rules_added` / `rules_removed` cannot fire from a document
  (the built-in rule set is closed and every slot mandatory); they exist for the
  deferred loader. See ADR-016 §7.
- **`explain`** is a **dry run of the real decision**: it calls
  `guard.evaluate_bash` / `guard.evaluate_write`, not a reimplementation, and a
  test pins its verdict to the evaluator's `Decision` so the two cannot drift.
  Exit 0 would-pass / 1 would-be-DENIED / 2 guard could not evaluate. Honest
  limit: it lists the rules that *can* imply each verb, not the single rule
  instance that matched — guard's own `reason` names the concrete inference.

> **`--file` validates; it does not activate.** baron loads the **packaged**
> artifact only. There is no `.baron/rules.yaml` discovery, no merge, no
> precedence — ADR-016 §5 records why the project-level loader is deferred and
> which one-way doors it has to settle first (add-only/deny-only, never new
> verbs, explicit supported ranges on both artifacts, refuse-don't-ignore on a
> malformed file, cache safety, and the `.baron/` vs root-level convention).

**Representation (ADR-016 §3):** the parsed rules are a *list* of typed rules
(`CommandRule` / `PathRule`, each with a stable `id`, a `matcher` from a closed
set, a `verb`, and a `source`), not a flat field-per-rule record — that is what
makes an additional rule representable at all. Every name `guard.py` grew up
with survives as a derived property, and `guard.py` is byte-identical across the
change.
### `baron doctor [--dir .] [--persona-file F] [--json]` (ADR-017)

The guard **wiring** self-test — and the answer to the badminton-analyzer
incident, where 15 PRs were merged by a persona denied `merge_pr` because the
hook had never been installed. Nothing failed; enforcement had degraded to
persona text, silently. Doctor breaks that silence and **exits 1 on any FAIL**.

Ten checks, each with a remedy line when it fails:

| id | proves |
|---|---|
| `cli-on-path` | the executable the hook names resolves and `--version` runs (wrapper prefixes like `uv run` are resolved as the launcher) |
| `hook-configured` | project `.claude/settings.json` wires a PreToolUse hook invoking `baron guard` |
| `hook-matcher` | that matcher selects every governed tool (`Bash`, `Edit`, `Write`, `NotebookEdit`) |
| `persona-file` | the persona the hook names exists and parses |
| `rules-artifact` | `capability-rules.v1.yaml` loads at a supported `rules_version` |
| `enforcement-path` | a synthetic denial fed to **the executable the hook names** really returns exit 2 |
| `fail-closed` | malformed hook stdin also returns exit 2 (ADR-004 §2.3), same executable |
| `override-env` | `BARON_GUARD_OVERRIDE` is not sitting exported (if it is, every denial is allowed) |
| `override-log` | the evidence sink is writable and not gitignored — **INFO only, never FAIL** |
| `platform-layer` | (ADR-034 §4.5) whether branch protection is on and whether each persona has its own push credential — the layer that could actually make an irreversible action impossible, and **not baron's**. **INFO only**, reported and never configured (ADR-007). The branch-protection half is doctor's only networked check and is opt-in behind `BARON_DOCTOR_PLATFORM=1`, so a green run stays reproducible offline |

```
$ baron doctor
baron doctor — guard WIRING self-test
project dir: /path/to/collab
guard probe:  subprocess — /usr/local/bin/baron guard

PASS    cli-on-path       baron -> /usr/local/bin/baron — barony 0.8.0 (named by the hook command)
FAIL    hook-configured   no `baron guard` PreToolUse hook in this project (no project settings file). Capability denials here are INSTRUCTED, not enforced.
                          -> `baron init` generated the wiring at agents/carson/runtime/.claude/settings.json but nothing copied it into place — ... Copy the runtime kit: cp -R .../runtime/. . (see adapters/claude/HYDRATE.md).
...
-- 5 pass, 1 fail, 2 unknown, 1 info
```

**Honesty boundary — printed on every run, green included.** Doctor verifies
WIRING, not invocation. It proves this install *can* enforce; it cannot observe
whether Claude Code actually ran the hook on a real tool call, because nothing
outside the runtime can. Read a green doctor as "correctly wired", never as
"enforcement happened" — implying otherwise would manufacture the exact false
confidence that produced the badminton merges.

**Two further bounds, also printed.** (a) Checks 6–7 spawn the hook's *own*
command — `<exe> guard --persona-file <synthetic probe>`, `uv run`-style prefixes
included — rather than calling the `baron` package doctor imported. A project
wired to a stale or hand-rolled `baron` is exactly the badminton shape and an
in-process probe cannot see it. Where the hook names no resolvable executable,
doctor falls back in-process and the detail says so: that PASS is about the
library, not about the command the hook would run (`probe_mode` in `--json`).
(b) A *bare* executable name is resolved with `shutil.which` against **doctor's**
PATH, not the runtime's, so `cli-on-path` for that shape is a property of the
invoking shell. An absolute path in the hook command removes the ambiguity.

Two scope notes, both deliberate (ADR-017 §3.4–§3.5): the override-log check is
**INFO whatever it finds**, because enforcement is fail-closed while evidence is
fail-open, and a broken audit trail must never be reported as broken
enforcement; and only **project-level** settings are inspected, so a hook wired
in the machine-global `~/.claude/settings.json` reads as a FAIL (the remedy says
so). Checking the home directory would make the verdict depend on the developer's
machine rather than on the repo. Read-only and fully offline — the only write is
a temp dir for the synthetic probe.

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

### `baron merge check <pr>` — the merger's gate, mechanized ([ADR-028](../docs/adr/ADR-028-mechanized-merge-gate.md))

The `__MERGER__` persona is specified as *a gate, not a button*. This makes the
checkable half of that gate a **fail-closed return value** instead of prose the
model can talk itself past (FM4: a persona merged ~15 PRs with `merge_pr` denied
in its own config).

```bash
baron merge check 128 --repo example-org/gardenkit    # exit 0 = allowed, 1 = REFUSE
baron merge check 128 --json                          # code repo from manifest.yaml
```

Four preconditions, in order, scored against **one** PR snapshot (so the verdict's
sha, the labels and the checks all describe the same observed head):

| # | Precondition | Passes when |
|---|---|---|
| 1 | `pr_open` | OPEN, not a draft, head resolves to a full 40-hex sha |
| 2 | `verdict_at_head` | a `REVIEW:PASS <sha>` comment exists whose sha **equals the current head** |
| 3 | `no_changes_requested` | no `REVIEW:FAIL` at the head, no platform changes-requested |
| 4 | `ci_green` | every check on the head sha succeeded, and at least one actually ran |

```
=== merge gate — example-org/gardenkit#128 @ 3f9c1a2b4d6e ===
  PASS  pr_open                open, not a draft, head sha resolved
  FAIL  verdict_at_head        newest verdict is REVIEW:PASS 8ab21c04f7d9 but the head is
                               now 3f9c1a2b4d6e — the head moved since review...
  FAIL  no_changes_requested   not evaluated — ...; fail-closed
  FAIL  ci_green               not evaluated — ...; fail-closed
  ----  labels IGNORED by design (index, not record): reviewed-approved
VERDICT: REFUSE — verdict_at_head [stale_verdict]: ...
```

**Fail-closed, everywhere.** Missing verdict, stale sha, abbreviated sha (never
prefix-matched — two commits can share a prefix), red CI, **pending** CI, **absent**
CI, an unrecognized check state, an open `REVIEW:FAIL`, a missing `gh` — each is a
refusal with a stable reason slug. Preconditions that could not be reached are
reported FAILED, not skipped. Unlike `baron decision check`'s three states, there is
no amber: a merge is an action, and for an action amber is red.

**Labels are an input to nothing** (ADR-008 §1) — collected and printed as *ignored*
in both directions: an approval label cannot rescue a stale verdict, and a
`changes-requested` label cannot block a clean head.

**It never merges, and there is no `baron merge do`** (ADR-007). Under one shared forge
account baron cannot attest *who* posted a verdict — the dev could post its own
`REVIEW:PASS` — so merging stays owner-in-the-loop until per-persona forge identity
(ADR-027) is deployed; `--verdict-author <login>` then pins the reviewer. Preconditions
3 and 4 of the persona's four (record obligations, hot-file collisions) are **not**
covered here and stay the merger's own; exit 0 means "1 and 2 hold", not "merge it".

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

### `baron sidecar run <persona>` — the persona as a deployable unit (ADR-026)

One **cycle** of a persona's work loop: sync → sweep → invoke → land. It is the
generalised, emitted form of a hand-written fleet runner, and it composes the
primitives above rather than adding machinery — `session start --sync` for the
sync + sweep, `session end` for the bookkeeping commit.

```bash
baron sidecar run fern --collab . --dry-run          # plan + the brief, nothing else
baron sidecar run fern --collab . --cmd "claude -p"  # one cycle
baron sidecar run iris --collab . --watch --interval 900   # long-running (cron/event triggers)
```

1. **sync** — `git pull --ff-only` every manifest working copy.
2. **sweep** — open `_handoff/` items addressed to this persona (or `all`) plus
   unchecked backlog lines carrying its routing label (parked items excluded per
   `backlog.park_label`). Nothing addressed and nothing labelled = **idle**: the
   runtime is never invoked (`--force` overrides). A tracker-backed backlog is
   the runtime's to read, and the report says so.
3. **invoke** — run the runtime command **once**, with a work brief on stdin
   (also at `$BARON_SIDECAR_BRIEF`; `{brief_file}` in the command is replaced by
   that path). The brief puts LIVE review feedback ahead of new work — the
   session-ritual ordering ADR-008 made load-bearing.
4. **land** — `session end` bookkeeping, then a plain `git push` of the collab
   repo. No force, no retry: a rejected push is a decision, not a race.

**The command is yours.** `--cmd` / `$BARON_SIDECAR_CMD` / the emitted
`sidecar.sh` supply it; a cycle without one is a usage error, never a default.
baron syncs, sweeps, commits and pushes — it does not own the agent loop
([ADR-007](../docs/adr/ADR-007-session-boundary.md)).

Flags: `--collab`, `--cmd`, `--trigger interactive|event|cron` (override the
persona spec), `--watch` + `--interval` + `--max-cycles`, `--timeout`,
`--force`, `--no-push`, `--dry-run`, `--json`. Exit 0 green / 1 if the runtime
failed / 2 on usage. `runtime.trigger` decides the loop form (ADR-026 §6 Q2):
`interactive` is one-shot by hand and **refuses `--watch`** (that loop is the
human's session), `event` is one-shot spawned by the wake
(`baron notify` → `baron-notify.yml`), `cron` is scheduler-driven and may watch.
A watching sidecar stays **stateless per task** — every cycle re-reads git as
truth, which is what keeps audit-by-diff true (ADR-026 §4).

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

## Events and sinks (ADR-013)

`src/baron/events.py` defines one `Event` shape covering guard verdicts, session
boundaries, ledger writes, decisions and tool outcomes; `src/baron/sinks/` defines
where they go. **The default is `null` — baron writes nothing unless you ask.**

```bash
BARON_EVENTS_SINK=disk baron ...   # append-only JSONL under .baron/events/<date>.jsonl
BARON_EVENTS_DEBUG=1               # print swallowed sink errors while debugging a sink
```

Three things worth knowing:

- **It observes; it never decides.** Guard is fail-CLOSED (ADR-004 §2.3). Emission is the
  deliberate opposite — fail-OPEN and silent, so a full disk or a broken sink can never turn
  "log this" into "deny everything".
- **`.baron/events/` is gitignored; `.baron/guard-override.log` stays tracked.** Overrides
  are a handful of deliberate human acts, and belong in the diff. Events are one row per
  tool call, and belong on local disk. Retention is yours: `find .baron/events -mtime +30 -delete`.
- **No OpenTelemetry dependency** (ADR-003 holds). The row shape is the flat JSONL that
  `skills/multi-agent-audit/scripts/ingest_otel.py` already parses, so the audit skill reads
  baron's own stream with zero new code. **Read that stream with ingester v1.1 or later.**
  The shared keys `agent.name` / `tool.name` / `session.id` are join keys, and an older
  ingester reads them as agent activity: it invents a session out of hook timings, publishes
  its duration as agent working time labelled `measured`, and counts each evaluation as a
  tool call. v1.1 partitions baron rows out of the activity plane and counts them separately
  (ADR-021). A live exporter is a plugin in the `baron.sinks` entry-point group, mirroring
  `baron.forges`:

```toml
[project.entry-points."baron.sinks"]
logfire = "barony_logfire:LogfireSink"
```

The `Sink` Protocol is **final at three members** (`name`, `emit`, `close`). Optional
capabilities are duck-typed (`flush()`, `bind(cwd)`), never Protocol members — see the
warning comment in `sinks/base.py` for why.

Only guard's verdict path emits today. Ledger, session and decision have the contract
available and adopt it on their own schedule.

## Development

```bash
uv run --project cli pytest cli/tests    # from the repo root
```

The suite includes the capability-vocabulary drift guard, the ritual-token
cross-renderer guard (every `RITUAL_TOKENS` entry renders real prose in both code
renderers, `RITUAL_TOKENS` equals the canon's session-ritual table, and
`tests/bi_runtime_accept.py` gates the three adapters' fenced `ritual-map:v1`
surfaces against that same canon — no unjoined end), a
synthetic divergent git topology reproducing the 2026-07-22 triple-stranding
incident classes, the ledger push-rejection race test, subprocess-driven guard
hook tests (synthetic PreToolUse JSON on stdin), a recorded fake forge for the
lock lifecycle, a real two-persona worktree fixture, the waiver
downgrade/expiry cases, the
capability-rules artifact tests (packaged + versioned, verb set ≡ the frozen
vocabulary, guard-consumes-the-data mutation test, the ADR-016 legacy-accessor
pin against hand-transcribed pre-refactor literals, and the `baron rules
explain` ≡ `guard.evaluate_*` equality pin), and the pydantic-ai
adapter tests (offline TestModel/FunctionModel: capability omission, write
scoping, a scripted-and-vetoed `git push origin main`, the clean import-error
path), the `baron init` acceptance tests (layout + self-validation via the real
schemas + runtime kits + the non-empty-dir refusal), and the template drift
guard (`test_template_sync.py`: the vendored `src/baron/data/templates/` must
stay byte-identical to `skills/barony/assets/collab-repo/` — re-vendor with
`python cli/scripts/sync_templates.py`). The dev dependency group repeats the
pydantic-ai extra's pins so those tests run for real.
