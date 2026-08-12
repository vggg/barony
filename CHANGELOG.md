# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Proposed (no code) — [ADR-023](docs/adr/ADR-023-reserved-filenames.md): the emitted config filenames are governed artifact types

Third instance of the ADR-002/ADR-008 promotion pattern, and the first to concern
the framework's **own output** rather than persona behaviour. `baron init` emits a
fixed set of config filenames — `CONVENTIONS.md`, `COORDINATION.md`, `CLAUDE.md`,
`BOOTSTRAP*.md`, the entry-point docs — and nothing in the emitted
`CONVENTIONS.md` tells an agent those names are taken. **Awaiting owner review —
nothing implemented.**

Field failure (2026-08-12, Irisidian vault): an agent wrote a prose briefing to
`COORDINATION.md` **at a vault root**. It conformed to no schema, and its position
placed it *above* `CONVENTIONS.md` in that vault's precedence chain — so a
briefing would have resolved rule conflicts for the entire vault. In a precedence
chain, **position is authority**. Caught by the owner; no mechanism caught it. The
agent had named the collision in the document's own text and shipped to that path
anyway — which is why §5 declines to add lint enforcement *yet*: prose failing once
is not yet evidence that prose is the wrong instrument.

Proposes two template additions (§4.1 reserved-name list, §4.2 a reserved name is
scoped to its emitted location — no vault-root `COORDINATION.md`), and surfaces one
**defect found while drafting**: §4.3, the emitted precedence order
(`CONVENTIONS` → `COORDINATION` → `AGENT.md`) is **inverted** relative to the
Irisidian vault's (`CLAUDE.md` → `COORDINATION` → `CONVENTIONS`). Both are live and
they disagree on CONVENTIONS-vs-COORDINATION. Needs an owner call; no
recommendation embedded.

Evidence base is deliberately marked thin — **one first-party incident**, against
ADR-002's and ADR-008's multi-persona pilot runs. The argument for promoting anyway
is structural, not statistical: `baron init` creates the namespace, so the exposure
is universal even where the observation is singular. §7 keeps *"wait for a second
instance"* as a legitimate owner call.

## [1.10.0] — 2026-08-04

### Added — ritual-token coverage is now gated in the adapters

Closes the gap `docs/BACKLOG.md` recorded during the 1.9.0 cycle. `check_review_feedback`
(ADR-008 §2) shipped to three of four runtimes on its first cut, because each renderer
keeps its own surface and nothing cross-checked them — and **both renderer styles fail
silently**: the code renderers echo the raw token, the prose surfaces simply omit the step.
1.9.0 guarded the two code renderers; the three prose surfaces stayed ungated.

- **`ritual-map:v1` marker** in `adapters/{claude,code-puppy,generic}/HYDRATE.md` — the same
  convention `capability-map:v1` already established. Adapter authors now maintain a parsed
  contract, which is why this is a minor bump rather than a patch.
- **`tests/bi_runtime_accept.py` check (d)** asserts every ritual token is declared in every
  prose surface, and flags unknown tokens. Token list comes from the **canon**
  (`persona.schema.md`'s session-ritual table), not from `baron.schemas` — the harness is
  stdlib-only and runs without baron installed (ADR-006 §2).
- **`test_ritual_tokens_match_the_canon`** — the JOIN, and the reason the rest is worth
  anything. Review of the first cut proved that adding a token to `RITUAL_TOKENS` plus both
  code renderers, without touching the canon, left all three prose adapters uncovered with
  every suite green: the guard was wired to one end of a contract whose other end nothing
  checked. The chain now runs **code renderers ← `RITUAL_TOKENS` ← canon → adapters**.
- **A closed fence, not a scan-to-next-heading.** Entries are read only between
  `ritual-map:v1` and its closing marker, because a prose bullet mentioning a token *after*
  the surface was otherwise miscounted as a declaration — a deleted entry could be masked by
  a passing mention. Both failure modes have mutation tests.
- **Shape-tolerant parser** — claude and code-puppy use pipe tables, generic a bullet list;
  normalising them would be churn for its own sake. An entry must *start* its line with `|`
  or `-` plus the backticked token, so a token merely mentioned in prose is not miscounted.
- Verified by mutation: deleting one token from one adapter fails the harness with that
  adapter and token named. (An earlier cut of the parser stopped at generic's wrapped
  continuation lines and reported 4 of 5 tokens missing from a surface declaring all 5 —
  caught by the guard itself before commit.)

_Nothing yet._

## [1.9.0] — 2026-08-02

The governance-hardening release: the 2026-07-31 pilot ways-of-working folded
into the canonical templates (ADR-008), and spec↔runtime drift detection
(P2.3). Bundles everything accumulated since **1.8.0** — the plugin/skill was
unreleased across 1.8.1 and 1.8.2, and the pending bundle was relabelled to
**1.9.0** when the P1 fold-in added a schema token and a new emitted workflow;
a patch label would have been wrong.

**CLI track (`barony` on PyPI, versioned independently — `cli/pyproject.toml`):**
0.5.1, 0.5.2, 0.5.3, 0.5.5 and 0.5.6 are live. **0.5.4 was never published** (its
content ships inside 0.5.5), and **0.6.0 is likewise not published separately** —
its content ships inside **0.7.0**, which is the version released here. Skipping
an intermediate version rather than back-publishing it follows the 0.5.4
precedent: the CHANGELOG keeps the full per-version history either way.

### Added — `barony` 0.7.0: spec↔runtime drift detection (AGENT-TASKS P2.3)

`baron validate` now compares the personas a project **declares** against the
agents its runtime has actually **registered**. Owner picked this over P2.1
(2026-08-02) as the smaller, schema-change-free build.

**The failure it closes** (badminton-analyzer pilot, 2026-07): the collab repo
declared eight personas; the Claude subagent registry held six. `terrence` and
`carson` existed only as `persona.yaml`. Routing work to them did not fail
loudly — it fell through to whatever agent the runtime *did* have, so a cron ran
under the **wrong persona**: wrong identity, wrong commit prefix, wrong
capability set. Verified against the real pilot repo: the check reports exactly
those two.

- **The signal is PARTIAL registration, not absence.** Some personas registered
  and others not is positive evidence that the project hydrates agents on this
  runtime, which makes the gaps genuine drift (**error**). **That evidence must be
  repo-scoped** — a user-level `~/.claude/agents` entry matching a persona name
  proves nothing about this project (the directory is machine-wide and `dev` /
  `librarian` are the scaffold defaults); it can satisfy a persona but never
  establish that the project hydrates agents. All-or-nothing is
  **silent**, because zero registered is *correct* for a Tier-2 Claude project
  (`HYDRATE.md`: at Tier 2 "do NOT emit a dead subagent file"), a freshly
  scaffolded project (Tier-3 hydration is conversational, ADR-006 §3), and any
  Tier-1 runtime. **`tier: auto` is treated as Tier 3 — a judgement call, not a
  sidestep:** under `auto` HYDRATE.md permits per-persona degradation to Tier 2,
  which baron cannot distinguish statically from drift. It errors, and names the
  escape hatch in the message — declare `runtime.adapters.<runtime>.tier: 2` on
  that persona and the check honours it. **That escape hatch has a real cost, and
  the message says so:** the override is permanent and locks the persona out of
  Tier 3, so its whole-tool denials drop from enforced to instruction-only —
  whereas the ambiguity it resolves (`auto` degradation) is per-session. Explicit `tier: 2` at **either** the
  manifest or the per-persona level (`persona.schema.md` v1.1) is skipped.
- **Registries** — `claude` (`.claude/agents/<slug>.md`) and `code-puppy`
  (`.code_puppy/agents/<slug>.json`), searched collab-root → `paths.root` → each
  `repos[].path` → `~/`. Registration matches the adapter's filename **or** a
  `name:` frontmatter match, since that is what Claude keys a subagent on.
  `pydantic-ai` and `generic` have no inspectable registry (in-process hydration
  / Tier-1 prose) and are excluded in code with a comment.
- **Only declared runtimes are checked**, so a stray registry cannot fail a
  project that does not hydrate agents. User-level-only resolution **warns**:
  `~/.claude/agents` is shared across every project on the machine.
- **Honest limits, stated in the module**: a one-persona project cannot produce a
  partial state, and a fleet that drifted *entirely* reads as "not hydrated".
- **On CI:** the Claude registry is repo-scoped and travels with the clone
  (`HYDRATE.md` step 3a), so a committed `.claude/agents/` **is** present in CI by
  design, and a partially-registered project fails there deliberately.
  `--no-runtime-drift` opts out. `baron init` passes it for its own self-check —
  init validates the spec it wrote, not the environment around it.
- **Tests:** `cli/tests/test_drift.py` (13 cases: the pilot shape, the
  fresh-scaffold regression, explicit tier 2 vs 3, `paths.root` resolution,
  frontmatter matching, and an anti-vacuity guard that fails if `check` is
  gutted). Two `test_scaffold.py` assertions were reading the *developer's* real
  `~/.claude/agents`; both now scope to schema conformance.

### Proposed (no code) — [ADR-009](docs/adr/ADR-009-baron-decision-reconciliation.md): `baron decision`

Design proposal for the FM6/D57 mechanism ADR-008 §4 named but shipped as prose:
a ratified decision must reach the surfaces personas pull *work* from, not just
`decisions/`. **Awaiting owner review — nothing implemented.**

Load-bearing boundary: **baron never determines what a decision contradicts** —
inferring it needs a model call (crossing ADR-007's line) and its worst failure
is parking live work. Surfaces are declared input; baron performs the mechanical
steps and **verifies discharge**, reporting three states (discharged /
outstanding / **unverifiable**) so an unreachable forge is never scored as
either. Obligations live in a marker-delimited region inside the
`decisions/index.md` entry (ADR-003 §2.2 — no second store).

**Rev. 2 after adversarial design review**, which found four blocking defects in
rev. 1. The material one: `park` discharged on "closed OR label+comment", but
D57's own table records the FM6 epic as parked exactly that way and left OPEN —
the check would have gone green on the state that caused the failure it cites.
Park now discharges only when an agent's backlog query stops returning the item
(closed, or filtered via a declared `manifest.backlog.park_label` — a real
schema change, which is the honest cost). Also corrected: the `enforced` tier
claim (nothing here vetoes a call — instructed + visibility, per ADR-004);
`direction_doc` discharging on a closed ticket (an index substituted for the
record — the exact ADR-008 §1 failure); and the "detection was never the
problem" justification, which generalized from a post-hoc RCA.
§10 lists five questions blocking implementation.

### Added — plugin 1.9.0 + `barony` 0.6.0 (ways of working 2026-07-31 — ADR-008)

Promotes the 2026-07-30/31 badminton-analyzer pilot hardening into the canonical
templates, so the next `baron init` scaffold ships with it instead of every
adopter re-discovering it. Same promotion mechanism ADR-002 used for the July
learnings; recorded in
[ADR-008](docs/adr/ADR-008-ways-of-working-2026-07-31.md). (AGENT-TASKS P1.1–P1.5.)

Both new review-loop rules trace to one structural gap: **ADR-002 gave verdicts a
SHA but never said what a label is**, so personas filled the answer in themselves,
in opposite directions, and both answers were wrong.

- **`CONVENTIONS.md` — "A label is not evidence, in either direction"** (ADR-008
  §1). Labels are an index; the record is the verdict comment bound to a head SHA
  (`REVIEW:PASS/FAIL <sha>`). Check the SHA against the current head **before
  acting on an approval label** *and* **before concluding a block is stale** — the
  second direction is new; the first existed only as a Merger precondition and is
  now general. Corollary: green CI does not clear a block. Forbids adjudicating a
  label-vs-verdict disagreement by adding another persona — check the SHA.
- **`CONVENTIONS.md` — "Decision & ADR intake: the Librarian RECORDS and
  RECONCILES"** (ADR-008 §4). Five-step intake: record with supersession →
  park/close contradicting epics and backlog items → reconcile the direction doc
  (route a ticket if it's in a repo the Librarian can't write) → broadcast →
  hydrate directional decisions at session start before ticket selection.
  Personas re-derive "what next" from the direction doc and open epics, never from
  `decisions/`, so a recorded-but-unreconciled decision is invisible to exactly
  the surfaces that drive work. Honest label: discipline-in-a-doc; the mechanical
  version is the proposed `baron decision` (AGENT-TASKS P2.1).
- **New session-ritual token `check_review_feedback`** (ADR-008 §2; persona
  schema **v1.2**) — *act on review verdicts that are LIVE at your current head,
  before claiming new work.* Ships in the `__DEV__` ritual ordered **before**
  `check_backlog` (the ordering is the substance: feedback on work you have
  outranks a new ticket). Mapped in the claude / code-puppy / generic
  `HYDRATE.md` prose ritual-token surfaces **and** in the pydantic-ai hydrator
  (which renders in code, not in prose), rendered as SHA-test prose by `baron
  init`'s runtime kits, and added to baron's `RITUAL_TOKENS`. Additive — a
  ritual omitting it behaves exactly as before, and unknown tokens were already
  a warning, not an error.
- **New cross-runtime drift guard** for the ritual vocabulary
  (`test_every_ritual_token_renders_on_every_runtime`). Both **code** renderers
  fall back to echoing the raw token, so a missing entry does not crash — the
  rule silently vanishes from that runtime's persona body.
  `bi_runtime_accept.py` never gated this (it parses capability maps, not ritual
  tokens). Every `RITUAL_TOKENS` entry must now render real prose on both code
  renderers (`scaffold._ritual_lines` and `runtimes.pydantic_ai._RITUAL_LINES`).
  The other three adapters' `HYDRATE.md` prose surfaces remained **ungated** at
  this version — a known, recorded gap, **closed in 1.10.0** (above).
- **`.github/workflows/strip-stale-verdict.yml`** (ADR-008 §3) — emitted by
  `baron init` alongside `lock-guard.yml`: on every `synchronize`, removes the
  project's reviewer verdict labels and comments that the head moved, so that —
  where it is installed and covers the label — "a review-state label is present"
  means "a verdict exists at *this* head". Owner gates (`needs-human`, `hold`,
  `contract-change`) are explicitly excluded — only the owner lifts those.
  Dependency-free (bash + `gh`, built-in `GITHUB_TOKEN`), no-ops on fork PRs.
  Carries the `lock-guard.yml`-style honest limitation: it removes a misleading
  label, it cannot stop a persona that never reads verdicts — the merge gate
  still lives in the Merger's preconditions. Written into the collab repo (the
  repo init scaffolds); the header instructs copying it to the code repo, where
  most reviewed PRs live.
- **Reviewer / Merger templates hardened** (ADR-008 §1). Reviewer: verdict format
  is a parsed contract (full head SHA, never a branch/`HEAD`/abbreviation, fetched
  via `gh pr view --json headRefOid`); re-review publishes a NEW verdict, never
  edits the old one; labels follow the verdict and never lead it. Merger: **a
  label is never an input to the merge decision** — read the verdict, compare the
  SHA yourself, and if label and verdict disagree strip the label and refuse.
- **`COORDINATION.md § Review and merge`** gains the dev-side feedback-sweep step
  and states that review-state labels are an index for every persona in the loop.

Vendored template copy re-synced (`cli/scripts/sync_templates.py`); drift guard
green; 133 CLI tests (2 new) + both stdlib suites pass.

### Added — `barony` 0.5.6 + plugin 1.8.2 (session boundary — ADR-007 + thin session primitives)

The 2026-07-28 pydantic-ai interop eval found the split: enforcement is solid
(the in-process guard vetoes denied tool calls, proven live) but the session
RITUAL — sync repos, read conventions/handoffs, check the backlog, record
findings/handoffs, commit with the right prefix, regenerate the index — was
instructed prose only; a human/script had to drive it.
[ADR-007](docs/adr/ADR-007-session-boundary.md) records two decisions.

- **Barony does NOT own the agent execution loop.** No `baron run` driver;
  orchestration/execution belongs to the runtime layer (ADR-001's three-layer
  positioning: Barony = coordination policy + governance + audit; runtime =
  execution). A driver would duplicate — and lose to — pydantic-ai / Temporal /
  Claude Code, and cross the boundary the design defends.
- **Barony DOES ship thin, optional session-ritual primitives.**
  `baron session start [--persona] [--sync] [--json]` (session-open: optional
  `git pull --ff-only`, then the persona's open handoffs + a
  CONVENTIONS/COORDINATION pointer + the manifest backlog location) and
  `baron session end [--persona] [--json]` (session-close: regenerate the handoff
  index, commit dirty `_handoff/ findings/ decisions/ wiki/` by path — never
  `git add -A` — with the persona's `commit_prefix` else `baron:`, then a
  `baron status` divergence check; exit 1 on red). They mechanize ONLY the
  git/markdown bookkeeping — no agent loop, no model calls, no runtime coupling;
  opt-in (nothing in baron requires them); NOT new capability verbs (the frozen
  10 stay frozen). They compose existing baron functions (`status`, `handoff`,
  `indexer`, `gitutil`) — nothing reinvented. Honesty in both `--help`: "they do
  NOT run an agent — orchestration is the runtime's job (ADR-007)."
- **Docs:** `cli/README.md` "session ritual primitives (optional)" (the boundary
  + the three composition points: a human between turns, a driver/CI wrapper, a
  runtime adapter capability/hook); `docs/concepts.md` short paragraph; the
  pydantic-ai adapter HYDRATE.md gains a "composing the session ritual (optional)"
  note (plugin/skill **1.8.1 → 1.8.2**; vendored template copy re-synced
  byte-identical). `docs/BACKLOG.md`'s "reverse-direction / `baron run` driver —
  decision pending" note is replaced with the ADR-007 resolution.
- **Tests:** `cli/tests/test_session.py` — start surfaces a persona's open
  handoff + brief, `--json` shape, `--sync` fast-forward pulls (bare-origin
  fixture), end regenerates the index + commits dirty coordination files with the
  persona prefix + reports status, end exits 1 on red, both no-op-clean.

### Added — `barony` 0.5.5 (worktree repair commands — rest of baron M6)

Closes the `docs/BACKLOG.md` "Worktree topology — repair commands" item: the
migration runbook surfaced two repair needs when a worktree dir is moved or
deleted *outside* baron (git leaves a stale registration in `.git/worktrees/`).

- **`baron worktree prune [--dry-run]`** — wraps `git worktree prune` to clear
  stale administrative registrations for worktree dirs that no longer exist.
  `--dry-run` uses `git worktree prune -n` to report what would go without
  changing anything; the report (git writes it to stderr) is surfaced in plain
  text, and a clean "nothing to prune" when there is none.
- **`baron worktree repair [PATH…]`** — wraps `git worktree repair` to fix a
  worktree's admin links (gitdir pointer + `.git` gitlink) after a worktree or
  the main repo was moved on disk. With paths, repairs those; otherwise all.
  Requires git >= 2.30 (a capability check via `git worktree -h` gives a clean
  error on an older git).
- Both are **non-destructive to committed work** — they touch only
  `.git/worktrees/` admin state, never a branch or its history (stated in
  `--help`), consistent with `remove`'s safety ethos. `--repo` resolves from the
  manifest (`repos[role=code]`) exactly like the other worktree commands.
- Docs: `docs/worktree-migration.md`'s gotcha section now points at
  `baron worktree prune`/`repair` instead of raw git; `cli/README.md` documents
  the subcommands.

### Security / hardening — `barony` 0.5.4 (interop hardening + backlog burndown)

Driven by a hands-on dogfood of the pydantic-ai adapter (2026-07-28).

- **Least-privilege Shell in the pydantic-ai adapter (real containment gap).**
  `build_agent`/`plan` previously gave any shell-granting persona a *full* shell
  (`Shell(cwd, denied_commands=[])`) — a reviewer whose only shell-implying grant
  was `run_tests` could `curl`/`rm`/`git push feature/x` (the guard only vetoes
  three git sub-verbs). Now: a persona whose only shell need is `run_tests` (and
  no broad `write_code`/dev verbs) gets an **allowlisted** shell restricted to
  test runners (`pytest`/`py.test`/`tox`/`nox`/`unittest`/`coverage`,
  `denied_commands=[]` since the harness makes allow/deny mutually exclusive); a
  broader dev shell stays general but now sets `denied_operators=['>', '>>', '|']`
  so a redirect can't write out of root behind the guard. `python -m pytest` /
  `make test` are intentionally excluded (the harness matches the executable
  name; allowing `python`/`make` would re-open a general runner).
- **Guard denies out-of-root writes itself (defense-in-depth).**
  `guard.evaluate_write` now normalizes the target and DENIES any path that
  escapes the collab/persona root (a `../outside.md` resolving above root),
  rather than leaving it to the harness FS jail (which a Shell `>` redirect
  escapes anyway).
- **Guard-bypass honesty is now prominent.** `bash -c '...'` / `sh -c "..."` /
  `python3 -c '...'` wrappers run their payload uninspected by the static parser
  — documented plainly in `guard.py`, the pydantic-ai `HYDRATE.md`, and
  `docs/concepts.md`. (No blocking heuristic added — it would false-positive on
  every read-only persona's legitimate `bash -c`.)
- **Calmer remote-less guard wording.** The first-run "origin default branch
  undeterminable; `main` conservatively treated…" stderr is reworded to a calmer,
  still-honest phrasing.
- **`RepoContext` wired (additive).** `build_agent` now adds
  `RepoContext(workspace_dir=<collab_root>)` when a `collab_root` is passed
  (auto-loads `CLAUDE.md`/`AGENTS.md`), with a clean fallback if the installed
  harness lacks it.
- **`baron handoff create --body-file F`** — parity with `finding`/`decision`;
  the file's content becomes the handoff body under the frontmatter.
- **`baron handoff close --as <slug>`** — attributes the close commit as
  `<slug>:` instead of the default `baron:`.
- **`BARON_NOW` clock override** — the default clock honors an ISO
  date/datetime `BARON_NOW` env var for demos/backfills (a testing seam, not for
  normal use; malformed values raise).
- **Docs — `--author` vs git author.** `cli/README.md` + command help now
  document that `--author` sets ledger attribution while the git author identity
  is separate (allocator-vs-proposer).
- **Version-string honesty.** The "pydantic-ai-slim 2.16.0" string in
  `cli/pyproject.toml`, `pydantic_ai.py`, and the adapter `HYDRATE.md` is
  corrected to the tested range (harness 0.10.0 / slim 2.14.1–2.19.x).

### Changed — plugin/skill **1.8.1** (paired with 0.5.4)

- The pydantic-ai adapter `HYDRATE.md` (skill asset + vendored template, kept
  byte-identical) documents the least-privilege Shell, `RepoContext` wiring, the
  prominent `bash -c`/`sh -c` bypass note, and the corrected version range.
  `plugin.json` + `SKILL.md` bumped together (lint-enforced).

### Fixed — `barony` 0.5.3 (install-UX shakeout)

- **`barony` now works as a command too**, aliased to `baron`. A fresh
  `pip install barony` followed by the natural `barony --version` was dead-ending
  in `command not found` (the package is `barony`, the command was only `baron`).
  Both now resolve to the same CLI; `baron` stays the primary/documented name.

### Fixed — `barony` 0.5.2 (first-publish shakeout)

- **`baron --version` / `-V`** now exists — it errored ("No such option") the
  minute 0.5.1 hit PyPI and someone ran the obvious first command.
- **`__version__` no longer drifts** — it derives from installed package
  metadata (it had silently sat at `0.4.0` while the package shipped `0.5.1`).
  New `test_version_flag_matches_pyproject` guards `--version` ≡ pyproject.
- README + `cli/README.md` install sections flipped to the live PyPI path
  (`uv tool install barony`) now that the package is published.

### Packaging — `barony` 0.5.1 (pre-publish polish)

- **`[project.urls]`** added to `cli/pyproject.toml` (Homepage/Repository/
  Documentation/Changelog/Issues → `github.com/vggg/barony`) so the PyPI page
  links home instead of rendering as an orphan. `description` sharpened to the
  product one-liner. `cli/README.md` opens as a proper package landing page.
- `.gitignore` covers build artifacts (`dist/`, `build/`, `*.egg-info/`).
- Homepage points at the repo until `barony.dev` is registered.

### Changed — docs only (no version bump)

- **README.md rewritten as the outsider's front door** (inverted pyramid): the
  one-liner + three-sentence identity, the four-walls 60-second pitch with one
  first-party receipt each (stranding incident, operational fidelity 0.53,
  handoff/ledger rot, single-account accountability), the verified v1.8.0
  quickstart (commands unchanged), ~3-sentence core concepts, the per-adapter
  runtime/enforcement matrix sourced from the HYDRATE capability maps, an
  explicit "what Barony is NOT" section, and status/links.
- **Deep material moved out of the README**: new `docs/concepts.md` (longer-form
  concept explanations, emitted layout, capability ladder, guard/lock/worktree/
  audit detail) and `docs/history.md` (the v0.3 → v1.8 evolution narrative,
  linking ADR-001/002/005/006). `CLAUDE.md` gains a one-line pointer to the
  README as the public story and lists the two new docs files.

## [1.8.0] — 2026-07-27

**The stranger release** — a stranger with a laptop gets a working project in
minutes: `pip install barony`, `baron init`, done. The deterministic scaffold path
lands as a CLI command ([ADR-006](docs/adr/ADR-006-baron-init-template-packaging.md));
the conversational path (`START.md` → `ORCHESTRATE.md`) keeps the judgment work.
CLI version `0.4.0 → 0.5.0`.

### Added

- **`baron init <name> [--dir] [--code-repo] [--personas archetype:slug,...]
  [--runtime claude|generic|pydantic-ai|code-puppy] [--no-git]`**
  (`cli/src/baron/scaffold.py`) — emits the canonical collab-repo layout:
  `CONVENTIONS.md`/`COORDINATION.md` filled, a schema-conformant `manifest.yaml`
  (relative paths, `backlog: file`, `workspace.worktrees_root` when a code repo is
  named), `canon/` + `adapters/` copied verbatim (ORCHESTRATE.md §2a), hydrated
  `agents/<slug>/persona.yaml` per persona (identity `<slug>@<project>.local`;
  librarian renameable, e.g. `librarian:iris`; generic edit-me scope — never fake
  specificity), a genesis handoff, `findings/`+`decisions/` index headers the real
  ledger allocator appends to, the wiki stub, and the lock-guard CI template.
  Self-validates with the real schemas (zero errors) before `git init -b main` +
  a first commit of exactly the files written. Refuses a non-empty directory.
- **Per-persona runtime kits** (`agents/<slug>/runtime/`) — the deterministic
  floor of each adapter: claude = Tier-2 persona `CLAUDE.md` + `.claude/settings.json`
  wiring the `baron guard` PreToolUse hook (HYDRATE.md steps 3b/3c); generic and
  code-puppy = Tier-1 `AGENTS.md`; pydantic-ai = the `agent_setup.py` bootstrap.
  Tier-3 hydration and scope prose stay conversational — the kits' READMEs say so.
- **Template packaging (ADR-006)** — the skill tree stays the single canonical
  source; `baron init` reads a byte-identical vendored copy shipped as package
  data (`cli/src/baron/data/templates/`, synced by `cli/scripts/sync_templates.py`).
  Drift guard: `cli/tests/test_template_sync.py` fails CI on any divergence.
- **Tests** — `cli/tests/test_scaffold.py` (layout, self-validation, hydration,
  runtime kits, git init, re-init refusal, ledger-on-scaffold) + the sync guard;
  cli suite 92 → 103 tests. *(Corrected post-release: this entry originally
  claimed 114.)*

### Changed

- **README.md / cli/README.md** — new Quickstart sections with the exact
  command sequence verified end-to-end from a fresh install against an existing
  git code repo: init → validate → status → finding → handoff create/close →
  index → worktree add, plus a `baron guard` deny/allow smoke. (The `status` and
  `worktree` steps require the code repo the quickstart creates first.)
- **`baron validate`** — the template-skip rule also covers baron's own vendored
  templates (`baron/data/templates/`), mirroring the repo lint.
- **ORCHESTRATE.md** — notes the `baron init` shortcut for its mechanical steps
  (1–2a) and where the conversational recipe resumes.

## [1.7.0] — 2026-07-27

**The Barony release** — the project is renamed from `agent-project-bootstrap` to
**Barony**: git-native governance for teams of AI coding agents. The rename is recorded
in [ADR-005](docs/adr/ADR-005-naming.md); the naming system is **Barony** = the
product/framework (spec + adapters + baron CLI + audit), **baron** = the CLI
(install `barony`, run `baron`, import `baron`).

### Changed

- **Repo** — `vggg/agent-project-bootstrap` → `vggg/barony` (GitHub redirects the old
  URLs). All live GitHub links updated.
- **Skill directory** — `skills/agent-project-bootstrap/` → `skills/barony/` (git mv);
  skill frontmatter `name: barony`; plugin manifest `name: barony`. The sister skill
  keeps its name (`multi-agent-audit`). All path references (docs, tests, templates,
  legacy pointers) updated.
- **CLI distribution** — `baron-cli` → **`barony`**, version `0.3.0 → 0.4.0`. Console
  script and import package stay `baron`; the optional extra is now
  `barony[pydantic-ai]`.
- **Positioning copy** — README/CLAUDE/STATUS identity statements rewritten around the
  current positioning ("git-native governance for teams of AI coding agents"); stale
  v0.3-era scaffolding/vault copy removed from CONTRIBUTING. The "signet" name is
  introduced for SHA-sealed review verdicts (reserved sub-brand, ADR-005 §2).
- **Leak scrub** — absolute local paths and non-fiction personal identities removed
  from audit-skill examples (`references/timeline.md`, `references/actor-resolution.md`,
  `assets/actors.example.yaml`, `references/confidence-and-trends.md`); replaced with
  generic placeholders.

### Added

- **`docs/adr/ADR-005-naming.md`** — the naming decision, research summary (PyPI/npm
  availability, rejected alternatives), and rename mechanics.

Historical entries below this line keep the old name where they describe the past —
history is not rewritten.

## [1.6.0] — 2026-07-23

The fourth-runtime release: the guard's rule table becomes a versioned, machine-readable
artifact every enforcer shares; the generic adapter emits `AGENTS.md` (the cross-runtime
context convention); and pydantic-ai lands as a full runtime adapter with a working
in-process hydrator — the first adapter whose sub-tool denials are natively `enforced`.

Also in this release — `multi-agent-audit` v1.4 telemetry mode: `scripts/ingest_otel.py`
(OTLP-JSON/JSONL trace-export ingestion — Claude Code, Logfire, Phoenix; stdlib-only,
files-only, never live endpoints) + `scripts/merge_telemetry.py` (additive, source-tagged
snapshot merge; git-derived metrics never overwritten). Upgrades intervention-tax inputs
from `inferred` to `measured` when an OTel export exists; `not measurable` is reported
honestly, never estimated. New `tests/test_ingest_otel.py` (66 checks) + fixtures.

### Added — the capability-rules artifact (single source for enforcement rules)

- **`cli/src/baron/data/capability-rules.v1.yaml`** (new, `rules_version: 1`) — the
  runtime-agnostic verb→enforcement rule table `baron guard` previously hardcoded, now
  shipped as baron package data (`importlib.resources`, loaded by the new
  `cli/src/baron/rules.py`): git command patterns (push to default branch / `--all` →
  `push_main`; force flags + `+refspec` → `force_push`; `gh pr merge` → `merge_pr`;
  `git merge` on the default branch → `push_main`), the value-taking options each parser
  must skip, fallback default-branch names, file-op scoping semantics
  (`_handoff/` universal-write, own-vs-other `agents/<slug>/` spec dirs, denied-scopes-
  always-block precedence), the `conservative-deny` ambiguity policy, and per-rule notes
  (including which verbs are deliberately NOT parsed: `open_pr`/`run_tests`). Placement
  rationale recorded in the ADR-004 addendum §4.1.
- **`guard.py` refactored to consume the artifact** — mechanics (shell splitting, refspec
  resolution, branch lookups, hook I/O) stay code; every pattern is loaded from the rules.
  Behavior identical: the 19 guard tests pass unchanged. A broken/unsupported artifact
  fails CLOSED (deny with the reason), never open. New `cli/tests/test_rules.py` asserts
  the artifact is packaged + versioned, its verb set exactly matches the frozen 10-verb
  vocabulary, guard decisions actually follow the loaded data (mutation test), and
  `rules_version` mismatches are refused.
- **`references/capability-rules.md`** (new skill reference) — the prose contract: the
  artifact is THE single source for enforcement rules; consumers (baron guard, runtime
  adapters) load it and never restate patterns. `capability-vocab.v1.md` gains a pointer
  note (the vocabulary itself is untouched — still frozen at 10 verbs).

### Added — AGENTS.md emission (generic adapter, Tier 1)

- **`adapters/generic/HYDRATE.md` step 3 (new)** — Tier-1 hydration now emits ONE
  artifact: an `AGENTS.md` in the persona's working-copy root, derived entirely from
  `persona.yaml` (marked generated-do-not-hand-edit), with identity, scope, session
  ritual, capability grants AND denials in plain imperative language, and collab-repo
  pointers. AGENTS.md-aware runtimes (pydantic-ai-harness `RepoContext()`, etc.)
  auto-load it; for everything else it is the core loop's re-read target. **Honest tier
  note carried in the template itself:** everything in it is instruction-only — emitting
  a file does not upgrade the tier.
- **Claude adapter note** — `CLAUDE.md` remains that adapter's native context file;
  emitting `AGENTS.md` alongside is optional/additive (useful when the same working copy
  is visited by AGENTS.md-aware runtimes), both derived from `persona.yaml`.

### Added — pydantic-ai runtime adapter (the fourth runtime)

- **`adapters/pydantic-ai/HYDRATE.md`** (new) — full adapter in the standard format with
  the machine-readable `capability-map:v1` table covering all 10 verbs. The adapter's
  distinction, stated honestly: hydration is **in-process**, so the five guard-covered
  sub-tool denials (`write_path` scoping, `merge_pr`, `push_main`, `force_push`,
  `edit_other_personas`) are natively class **`enforced`** — the interception hook cannot
  be absent from an agent built via `build_agent` (unlike the Claude hook, which degrades
  without baron). Whole-tool denials via capability omission (no shell verbs → no `Shell`
  capability at all; no write verbs → natively read-only `FileSystem`).
  `open_pr`/`run_tests` denials stay `instructed` (the rules artifact defines no
  detection for them). Verified against **pydantic-ai-harness 0.10.0** +
  **pydantic-ai-slim 2.16.0** (2026-07-23; APIs: `Agent(capabilities=[...])`,
  `AbstractCapability.before_tool_execute` + `ModelRetry` veto, harness
  `FileSystem`/`Shell`/`RepoContext`).
- **`cli/src/baron/runtimes/pydantic_ai.py`** (new) — the working hydrator:
  `build_agent(persona_file, collab_root=None, model=...) -> Agent`. Instructions
  composed from persona identity/scope/ritual/capabilities; `FileSystem` scoped per
  write verbs (`protected_patterns=['*', '**/*']` = natively read-only when no write
  verb); `Shell` only when a shell-granting verb is allowed, with `denied_commands`
  seeded with common test runners when `run_tests` is denied; a guard capability whose
  `before_tool_execute` evaluates `run_command` commands and file-write paths through
  `baron.guard`'s evaluators — i.e. the SAME `capability-rules.v1.yaml` the Claude hook
  uses — and vetoes denials with `ModelRetry` (reason fed to the model, mirroring
  exit-2 + stderr). `runtime.model_hint` honored as the default model; the offline
  `"test"` model is the fallback placeholder.
- **Optional extra `baron-cli[pydantic-ai]`** — pinned `pydantic-ai-harness>=0.10,<0.11`
  + `pydantic-ai-slim>=2.14.1,<3` (harness is 0.x; minor releases may break). Without
  the extra the module import-errors cleanly with install instructions. The dev
  dependency group repeats the pins so the test suite exercises the real APIs.
- **`baron hydrate pydantic-ai --persona-file F [--out agent_setup.py]`** (new command,
  new `hydrate` sub-app) — emits a ready-to-edit bootstrap script (imports
  `build_agent`, offline-model placeholder). Emission needs only baron; running the
  script needs the extra.
- **`cli/tests/test_pydantic_ai.py`** (new, offline only — TestModel/FunctionModel, no
  API keys): dev fixture gets Shell, reviewer fixture gets NO Shell capability;
  write scoping follows the verbs (scopes allowed, `src/` blocked, own vs other
  `agents/<slug>/` dirs); a scripted `git push origin main` attempt through a REAL agent
  run is vetoed before execution with the guard's reason (FunctionModel scripts the tool
  call — TestModel cannot script specific args); interceptor unit tests; clean
  import-error path (subprocess with the dependency blocked); CLI emission tests.
- **`tests/bi_runtime_accept.py`** — the sweep now covers **4 adapters**; the pydantic-ai
  map must cover all 10 verbs and the tess/rex fixtures must hydrate to the equivalent
  contract. Enforcement-tier consistency extended and TIGHTENED: both per-adapter
  allowances (claude's `enforced-with-baron (instructed otherwise)`, pydantic-ai's plain
  `enforced` on sub-tool rows) are now accepted ONLY on the five guard-covered verbs —
  a guard claim on an `open_pr`/`run_tests` row fails for every adapter.

### Changed — meta

- `plugin.json` + `SKILL.md` frontmatter `1.5.0 → 1.6.0`; `baron-cli` package
  `0.2.0 → 0.3.0` (and `baron.__version__` re-synced — it had lagged at 0.1.0).
- ADR-004 gains a **§4 addendum**: §4.1 rules-artifact externalization + placement
  rationale; §4.2 the pydantic-ai adapter's native-`enforced` sub-tool claim and why it
  needs no qualifier.
- ADR-001 §4.5/§4.6 current-adapter enumerations, `README.md` (runtime count 3 → 4,
  support table row, adapters listing, baron section), `CLAUDE.md`, `CONTRIBUTING.md`,
  `cli/README.md` (rules artifact, `baron hydrate pydantic-ai`, the extra),
  `STATUS.md`, `docs/BACKLOG.md` (guard-coverage entry re-scoped: pydantic-ai now has an
  in-process seam; pilot validation of the new adapter tracked), emitted
  `START.md`/`ORCHESTRATE.md` (runtime-key table + canon/adapters copy lists now include
  pydantic-ai and `capability-rules.md`).
- `tests/lint_repo.py` skips `.venv`/`.pytest_cache` (the newly installed harness ships
  READMEs whose relative links are not this repo's content).
- CLI test suite 75 → 91 tests.

## [1.5.0] — 2026-07-23

The mechanisms release: baron grows enforcement (guard), locking (PR-as-lock), the
worktree topology tooling, and status waivers — and the M1–M3 work ships properly.

> **Honest release note:** the "baron CLI M1–M3" block below was developed and pushed
> under `[Unreleased]` (2026-07-22) without a version cut — it reached `main` unreleased.
> It is folded into this 1.5.0 entry verbatim rather than back-dated as a phantom
> release; 1.5.0 is its first released version.

### Added — `baron guard` M4: deterministic capability enforcement (ADR-004)

- **`docs/adr/ADR-004-baron-guard-enforcement.md`** (accepted 2026-07-23) — why
  hook-based sub-tool enforcement is a contract change deserving its own record: it
  amends the enforceability-class honesty boundary (`capability-vocab.v1.md`) that every
  adapter's "do not oversell" rule is built on.
- **`baron guard --persona-file <persona.yaml>`** (`cli/src/baron/guard.py`) — a Claude
  Code **PreToolUse hook** implementing the documented contract
  (https://code.claude.com/docs/en/hooks): hook JSON on stdin (`tool_name`,
  `tool_input`, `cwd`); exit 0 + silence = defer to the normal permission flow; exit 2 =
  block with stderr fed to the model. Decision logic maps tool calls to the frozen v1
  verbs: `git push` to the default branch → `push_main` (conservative on ambiguity —
  an unresolvable target is inferred as the enforcement-relevant verb and denied for
  personas lacking it, stderr naming the inference); force flags / `+refspec` →
  `force_push`; `gh pr merge` → `merge_pr`; `git merge` while on the default branch →
  `push_main`; Edit/Write/NotebookEdit paths → `write_path` scopes /
  `edit_other_personas` / `write_code`, with `_handoff/` universally writable and a
  persona's own `agents/<slug>/` dir its own surface. Non-git/gh commands and unknown
  tools pass — a capability gate, not an allowlist. **Fail-closed but not brick**:
  malformed stdin / unreadable persona → deny with actionable stderr;
  `BARON_GUARD_OVERRIDE=<reason>` allows AND appends to the **tracked**
  `.baron/guard-override.log` (overrides are visible in diffs; each is expected to
  become a handoff). Env `BARON_PERSONA_FILE` honored.
- **Claude adapter HYDRATE.md step 3c** — Tier 2/3 hydration also emits a
  `.claude/settings.json` hooks block (PreToolUse, matcher
  `Bash|Edit|Write|NotebookEdit` → `baron guard`), with the honest note: five sub-tool
  denials (`push_main`, `force_push`, `merge_pr`, `write_path` scoping,
  `edit_other_personas`) upgrade from instructed to ENFORCED **when baron is
  installed**; without it the hook fails non-blocking and they degrade to instructed.
  The capability map's sub-tool rows now claim the exact qualified form
  `enforced-with-baron (instructed otherwise)` (`open_pr`/`run_tests` stay
  `instructed` — guard does not parse for them), and
  **`tests/bi_runtime_accept.py`**'s tier-consistency assertion accepts exactly that
  form, only on sub-tool rows, only for the claude adapter.

### Added — `baron lock` M5: PR-as-lock (mechanizes ADR-002 §3)

- **`baron lock claim <path> [--reason]` / `release <path>` / `list`**
  (`cli/src/baron/lock.py`) — the open PR is the lock: claim = `lock/<slug>` branch with
  one empty commit (`git commit-tree`; the local checkout is never touched) + a draft PR
  labeled `lock:<path>` with the reason in the body; claim refuses when an open lock PR
  for the path exists, showing the holder; release closes the PR + deletes the branch;
  list prints path/holder/age/PR#. Replaces the markdown LOCK-commit protocol.
- **Forge Protocol extended** (additive): `create_branch`, `close_pr`, label-aware
  `open_pr` (`head`, `labels` — labels created idempotently) and richer
  `list_open_prs` (labels/author/createdAt/url). All `gh` calls stay behind the Forge
  interface; `ForgeUnavailable` raised cleanly without `gh`; lock tests run against a
  recorded fake forge — no live `gh`.
- **`assets/collab-repo/.github/workflows/lock-guard.yml`** (new template) —
  dependency-free CI guard (bash + the `gh` Actions provides): fails a PR that touches a
  locked path unless it IS the lock PR; carries the ADR-002 §3 honest limitation
  (without branch protection a red check is an alarm, not a wall). The emitted
  `COORDINATION.md` lock mechanics now name the concrete commands and file.

### Added — baron M6 tooling: worktree topology

- **`baron worktree add <persona> [--root DIR]` / `list` / `remove [--force]`**
  (`cli/src/baron/worktree.py`) — one shared object store, branch `persona/<slug>`,
  worktrees under the manifest's `workspace.worktrees_root` (v1.2 seam, consumed
  unchanged). `remove` refuses on dirt or unmerged commits unless `--force` and never
  deletes the persona branch. `baron status` sweeps worktrees like clones (each
  worktree reports its checked-out HEAD; the repo-wide branch sweep runs once).
- **`docs/worktree-migration.md`** (new) — clone-per-persona → worktrees runbook
  (drain clones, verify with `baron status --fetch`, create worktrees, repoint
  manifest + session CLAUDE.md paths, retire clones) with an honest rollback section.
  The live migration of the pilot workspace is deliberately NOT in this release.

### Added — status waivers (from the pilot-triage backlog entry)

- **`.baron-waivers.yaml` + `baron waiver add|list`** (`cli/src/baron/waivers.py`) —
  `{subject (fnmatch on the status SUBJECT column), reason, handoff, expires}`.
  `baron status` downgrades matching reds to warn with `(waived: <reason>)` appended;
  EXPIRED waivers stop matching (the red resurfaces) and are reported as their own
  `expired-waiver` warn; malformed entries are reported, never silently dropped.
  `waiver add` refuses past expiry dates and duplicate patterns.

### Changed — meta

- `plugin.json` + `SKILL.md` frontmatter `1.4.0 → 1.5.0`; `baron-cli` package
  `0.1.0 → 0.2.0`; `STATUS.md`, `README.md`, `cli/README.md`, `docs/BACKLOG.md`
  (waivers entry removed as shipped; remaining M6/merger-preconditions/guard-coverage
  items re-scoped), ADR-003 gains a §5 addendum for the lock/worktree/waiver decisions.
- CLI test suite 36 → 74 tests (guard subprocess tests, fake-forge lock tests, worktree
  fixture, waiver cases).

### Added — baron CLI M1–M3 (Phase 2: conventions → mechanisms, ADR-003)

- **`docs/adr/ADR-003-baron-cli.md`** (accepted 2026-07-22) — the `baron` CLI decisions:
  markdown/git substrate as the only database; typer+pyyaml-only dependency policy (git/gh
  via subprocess); forge Protocol with GitLab-as-plugin backlog (`baron.forges` entry-point
  group); ledger ID allocation via push-retry; archive-not-delete handoff lifecycle.
  Motivations traced to field evidence: three F-number collisions, the 2026-07-22
  triple-stranding incident, markdown LOCK-commit races, 18/40 open handoffs
  (badminton-analyzer), and enforcement theater (GardenTwin audit, operational fidelity 0.53).
- **`cli/`** — the `baron-cli` package (src layout, Python ≥ 3.10, console script `baron`):
  - **M1 `baron validate [PATH]`** — persona.yaml/manifest.yaml validation against
    declarative schemas (`cli/src/baron/schemas.py`) formalized from the prose specs;
    embeds the FROZEN 10-verb capability vocabulary with a drift-guard test that re-parses
    `references/capability-vocab.v1.md`. Checks parse/fields/types/verbs/allow-deny
    overlap/unfilled placeholders; template dirs (`assets/collab-repo/`, `legacy/`) skipped
    on discovery. `--json`; exit 0 clean / 1 errors.
  - **M2 `baron status [--fetch] [--sla N] [--json]`** — divergence & staleness report:
    ahead/behind origin default branch, dirt, unmerged local branches with age, open
    handoffs past SLA, ledger staleness vs code-repo activity (labeled heuristic), stale
    `wiki/status.md`. Acceptance test builds a synthetic topology reproducing the three
    2026-07-22 stranding classes. Exit 0 green / 1 any red.
  - **M3 ledgers & handoffs** — `baron finding new` / `baron decision new` (max-ID parse of
    both heading and table-row forms, push-retry renumbering on rejection, injectable
    clock, `--no-push`); `baron handoff create/close/list` (standard frontmatter; close =
    status flip + `closed:` date + optional note + `git mv` to `_handoff/archive/YYYY/`);
    `baron index` (marker-delimited summary block in `_handoff/README.md` + report-only
    numbering verification). Race acceptance test: two clones allocate the same F-number;
    the rejected writer renumbers and both land.
- **`references/manifest.schema.md` v1.2** — optional `workspace.clones` /
  `workspace.worktrees_root` fields (local persona working copies for `baron status`
  sweeps); commented example block in `manifest.example.yaml`.
- **`docs/BACKLOG.md`** — GitLab forge plugin design sketch (entry-point discovery, same
  Protocol, `forge: gitlab` manifest key) plus consciously deferred M1–M3 items; worktree
  topology tracked as baron M6.
- **CI** — new `baron-cli` job (`uv run --project cli pytest cli/tests`); the stdlib-only
  jobs are untouched.

## [1.4.0] — 2026-07-22

The credibility-debt release: one front door, honest artifacts, real tests, and the
field-proven July-2026 ways-of-working (ADR-002).

### Changed — one front door (legacy path quarantined)

- **`SKILL.md` rewritten as a thin front door** (frontmatter bumped `1.1.0 → 1.4.0`, gains a
  `description:` for skill discovery). All new-project creation and joining routes through
  `assets/collab-repo/START.md` → `ORCHESTRATE.md` / `PARTICIPATE.md`; the legacy modes are a
  one-line pointer.
- **Legacy v0.3 path moved to `legacy/`** at the repo root: `legacy/vault/`,
  `legacy/workspaces/` (the template trees only the legacy modes consume) and
  `legacy/SKILL-v0.3.md` (the three-mode emit instructions, verbatim). `legacy/README.md`
  marks it deprecated/unmaintained, kept for existing v0.x projects.
- **`.claude-plugin/plugin.json`** `1.3.0 → 1.4.0`; description reflects the one-front-door +
  legacy-quarantine reality. Version sync with `SKILL.md` is now lint-enforced.
- **Doc dedup:** the v0→v1 migration story now lives ONLY in ADR-001 + this changelog;
  `README.md`, `SKILL.md`, `CLAUDE.md`, `STATUS.md`, and `docs/LEARNINGS.md` trimmed to
  one-line pointers. `CLAUDE.md`/`STATUS.md` no longer claim "v1.0 shipped / v1.1 candidates"
  as the current state.

### Added — missing/broken artifacts fixed

- **`assets/collab-repo/manifest.example.yaml`** — realistic worked example of the
  `manifest.schema.md` contract (two interactive dev personas + librarian, two-repo pattern).
- **`agents/__DEV__/persona.yaml` is a real template** — was a verbatim copy of the
  `tests/examples/tess` fixture (hardcoded `persona: Tess`); now uses the same
  `{{PLACEHOLDER}}` tokens as its sibling `AGENT.md`.
- **Archetype parity (closes an ADR-001 §10.8 deferred item):** `persona.yaml` templates for
  `librarian`, `__AUTONOMOUS_EVENT__`, and `__AUTONOMOUS_CRON__` alongside their `AGENT.md`s,
  capability sets drawn from the frozen v1 vocabulary. `persona.schema.md`'s "these archetypes
  only exist as legacy AGENT.md templates" caveat replaced with the supported-archetype table.
- **`docs/notes/CORRECTION-wibey-vs-codepuppy.md`** and **`docs/notes/code-puppy-capability-map.md`**
  — reconstructed stubs (originals were cited by `capability-vocab.v1.md` and the code-puppy
  adapter since v1.0 but never committed; marked as reconstructed).

### Added — July-2026 ways-of-working (ADR-002; field-proven on badminton-analyzer)

- **`docs/adr/ADR-002-ways-of-working-2026-07.md`** (accepted 2026-07-22) — decisions + evidence.
- **Emitted `CONVENTIONS.md`:** single-GitHub-account constraint as a stated first principle
  (every gate enforced by persona capability, never GitHub perms); "everything material gets
  a handoff" (findings, decisions, corrections; numbers are proposed to the Librarian, never
  self-assigned); machine-local persona-state convention (`~/.claude/agent-state/` analog +
  snapshot-restore).
- **Emitted `COORDINATION.md`:** Lock pattern is now lock-via-open-PR + `lock:*` labels + a CI
  guard (CODEOWNERS explicitly rejected — no enforcement without branch protection); Owner
  pattern is an evidence gate; new "Review and merge" section (SHA-bound Reviewer verdicts,
  Merger preconditions); persona.yaml CI validation documented.
- **Reviewer + Merger persona archetype templates** (`agents/__REVIEWER__/`,
  `agents/__MERGER__/`, each `persona.yaml` + `AGENT.md`): adversarial fresh-context reviewer
  publishing SHA-bound verdict comments; merger holding the project's only `merge_pr` as a
  precondition gate.
- **Librarian template corrections** (ADR-002 §6): `open_pr` allowed; event-triggered
  reconcile preferred with cron as backstop.

### Changed — real tests + CI

- **Adapters carry a normalized machine-readable capability map** (`capability-map:v1` marker
  in each `adapters/*/HYDRATE.md`): one row per frozen v1 verb — class, runtime-neutral
  grants category, runtime tools, deny-enforcement claim. The claude/code-puppy maps also gain
  rows for `merge_pr`/`push_main`/`force_push`/`edit_other_personas` (needed now that merger
  and librarian archetypes can ALLOW them).
- **`tests/bi_runtime_accept.py` rewritten** — it previously re-implemented the
  capability→tool mapping in Python and tested itself (tautological). It now PARSES the
  actual HYDRATE.md tables + `capability-vocab.v1.md` and asserts: every v1 verb mapped in
  every adapter; tess/rex fixtures hydrate to an equivalent contract across adapters
  (identity, grants, denies, whole-tool denial honoring); enforcement-tier claims consistent
  (generic all-instructed; Tier-3 adapters enforced exactly for whole-tool verbs). Now
  stdlib-only (no PyYAML).
- **`tests/lint_repo.py` (new, stdlib):** unfilled `{{placeholder}}` tokens outside template
  dirs; dead relative markdown links repo-wide; fixture-name leaks ("Tess"/"Rex") in shipped
  templates; plugin.json ↔ SKILL.md version sync.
- **`.github/workflows/ci.yml` (new):** runs both tests with plain python on push + PR.
- **code-puppy adapter worked example** re-anchored to the `tests/examples/tess` fixture and
  de-named (fixture display names no longer appear in shipped templates); its stale v0 verb
  list (`write_findings`/`write_handoff`) corrected to the v1 `write_path` form.
- **`CLAUDE.md` / `CONTRIBUTING.md`** test instructions updated (`uv run --with pyyaml` no
  longer needed).

## [1.3.0] — 2026-06-12

The first-real-audit-feedback release. v1.2.0 shipped the `multi-agent-audit` skill and Iris ran it against GardenTwin within hours; the audit's own write-up identified 13 substantive failures + a missing timeline feature. v1.3 closes all 13 and adds the timeline. Self-validating loop completed in <24h.

### Added — `multi-agent-audit` skill v1.3 (closes all 13 v1.2.0 findings + timeline feature)

#### Multi-substrate Agents lens (Finding #1)

The biggest v1.2 framing flaw was overweighting the `git log` lens for the Agents drift dimension. v1.3 codifies the multi-substrate rule in `references/drift-analysis.md` and `references/bootstrap-adapter.md`:

- **Agents identity** is mined from **five substrates** (GitHub `agent-*` labels, vault `_handoff/` `from:`/`for:` fields, dev-log/EOD/session-log frontmatter, optional persona-prefix commits, and `git log` as a last-resort fallback). Git-log identity collision is the *rule* for single-human multi-agent projects, NOT pathological drift.
- `bootstrap-adapter.md` now ships a per-substrate presence vector + operationally-present threshold.

#### Conv-commits filter (Finding #8)

`scripts/collect_git_metrics.sh` now defaults `CONV_COMMITS_FILTER=1` — Conventional Commits keywords (`feat`/`fix`/`docs`/`chore`/`refactor`/`test`/`ci`/`style`/`perf`/`build`/`revert`) bucket into a new `commits_by_conv_commit_type` field rather than polluting `commits_by_persona_prefix`. New `PERSONA_PREFIXES` env supports an explicit allowlist; everything else goes to `commits_by_other_prefix`. Smoke-tested.

#### Snapshot schema v1.0 → v1.1 — `addenda:` + `auditor_independence:` (Findings #3, #6)

`references/confidence-and-trends.md` defines schema v1.1 (additive — old snapshots still readable):

- **`addenda:` array** on the snapshot is the ONE allowed edit to a shipped point-in-time record. `addenda[*].revised_values` overrides any body field via dot-path; `trend_reader.py` applies them automatically before computing deltas.
- **`audit_run.auditor_independence`** flag captures whether the auditor is itself a participant in the audited project. Renderer surfaces this as a callout banner. Required starting v1.3; surfaces conflict-of-interest in §11 Methodology.

#### Weighted operational-fidelity formula (Finding #12)

`references/metric-taxonomy.md` adds the optional weighted formula. Default per-dimension weights: Guardrails 2.0, Reviewers 1.5, Agents/Autonomy/Routing/Backlog 1.0 each, Rituals 0.5. Equal-weight remains the default; weighted is opt-in.

#### Timeline feature (new — user request)

A new §9.5 Timeline section in the markdown report + horizontal SVG block in the HTML dashboard, surfacing the **important events** in the audit window (releases, ADR creations, roster changes, CONVENTIONS/COORDINATION changes, incidents, audit snapshots, large features).

- **`references/timeline.md`** (new) — event taxonomy, detection rules per type, importance heuristic 1–10, output formats.
- **`scripts/extract_timeline.py`** — detector for 8 event types from a code repo + optional coordination/vault path. Importance scoring with adjacency-aware label staggering. Emits markdown or JSON.
- HTML SVG in `assets/report-template.html`: markers colored by type and sized by importance; week-tick axis; legend; labels for importance ≥7.

#### Five Python helpers — stdlib-only (Findings #4 #5 #9 #10 #11)

- **`scripts/trend_reader.py`** — walks `snapshots/`, applies `addenda[*].revised_values`, computes deltas on the canonical trend metrics, emits §10 Trend markdown OR JSON. Handles single-snapshot, schema mismatch, window-size mismatch gracefully.
- **`scripts/compute_centrality.py`** — Brandes' betweenness centrality on the coordination network (handoffs + optional reviews/merges). SPOF flag at 2.5× mean ratio. **Smoke-test against the vault's handoff graph produced Iris ratio 4.7× — sharper than the v1.2.0 hand-waved 2.1× estimate**, demonstrating the script generates findings the human-driven audit missed.
- **`scripts/parse_coverage.py`** — auto-detects Istanbul / LCOV / Cobertura formats; optional `--baseline` for delta computation; normalized output schema.
- **`scripts/persona_attribution.py`** — joins `agent-*` claim labels → PRs closing those issues → files touched per persona. The v1.3 fix for the v1.2.0 identity-collision finding using the multi-substrate lens.
- **`scripts/extract_timeline.py`** — see Timeline feature above.

#### HTML dashboard renderer (Finding #2 — "HTML dashboard wasn't produced")

- **`scripts/render_report.py`** (new, ~350 lines, stdlib) — fills the template's 18 simple `{{X}}` placeholders + 10 `<!-- INSERT:X -->` block markers; auto-detects template location relative to the script; injects a single JSON `data` object for the Chart.js script block (no inline mustache).
- **`assets/report-template.html` rewritten** — mustache-style loops replaced with INSERT markers (renderer-fillable, no template engine dep). Adds: per-persona scorecards grid, timeline SVG section, auditor-independence callout, false-win callout, addenda card.

#### Short-form executive-summary mode (Finding #13)

- **`references/short-form-mode.md`** — spec + markdown/HTML templates.
- **`scripts/render_short.py`** — stdlib renderer. Markdown: ~1 KB. HTML: ~4 KB (no Chart.js dependency). Applies addenda like the full renderer.

#### Subagent isolation smoke test (Finding #10 — "subagent-isolation test didn't happen")

- **`tests/subagent_isolation_smoke.md`** — runbook for verifying the `project-auditor` subagent's read-only contract. Static checks + manual runtime tests (Edit-injection refusal, destructive-shell refusal, audited-repo-unchanged verification). Honest about tool-enforced vs instruction-enforced layers.
- **`tests/verify_readonly_contract.sh`** — automated static portion: 6 checks (subagent file exists, tools list correct, Edit absent, no destructive `gh api -X` in scripts, no destructive `git`/`gh` in `.sh` code or `.py` subprocess calls, SKILL.md retains read-only language). All 6 pass on the v1.3 skill.

#### Coverage-parser documentation (Batch 2 companion)

- **`references/coverage-parsers.md`** — documents `parse_coverage.py` usage, supported formats, project-type-specific discovery rules, baseline-vs-current workflow, recommended remediation when reports are absent.

### Changed — meta-docs for v1.3

- **`SKILL.md`** — inputs-to-confirm checklist gains independence flag, weighting choice, timeline-yes/no. File inventory updated for the v1.3 layout (scripts/, tests/).
- **`STATUS.md`** — v1.3 marked shipped; v1.4+ candidates updated.
- **`README.md`** — sister-skill section mentions v1.3 enhancements.
- **`.claude-plugin/plugin.json`** — version 1.2.0 → 1.3.0; description mentions short-form mode + timeline feature.
- **`skills/multi-agent-audit/.gitignore` (new)** — prevents accidental `__pycache__/` tracking.

### Validation

The v1.3 skill running on its own coordination substrate (vault handoffs) already produced findings sharper than the v1.2 human-driven audit. Re-audit of GardenTwin with v1.3 is the formal validation step; first opportunity for trend-mode-with-overrides to fire on a real project.

## [1.2.0] — 2026-06-12

### Added — `multi-agent-audit` skill + `project-auditor` subagent (sister skill to `agent-project-bootstrap`)

New skill at `skills/multi-agent-audit/` for grading multi-agent software projects against an evidence-based rubric. Sister to `agent-project-bootstrap`: bootstrap **builds** multi-agent projects; multi-agent-audit **grades** them. **Read-only by construction.** Headline metric: **INTERVENTION TAX** = human touches per autonomous task. Framework-neutral (works on `agent-project-bootstrap`, CrewAI, LangGraph, AutoGen, Copilot agents, custom loops); two-layer (universal WHAT-to-measure + per-layout WHERE-it-lives discovery).

- **`skills/multi-agent-audit/SKILL.md`** (326 lines) — orchestrator: read-only principle, two-layer framework-neutral design, Steps 0/0.5/1/3/4 workflow, inputs-to-confirm checklist, output-location convention (collab-repo `audit/` if exists, else `~/Workspace/audit-reports/`), invocation paths for Claude Code (subagent + direct) and code-puppy (read SKILL.md by path).
- **`agents/project-auditor.md`** — Claude Code subagent. Tool allow-list `Read, Grep, Glob, Bash, Write` (no `Edit`); `Write` only for the report file outside the audited repos. Refuse-to-fix policy explicit ("while you're in there, can you also..." → no).
- **`references/discovery.md`** — Step 0 procedure: declared roster sources (in priority order: `actors.yaml` → `manifest.yaml` → `agents/<name>/persona.yaml` → `AGENT.md` → CONVENTIONS.md), backlog source detection, coordination substrate, autonomy triggers, declared guardrails; layout-family heuristics (bootstrap v1.x / v0.x / vault-project / CrewAI / LangGraph / AutoGen / Copilot / custom); default 90-day window.
- **`references/actor-resolution.md`** — Step 0.5 inventory: enumerate from ALL sources (git committers + PR authors + PR REVIEWERS + mergers + CI bots/Apps + declared roster + coordination substrate); classify `human | autonomous | hybrid`; resolve N identities → 1 canonical actor (persona-prefix wins over email); non-committing-agents special case.
- **`references/drift-analysis.md`** — DUAL-LENS rule (INTENDED | ACTUAL | GAP + confidence) across 7 dimensions (agents / autonomy / reviewers / guardrails / routing / backlog / rituals); the load-bearing **enforced-vs-instructed** distinction; **operational fidelity** formula 0.00–1.00 with four interpretation bands; three drift archetypes (declared-not-operationalized, observed-undeclared, instructed-only-vs-enforced).
- **`references/metric-taxonomy.md`** — 7-category universal metric definitions (Throughput / PR review / Autonomy split + INTERVENTION TAX / Coordination + Network / DORA + flow / Quality + rework / Guardrail + ritual efficacy); per-axis 1–5 scoring rubric; **score-rollup-without-collapse** rule (do NOT compress 7 axes into a single number; name the failure-mode pattern instead).
- **`references/platform-integrations.md`** — read-only gh/git queries for every metric; explicit `gh api` GET-only enumeration; HTTPS-clone rule; pagination/sampling guidance; explicit don'ts (no `-X POST/PUT/PATCH/DELETE`, no `git commit/push/tag/rebase/merge/reset`).
- **`references/advanced-metrics.md`** — DORA four + extensions (merge-gate wait, WIP); network analysis with betweenness centrality + single-point-of-failure heuristic (top centrality > 2.5× mean); review/handoff/merge edge taxonomy.
- **`references/confidence-and-trends.md`** — confidence labels (`measured | inferred | not measurable`); full snapshot JSON v1.0 schema with worked example; trend-mode delta computation; window normalization rules (rate vs count metrics).
- **`references/bootstrap-adapter.md`** — agent-project-bootstrap v1.x layout adapter: exact mining commands for `manifest.yaml`, `agents/<slug>/persona.yaml`, `_handoff/`, `decisions/`, `findings/`, `wiki/`; commit-prefix attribution; enforced-vs-instructed cross-reference table; non-committing-agent reminder (Iris librarian, gh-actions PR review bots).
- **`references/report-template.md`** — markdown audit-report skeleton with 12 sections; placeholders only — every audit fills the same shape.
- **`assets/actors.example.yaml`** — declared-roster template; supports human/hybrid/autonomous classes, identity-resolution rules, declared guardrails, declared rituals, and an explicit `committing: false` marker for non-committing agents.
- **`assets/report-template.html`** — self-contained flat HTML + Chart.js dashboard template (stone/emerald palette matching TrellisIQ brand): verdict card, drift table, headline cards (intervention tax / autonomy donut / DORA / fidelity), per-persona bars, throughput trend, score radar, agent inventory table, ranked-opportunities list, trend section (renders only when ≥2 snapshots exist), methodology + caveats.
- **`scripts/collect_git_metrics.sh`** — read-only bash script that produces machine-readable JSON: commits-by-canonical-actor (persona-prefix honored), reverts/hotfixes/fixups, lines-by-author, cadence (active days), large-commit proxy (≥20 files = `git add -A` heuristic). Refuses to run inside the audited repo (working-directory guard); uses `git -C <repo>` exclusively.

**Status:** scoping → built. v1.2.0 will ship this skill alongside `agent-project-bootstrap`. First intended audit target: **GardenTwin** (real product with longest multi-agent history, especially timely given the 2026-06-10 workforce reduction — a before/after audit will quantify the intervention-tax impact). Distribution: personal use for now.

### Added — v1.0 close-out: §10.2 self-hosting outcome notes + §10.2/§4.6 docs

- **`references/v1-self-hosting-notes.md` (new)** — the comprehensive §10.2 "empirical backbone"
  writeup: which capability verbs surfaced from observed need, where the spec held, where it bent
  (`write_path` collapse, `pull_both_repos`→`sync_repos`, F7/F8), and what was discarded as YAGNI.
  Companion to the short `docs/LEARNINGS.md` index.
- **ADR-001 §4.6** — added a caption clarifying the "Resulting repo shape" diagram is the
  *emitted project's* structure (root `canon/` + `adapters/`), not the skill repo's. Resolves the
  long-standing adapter-location ambiguity.
- **`USING-WITH-CODE-PUPPY.md`** — added a "Vault commit / `/vc` on code-puppy" section (the two
  equivalents: the emitted `/vc-<slug>` command, or describing the workflow in plain language).
  *Reconciled from PR #15, which is now closed.*
- **`STATUS.md`** — v1.0 close-out marked complete (§10.2 + adapter-location done; Step 2 → `[x]`).

## [1.1.1] — 2026-06-08

Documentation-only release. Pulls the user-facing docs (README, `SKILL.md`) forward to the
runtime-agnostic v1.0/v1.1 architecture, adds the required "install canon + adapters" step to
`ORCHESTRATE.md`, and relabels the forward backlog `v1.1+` → `v1.2+` now that v1.1 has shipped.
No behavior or template-logic change.

### Changed — relabel the forward backlog `v1.1+` → `v1.2+` (v1.1 shipped)

- v1.1 is shipped, so the deferred-items backlog is now "v1.2+ candidates" (was the stale
  "v1.1+ candidates"). Updated `STATUS.md` (section heading + 2 internal refs), `CLAUDE.md`
  (versioning note), and `references/persona.schema.md` (the archetype-support pointer). Status
  sync only.

### Changed — reconcile user-facing docs to v1.0/v1.1 (documentation only)

A new-user doc review found the older user-facing layer (README, `SKILL.md`) had not been pulled
forward to the runtime-agnostic architecture. No behavior change — docs/templates only.

- **README** — the *Runtime support* table now shows **Claude Tier 3** (v1.1 enforced subagents),
  not just code-puppy; added a "Two generations — which path to use" section distinguishing the
  runtime-agnostic path (`START`/`ORCHESTRATE`/`PARTICIPATE` + `persona.yaml` + adapters) from the
  legacy v0.3.x emit modes; clarified `/plugin install` (URL or local clone).
- **`SKILL.md`** — bumped frontmatter `0.3.2 → 1.1.0`; **fixed the canonicality banner** (it
  claimed "vault is canonical, repo is a snapshot" — sunset since v1.0; now repo-canonical, matching
  `CLAUDE.md`); added a "Two paths" section so an invoked skill knows the runtime-agnostic
  entrypoints exist; corrected the stale "cron targeted for v0.4.0" note (shipped v0.3.2); updated
  the File manifest to list the v1 canon/adapters/entrypoints.
- **`ORCHESTRATE.md`** — added the required **"Install the canon + adapters into the project"**
  step; the entrypoints/adapters reference `canon/…` and `adapters/<runtime>/…` paths that no emit
  step previously created, which would have left future joiners pointing at missing files.
- **`persona.schema.md`** — added an **Archetype support** note (only `dev` is rendered
  end-to-end by v1 adapters; `autonomous-*`/`librarian` remain legacy `AGENT.md` templates) and
  surfaced the optional `runtime.adapters` override in the example.
- **`STATUS.md`** — added v1.1+ candidates: archetype parity in `persona.yaml`, native code-puppy
  skill packaging; noted `join-collab-project` shares vault-project's re-integration gap.
- **`.claude-plugin/plugin.json`** — modernized the plugin `description` from the v0.3.x
  "Claude Code project / three modes" framing to the runtime-agnostic v1 reality (multi-runtime,
  `persona.yaml` + adapters; legacy modes still listed).

## [1.1.0] — 2026-06-04

The Claude Tier-3 milestone. The Claude adapter now renders native subagents with an enforced
tool allow-list, plus the v1.0 close-out work. First properly cut release since v0.3.2
(plugin.json bumped 0.3.2 → 1.1.0; forward-only — the partial v1.0.0/v1.0.1 tags are left as-is).

### Added — `USING-WITH-CODE-PUPPY.md` quickstart

- New top-level guide for running the bootstrap on code-puppy, which does not auto-discover the
  Claude skill format. Documents the invoke-by-file-path flow (START → ORCHESTRATE → code-puppy
  adapter), the launch-from-project-root requirement, a verified file map, and the Tier-3
  enforcement note. README links to it from the Installation section.

### Added — Claude Tier-3 subagent rendering (ADR-001 §10.8; v1.1 feature)

- **`adapters/claude/HYDRATE.md` now renders BOTH tiers from one configurable adapter** (not
  two folders):
  - **Tier 3 (new)** — hydrates a persona into a native Claude **subagent** at
    `.claude/agents/<slug>.md` with an **enforced** `tools:` allow-list. Whole-tool denials
    become real (a read-only persona gets `Read, Grep, Glob` only; `Write`/`Edit`/`Bash` are
    absent and unavailable). Sub-tool denials (e.g. allow `open_pr`, deny `merge_pr`) stay
    instruction-only in the body — same honesty boundary the code-puppy adapter documents.
  - **Tier 2** — unchanged `CLAUDE.md` rendering (capabilities instructed).
  - Capability → Claude tool mapping for the enforced layer: `read_*`→`Read,Grep,Glob`;
    `write_code`/`write_path`→`Write,Edit`; `open_pr`/`run_tests`→`Bash`.
- **Tier selection via a runtime-neutral `adapters.<runtime>` config envelope** (keeps the
  canonical schemas free of runtime tool names):
  - `manifest.adapters.claude.tier` — project default (`auto` | `2` | `3`, default `auto`).
  - `persona.yaml > runtime.adapters.claude.tier` — per-persona override.
  - `auto` self-assesses subagent support and degrades to Tier 2 when the session can't host
    subagents (CI / constrained sub-sessions). Explicit `2`/`3` always wins.
- **Schemas** (`manifest.schema.md`, `persona.schema.md`) gain the optional `adapters.<runtime>`
  / `runtime.adapters.<runtime>` override envelope (v1.1; additive, forward-compatible).
- **`tests/bi_runtime_accept.py`** extended: the same harness now asserts code-puppy (Tier 3) ≡
  Claude Tier 2 ≡ Claude Tier 3 produce an identical behavior contract — not a second
  top-level test. Both fixtures (dev `tess`, read-only `rex`) pass.
- **ADR-001** §10.5 / §10.8 updated (Tier-3 shipped; config-location rationale recorded).

### Fixed — correct the bi-runtime test invocation in docs

- The documented command `python tests/bi_runtime_accept.py` fails with `ModuleNotFoundError:
  yaml` on a stock interpreter. Corrected `CLAUDE.md` (release workflow + Testing section) and
  `CONTRIBUTING.md` to `uv run --with pyyaml python tests/bi_runtime_accept.py`, matching the
  harness's own dependency need.
- Fixed the harness docstring, which still pointed at the pre-move path
  `wip/acceptance/bi_runtime_accept.py`, to the current `tests/bi_runtime_accept.py`.

### Added — `docs/LEARNINGS.md` (minimum-viable lessons index)

- **`docs/LEARNINGS.md` (new)** captures the ADR-001 §10 dogfood lessons (`L1`–`L3`) and proven
  rules (`Proven #1`–`#2`). Resolves four previously dangling references — in
  `references/capability-vocab.v1.md` (proven #2, L3), `adapters/claude/HYDRATE.md` (L3), and
  `adapters/generic/HYDRATE.md` (L3). Minimum-viable by design; the comprehensive §10.2
  self-hosting outcome notes remain a tracked v1.0 close-out item in `STATUS.md`.

### Changed — de-Claude the emitted `COORDINATION.md` (ADR §10.6, finishes Step 6)

- Removed the three runtime-isms from the emitted `COORDINATION.md` template, mirroring PR #7's
  treatment of `CONVENTIONS.md`:
  - **Session-start checklist** — replaced the `git pull` / `grep` / `gh issue list` bash blocks
    with intent-level steps that point at `adapters/<runtime>/HYDRATE.md` for concrete syntax and
    `references/capability-vocab.v1.md` for the verbs.
  - **Ticket lifecycle** — abstracted the `gh issue edit … --add-assignee/--add-label`
    self-assignment to backlog-source language (`gh` is one runtime's shell, not the canon).
  - **Async handoff protocol** — generalized the Iris-specific "personal librarian" paragraph to
    any librarian-equivalent persona (`for: librarian`), and dropped the Obsidian-specific "vault"
    wording. Runtime-neutral, matching the canon. Cosmetic for existing scaffolds (no behavior
    change).

### Changed — meta-docs refresh for v1.0 development surface

- **`CLAUDE.md` rewritten** to reflect the post-ADR-001 reality: this repo is the canonical home and active development surface for v1.0+; the v0.x "vault canonical, repo snapshot" rule is sunset. Updates repo layout, persona expectation for a fresh agent landing in the repo, and release workflow.
- **`STATUS.md` (new)** at repo root tracks ADR-001 §10 progress (most of v1.0 shipped; `COORDINATION.md` de-Claude + §10.2 self-hosting outcome notes still open) and v1.1 candidates (Claude Tier-3 subagents, vault-project re-integration, cron live-wiring, additional adapters). Update on every PR that ships a step.
- **ADR-001 body header** corrected: `Status: Proposed` → `Status: Accepted (2026-05-30)`. Frontmatter already said accepted; this fixes the internal inconsistency.
- **`CONTRIBUTING.md`** adds a **"Documentation is part of every PR"** section codifying the rule that affected ADRs, `CLAUDE.md`, `README.md`, `CHANGELOG.md`, and `STATUS.md` updates land in the same PR as the code change — never as a follow-up. Surfaces explicit checklist + cosmetic-changes exception. Also notes the `uv run --with pyyaml python tests/bi_runtime_accept.py` gate for adapter / spec / canonical-contract changes.

## [1.0.1] — 2026-06-03

### Changed — README reflects the v1.0 runtime-agnostic architecture

- Rewrote the intro (no longer "a Claude Code plugin" only) and added a **Runtime support**
  section documenting the capability ladder, adapters, neutral entrypoints, and the canonical
  spec files. Points to ADR-001. Docs-only; no behavior change.

## [1.0.0] — 2026-06-03

### Added — runtime-agnostic spec + adapters (ADR-001 implementation, v1.0)

Implements ADR-001 (§10 phased rollout). The bootstrap pattern is no longer Claude-only: a
single runtime-neutral `persona.yaml` hydrates working personas on any runtime, at the highest
fidelity that runtime supports. Every capability verb and schema field was coined during real
adapter work and exercised on a real dogfood project (55%→100% coverage) — nothing speculative
(YAGNI).

- **Neutral entrypoints** in `assets/collab-repo/`:
  - `START.md` — front door; routes on directory state + documents runtime keys (§7.3).
  - `ORCHESTRATE.md` — Role 1 (bootstrap a new project), runtime-neutral.
  - `PARTICIPATE.md` — Role 2 (join a project) + the 3-tier capability ladder.
- **Adapters** in `assets/collab-repo/adapters/<runtime>/HYDRATE.md` (the only runtime-specific
  surface; Open/Closed for runtimes):
  - `generic/` — Tier-1 fallback (MANDATORY): re-read `persona.yaml` each turn, self-enforce.
  - `code-puppy/` — Tier-3: maps capabilities to enforced JSON sub-agent tool allow-lists.
  - `claude/` — Tier-2: renders `persona.yaml` → `CLAUDE.md` + `/vc`, mirroring v0.3.x shape.
- **Canonical spec docs** in `references/`: `capability-vocab.v1.md` (frozen 10-verb API),
  `persona.schema.md`, `manifest.schema.md` (relative paths + configurable backlog source).
- **`agents/__DEV__/persona.yaml`** — machine-truth companion to the existing `__DEV__/AGENT.md`
  (yaml canonical, md derived).
- **`tests/bi_runtime_accept.py`** — bi-runtime acceptance harness: proves one `persona.yaml`
  yields an identical behavior contract (identity, capabilities, guardrails) on code-puppy +
  Claude. Passes for both a `dev` and a read-only `reviewer` persona.

### Compatibility

- Purely additive. Existing v0.3.x scaffolds and invocations are unaffected.
- Claude native sub-agents (Tier-3 at home) deferred to a follow-up (ADR §10.8).

### Changed — de-Claude the emitted `CONVENTIONS.md` (ADR §10.6)

- Replaced the "Tool hierarchy" section's runtime tool names (`Read`/`Write`/`Edit`/`Bash`,
  `gh` CLI) and the Obsidian/MCP note with capability-level language + a pointer to
  `adapters/<runtime>/HYDRATE.md` and `references/capability-vocab.v1.md`. The emitted
  convention doc is now runtime-neutral, matching the canon. Additive/cosmetic for existing
  scaffolds (no behavior change).

## [0.3.2] — 2026-05-29

Same-day follow-up to v0.3.1, closing out the remaining items from an early
bootstrap-genesis decision (now superseded by [ADR-001](docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md)). All v0.3.1 invocations still work unchanged.

### Added — runtime-aware cron + FAILOVER templating

- **`runtime:` taxonomy** for AGENT.md frontmatter, replacing the older `schedule-skill` / `github-actions` strings. Supported values:
  - `launchd-cron` — macOS launchd; per-runner machine; laptop must be on.
  - `systemd-timer` — Linux systemd timer; per-runner machine; laptop must be on.
  - `cloud-routine` — Anthropic-hosted `/schedule` routine; always-on.
  - `gh-actions-cron` — GitHub Actions scheduled workflow; always-on.
  - `gh-actions-event` — GitHub Actions on PR / event webhook (for `__AUTONOMOUS_EVENT__` personas).
  Each AGENT.md template now carries a comment block documenting the taxonomy inline.
- **Per-runtime FAILOVER cron section snippets** under `assets/collab-repo/_failover-cron-sections/`:
  - `launchd-cron.md` — generated wrapper + plist; `launchctl bootstrap` / `bootout` commands.
  - `systemd-timer.md` — generated `.service` + `.timer`; `systemctl --user` lifecycle.
  - `cloud-routine.md` — `/schedule` invocation; per-account billing notes.
  - `gh-actions-cron.md` — workflow file pattern; PAT secret requirements.
  The skill picks the right snippet at scaffold time based on the persona's `runtime:` field and substitutes it into the templated `agents/<persona>/FAILOVER.md`'s `{{FAILOVER_CRON_SECTION}}` placeholder.
- **`workspace-template/setup.sh` gains opt-in cron stub generation** behind `REGISTER_CRON=yes`:
  - `launchd-cron` → generates `~/Workspace/<project>/<persona>/com.<project>.<persona>.plist` + wrapper script. Stub is generated, NOT loaded; you load it manually via `launchctl bootstrap` after reviewing the schedule. Idempotent (skips if plist already exists).
  - `systemd-timer` → generates `.service` + `.timer` + wrapper. Same opt-in-load pattern.
  - `cloud-routine` → prints the `/schedule` command to run in Claude Code.
  - `gh-actions-*` → no-op locally (cron lives in the code repo workflow).
  Generation happens only when `REGISTER_CRON=yes` is set; default behavior is workspace-only.

### Changed

- **`agents/librarian/FAILOVER.md`** "Enable the cron on your machine" section is now `{{FAILOVER_CRON_SECTION}}` (per-runtime). The skill fills it from the matching `_failover-cron-sections/*.md` snippet.
- **`agents/__AUTONOMOUS_EVENT__/AGENT.md`** frontmatter `runtime` field is now `gh-actions-event` (was `github-actions`).

### Compatibility

- v0.3.1 invocations work unchanged. Existing collab repos do not need to migrate.
- The old `runtime: schedule-skill` and `runtime: github-actions` values still parse — the new taxonomy is additive.

### Why generation but not auto-load

Cron registration is the kind of action where "almost right" is much worse than "explicitly opt-in." DST drift, double-registration across two laptops, accidental cron-from-the-wrong-runner — these are real failure modes. The stub-and-load split makes the dangerous step explicit and human-reviewed. Auto-load may land in a later release once we've gathered usage data on whether the explicit step actually catches errors in practice.

### Validated against

VANAR's launchd-cron pilot (Vikram's machine, daily 15:00 PT). The generated plist + wrapper produced by v0.3.2's `setup.sh REGISTER_CRON=yes` matches VANAR's hand-rolled artifacts byte-for-byte (modulo the manual TODO timestamp adjustment).

## [0.3.1] — 2026-05-29

Patch release codifying lessons from VANAR's pilot day (first real use of v0.3.0). All additions are template content; no interface changes. v0.3.0 invocations still work unchanged.

### Added — `collab-repo-project` mode emissions

- **`QUICKSTART.md`** — agent-led onboarding doc as a first-class artifact. Contains the canonical "Onboard me to {{PROJECT_NAME}}" prompt that human collaborators paste into Claude Code / code-puppy / their AI coding agent. ~30 min to first PR vs. ~45 min for the manual BOOTSTRAP.md path.
- **`wiki/log.md`** — genesis log entry seeded at scaffold time. Establishes the `find -newer wiki/log.md` timestamp baseline so the Librarian's first cron run isn't a silent no-op.
- **`wiki/index.md`** — standard catalog scaffold (log, entities, concepts, sources sections with placeholder descriptions).
- **`_handoff/{{DATE}}-bootstrap-to-librarian-genesis.md`** — one-time genesis handoff for the Librarian. Acknowledges the wiki has been seeded; first run flips it to `status: done` and the standard cycle takes over.
- **`workspace-template/{CLAUDE.md, AGENTS.md, setup.sh}`** — runtime-portable workspace bootstrap. `setup.sh <persona-slug>` clones both repos into `~/Workspace/{{PROJECT_NAME}}/<slug>/`, configures per-repo git identity, and drops the thin CLAUDE.md (Claude Code) + AGENTS.md (code-puppy and similar) pointers. Cron self-registration deferred to v0.4.0.

### Added — template content updates

- **CONVENTIONS.md `_handoff/` lifecycle:** new "Push policy" paragraph carving out `_handoff/` files as direct-push-permitted on `main` (they're coordination metadata, not substantive changes). Resolves a doc-fork that surfaced when persona AGENT.md "PR only" rules clashed with BOOTSTRAP "push origin main" guidance for the joined handoff.
- **BOOTSTRAP.md Step 3 (rewritten):** consolidated "fire up your VANAR workspace" with the new `~/Workspace/{{PROJECT_NAME}}/<your-slug>/` folder pattern (both repos in one folder) + an optional AI-agent bootstrap sub-section (CLAUDE.md / AGENTS.md template for Claude Code / code-puppy users).
- **BOOTSTRAP.md Step 6 (new):** "Announce yourself to the Librarian" — the joined collaborator drops a `_handoff/` so the Librarian picks them up on the next run and updates the wiki personas page.
- **Root `CLAUDE.md`:** `QUICKSTART.md` promoted to item 1 in "Read these first" (fast path); `BOOTSTRAP.md` becomes item 2 (deeper reference).
- **`agents/__DEV__/AGENT.md`:** optional two-clone note for project owner — owners often have a "library copy" clone (used by their personal Iris) separate from their dev working copy. Conditionally rendered.
- **`agents/__AUTONOMOUS_CRON__/AGENT.md`** + **`agents/__AUTONOMOUS_EVENT__/AGENT.md`:** new "First-run handling" section telling the persona to look for and process a `_handoff/*-bootstrap-to-*-genesis.md` file before its standard cycle.
- **`agents/librarian/AGENT.md`:** new "Drift checks" section listing concrete things to compare across files (AGENT.md frontmatter `runtime:` vs FAILOVER.md cron section; AGENT.md scope vs CONVENTIONS routing table; AGENT.md cadence vs actual cron file). Librarian surfaces drift; never auto-fixes.

### Compatibility

- v0.3.0 invocations work without changes. Existing collab repos do not need to migrate; v0.3.1 only affects new scaffolds.
- The `mode:collab-repo-project` artifact set is now ~24 files (was 20 in v0.3.0).

### Validated against

VANAR (first project to use the collab-repo-project mode). All v0.3.1 additions were hand-rolled into VANAR's collab repo during 2026-05-29 and validated by the Librarian (Vidya) successfully processing the manual genesis handoff and surfacing drift on her first scheduled cron run.

## [0.3.0] — 2026-05-29

### Added

- **Multi-mode dispatch.** SKILL.md restructured around three modes selected at invocation:
  - `vault-project` — original v0.2.0 behaviour (vault-based five-agent project scaffold), preserved verbatim.
  - `collab-repo-project` — emits a dedicated collab repo for projects with remote collaborators. Implements the "Option A" pattern: collab substrate (conventions, coordination, agent manuals, handoffs, decisions, findings, project wiki) lives in its own GitHub repo, separable from any personal vault.
  - `join-collab-project` — walks a human remote collaborator through cloning an existing collab repo, claiming a persona, setting per-repo git identity, and validating the round trip with a "hello" PR.
- **`assets/collab-repo/` template tree** (16 new files) for the `collab-repo-project` mode:
  - Root: `README.md`, `CONVENTIONS.md`, `COORDINATION.md` (with `## Hot files` section), `CLAUDE.md`, `BOOTSTRAP.md` (collaborator-facing), `BOOTSTRAP-ADMIN.md` (owner-only operations including optional trust-gating).
  - `agents/__DEV__/AGENT.md` — human dev persona template (workspace path, session-start ritual, ADR rules).
  - `agents/__AUTONOMOUS_EVENT__/AGENT.md` — webhook-triggered autonomous persona template (e.g. PR Reviewer, Backtest Runner). Cost ceilings, decision authority, hot-file flagging.
  - `agents/__AUTONOMOUS_CRON__/AGENT.md` — `/schedule`-triggered autonomous persona template (e.g. PM+UAT). Cadence, default runner, failover.
  - `agents/librarian/AGENT.md` + `agents/librarian/FAILOVER.md` — always emitted by default; centralized-with-failover model documented.
  - Subfolder stubs with READMEs: `_handoff/`, `decisions/`, `findings/`, `wiki/`.
- **New reference doc:** `references/collab-repo-design.md` — rationale for the collab-repo-project mode design choices (why a separate repo, why three persona archetypes, why centralized-with-failover librarian, why optional trust-gating, etc.).

### Changed

- `SKILL.md` is no longer a single emit sequence. It's now a dispatcher that documents mode selection, then provides three self-contained mode-specific emit sections. The `vault-project` section preserves v0.2.0 behaviour unchanged — existing usage is unaffected.
- File manifest updated to reflect the new asset tree.

### Compatibility

- v0.2.0 invocations (vault-project mode) work without changes. Existing users do not need to migrate.
- The `mode:` parameter is the new entry point. If unspecified, the skill prompts for mode selection.

## [0.2.0] — 2026-05-27

### Added
- New asset: `assets/commands/vc.md` — the `/vc` slash command for vault commits. Installed to `~/.claude/commands/vc.md` (user-global), available to every Claude Code session. Workflow: check vault state, stage thoughtfully (never `git add -A`), compose a commit message using the canonical `<persona>: <operation> | <description>` convention, commit, push, and verify the push against GitHub. Uses `{{VAULT_PATH}}` placeholder; derives the vault GitHub repo from `git remote get-url origin` so no new placeholder is required.
- SKILL.md: new emit step `3a` documenting the commands copy step; file manifest updated.
- README.md: new "Slash commands" section under *What gets generated*.

## [0.1.1] — 2026-05-22

### Added
- Workspace context files: `CLAUDE.md` (repo orientation + sync rules), `CHANGELOG.md`, `CONTRIBUTING.md`.
- Sync rule documented: vault is canonical, this repo is a release snapshot.

## [0.1.0] — 2026-05-22

### Added
- Initial release of the `agent-project-bootstrap` skill.
- Vault scaffolding templates, workspace scaffolding templates, reference docs.
