# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Published doc pages** — `docs/product-overview.md` and `docs/capability-value-map.md`
  now render as styled pages at `/overview/` and `/value-map/` on the Pages site, in the
  v1 "calm control" treatment shared with the dashboard. The markdown stays the source of
  truth: `dashboard/build_docs.py` (stdlib only) projects it, `./dashboard/build-docs.sh`
  regenerates, and `--check` gates the committed HTML against its source in CI and again
  before every Pages deploy. The site index becomes a nav over all five pages. Docs only —
  no CLI, skill or version change.

### Changed — P2.2 deterministic enforcement: denial becomes structural (plugin 1.20.0 / CLI 0.18.0, `rules_version` 1 → **2**, [ADR-034](docs/adr/ADR-034-deterministic-capability-enforcement.md))

**BREAKING for personas, deliberately.** A persona can no longer write its own
`agents/<slug>/` directory — including its `persona.yaml` — nor any persona's capability
document, nor `.claude/settings.json`. **Changing a capability set is now a PR a human
merges, for everyone, always, including a solo owner.**

The finding that forced it (**G5**, in merged code): the guard hook re-reads
`--persona-file` on *every* invocation, `evaluate_write` made a persona's own spec dir
always writable, and `.claude/settings.json` was an ordinary path. So a persona holding
`write_code` could **grant itself a denied verb, or unwire the hook, in one edit** — and the
next tool call was adjudicated against the document it had just written. Layering
enforcement on a policy the enforced party can rewrite is theatre; every other layer was
conditional on this one.

- **L0 — structural config-path refusal.** New `file_ops.protected_config` /
  `.protected_spec_file` / `.own_spec_dir` rules in `capability-rules.v1.yaml`, applied at
  `evaluate_write` **step 0.5** — above the universal-write allow, because `_handoff`
  matches as a component anywhere in a path. Modelled on the step-0 path escape: **no verb
  unlocks it**, including `edit_other_personas`, so `adjudicated=False` and the event reads
  `unevaluated` (ADR-018 §2). Fenced paths: every `agents/*/persona.yaml`, the acting
  persona's `agents/<slug>/**`, `.claude/settings.json{,.local}`, `.baron-waivers.yaml`,
  `.baron-rules.yaml`, `.barony/allowed_signers` — matched on **trailing** components, so
  the copy inside an emitted runtime kit is covered too.
- **L2 — the `bash -c` class narrowed.** New `commands.wrappers` block: one level of
  recursion into `bash`/`sh`/`zsh`/`dash`/`ksh -c '<payload>'` (optionally behind `env`),
  re-run through **the same evaluators** rather than a second parser. An untokenisable
  payload, or one nested past the cap, is ambiguous and gets conservative-deny **narrowed to
  `merge_pr`/`push_main`/`force_push`** — a persona holding those three sees no change.
- **L3 — the platform layer, reported and never configured.** `baron doctor` gains a tenth
  check, `platform-layer` (**INFO**, never FAIL): branch protection and whether each persona
  has its own push credential. Baron does not create tokens or configure a forge (ADR-007);
  reporting an absent wall is governance, building it is somebody else's layer. The
  branch-protection half is doctor's only networked check and is **opt-in** behind
  `BARON_DOCTOR_PLATFORM=1` so a green run stays reproducible offline. It states, rather
  than blurs, ADR-033 §5: per-persona *signing* keys are not per-persona *push authority*.
- **Proof by invocation — a new opt-in test tier.** `cli/tests/test_live_runtime.py` drives
  a real `claude -p` in a scaffolded temp repo behind a `PATH`-shimmed `git`/`gh` sentinel
  and asserts the denied operation **did not run** — evidence about the world, not about a
  hook being configured. Its **negative control is load-bearing**: the same prompt runs first
  against a persona that *grants* the verb and the sentinel must appear, or the run reports
  **INCONCLUSIVE**, never PASS. Marked `live_runtime`, gated on `BARON_LIVE_RUNTIME=1`,
  excluded from the default job via `addopts`, and run from a manual
  `.github/workflows/live-runtime.yml`.

**Honest status (OD-3):** that tier is **advisory** — an INCONCLUSIVE or failing run does
**not** block a release, and as of this entry it **has not been run**. Its harness *is*
covered in the default job (`test_live_harness.py`), because a silently-broken shim would
make the live test report a false green.

**Deliberately NOT built — `baron init` does not emit `permissions.deny` (OD-2 = NO).** It
would publish a stronger-*looking* posture that `bash -c` still evades, and not
over-claiming is the differentiator. Consequently **G1 is unchanged** (an unwired hook is
still zero enforcement) and the ADR-020 read-verb measurement for `claude` **stands**:
`test_adapter_omission.py` is untouched.

**Bounds that survive, pinned by tests rather than only documented:**
`~/.claude/settings.json` is outside the repo root and invisible to L0 and doctor; a shell
redirect is neither a write-tool call nor a capability verb; `python -c`, `eval`,
base64/`printf` indirection, script files and `xargs` remain uninspected. Credentials are
not revoked. Positioning unchanged: **a policy guard at the agent-tool interface for
cooperating agents, not a security boundary.**

Migration: `rules_version` is negotiated by exact match, so a consumer pinned to an older
`barony` refuses the new artifact rather than mis-enforcing it — upgrade both together. The
artifact filename stays `capability-rules.v1.yaml` (`.v1` names the still-frozen
*vocabulary*, not the table).

## [1.19.0] — 2026-08-14

**The governance release.** Eight plugin versions and eight CLI versions accumulated since
v1.10.0 (2026-08-09) without a tag; this cuts them as one. The through-line is that the
things Barony asserted in prose became things it *checks*: who a persona is (ADR-027), who
approved a commit (ADR-033), whether the merge preconditions hold (ADR-028), whether an
ADR did its prior-art sweep (ADR-029), and — newly, and only advisorily — whether a change
said anywhere what it did.

Grouped below by what it does for a reader, newest first within each group. Every entry
keeps the version markers it shipped under, because the CLI and the plugin are independent
tracks and a reader chasing `barony==0.14.0` needs to find it.

- **Governance & attribution:** signed review verdicts (§ADR-033) and its enrollment-keyed
  default; agent identity and SSH signing (§ADR-027) plus the `baron identity` onboarding
  commands; the mechanized merge gate (§ADR-028); the prior-art gate (§ADR-029).
- **Topology & reach:** the coordination monorepo (§ADR-025), `baron adopt-project`, the
  `baron health` plane fix, `baron export` at a monorepo root and `--wide`.
- **New surfaces:** the persona sidecar (§ADR-026), the `observer` archetype (§ADR-030),
  the `baron memeval` harness (§ADR-031), the fleet dashboard.
- **Process:** the advisory docs-coverage check, and the release gate that now names the
  product docs explicitly.

**Governance record — ratified 2026-08-14.** The owner accepted **[ADR-028](docs/adr/ADR-028-mechanized-merge-gate.md)**
(the mechanized merge gate) and **[ADR-030](docs/adr/ADR-030-observer-archetype.md)** (the
`observer` archetype). Both had shipped while still marked *proposed* — the code has been
live on `main` since CLI 0.11.0 and 0.13.0 respectively — so ratification changes the
**record**, not the behavior, and neither ADR was rewritten. In particular ADR-028 §4's
account of the attribution hole is left standing exactly as written: it is the reasoning
ADR-033 was built on, and an ADR that edits away its admitted gaps after the fact is worth
less than one that leaves them visible. §7 Q4 remains superseded by ADR-033.

This closes the "shipped ahead of its record" gap for both. It does **not** close it for
[ADR-031](docs/adr/ADR-031-governed-memory-eval-harness.md) (`baron memeval`) or
[ADR-015](docs/adr/ADR-015-baron-export.md) (`baron export`), which ship in this release
and remain **proposed** — deliberately, and still worth reading as unsigned.

### Changed — the signed-verdict gate enforces itself once a reviewer is enrolled (plugin 1.19.0 / CLI 0.18.0, [ADR-033 §7 Q1](docs/adr/ADR-033-signed-review-verdicts.md) RESOLVED)

ADR-033 shipped `--require-signed-verdict` **off**, and said why: turning a missing
signature into a refusal is a fleet-wide breaking change, and *a default nobody signed and
a default somebody signed look identical in a diff* (ADR-013 §7.1). It left the question
open for the owner. **Answered 2026-08-14 — approved: default-ON once a reviewer persona is
enrolled, warn-only before enrollment.**

None of the three candidate triggers in §7 Q1 was chosen. A manifest field is a new
configuration surface that drifts from the registry it describes; a flag day breaks
projects on a *date* rather than on a *fact*; `baron doctor` reports readiness without
anybody acting on it. **Enrollment is the trigger** because it is the fact that decides
whether a signature was possible at all — before a reviewer's key is in
`.barony/allowed_signers`, nothing *could* have signed, and refusing would punish a project
for a capability it does not have.

- `merge.resolve_signed_posture()` reads enrollment **at HEAD**, never from the worktree.
  A persona that writes its own registry line into its own worktree has enrolled nothing —
  and if the worktree counted, any persona could flip the fleet's merge posture by editing
  a file it already controls (ADR-027 §2).
- **Both halves must hold:** an enrolled key *and* an `archetype: reviewer` persona behind
  that slug. Either alone leaves nobody who can sign.
- `--require-signed-verdict` / `--no-require-signed-verdict` override in **both**
  directions, so a project mid-migration turns enforcement off without un-enrolling a key.
- The posture **and its trigger** print in the `verdict_signed` detail line on every run.
  §2.2's objection was to enforcement arriving *silently*; it never does.

**The honest bound is unchanged.** Enforcing that a signature is *present* does not make
the verdict *correct* (that stays ADR-024's escape-rate axis), and a hostile workspace
holding the reviewer's key can still sign anything. This closes a coverage gap, not the
trust question — and still only the evidence half of the autonomous merger, not the
authority half. There is still no `baron merge do`.

**Upgrade note.** A project with an enrolled reviewer and unsigned verdicts will start
seeing `baron merge check` refuse. That is the intended change. Either sign verdicts with
`baron review sign`, or pass `--no-require-signed-verdict` while you migrate.

### Added — the docs-coverage check: "docs land with code" stops being only prose (`tests/check_docs_coverage.py`)

`CONTRIBUTING.md` has carried the rule since 2026-06-03 and enforced it by memory. CI now
warns when a PR changes `cli/` or `skills/` but touches neither `CHANGELOG.md` nor
anything under `docs/` — the same move ADR-028 made for the merge gate and ADR-029 made
for the prior-art sweep.

**It is advisory and says so, in the script, in CI, and in `CONTRIBUTING.md`.** It sees
that a file changed, not that the change *describes what shipped*; a one-word edit
satisfies it. Its false positives are legitimate — a refactor or a test-only fix owes no
docs. Claiming to *enforce* documentation on that evidence would be claiming a property it
never measured, which is the failure `dashboard/check_snapshot.py` exists to prevent. It
prints and exits 0; `--strict` blocks, and switching the CI line over is the one-line
escalation to make once there is evidence the warning is ignored rather than answered.

`CLAUDE.md`'s release workflow gains an explicit gate: **`docs/product-overview.md` and
`docs/capability-value-map.md` reviewed** before tagging. Those two go stale in the way
that is hardest to notice — they stay *true* while becoming *incomplete*, which reads as
fine right up until a reader concludes the product cannot do something it has done for
three releases. The workflow also now records the PyPI publish step and states plainly
that tagging, releasing and publishing are **owner** steps run under the owner's own
credentials.

### Added — fleet dashboard on GitHub Pages (plugin 1.18.0, `dashboard/`)

A static, server-less dashboard published from `dashboard/` — three visual treatments (`/v1/`
calm control, `/v2/` editorial, `/v3/` ops wall) rendering one committed JSON snapshot. The
private coordination repo stays private: `dashboard/build-data.sh` runs only read-only `baron`
reporters and writes a sanitised one-way projection to `dashboard/data/fleet.json`, and
`dashboard/check_snapshot.py` fails CI on a leaked path, a leaked credential, or a metric that
claims a number it never measured. See `dashboard/README.md`.

### Added — signed review verdicts: the merge gate proves WHO approved (plugin 1.17.0 / CLI 0.17.0, [ADR-033](docs/adr/ADR-033-signed-review-verdicts.md), **supersedes ADR-028 §7 Q4**)

[ADR-028 §4](docs/adr/ADR-028-mechanized-merge-gate.md) recorded the hole in its own words: *baron
can verify that a `REVIEW:PASS` exists at the current head. It **cannot verify who posted it**. The
dev whose code is under review can post its own `REVIEW:PASS`, and the gate — correctly, given its
inputs — returns exit 0.* A verdict was a PR comment: forge state, unsigned, under one shared login.

The reviewer now **SSH-signs its verdict into the repo**, and the gate verifies that signature
offline — the route ADR-028 §7 Q4 named and preferred, built on ADR-027 §2.3 with **no new key, no
new registry and no new trust root**.

```
.barony/verdicts/pr-<n>-<sha12>.md        the verdict — canonical bytes
.barony/verdicts/pr-<n>-<sha12>.md.sig    ssh-keygen -Y sign, namespace barony-verdict
```

- **`baron review sign --pr N --head <sha> --state PASS|FAIL --persona <slug>`** — writes and signs
  the artifact with the reviewer's own enrolled key. Its first line is the **existing**
  `REVIEW:PASS <40-hex>` contract (ADR-002 §4, ADR-008 §1), so one format is parsed everywhere.
- **`baron review verify --pr N --head <sha>`** — the attribution check alone. No network.
- **`baron merge check`** gains a **`verdict_signed`** precondition, scored right after
  `verdict_at_head`, plus `--require-signed-verdict` and `--code-repo`.

**Four legs, all fail-closed.** The signature verifies against `.barony/allowed_signers`; the
**signed content** binds (repo, PR, sha) — re-derived from the content, never the filename, so a
valid signature cannot be replayed onto another PR by copying the file; the signer is a
`reviewer`-archetype persona (**a dev's key is a real enrolled key** — without this leg it produces
a real verified verdict); and the signer is **not the persona that signed the head commit**
(`%GS`, cryptographic — not the self-asserted git author field). **Reviewer≠author becomes a
property of the repo**, checkable offline, rather than a rule in a persona file.

**Posture — the ADR-027 §7.3 precedent, unchanged.** An *invalid* signature always refuses, in
every posture. A *missing* one warns by default and refuses under `--require-signed-verdict`:
turning absence into a refusal is a fleet-wide breaking change and should be signed, not defaulted.
An unattested pass reports `UNATTRIBUTED` rather than rendering as a clean pass.

**Honest bounds, in the ADR and in the command output.** This is attribution among *cooperating*
agents — a hostile workspace holding the reviewer's key can still sign anything. It does not make a
verdict *correct* (that is ADR-024's escape-rate axis). And it closes the **evidence** half of the
autonomous merger, **not the authority half**: merging still means acting under the owner's token,
so `baron merge check` stays owner-in-the-loop and there is still no `baron merge do`.

The PR comment is **demoted to an index** (ADR-033 §2.3) — the same move ADR-008 §1 made for labels.
`cli/tests/test_signed_verdict.py` (23 tests) drives real `ssh-keygen` and real git signing;
`test_dev_cannot_sign_a_verdict_for_its_own_work` reproduces the ADR-028 §4 failure end-to-end with
genuinely valid signatures throughout, and refuses it.

### Added — `baron identity register|enroll|protect`: the ADR-027 runbook, mechanized (plugin 1.14.0 / CLI 0.14.0)

### Fixed — `baron export` at a coordination-monorepo root reported 0 records (plugin 1.16.0 / CLI 0.16.0, [ADR-032](docs/adr/ADR-032-export-reach-monorepo-and-widened-corpus.md), ACCEPTED)

Run at an ADR-025 monorepo root, `baron export` walked no project subdir and printed
`no records` — while a run inside each subdir returned real counts. Measured on a two-project
fixture: **0 at the root, 2 + 2 in the subdirs**. Same silent-false-zero class as the ADR-025
§6.8 health bug, and the exact instance §6.3's generalisation predicted ("the monorepo turns
*the repo* and *the project* into different things"). A zero from a knowledge producer is worse
than one from a health report: an export is piped into an index, and an empty index answers
every future question with silence.

- **`export.collect_portfolio()`** walks the `.baron-monorepo.yaml` registry and aggregates.
  The payload keeps the **same shape** (`layout: "monorepo"`, records concatenated), so
  `baron export --json | jq '.records[]'` does not fork per topology.
- **`path` needed no adjustment** — `_repo_prefix` already resolved each subdir's offset from
  the git top-level, so `git show <sha>:barony/docs/adr/…` works from the root. ADR-015 §3.1's
  choice of repo-root-relative paths, made when a sub-directory collab repo was hypothetical,
  is what made this a no-op.
- **The primary key is now `(project, kind, id)`.** Two projects legitimately both hold an
  `ADR-001`; the old key would have reported the second project's whole corpus as duplicates
  and dropped it — trading the silent zero for a silent halving.
- **One bad leg does not zero the portfolio**: unwalkable projects land in `unreadable{}` by
  name, unregistered subdirs in `unregistered[]`, and neither stops the rest.
- Regression test reproduces the root-level zero (fails before, passes after), plus a
  single-project no-regression test.

### Added — `baron export --wide`: `status` and `note` join the four ledgers, opt-in ([ADR-032](docs/adr/ADR-032-export-reach-monorepo-and-widened-corpus.md))

Acts on [ADR-031](docs/adr/ADR-031-governed-memory-eval-harness.md) (P3.3)'s measured finding that the retrieval miss was **coverage, not
ranking**: the lexical baseline already retrieved the flagship gold record at rank 1, and its
only miss was a `wiki/` research note `baron export` never walked. **Supersedes ADR-015 §7**'s
"curated status is not exported — deferred rather than guessed at", and closes 3.4's own corpus
list.

- **`status`** — `wiki/status.md`, `STATUS.md`. **`note`** — every `*.md` under `wiki/` and
  `docs/notes/`, retargetable with the repeatable `--note-dir`.
- **Opt-in, not the default.** `DEFAULT_KINDS == LEDGER_KINDS`: a caller naming no kinds gets
  the same four-ledger record set as before, and `--wide` (or an explicit `--kind`) asks for
  the widened one. **ADR-032 §3.1 was amended at integration to reverse this**: as written the
  new kinds were on by default, decided while ADR-031 was unmerged and the export therefore had
  no consumer in the tree. It has one now — `baron memeval` calls `collect()` with no kinds —
  and measured on the integrated stack a six-kind default moved its pinned numbers (MRR
  **81.2 → 68.8**, citation **100 → 94.4**) and failed three `test_memeval.py` assertions,
  while delivering **no** ceiling gain. The capability ships whole behind one flag; the default
  stays where every existing consumer already is.
- **An explicit include-list, not "every `.md` in the repo"**: `note` means *curated*, and a
  recursive walk would sweep in agent templates and emit-time fixtures nobody wrote to be
  retrieved.
- **The citation gate is not relaxed for the new kinds.** An untracked research note is skipped
  and named, exactly like an untracked handoff, and `--allow-dirty` still cannot cover it.
- **`project` is now a core record field, in both layouts** (`null` when there is no readable
  manifest) — so an index built across projects gets attribution without knowing the topology.
  Per ADR-015 §5 this is not a format bump, but it is a visible diff: `test_cli_json_shape`
  pins the key set and was updated by hand.
- **Measured against the P3.3 fixtures, under `--wide`**: 22 → 23 records, retrieval ceiling
  **84.4% → 87.5%**, R@5 **76.0 → 79.2**, and the flagship query's permanently-unreachable gold
  record becomes reachable (`unreachable: []`). MRR fell **81.2 → 75.0** — reported, not
  suppressed: widening a 22-record corpus adds competition, and the note that closes one query's
  gap crowds another's top slot. **Those numbers require ADR-032 §4.3's two one-line harness
  fixes**, which are an open follow-up on `main`, not part of this PR — without them `--wide`
  measures 84.4 / 76.0 / 68.8 / 94.4. The shipped default is unaffected either way: `baron
  memeval`'s numbers are byte-identical before and after this change.
- **Nothing was built toward a backend.** No `baron.knowledge` group, no vendor, no new
  dependency; ADR-015 §4.2 / ADR-022 §5.1 and their three guard tests are untouched and green.

### Added — `baron identity register|enroll|protect`: the ADR-027 runbook, mechanized (plugin 1.15.0 / CLI 0.15.0)

`docs/runbooks/identity-signing.md` was a list of owner actions performed by clicking. Each is
deterministic, and a hand-run checklist repeated once per persona is exactly the kind of thing
that gets done inconsistently, or half-done, or skipped on persona seven. Three commands now
perform them — **without moving the trust boundary** ([ADR-027 §7.5](docs/adr/ADR-027-agent-identity.md),
amended in this PR):

- **`baron identity register --persona <slug>`** — registers the persona's **public** key as a
  GitHub **signing key** (`POST /user/ssh_signing_keys`). Signing key, not authentication key:
  separate GitHub lists, and pasting into the wrong one is the likeliest way to do this step and
  believe it worked. Idempotent — a key already on the account is detected and skipped; a title
  collision with *different* key material warns rather than silently creating a second `carson`.
- **`baron identity enroll --persona <slug>`** — branches, commits the `.barony/allowed_signers`
  request line (plus `agents/<slug>/persona.yaml` when it exists, so the owner approves the key
  and its declared capabilities in one look), pushes, and opens the PR. **It does not merge, and
  there is no `--merge` flag** — `.barony/` is CODEOWNERS-owned so a persona cannot enroll
  itself, and that one human approval is the whole trust root (ADR-027 §2/§7.2).
- **`baron identity protect`** — creates the `main` ruleset of ADR-027 §2.2(c): require a PR with
  **code-owner review** (what actually gives CODEOWNERS teeth over `.barony/`), require the
  **`verify-identity`** status check (a check that is not *required* is a report, and a report
  can be merged around), and **require signed commits**. `allowed_merge_methods` excludes
  **rebase**, which adds head-branch commits to the base without verifying signatures and would
  quietly defeat the signature rule beside it. Refuses to stack a second ruleset over its own.

**Safety properties, all tested:**

- **Dry run is the default for all three.** Each prints the exact `gh` argv and JSON payload and
  exits. `--apply` is the only thing that executes. The dry-run rendering *is* the plan object,
  so what is printed cannot drift from what is run.
- **No credential is handled anywhere.** Calls run under the operator's existing `gh auth`. baron
  accepts no `--token`, reads none from the environment, stores none, prints none. No forge
  credential is introduced — ADR-027 §2's property is unchanged.
- **Only the public key leaves the machine**; the private half is never read.
- `protect` warns *before* applying about the two ways to brick a repo: requiring a check nothing
  publishes, and enabling signatures before the personas are enrolled.
- `cli/tests/test_onboard.py` (24 tests) drives the real planners against a recording fake. **No
  test touches a live account** — a property of the design (planners are pure; one injected
  runner spawns anything at all), not of the tests.

### Added — `baron memeval`: the governed-memory evaluation harness (plugin 1.14.0 / CLI 0.14.0, P3.3, [ADR-031](docs/adr/ADR-031-governed-memory-eval-harness.md), PROPOSED)

P3.4 says the default *"remains git+markdown until 3.3 shows material retrieval or scale
benefit"* — a sentence that means nothing until 3.3 can produce a number the default can lose
to. It can now. `baron memeval --fixtures evals/governed-memory` materializes a labeled
fixture corpus into a throwaway git repo, walks it with the **existing** `baron export`
producer (ADR-015 — the walker is consumed, not rebuilt), and scores each approach on every
metric 3.3 names: propagation precision/recall, duplicate suppression, schema/path/status
accuracy, Recall@k, MRR, source-citation accuracy, freshness/supersession, and human
intervention tax. A metric with an empty denominator reports `n/a`, never a silent `0`.

- **The fixture set covers 3.3's case list and asserts it** — routine commit, release,
  accepted/proposed/parked/superseded ADR, thesis-changing finding, duplicate event, and
  bad/missing source SHA. `evals/governed-memory/README.md` documents it.
- **The flagship fixture is this repo's own 2026-08-04 identity incident**, and its numbers
  are pinned by test. **Measured, and not the expected result:** the lexical baseline
  retrieves every *in-corpus* gold record at rank 1. Its only miss is the survey note — which
  `baron export` never walks. On this corpus the binding constraint is **coverage, not
  ranking**, which is a different first move for 3.4 than "add embeddings".
- **The citation gate now has a price.** One labeled query is unanswerable because its answer
  sits in an uncommitted file: the gate working as designed, measured rather than assumed.
- **Two of four approaches are measured; two are declared and left unmeasured.** The seam for
  semantic retrieval is an in-process dict (`memeval.RETRIEVERS`), deliberately **not** an
  entry-point group — ADR-015 §4's rule is not repealed by 3.3. Unavailable approaches print
  `NOT MEASURED` with the reason and estimate nothing.
- **Honest bound, carried in the output** (`honesty_bound` in the JSON, printed on the table):
  this measures fixtures, not a live repository or a running fleet. ADR-031 §4 additionally
  discounts the `hooks` row — its rule table encodes the same policy the gold labels do.
- **Still not built, and asserted by test:** no knowledge backend, no `baron.knowledge`
  entry-point group, no vendor named or run, no new runtime dependency (still typer + pyyaml).

> Renumbered **028 → 031** at integration: the ADR was written against 028 on a parallel
> branch, and 028 landed first as the mechanized merge gate. Recorded in `docs/adr/README.md
> § Numbering` rather than silently renamed.

### Added — the `observer` archetype, a strictly read-only watcher (plugin 1.13.0 / CLI 0.13.0, [ADR-030](docs/adr/ADR-030-observer-archetype.md), ACCEPTED 2026-08-14)

The fleet's first agent, and the one with no blast radius: it may **read everything** (handoffs,
ledgers, wiki, git/PR activity, the ADR-013 event plane, `baron status` / `baron health`) and
writes **one zone** — its own `observations/` — plus `_handoff/` to raise something to the
Librarian. No `write_code`, no `open_pr`, no `merge_pr`, and **no numbering authority**: findings
and decisions stay the Librarian's single-writer surface, so an observation that deserves a
number is proposed by handoff, never self-assigned.

- **`agents/__OBSERVER__/{persona.yaml,AGENT.md}`** + `baron init --personas observer:<slug>`.
- **Read-only where it can be mechanical.** With `write_code` denied and `write_path` allowing
  only `[observations, _handoff]`, `baron guard` blocks a write to every other zone and blocks
  `merge_pr`/`push_main`/`force_push` — asserted against a real guard subprocess in
  `cli/tests/test_observer.py`, not just stated in prose. The *read* breadth is unenforced by
  design and by ADR-020: it is total, so there is nothing to deny.
- **`observations/`** is a dated, append-only zone emitted only when the roster carries an
  observer, and deliberately **not** a numbered ledger (ADR-030 §2.1). `observations` joins the
  named `write_path` scopes; scopes are data, so **the frozen v1 verb list is untouched**.
- **Cadence is recommended, not wired**: a daily cron sweep via a persona sidecar (ADR-026),
  stateless per cycle. ADR-007 holds — baron still does not own the loop.
- **First live pass included**: `docs/notes/observer-first-pass-2026-08-14.md`, run read-only over
  the `fleet-coordination` monorepo and recent `vggg/barony` activity. It found a coordination
  substrate with **no git remote** (the VANAR "producing into a void" pattern), two live PRs
  proposing agent identity with no cross-reference, and persona identity claimed in commit
  subjects but present in the author field for only 3 of 23 commits.
- **Honest bound**: an observer reports what the substrate exposes. It is not a correctness
  guarantee and enforces nothing — that is the guard's and the gate's job. Every note carries its
  own coverage bound so an empty section cannot read as "all clear".
### Added — the prior-art gate: `baron adr check` (plugin 1.12.0 / CLI 0.12.0, [ADR-029](docs/adr/ADR-029-prior-art-gate.md))

Barony's enforcement thesis — *instructed → enforced*, the FM4 lesson — applied to its own
governance process. **Incident (2026-08-14, first-party):** an ADR-027 session re-derived an
identity design that a **2026-08-04 vault spike had already decided against**. The prior art
was written down, findable, and in the corpus the owner maintains for exactly this. No step in
the ADR-authoring path ever *asked* whether it had been consulted, so it never was.

Two rules; one of them mechanized:

- **One canonical home** — a decision is canonical only once promoted to an **accepted ADR in
  the repo**. Vault notes and spikes are *inputs*; the promotion step is required. Instructed
  tier, and ADR-029 §6 says so rather than borrowing the mechanized half's credibility.
- **A recorded prior-art sweep** — every ADR reaching `status: accepted` carries a
  **Supersedes / Prior art** block naming the corpora searched (repo `docs/adr/` **and** the
  owner's vault), with query and date, citing or explicitly superseding every hit.

**`baron adr check [docs/adr]` is fail-closed**: missing block, malformed block, empty
`searched:`, a required corpus unsearched, an omitted `hits:` key, or a malformed hit are all
**errors → exit 1**. Not a warn-and-continue lint. `baron adr scaffold` prints the block.
Storage is the ADR-009 §3 marker region inside the record itself (the substrate is the
database, ADR-003 §2.2); a malformed block is *reported*, never rewritten (§2.6). Design
choices that carry weight: `corpus` is a **closed vocabulary** (a free-text field would let
`corpus: "had a think about it"` pass); `hits: []` must be **written**, because omission is
indistinguishable from never having looked; and pre-2026-08-14 records are **exempt, never
reported as passing** — failing 26 legacy ADRs on day one is how a gate teaches people to
ignore it (the ADR-009 §10 Q4 call, reapplied).

Landed with it: `docs/adr/ADR-TEMPLATE.md` and the emitted
`decisions/ADR-TEMPLATE.md` (so `baron init` scaffolds the required section), step 0 of the
`CONVENTIONS.md` decision/ADR-intake rule, the `COORDINATION.md § ADR rules` update, and a CI
step running the gate on **this repo's own corpus** — including ADR-029, which is gated by its
own rule rather than grandfathered.

> **Honest bound, stated in the record and in every surface:** the gate enforces that a search
> was **recorded**, not that it was **thorough**. Recall quality is a separate axis (P3.3/P3.4).
> It converts "I forgot to check" from silent to blocked — nothing more. A determined author
> can still record a sweep they never ran.

**Residual owner-decision points** (ADR-029 §8): point 1 is **resolved** — ADR-027 and ADR-028
merge ahead of this and carry populated blocks (§10 and §8), so `--since 2026-08-15` was not
needed and the effective date stays 2026-08-14, leaving ADR-029 gated by its own rule. Writing
ADR-028's block is what caught that its §4 rested on a rejected ADR-027 — the gate found a
defect on first use. Still open: whether `vault` is the right default requirement for *emitted*
projects; and whether `status: proposed` should be gated too.
### Added — `baron merge check`: the merge decision becomes a fail-closed gate (CLI 0.11.0, [ADR-028](docs/adr/ADR-028-mechanized-merge-gate.md))

The `__MERGER__` archetype was always specified as *a gate, not a button* — but the gate
was **persona prose**, the same enforcement tier FM4 watched a persona override ~15 times.
`baron merge check <pr>` makes the checkable half a return value: exit 0 = allowed, exit 1
= REFUSE naming the failed precondition, a stable reason slug, and the sha it checked.

- **Four preconditions, scored against ONE PR snapshot** — `pr_open`, `verdict_at_head`,
  `no_changes_requested`, `ci_green`. One snapshot is load-bearing: assembled from separate
  queries, a push landing mid-check could pair a "matching" verdict with a head CI never ran
  on — the stale-verdict merge the gate exists to stop, rebuilt at the mechanism layer.
- **`reviewed-sha == head`, exactly.** A verdict on any other sha is `stale_verdict`; an
  abbreviated sha is `verdict_malformed` and is **never prefix-matched** — two commits can
  share a prefix, and the whole gate rests on that equality being exact.
- **Fail-closed with no amber.** No verdict, pending CI, *absent* CI, an all-skipped check
  set, an unrecognized check state, an open `REVIEW:FAIL` (even beside a later PASS on the
  same sha — same sha means same code), a missing `gh`: each REFUSES. Preconditions that
  could not be reached are reported FAILED, not skipped, because a reader rounds an absence
  down to "fine". Deliberately unlike `baron decision check`'s three states: that is a
  report, this is an action, and for an action amber is red.
- **Labels are an input to nothing** (ADR-008 §1) — collected and printed as *ignored*, in
  both directions: an approval label cannot rescue a stale verdict, and a
  `changes-requested` label cannot block a clean head.
- **It never merges, and there is no `baron merge do`** (ADR-007). The honest bound, stated
  in the command's own output: under one shared forge account baron cannot attest *who*
  posted a verdict — a dev can post its own `REVIEW:PASS` — so merging stays
  owner-in-the-loop until per-persona forge identity (ADR-027) is deployed. `--verdict-author`
  ships now, useless today, load-bearing the moment identities exist.
- **Honest scope:** two of the merger's four preconditions are mechanized. Record
  obligations and hot-file collisions stay the persona's, and the command says so — exit 0
  means "1 and 2 hold", never "merge it".
- New optional forge extension `get_pr` (duck-typed, outside the Protocol per the
  `forge/base.py` rule); the `__MERGER__` template, `COORDINATION.md § Review and merge`
  and `cli/README.md` carry the wiring.

**Correction made at queue integration (2026-08-14).** ADR-028 §4 was drafted against an
earlier, *rejected* ADR-027 that proposed per-persona **forge credentials**, and claimed that
ADR-027 would unblock autonomous merging. The accepted ADR-027 is **SSH commit signing** and
introduces no forge credential at all — so the claim was false and is **withdrawn in §4**, not
reworded. The gap is real and now stated: ADR-027 attributes *commits*, a `REVIEW:PASS` is a
*PR comment*, and the two do not meet. `--verdict-author` therefore does **not** become useful
when ADR-027 lands. New ADR-028 §7 Q4 records the two candidate routes (per-persona forge
identity, or a signed in-repo verdict artifact under ADR-027 §2.3) and that neither is
designed. `baron merge check` stays owner-in-the-loop, which is what it already shipped as.

### Added — agent identity: per-persona SSH signing keys, enrolled in the repo (plugin 1.11.0 / CLI 0.10.0, [ADR-027](docs/adr/ADR-027-agent-identity.md))

On **2026-08-04** an un-onboarded Codex agent committed to `main` **under the owner's git
identity**. From the repo alone it is unattributable — it reads as Vikram. ADR-027 promotes the
verdict of the vault spike written that day (*Lightweight verifiable agent identity at spawn*,
fourteen options against five criteria) into a decision and builds its §4.

**Per-persona SSH signing keys, generated at spawn, enrolled once into an in-repo
`.barony/allowed_signers` file, verified offline with `git verify-commit`.** The registry is a
file in the repo, so a clone is sufficient to verify any artifact this project ever produced —
no server, no CA, no vendor, no network. Invariant #1 holds by construction.

**Agents still push under the owner's GitHub identity.** Per-persona attribution comes from the
signing **key**, not from a separate account, app or token — GitHub places no limit on signing
keys per account and records which key signed each commit. No forge credential is introduced
anywhere by this change.

- **`baron identity init --persona <slug>`** — generates `~/.barony/keys/<slug>.key` if absent
  (`$BARON_KEY_DIR` overrides), configures **repo-local** git (`gpg.format=ssh`,
  `commit.gpgsign`, `tag.gpgsign`, the in-repo allowed-signers file, and a distinct
  `<slug>@agents.barony.invalid` author email — which alone would have made the Codex commit
  visibly non-human), emits an enrollment **request**, and **exits non-zero until that request
  is merged at HEAD**. Enrollment is read from HEAD, never the worktree: an agent that writes
  the line itself has enrolled nothing. `.github/CODEOWNERS` makes `.barony/` owner-only, and
  that one human merge is the trust root. Identity precedes work.
- **`baron verify identity --base --head [--label]`** — the CI gate, fail-closed. Per commit:
  the signature verifies against the in-repo allowlist, git trust status is `G`, and the
  **three-way cross-check** — signer principal ↔ the persona the commit claims ↔ an
  `agents/<slug>/persona.yaml` registry entry. A commit signed by a *genuinely enrolled* key but
  *labelled* as another persona fails, which closes the `from:` misattribution class with the
  same check that closes the anonymous-commit class. The trailer and the routing label are
  checked **independently**; first-match-wins would reopen the hole from the other side.
- **`baron init` scaffolds the whole gate**: `.barony/allowed_signers` (empty = fail-closed),
  `.github/CODEOWNERS` (`--owner <handle>`, else a loud placeholder — a plausible wrong owner
  would silently guard nothing), and `.github/workflows/verify-identity.yml`.
- **Handoffs and findings carry detached signatures** (`ssh-keygen -Y sign` → `<file>.sig`).
  `baron handoff sign|verify`, and `baron handoff close` — the librarian's ingest moment —
  refuses an artifact whose signature does not verify and **records the refusal as a finding**.
  An attribution failure is evidence; dropping it silently is what the audit product cannot
  afford. A *missing* signature only warns (ADR-027 §7.3 — flipping that default is a
  fleet-wide breaking change and should be signed, not defaulted).
- **Owner runbook**: [`docs/runbooks/identity-signing.md`](docs/runbooks/identity-signing.md).
  Nothing here works until the owner registers the keys and turns on the `main` ruleset —
  including *not* using rebase-merge, which adds head-branch commits to the base without
  signature verification.

**Deliberately not built** (ADR-027 §4, adopting the spike's §5 verbatim): no Barony CA or PKI,
no hosted registry or identity API, no custom signature format, no key escrow or rotation
automation, no DID method, no NANDA/ANS/A2A integration on speculation — and **no per-persona
machine accounts, GitHub Apps or PATs as the attribution mechanism**. The spike surveyed and
rejected both: Apps/bot accounts are a separate heavyweight *authorization* question needing
per-persona human provisioning and unverifiable from a clone; fine-grained PATs attribute to the
*account*, not the persona, so they do not attribute at all.

**Honest bound, stated in the ADR, the runbook, the template, and every command's output:** this
establishes attribution among **cooperating** agents. The private key sits unencrypted in the
agent's workspace, so it does **not** defend against a hostile actor with write access there —
the same bound as `baron guard`. Overclaiming is the fastest way to lose the credibility the
audit product depends on.

**Supersedes [ADR-026](docs/adr/ADR-026-persona-sidecar.md) §6 Q4**, whose answer to "how does a
sidecar get its identity?" was a forward pointer to *"the deferred per-persona signing keys"*.
They are no longer deferred. Both ends carry the supersession note, per the house convention.

**Also supersedes ADR-011 (PR #32, opened 2026-08-04, `proposed`, never merged) — and the way
that happened is itself the record.** ADR-011 proposed *the same mechanism*: SSH signing keys at
spawn, an in-repo `allowed_signers` under CODEOWNERS, the signature ↔ registry ↔ claimed-persona
cross-check, the same three-layer gate, the same rejection table. Both are readings of the same
2026-08-04 spike, written ten days apart, **neither citing the other** — a live open PR in this
repo's own corpus was missed, not just a vault note. ADR-011 stopped at `proposed` with five
blocking owner questions and no code; ADR-027 §9 dispositions all five (Q1 answered yes, Q2
answered with one case still open, Q3 and Q4 answered, **Q5 — a `baron validate` enrollment
check — explicitly NOT built in this cut**). PR #32 is closed as superseded; ADR number 011 is
not reused. This is the exact failure the prior-art gate (ADR-029) is being built to catch.

`cli/tests/test_identity.py` (28 tests) drives **real** `ssh-keygen` and **real** git signing —
a mocked `ssh-keygen` would prove the mock, and the whole claim is that stock tools suffice.
Covered: enrollment read from HEAD not the worktree, the non-zero refusal, unsigned commits,
self-minted unenrolled keys, misattribution from label *and* trailer *and* both together,
a signer with no registry entry, tampered handoffs, a handoff signed by a persona other than its
`from:`, the recorded-finding ingest refusal, and backward compatibility for unsigned handoffs.

### Fixed — `baron health` read a plane nobody writes to in a monorepo (CLI 0.9.0, [ADR-025 §6.8](docs/adr/ADR-025-coordination-monorepo.md))

Stage 2 of the same dogfood, and the defect §6.3's generalisation predicted. The disk sink
hangs the event plane off the **git top-level**, and a monorepo project subdir is not its own
git repo — so a verdict recorded from `<root>/barony/` is written to `<root>/.baron/events/`.
`verdict.read` joined `.baron/events` onto the *collab path* and looked in
`<root>/barony/.baron/events/`, which does not exist. Measured: `verdict.read(<root>)` → 1 row,
`verdict.read(<root>/barony)` → **0**. A well-formed approved verdict sat on disk while `baron
health` printed `0 verdict(s)`, offered "a project that records no verdicts shows a clean
board", and advised enabling a sink **that was already enabled** — the same silent-false-green
class as the `--code-repo` aliasing bug. Single-project layouts were never affected (there the
collab dir IS the git top-level), which is exactly why it survived to Stage 2.

- **One resolution, shared by the write and the read.** `sinks.disk.events_dir(cwd)` is now the
  single answer to "where is the plane", used by `DiskSink.directory()` and `verdict.read`
  alike. The two cannot drift apart again.
- **The portfolio reads that plane once, not once per project.** Summing a per-project read over
  a *shared* plane would report N× the verdicts that exist — a new false number in place of the
  old false zero. `baron health` at a monorepo root now rolls the verdict half up once from the
  root; per-project boxes carry stalls, which are genuinely per-project.
- **A zero is attributable.** ADR-024 §5's honest bound is about *emission* and is unchanged —
  health still measures what was emitted, not what happened. But it was never a licence to miss
  rows that were emitted, so the report now names the directory it read, and flags when those
  rows are the whole clone's rather than this project's alone.

### Fixed — ADR-025 hardening from the first real coordination monorepo (CLI 0.9.0, [ADR-025 §6](docs/adr/ADR-025-coordination-monorepo.md))

Standing up `fleet-coordination` as a real coordination monorepo — Barony grafted
in as its first non-`_meta` project — found two defects that made the topology
unusable and four more that made it unpleasant. Both criticals **failed silently
upward**, which is why the dogfood was worth doing at all.

- **`baron add-project --code-repo` no longer aliases the coordination repo.** A git
  URL names no local path, so baron assumes the conventional sibling clone — and the
  sibling of a monorepo *subdir* is one level further up. Emitting `../<name>` pointed
  at the project subdir itself; every path existed inside a git work tree, so `baron
  status` reported the code repo **green** with nothing cloned. The assumed sibling is
  now re-based for the nesting level, and any `--code-repo` resolving to the
  coordination repo, inside it, or containing it is **refused** — a code repo is a
  separate repo, so aliasing is never a valid spelling. (A refusal now also happens
  before the target directory is created, so a rejected graft leaves nothing behind.)
- **`manifest.yaml` always carries a `notify:` block** — `add-project` emitted none, so
  `wake_allowed` was empty and a grafted project could never be woken. Fail-closed stays
  the contract (ADR-010 §5.5), but *absent* and *empty* are not the same thing to a
  reader: absent gives you nothing to search for. Emitted always, empty-with-instructions,
  from the emitter `init` and `add-project` share — so standalone `baron init` gains it too.
  New **`--wake-allowed <slug>,...`** on both commands scaffolds a working wake loop in one
  flag, and rejects a slug that is not a persona of the project (the gate matches the
  handoff's `from:`, so an unknown name could never fire).
- **`baron status` dirt is path-scoped per project.** `git status --porcelain` reports the
  whole work tree wherever it runs, so one uncommitted file made every project dirty —
  `_meta` was flagged for an edit to `barony/manifest.yaml`.
- **`reviewer` and `merger` are first-class archetypes.** Both templates hard-coded
  `archetype: dev`, so a scaffolded roster read back as indistinguishable devs. They stay
  dev-*shaped* (same hydration mechanics, narrower capabilities); dev-shaped is not the same
  claim as `dev`. Enum severity is unchanged (warning), so nothing downstream breaks.
- **A nested `.github/` in a project subdir is reported inert.** GitHub resolves workflows
  from the repository root only, so a nested one fires never while reading like working CI.
  `init --layout monorepo`, `add-project` and `adopt-project` warn; none delete.
- **The code-repo refusal reads consistently** (docs-only follow-up to the PR #43 review).
  `cli/README.md` documented the standalone `init` refusal as the "itself" case alone, so
  the nesting cases read as monorepo-only when the guard has always been shared; and the
  refusal messages named the same directory twice per sentence ("an ANCESTOR of *the collab
  repo* — the *coordination repo* would live inside…"). Both now use one name throughout.

### Added — `baron adopt-project <subdir>`: the monorepo migration path (ADR-025 §6)

`add-project` scaffolds and refuses a non-empty target, so an existing collab repo — with
its own history, personas and ledgers — had no way into a monorepo short of hand-editing
the marker. `adopt-project` registers one that is **already a subdir**: verify it is a
collab repo, read its project name from its own manifest (never rewrite it), register it,
re-render the root README, commit.

Placing the directory stays **git's** job — `git subtree add --prefix=<dir>` keeps history,
`mv` does not, and choosing is the owner's call. Wrapping either would be baron guessing
which was meant and re-implementing git badly. It refuses a subdir that is still its own
git repo, one with no `manifest.yaml`, a duplicate, a path rather than a plain name, and a
`--project-name` contradicting the manifest. It deliberately does not delete the adopted
`.github/` or re-base its `repos[].path` — both are reported instead.

**Deferred to its own PR:** persona-name collisions across projects in one monorepo clone
(ADR-025 §6.7). The fix spans the persona spec, all four adapters and the drift checker —
"how does persona registration become project-local" is an ADR, not a patch to
`add-project`. Workaround meanwhile: per-project slugs (`--personas dev:fern,librarian:iris`).


### Added — the coordination monorepo: `baron init --layout monorepo` + `baron add-project` ([ADR-025](docs/adr/ADR-025-coordination-monorepo.md))

A second **topology**, not a new abstraction. `baron init` emits one collab repo per
project (ADR-006); for a single owner running a portfolio of fleets that is N×2 repos
and — the real cost — no cross-project view. ADR-025 adds the other shape: **one collab
repo whose projects are subdirs**, each carrying its own `manifest.yaml`, `agents/`,
`_handoff/`, `decisions/`, `findings/` and `wiki/`.

- **`baron init <name> --layout monorepo`** scaffolds the coordination-monorepo root —
  the `.baron-monorepo.yaml` marker + registry, a README, and the CI seam owned **once**
  — with a first project as a subdir. That first project defaults to `_meta`, the
  **portfolio project**: no code repo, its work items are the cross-project decisions.
  The recursion is the point — the portfolio is a project that coordinates projects.
- **Per-project-repo remains the DEFAULT** (ADR-025 §7 Q4). Adopters keep isolation;
  monorepo is explicit, because a monorepo cannot grant per-project access and that is a
  blocker for the multi-tenant case, not a detail.
- **`baron add-project <name>`** grafts a subdir into an existing root, reusing `baron
  init`'s emitters verbatim, then registers it in the marker. The subdir gets no
  `.github/` and no repo of its own — CI and git belong to the root. It **refuses
  cleanly** on a non-monorepo directory, a duplicate, or anything that is not a plain
  subdir name.
- **Portfolio-wide reads.** Run at a monorepo root, `baron status` and `baron health`
  walk the registered subdirs and report per project plus a portfolio total (`--json`
  gains `layout`/`projects`/`summary`); `baron validate .` already recursed, and now
  names the projects covered and **warns on a manifest-carrying subdir the marker does
  not list** — portfolio reads would otherwise skip it in silence. Run inside a single
  project — monorepo subdir or standalone collab repo — behaviour is unchanged.
- **Per-subdir wake routing** (§7 Q2). `baron notify` inside a subdir puts the `project`
  in the `repository_dispatch` payload and does its git work (default-branch check,
  push, dispatch) at the **root**, which is the actual git repo. The root's emitted
  `baron-notify.yml` validates that project against the registry and `cd`s into it
  before resolving the handoff and the manifest — `paths:` cannot scope a
  `repository_dispatch`, so the `cd` *is* the scoping. Authorization is unchanged and
  still comes from the committed handoff `from:`, never the payload; concurrency is now
  keyed per project so two fleets' wakes never queue behind each other. `lock-guard` and
  `strip-stale-verdict` act on the PR itself and are correctly repo-wide.
- **Identity survives** (§7 Q3): `<slug>@<project>.local`, namespaced by subdir. The one
  wrinkle handled explicitly — the portfolio subdir is `_meta` but its **project name is
  `meta`**, because that name becomes a hostname and a leading underscore has no business
  in one.
- A project's `workspace.worktrees_root` resolves to `../../<project>-worktrees` in a
  monorepo, keeping worktrees a sibling of the root rather than a stray directory inside
  it; runtime kits point back through both levels (`../<monorepo>/<project>/...`).

### Added — the persona sidecar: `baron sidecar run` + an emitted `agents/<slug>/sidecar.sh` ([ADR-026](docs/adr/ADR-026-persona-sidecar.md))

ADR-026's launcher half, built. A persona becomes a **deployable unit**: the
runtime kit `baron init` already emitted, plus a work loop that coordinates
through the collab repo as shared state. It is the hand-written badminton
`fleet-runner` generalised and emitted, and it adds no machinery — the cycle
composes `baron session start --sync` and `baron session end`.

- **`baron sidecar run <persona>`** runs one cycle: **sync** (`git pull --ff-only`
  every manifest working copy) → **sweep** (open `_handoff/` items addressed to the
  persona, plus unchecked backlog lines carrying its routing label, parked items
  excluded) → **invoke** the runtime once with a work brief on stdin → **land**
  (index + scoped coordination commit, then a plain `git push` — no force, no
  retry). Flags: `--cmd`, `--trigger`, `--watch`/`--interval`/`--max-cycles`,
  `--timeout`, `--force`, `--no-push`, `--dry-run`, `--json`.
- **Nothing is paid for nothing.** No addressed handoff and no labelled backlog
  item = idle: the runtime is not invoked at all (`--force` overrides). That
  guard is the fleet-runner's, kept.
- **The brief resolves review feedback before new work** — the `check_review_feedback`
  → `check_backlog` ordering ADR-008 made load-bearing, now enforced by the one
  thing that plans an unattended cycle.
- **ADR-007 holds, visibly.** baron syncs, sweeps, commits and pushes; the *model
  invocation* is supplied by the project (`--cmd` / `$BARON_SIDECAR_CMD` / the
  emitted script). A cycle with no command is a usage error, never a default —
  baron still does not own the agent loop.
- **`baron init` emits `agents/<slug>/sidecar.sh`** (executable) beside each
  runtime kit, from a new vendored template. Its header renders the persona's
  `runtime.trigger` (ADR-026 §6 Q2): `interactive` is one-shot by hand and
  refuses `--watch` (that loop is the human's session), `event` is spawned by the
  ADR-010 wake, `cron` is scheduler-driven or self-paced. The runtime invocation
  is a **PROJECT-OWNED SLOT** — pre-filled for `--runtime claude`, an explicit
  fill-me elsewhere rather than a guess that fails at 3am. Cycle logs land in an
  auto-ignored `agents/<slug>/logs/`, so a running sidecar never reads as drift.

Containers stay deferred exactly as the ADR decided: launcher first, containerise
when a fleet needs laptop-off durability.

### Added — `manifest.yaml` schema **v1.4**: the optional `notify` block (ADR-010 §5.5)

`notify.wake_allowed` — the list of persona slugs whose handoffs may fire a
`repository_dispatch` wake — is now a **recognized, optional** manifest field.
It was already read by two live consumers (`baron notify` before it dispatches, and
the `gate` job of the emitted `baron-notify.yml`), but the schema did not know it,
so every project that had actually enabled wake got `manifest.notify: unknown field`
out of `baron validate`. A manifest carrying the block now validates with **zero**
warnings; `wake_allowed` must still be a list of strings, and a genuinely unknown
block still warns. Semantics are unchanged and deliberately fail-closed: **absent
means nobody may wake.** Canon doc + vendored copy updated; ADR-010 §5.5 left the
minor number unpinned, and this takes **v1.4** (ADR-009's `park_label` took v1.3).

### Accepted design (no code yet) — [ADR-025](docs/adr/ADR-025-coordination-monorepo.md): the coordination monorepo

`baron init` emits one collab repo per project, so N projects is 2N repos and there
is **no cross-project view**. ADR-025 reframes the missing "portfolio tier" as a
*topology*, not a new abstraction: one coordination monorepo with each project as a
subdir, and the portfolio itself as a code-less `_meta/` project — the portfolio is
a project that coordinates projects, governed by the same primitives one level up.
**Accepted (Vikram, 2026-08-13)** with §7 answered as recommended: keep `baron init`
for the root and add `baron add-project`; `repository_dispatch` carries the project
and the gate `cd`s into that subdir; identity stays `<slug>@<project>.local`; and the
monorepo is an **opt-in `--layout monorepo`** — per-project repos remain the default,
because a monorepo cannot grant per-project access.

### Accepted design (no code yet) — [ADR-026](docs/adr/ADR-026-persona-sidecar.md): the persona sidecar

Deploying a fleet is bespoke today — a hand-written launchd job on one machine — so
autonomous fleets stay "works on the author's laptop". ADR-026 packages a persona as
a **deployable unit**: baron CLI + the already-emitted `agents/<slug>/runtime/` kit +
a work loop, coordinating through the collab repo as shared state. **Accepted
(Vikram, 2026-08-13)** with §6 answered as recommended: launcher first (`baron
sidecar` + an emitted `sidecar.sh`), containerise once a fleet needs laptop-off
durability, loop configurable per persona, identity via the deferred per-persona
signing keys. ADR-007 holds — the sidecar *runs* the loop; baron still does not own it.

### Added — `barony` 0.8.0: `baron decision reconcile` / `check` (P2.1, ADR-009 — `park` only)

The FM6 mechanism. A ratified decision was recorded in `decisions/` and still
silently re-litigated for days on the pilot, because the epic encoding the
superseded direction sat **open, generating tickets**. Agents do not re-read
`decisions/` when choosing work — they re-derive it from the backlog.
**`decisions/` is a record; the backlog is a control.**

Scope is `park` alone (owner decision, 2026-08-02) — the obligation that
demonstrably caused FM6. `supersedes` / `broadcast` / `direction_doc` stay designed
in ADR-009 §3 and unbuilt.

- **`baron decision reconcile <N> --park <item>`** records what a decision
  supersedes, in a marker-delimited block **inside that decision's own
  `decisions/index.md` entry** (ADR-003 §2.2 — no second store). Idempotent.
  baron never infers *what* a decision contradicts: the items are declared input.
- **`baron decision check [N] [--fetch]`** verifies discharge. Exit 1 on
  outstanding, CI-usable.
- **The discharge condition is the whole feature.** A park is discharged only when
  an agent's backlog query stops returning the item: **closed** (tracker), or
  **marked and declared** via the new `manifest.backlog.park_label` (schema
  **v1.3**, additive). On a **file** backlog the item carries an HTML-comment
  marker `<!-- parked -->`, and **removal alone is NOT a verifiable discharge** —
  baron cannot tell "removed" from "renamed" or "never matched", so it reports
  unverifiable rather than guessing green.
- **Green means DISCHARGED, nothing else.** `check` exits 0 only when every
  obligation is positively discharged. An earlier cut exited 0 on `unverifiable`,
  which meant moving absence from discharged to unverifiable produced the
  *identical* exit code and changed nothing a CI gate could see — the fix relabelled
  the failure without fixing it.
- **Three states, never two** — discharged / outstanding / **unverifiable**. A
  github_issues backlog without `--fetch`, an unreachable forge, or a `jira`
  backlog reports unverifiable and is scored as neither. A **malformed block is
  OUTSTANDING**, not unverifiable: corrupting it must not be the easiest way to
  turn the gate green.
- **Matching is token-bounded, never substring.** Review constructed three
  independent false DISCHARGEDs against the first cut: `unparked` satisfied a
  `parked` label; `--park #214` against a line reading `issue 214 …` reported
  **absent** — the *strong* discharge — while the item sat there active; and
  `--park 214` was discharged by an unrelated `SHU-2140`. A false discharge prints
  green on exactly the FM6 state this exists to catch, so ids are normalized
  (`#214` ≡ `214`) and both ids and labels match on `[\w-]` boundaries.
- **Forge queries target the declared repo.** Without `--repo`, `gh` runs against
  the collab checkout and answers the *collab* repo's same-numbered issue. A park
  naming a repo baron cannot resolve reports unverifiable rather than querying the
  wrong one.
- **`check_backlog` now excludes parked items** in all SEVEN renderers (the two
  code renderers, the three prose adapter surfaces, plus `PARTICIPATE.md` and
  `persona.schema.md`'s token table — the last two found only when a reviewer
  counted them), which is what makes the `filtered` discharge real rather than
  notional.
- **Authored data, not a derived view.** Unlike the handoff index this block cannot
  be regenerated, so reconcile only ever appends or updates its own region, never
  rebuilds it, and a malformed block is **reported, never silently rewritten**
  (ADR-003 §2.6 precedent) — with a test asserting the file is left byte-identical.

**Forge Protocol lesson, recorded because it bit during the build:** `get_issue`
was first declared on the `@runtime_checkable` `Forge` Protocol — and immediately
broke `test_lock.py`'s recorded fake, because those `isinstance` checks test method
**presence**. Adding a method to the Protocol retroactively invalidates every
implementation that predates it: the opposite of additive, and it would have broken
any third-party `baron.forges` plugin the same way. Optional capabilities now live
**outside** the Protocol as a documented duck-typed contract detected with
`forge.base.supports()`, degrading to `unverifiable`. A regression test pins it.

### Added — plugin 1.10.0: ritual-token coverage is now gated in the adapters
### Accepted design (no code yet) — [ADR-010](docs/adr/ADR-010-baron-notify-wake.md): `baron notify`

Design for the FM1/FM5 wake gap: Barony fleets are poll-only, so when a verdict or
handoff lands nothing wakes the responsible persona and a human ends up being the
message bus. **Accepted with changes (Vikram, 2026-08-02) — all eight §8 questions
answered; implementation unblocked but not yet started.** Owner's substantive
departures from the draft: the poll cron drops to a **slow backstop** rather than
being retired, and a **manifest allowlist** gates who may fire a wake.

The survey settles the landscape: **no agent framework wakes a cold headless
agent** — LangGraph resumes a checkpointed graph, Temporal signals a hosted
workflow, A2A notifies the dispatching orchestrator and presumes a long-running
worker. Cold-starting an ephemeral CLI agent from an event belongs to the
*platform* (GitHub Actions), not to agent frameworks.

**The design departs from its own research on one point:** the research proposed a
new `_mailbox/<persona>/` delivery surface. This ADR drops it — `_handoff/` is
already ordered, addressed, durable and swept at session start, and sweep order is
already expressible (ADR-008 §2). A second inbox would be two surfaces restating
one contract, and would need ADR-002 §2's "no exceptions" rule to grow an exception
on day one. So `baron notify` = an ordinary handoff **plus** a
`repository_dispatch`, with **delivery independent of wake**: if the dispatch
fails, the message is still a committed file and arrives on the next spawn.

ADR-007 holds — baron writes the file and fires the event; the *spawn* lives in a
project-owned workflow slot, never in baron.

**Rev. 2 after adversarial design review**, which upheld the mailbox call (and
supplied a better argument for it: `_handoff/` already carries `priority:`) but
found four false claims asserted as decided. The material one: **"delivery is
independent of wake" was false** — `handoff.create` commits but never pushes, so
the dispatch would reach GitHub before the message and a cloud runner would clone
and find nothing. Notify must push before dispatching, and must not dispatch if the
push fails. Loop safety was rebuilt rather than restated: the depth counter had no
propagation channel (each spawned agent re-invokes fresh; ADR-003 §2.2 forbids
sidecar state) so depth now rides in the **handoff frontmatter**; the concurrency
group bounds parallelism, not recursion, and no longer claims otherwise; and the
real backstop turns out to be that `GITHUB_TOKEN` cannot chain dispatch-driven
workflows — simultaneously the strongest guard and a silent failure, neither
previously mentioned. FM5 was overclaimed (it needs the reviewer's same-SHA
idempotency carve-out too). §8 now lists eight blocking questions.
Nine parallel hardening workstreams, consolidated onto one branch. Baron gains an event
stream, a wiring self-test, an inspection surface over its own capability rules, and an
export of the governed corpus. It also reports **less** enforcement than it used to — on the
event stream and on `baron rules list` — because what it printed was wider than the evidence
behind it. That is the part to read first, and it is under *Breaking* below.

**Reviewers start at [`docs/DECISIONS-FOR-REVIEW.md`](docs/DECISIONS-FOR-REVIEW.md).** All
five owner decisions are signed. Its **§E — what is NOT verified** is not an appendix: a
green suite invites the wrong inference, and the short version is that nothing here drives a
real Claude Code process, `.baron/rules.yaml` is parsed but never activated, `baron doctor`
reads project-level settings only, the `bash -c '…'` guard bypass is unchanged, and runtime
neutrality rests on two producers rather than three.

cli `pytest` **148 → 424**. The audit skill's suite is **265 checks** and is in CI for the
first time. `tests/lint_repo.py` and `tests/bi_runtime_accept.py` PASS. No test was deleted
at any merge in this pass; four were corrected, and one was **flipped** — the check that
asserted the pre-ADR-018 enforcement defect as current truth now asserts the fix.

**ADR numbering.** Three workstreams independently wrote an `ADR-018`. The number stayed
with the adjudicated-enforcement decision, which ADR-019 already cited by number; the
read-verb posture ADR became **ADR-020** and the audit-ingester ADR became **ADR-021**. Only
identifiers changed. [ADR-014](docs/adr/ADR-014-guard-telemetry.md) in `docs/adr/` is a
**status record on a reserved number, not the ADR** — see *Retired*, below.

### Versioning — two independent tracks, and a recommendation. Nothing is bumped here.

This repository carries **two** version numbers that are easy to conflate and mean different
things. Both appear in this file; only one of them ever gets a `## [X.Y.Z]` heading.

| Track | Where it lives | Released as | Now at |
|---|---|---|---|
| **Spec / plugin release line** | `.claude-plugin/plugin.json` and each `skills/*/SKILL.md` (lint-enforced to move together) | git tag `vX.Y.Z`; the `## [X.Y.Z]` headings in this file | **1.10.0** (`v1.10.0` is on `origin`) |
| **CLI distribution** | `cli/pyproject.toml` | PyPI package `barony`, command `baron` | **0.7.0** |

The CLI track is versioned **independently** and has never had its own heading here; it
appears as a sub-heading *inside* a spec release (`### Added — barony 0.7.0: …`). The
precedent is consistent: 1.7.0 carried CLI 0.3.0 → 0.4.0, 1.8.0 carried 0.4.0 → 0.5.0, and
1.9.0 bundled 0.5.1 through 0.7.0 while stating the tracks move independently. Reading
`[1.10.0]` as a CLI version, or `0.7.0` as a release, is a real error in both directions.

A third family of numbers appears throughout and is **not** a release version of anything:
artifact and schema versions (`rules_version: 1`, `EVENTS_VERSION = 1`, manifest schema v1.3,
persona schema v1.2) and the audit skill's `INGESTER_VERSION` (1.0 → **1.1** here). They
version a *document format* or a *script's output*, and they are pinned by tests that fail on
drift.

**Recommendation, for the owner to take or refuse — no file in this branch bumps anything:**

- **CLI `0.7.0` → `0.8.0`.** Minor, not patch: three new command surfaces (`baron doctor`,
  `baron rules` with four subcommands, `baron export`), a new public `baron.sinks`
  entry-point group, and two breaking changes to the event wire.
- **Not `1.0.0`.** Under 0.x the minor slot is where a break goes, which is exactly what this
  release needs. More to the point, 1.0.0 is a stability claim, and §E items 1, 5, 6 and 7
  are the reasons this codebase has not earned one yet.
- **Spec / plugin `1.10.0` → `1.11.0`.** Minor: skill assets changed materially — two
  `HYDRATE.md` surfaces, `capability-rules.md`, `manifest.schema.md`, and the whole
  `multi-agent-audit` ingester — and the manifest schema gained an **additive** `events:`
  block. Nothing was removed from the skill surface and the persona schema is untouched, so
  a major bump would overstate it.
- **One collision to settle before tagging.** The unmerged `p2-1-baron-decision` branch
  already sets `cli/pyproject.toml` to **0.8.0** for `baron decision`. Two branches cannot
  both ship 0.8.0. Whichever lands second takes 0.9.0; if a number is burned rather than
  reused, this file's own **0.5.4 precedent** applies — the skipped version stays documented
  and is not back-published.

---

### Breaking — read this section before upgrading

Four user-visible changes. Three narrow a claim baron was making; one invalidates documents
that used to parse.

**1. The `baron.enforcement` event attribute has a new, smaller vocabulary**
([ADR-018](docs/adr/ADR-018-adjudicated-enforcement-on-the-event.md)).

It is now exactly `enforced` | `unevaluated` | `unknown`. **`not-applicable` is gone**
(subsumed by `unevaluated`) and **`instructed` is gone from the event path entirely** — it is
a static posture property of a (persona, verb, runtime) triple and asserts a control a
PreToolUse hook cannot measure.

The attribute used to derive its value from the rules artifact's `detection` field, which is
a static property of a **verb** answering a **per-call** question. Measured against merged
code, it was wrong in both directions: `Write ../../../outside.md` emitted `enforced` for a
structural refusal every persona is denied identically, while `Write src/x.py` by a persona
holding `write_code` — a real, persona-dependent adjudication — emitted `not-applicable`. An
enforcement counter that inflates itself by construction is the failure this project exists
to catch. `enforced` now requires **both** halves: a capability rule matched **and** the
outcome turned on the acting persona.

- **Consumer caveat, stated in `events.py`, ADR-018 §5 and a test:**
  `baron.capability.verb` **can be non-empty on an `unevaluated` row**. Any verb-level
  aggregation must filter on `baron.enforcement == "enforced"` **first**.
- A fail-closed deny is `unevaluated`, not `enforced` — guard blocked *because it could not
  evaluate*. `unknown` is kept for the one case it means something: an unreadable rules
  artifact.
- `instructed` is **unchanged** on the posture surface (`baron rules list`,
  `CapabilityRules.label`), where `open_pr` and `run_tests` still carry it.

**2. `baron.hook_event` is renamed to `baron.trigger`, with no alias**
([ADR-019](docs/adr/ADR-019-runtime-neutral-event-plane.md)).

The key is now runtime-neutral; the **value stays the runtime's own seam name**
(`PreToolUse`, `before_tool_execute`), because normalising values would put an unverifiable
translation between the reader and the name the runtime uses in its own docs. Only meaningful
read together with the new `baron.runtime`.

Both of these breaks were taken now because **the default sink is `null` and nothing is
emitting yet** — the last moment a clean rename beats an alias. That argument expires the
moment the sink default flips.

**3. `baron rules list` prints `instructed`, not `enforced`, for `read_code` and
`read_collab`** (ADR-016 §8 D-1, decided 2026-08-09;
basis [ADR-020](docs/adr/ADR-020-read-verb-posture-measured-on-four-adapters.md)).

Baron reports less enforcement than it did. Nothing got weaker — the label was wrong.
`list` now reports three states and only one of them is `enforced`: `guard` (guard
mechanically checks it), `adapter-dependent` (guard does **not** parse for it; a runtime with
a tool allow-list *could* enforce it, and the adapters baron ships do not), and `instructed`
(nothing checks it). `label` says `enforced` only for `guard`.

The published bound travels with the label, in `--json` and in the table footer: the measured
claim is *baron emits no mechanism capable of omitting the read tools*, **not** *the runtime
cannot enforce them*. A hand-written `permissions.deny`, or the Tier-3 subagent the `claude`
and `code-puppy` HYDRATE.md recipes describe, does enforce them — and is outside what
`baron rules list` speaks for. Those HYDRATE tables still print `enforced` for the read verbs
and are not wrong; the divergence is recorded in ADR-020 §7 rather than papered over by
editing one table to match the other.

**4. `capability-rules.v1.yaml` now requires `class` and `detection` on every verb entry, and
both are closed sets** ([ADR-016](docs/adr/ADR-016-externalizable-capability-rules.md)).

A document that omitted them, or carried a value outside the set, used to parse. It is now
refused, and guard turns every parse refusal into an exit-2 DENY — so **a forked or vendored
copy of the artifact that is missing these keys will fail closed on upgrade**, loudly, at the
first guarded tool call. The packaged artifact is compliant; only a hand-edited copy or a
candidate fed to `baron rules validate --file` is affected, and no project-level artifact is
loaded by an enforcer at all (see *Not shipped*).

Defaulting an enforcement decision is a guess, and the measured cost of allowing it was
concrete: `detection: banana` passed validation; `class: banana` passed and silently
re-routed `enforcement()`; and `read_code` declared `detection: command` with no rule behind
it passed **and made `baron rules list` print `LABEL=enforced` for a verb nothing checks** — a
false enforcement claim from a one-word document edit.

---

### Added

- **`baron doctor [--dir .] [--persona-file F] [--json]` — the guard wiring self-test**
  ([ADR-017](docs/adr/ADR-017-baron-doctor-wiring-selftest.md)). Nine read-only checks, each
  with a remedy line, exit 1 on any FAIL: the hook's executable resolves and runs; project
  `.claude/settings.json` wires a `baron guard` PreToolUse hook; its matcher covers every
  governed tool; the named persona parses; the rules artifact loads at a supported version;
  **a synthetic denial fed to the executable the hook actually names really returns exit 2**;
  malformed stdin also returns exit 2; `BARON_GUARD_OVERRIDE` is not sitting exported; and
  the override log is writable.
  - **The caveat ships with the command, not just the docs.** Doctor verifies WIRING, not
    invocation — it proves the install *can* enforce and cannot observe whether the runtime
    ever ran the hook. That sentence prints on every run including green ones, is a field in
    `--json`, and is grep-asserted by a test.
  - It exists because of a real incident: 15 PRs merged under a persona denied `merge_pr`,
    and nothing had failed — `baron guard` had never been wired in, so the denial degraded to
    persona text exactly as designed, and **silently**. An absent guard and a guard that
    never had to fire produce identical evidence: nothing.
  - Evidence checks are INFO, never FAIL. Enforcement is fail-closed; evidence is fail-open.
    A broken audit sink reported as broken enforcement teaches people to ignore the exit code.
  - `baron init`'s next-steps and both READMEs' quickstarts now have an explicit
    install-the-kit step followed by `baron doctor`.

- **`baron rules list|validate|diff|explain` — the read-only audit surface over the
  capability rules** (ADR-016). Until now the only way to ask baron what it enforces was to
  read the YAML by hand. All four take `--json`.
  - `explain` is a **dry run of the real decision** — it calls `guard.evaluate_bash` /
    `guard.evaluate_write`, and a test pins its JSON verdict to the evaluator's `Decision`
    for the same input, so a second implementation cannot creep in. Exit 0 would-pass /
    1 would-be-DENIED / 2 could not evaluate. Honest limit, in `--help`: it lists the rules
    that *can* imply each verb, not the single rule instance that matched.
  - Underneath, `CapabilityRules` became a rule **list** (`command_rules`, `path_rules`) with
    stable ids, a matcher from a **closed** set, and a `source` provenance tag. The old shape
    had one field per built-in rule, and a structure with a fixed field per rule cannot hold
    an additional rule. `guard.py` and `runtimes/pydantic_ai.py` are **byte-identical** across
    the change; all fifteen pre-existing accessors survive as derived properties, pinned
    against hand-transcribed pre-refactor literals.
  - **Unrecognised content is refused, never ignored** — at the top level, in `verbs.<verb>`,
    throughout `commands.*`, and in `file_ops`. Silently dropping an unrecognised rule is the
    worst failure mode an enforcement artifact has: the document says a thing is blocked and
    nothing blocks it.

- **`baron export [--kind …] [--json]` — the governed corpus as citable records**
  ([ADR-015](docs/adr/ADR-015-baron-export.md)). Walks `docs/adr/*.md`, `decisions/index.md`,
  `findings/index.md` and `_handoff/**.md` into one flat record per artifact —
  `{id, kind, title, path, commit_sha, status, body, links}` plus an open `meta` bag. No new
  dependency, no network, no plugin seam.
  - **The citation gate is the point.** A record is emitted only if its source is tracked and
    unmodified, so `git show <commit_sha>:<path>` reproduces the parsed bytes exactly.
    Failures are **skipped and named** in `skipped[]` with a reason and a lost-record count,
    never emitted with a SHA that resolves but returns different text. `--allow-dirty` relaxes
    it for **modified tracked** sources only, stamping `meta.dirty` so the caveat travels with
    the data rather than with the invocation.
  - Output is byte-stable across runs (sorted, ISO-coerced dates, `age_days` deliberately
    dropped), locked by a test — without it nothing downstream can sync incrementally.
  - Measured on a real repo: 284 records (62 decisions / 62 findings / 160 handoffs), all 284
    citations verified by **byte-equality** rather than mere resolvability.
  - `status` is null for findings and decisions on purpose: the canon gives ledgers no
    lifecycle field, and a regex producing `"superseded"` would be the enforced-vs-instructed
    overclaim ADR-002 bans.

- **The observation plane: one event shape, pluggable sinks**
  ([ADR-013](docs/adr/ADR-013-observation-plane-events-and-sinks.md)). Baron had no event
  stream — six unrelated per-command emissions, most of them printed and discarded.
  - **`baron.events`** — `EVENTS_VERSION = 1`, a frozen
    `Event(kind, actor, subject, outcome, attributes, ts, trace_id, span_id)`, and `to_row()`
    producing one flat JSON object per line. Timestamps come from `clock.now()`, so the
    `BARON_NOW` backfill hatch reaches events.
  - **`baron.sinks`** — a `@runtime_checkable` `Sink` protocol, `get_sink()` structurally
    identical to `get_forge()`, plus `disk` (append-only JSONL, date-rotated, stdlib `json`
    only) and `null`. A **`baron.sinks` entry-point group** in `cli/pyproject.toml` mirrors
    `baron.forges`; a test loads both built-ins through real `importlib.metadata` discovery.
  - **`null` is the shipped default** and stays that way — see *Decided*, below. A downstream
    repo does not begin writing to disk because it upgraded.
  - **Guard's verdict path emits, and only guard's.** The tab-separated **tracked**
    `.baron/guard-override.log` is byte-for-byte unchanged; events are additive, and all 24
    pre-existing guard tests pass unmodified.
  - **The event stream is gitignored; the override log stays tracked.** The `.gitignore` the
    disk sink writes lives *inside* `.baron/events/`, deliberately not at `.baron/` level —
    an ignore there would silently un-track `guard-override.log` in every downstream repo.
  - **No OpenTelemetry dependency, ever.** ADR-003 holds; runtime deps are still exactly
    `["typer", "pyyaml"]`. The five top-level row keys are each the first entry of the audit
    skill's flat key lists, so the ingester reads baron's stream with zero new code, and a
    test re-derives those keys from the script and fails if either side drifts.
  - An `events:` manifest block was added to `MANIFEST_SPEC` and `manifest.schema.md` (v1.3)
    so a manifest can carry the config without tripping `baron validate`. **Reserved, not
    read** — `BARON_EVENTS_SINK` is the only live selector, and it is labelled as such in the
    schema, the canon and ADR-013 §7 rather than quietly implied.

- **`baron guard` taps the wider Claude Code hook surface**
  ([ADR-012](docs/adr/ADR-012-hook-coverage-and-evidence-capture.md)). Guard was wired to
  exactly one hook event and shaped to match, so a `SessionStart` payload returned 0 not
  because guard decided anything but because `"SessionStart"` is not `"Bash"`.
  - **`hook_event_name` dispatch.** Absent or `PreToolUse` → the ADR-004 enforcement path,
    byte-unchanged. Five events get evidence handlers (`SessionStart` → `session.start`,
    `SessionEnd`/`Stop` → `session.end`, `PostToolUse` → `tool.post`, `PostToolUseFailure` →
    `tool.failure`). **Everything else exits 0 immediately.**
  - **The hook surface is bigger than the docs say** — a list of 9 became 14 by survey and
    **31** by reading Claude Code 2.1.226's own event enum. `guard.KNOWN_HOOK_EVENTS` records
    them and is deliberately **inert**: a name in it without a handler behaves exactly like a
    name invented tomorrow. The surface grows, so unknown must be normal.
  - **Hard invariant: only `PreToolUse` may exit 2.** `Stop`/`SubagentStop` blocking is a real
    capability and exactly the trap to avoid — a blocked `SessionStart` cannot be un-blocked
    from inside the session. `test_only_pretooluse_can_block` drives all 30 non-`PreToolUse`
    events with one payload carrying a force-push to main, a write to `/etc/passwd` and a `..`
    escape simultaneously, asserting exit 0 for every one.
  - Evidence handlers record the *presence* of `tool_response`, never its content: responses
    carry file bodies and stdout, and a stream that accumulates them is an exfiltration
    surface, not telemetry.
  - **Generated wiring** — `baron init`'s Claude kit and both copies of
    `adapters/claude/HYDRATE.md` (step 3d) emit four evidence hook blocks alongside the
    enforcement one. Session events get **no matcher** (they carry no tool name, so a matcher
    would silently never fire). The `PreToolUse` block is **byte-frozen** and pinned by test,
    because it already exists verbatim in every repo `baron init` has ever generated. Because
    the default sink is null, a freshly scaffolded repo with these hooks behaves identically
    to one without them.
  - Session correlation: `trace_id = sha256(session_id)[:32]` — deterministic, no producer
    state. Nothing consumed `session_id` before.

- **`baron.runtime`, `guard.observe_decision()`, and a second producer** (ADR-019). The plane
  *looked* neutral, but exactly one producer had ever written a row and one attribute carried
  Claude Code's vocabulary onto the shared wire. Nothing distinguished "this plane is
  runtime-neutral" from "this plane has one producer and it is Claude Code".
  - **`baron.runtime` on every guard-sourced row** — `claude-code`, `pydantic-ai` or
    `unknown`, pinned as `guard.KNOWN_RUNTIMES`. Without it a merged stream is unpartitionable
    and a consumer cannot tell *"pydantic-ai never denied anything"* from *"pydantic-ai never
    ran"*. It defaults to `unknown`, never `claude-code`: a producer that forgets is
    unattributed, never mis-attributed.
  - **`guard.observe_decision(...)` is the public producer seam.** It takes a `Decision`, has
    **no `enforcement=` argument**, and infers nothing from `outcome`/`verbs`/`subject`, so
    ADR-018's "read the label off `Decision.adjudicated` and nothing else" survives exposure
    as public API.
  - **pydantic-ai is now a real second producer.** `BaronGuardCapability.before_tool_execute`
    emits into the same plane; `check()` gained a sibling `decide() -> Decision | None`
    because `str | None` collapsed "allowed" and "no jurisdiction". A broken sink still cannot
    stop the veto.
  - **The evidence is measured, not asserted:** driven with the same persona and the same
    command, both producers append to the **same** `.baron/events/` file and the two rows
    differ in **exactly four** attributes — `baron.runtime`, `baron.trigger`, `tool.name` and
    `session.id`. Verdict, verb, enforcement label, actor, subject and reason are
    byte-identical, and the difference set is asserted exactly. The headline test drives a
    real `Agent.run_sync` and reads what the real `DiskSink` wrote.

- **Audit skill: baron rows are partitioned out of agent activity**
  ([ADR-021](docs/adr/ADR-021-audit-ingester-partitions-observation-rows.md)) — see *Fixed*
  for why. New surface: `ingest_otel.partition_guard_records`, two new aggregate keys
  (`guard_decisions` and `baron_events_by_kind`, both direct counts, both folded through
  `merge_telemetry.TELEMETRY_KEYS`), and `INGESTER_VERSION` 1.0 → **1.1**. **The audit
  skill's tests are now in CI** — they shipped in v1.6.0 and were never wired up, so nothing
  caught drift between baron's emitted shape and the ingester that reads it.

---

### Changed

- **Product-vision invariant #1 is amended: git + markdown is the DEFAULT substrate, not the
  only one**
  ([ADR-022](docs/adr/ADR-022-substrate-invariant-amended-default-not-only.md), owner decision
  D2). Plugins may extend it to other suitable platforms. **No code change**, and it is the
  most consequential item of the 2026-08-10 decision pass.
  - **The bound is the load-bearing half and it is normative.** Governance state stays
    **complete in git**: *who may do what*, *who did what* and *what is true now* must remain
    answerable from the repository **alone** — no credentials, no running service, no index. A
    plugin may be authoritative for **derived or auxiliary** domains and **never** for
    authority, evidence, or the ledger.
  - **The deletion test** makes that checkable rather than interpretable: delete every plugin,
    clone fresh, ask the three questions. Answer lost, or now needing a second system →
    forbidden. Only *speed of finding it* lost → permitted.
  - The argument, not just the conclusion (ADR-022 §3): under an authoritative plugin a
    capability grant stops appearing in a PR, the auditor needs a vendor's cooperation rather
    than a `git clone`, and the failure is silent — a stale index does not announce itself.
    The claim degrades from *read the diff* to *trust the index*.
  - **Nothing is authorised and nothing is un-cut.** No `baron.knowledge` entry-point group,
    no adapter, nothing about any candidate vendor has been run, and `docs/BACKLOG.md`'s five
    prior cuts of the cross-project-memory surface **stand**. This changes the answer to *"may
    we ever?"*, not to *"may we now?"*.
  - Updated to match, found by grep rather than memory: ADR-015 §4.1/§8 and its status header
    and `Blocking question` field, ADR-003 §2.2, `README.md`, `AGENT-TASKS.md` 3.4,
    `STATUS.md`, `docs/BACKLOG.md`, `docs/DECISIONS-FOR-REVIEW.md`. `docs/history.md`'s "the
    substrate never changed" is **deliberately left alone** — it is true about the period it
    narrates, and editing history to match a later decision is what this project's ledger
    conventions exist to prevent.

- **Decided — the shipped sink default stays OFF.** `BARON_EVENTS_SINK=null` remains the
  default ([ADR-013](docs/adr/ADR-013-observation-plane-events-and-sinks.md) §7.1, owner
  decision D4). **This is a decision, not a deferral, and there is no code change** — the
  default was already correct, so the signature is the whole of it. Recorded explicitly
  because a default nobody signed and a default somebody signed look identical in a diff.
  - **The cost is not buried:** the **0.53 operational-fidelity measurement that motivated
    this entire plane still has no data**, and will keep having none until someone sets the
    variable. That cost is *accepted* by this decision, not reduced by it.

- **Retired — ADR-014's producer transport** ([ADR-014](docs/adr/ADR-014-guard-telemetry.md),
  owner decision F3). `baron.telemetry` is retired: `telemetry.py`, `test_telemetry.py`,
  `BARON_TELEMETRY`, `.baron/telemetry/`, and that branch's separate `baron.sinks`
  declaration.
  - **A recording action, not a deletion.** None of it was ever merged, so there is no revert
    and nothing is removed. The `harden/otel` branch is **not deleted** (3 commits, tip
    `3b9a4d8`), nothing further is merged from it, and the 435-line original ADR still lives
    only there. The suite is unchanged at 424.
  - **Adopted in part, and NOT recorded as rejected.** §4.2's `Decision.adjudicated` and the
    `enforced`/`unevaluated` vocabulary became **ADR-018**, which cites ADR-014 as *"the
    correct basis"*; §9.1's guard/activity partition became **ADR-021**; §3's *no
    `opentelemetry-api` in core, ever* **stands**. ADR-014 §12.2 had itself named this
    outcome as the correct resolution.
  - **Forward path:** a live OTel exporter belongs **out-of-tree**, registered over the
    **existing** `baron.sinks` group — no new group needed, and the plugin carries its own
    dependency. Nothing is authorised or planned.

---

### Fixed

- **Baron's own evidence was being counted as agent activity** (ADR-021). ADR-013 §6 chose a
  wire shape the audit ingester reads "with zero new code", and verified it. That worked, and
  it was the defect: `agent.name`, `tool.name` and `session.id` are join keys on every baron
  row *and* how `ingest_otel.py` decides a row describes an agent working. A
  `.baron/events/*.jsonl` file handed to the ingester was read as an agent session.
  - Measured on the committed fixtures, every value labelled `measured`: paired with a real
    spans file, nine activity metrics moved — `session_count` 1 → 2, `session_duration_p50_s`
    **600.0 → 300.444**, `tool_calls_total` 1 → 12, `tool_error_rate` 1.0 → 0.0833 — and
    `human_turns_total` was silently **downgraded from `measured` to `inferred`** by the
    arrival of evidence. Publishing instrumentation overhead as agent working time under a
    `measured` label is the 0.53 failure mode with the sign flipped, so the numbers are
    recorded in ADR-021 §2 rather than quietly corrected.
  - `partition_guard_records` splits every row carrying `baron.outcome` out **before**
    `build_sessions` — keyed on the attribute, not a span-name allowlist, because ADR-013
    deliberately leaves `kind` open. All six kinds are partitioned, not only the guard ones:
    `tool.post` carries `tool.name` and would otherwise be counted as a tool call.
  - `any_spans` now counts activity spans, so a baron-only file is not mistaken for a spans
    stream — a `measured` zero tool calls would read as "the agents made none". Absence notes
    now say *why*, pointing at the axis where the rows **are** counted.
  - `test_no_contamination_from_paired_export` is the lock that can actually fail, verified by
    reverting the fix: `return records, baron` fails 34 of that test's own checks and 45
    across the suite. Its companion `test_additivity_lock` only reads guard-free fixtures and
    therefore proves nothing about contamination; its own docstring now says so.
  - **Cross-version hazard, stated not papered over:** a pre-1.1 ingester reproduces every
    number above. Snapshots carry `telemetry_metrics_version`.

- **The audit fixture was a fossil of the pre-ADR-018 producer** (found at consolidation).
  `baron_events.jsonl` is documented as the verbatim output of a real `baron guard` run, and
  its whole purpose is to prove the wire shape baron **emits** is the shape the ingester
  **parses**. It predated ADR-018/ADR-019, so it still carried four `not-applicable` rows and
  none of the `baron.runtime` / `baron.trigger` attributes the merged producer stamps — a
  fixture from a producer that no longer exists, which would have defeated the CI step this
  same workstream added to catch exactly that drift.
  - Regenerated against the merged producer; the ingester parsed the new attributes with **no
    code change**, which is an independent check on ADR-019's wire-shape claim.
  - `test_baron_guard_metrics` now asserts the fix rather than the defect: the previous round
    left a check asserting the structural-refusal row was *wrongly* labelled `enforced`.
  - Three published `session_duration_*` figures moved and were re-pinned in the four
    documents `test_adr021_published_figures_reproduce` names. These are hook wall-clock on
    the generating machine and **move on every regeneration by design**;
    `gen_baron_events.py` now says so.
  - **Four passages describing `baron.enforcement` as "under correction" were stale** once
    ADR-018 merged, and are corrected in `SKILL.md`, `ingest_otel.py`, ADR-021 §5 and
    `gen_baron_events.py`. The enforcement axis is still unpublished, but the honest reason
    changed from "the field is wrong in both directions" to "an honest aggregate must filter
    on `enforcement == "enforced"` before grouping, and that filter is un-built" — a gap, not
    a blocker.

- **`baron export`'s citation gate failed open on quoted paths** (ADR-015 §3.2). Plain
  `git status --porcelain` C-quotes non-ASCII and spaced paths, so the dirty check silently
  passed them. Now `-z`, regression-tested with a literal non-ASCII filename.

- **`baron rules validate` checked keys but never values** (ADR-016, round 3). Every refusal
  shipped in rounds 1–2 targeted a *key* or a *rule slot*. `rules._check_detection_consistency`
  now cross-checks `detection` against the rules that actually bind each verb,
  **symmetrically** — over-claiming (`command`, no rule) and under-declaring (a rule binds it,
  entry says `none`) are both refused. That check previously existed only as an assertion in
  `test_rules.py` against the packaged artifact, where no document input could ever reach it.

- **`baron rules diff` was blind to verb entries** (ADR-016, round 3). A candidate that
  rewrote `detection`, `class` or `notes` on an existing verb printed `identical to the
  packaged artifact` and exited 0 — reproduced three ways. Those are the fields that decide
  whether baron prints `enforced`, so the edit most worth reviewing was the one the review
  surface could not see. `diff` now joins on verb id (`verbs_changed`), names the resulting
  `enforcement`/`label` transition inline, and prints values in full — a first draft truncated
  to a fixed prefix, making two different `notes` blocks look identical.

- **`validate`'s "no unrecognised content" check overstated itself** (ADR-016, round 3). It
  was hardcoded `True` behind text claiming "every key and rule in the document is one this
  baron implements", and printed `ok` over a document containing `detection: banana`. Its text
  now names exactly what is covered, and a new **computed** check re-derives the
  enforced/backed relationship from the parsed table instead of asserting it.

- **A circular label test was replaced** (ADR-016, round 3).
  `test_only_guard_checked_verbs_are_labelled_enforced` derived its expectation from
  `detection` — the field under test — and so restated the document back to itself, which
  green-lit the `detection: command` hole. Replaced by a **literal** `EXPECTED_CLAIMS` table
  for all ten verbs plus a test asking whether a rule could actually fire.

- **`baron doctor` probed the wrong binary** (ADR-017). Checks 6 and 7 now spawn the hook's
  own command — wrapper prefixes such as `uv run` included — not the `baron` package that
  happens to be importable in doctor's interpreter. A project wired to a stale, shadowed or
  hand-rolled `baron` *is* the incident shape, and an in-process probe is structurally blind
  to it. Where the hook names no resolvable executable, doctor falls back in-process and says
  so in those words. Relatedly, `uv run baron guard …` used to produce a **false FAIL** on a
  correctly-wired project by resolving the bare `baron` token instead of the launcher; a
  resolvable launcher that will not answer `--version` is now UNKNOWN, not FAIL.

- **Guard's read-verb posture caveat was scoped to what was measured, then measured properly**
  (ADR-016 round 3, superseded by ADR-020). `LABEL_CAVEAT` stated "no adapter baron ships
  does" omit read tools as fact for all four adapters on the strength of one instrumented
  test. Round 3 narrowed it to "unmeasured"; ADR-020 then measured the other three statically
  and retired the scoping. `rules.READ_VERB_MEASUREMENTS` now carries one entry per shipped
  adapter naming the evidence and the test behind it, `LABEL_CAVEAT` is built **from** it so
  the published caveat cannot drift from the measurements, and a test asserts its keys equal
  `scaffold.ADAPTERS` — **a fifth adapter breaks the label's basis until it is measured.**

---

### Documented — two evaluation gaps that were already decided

From the 2026-08-08 Barony/Nasiko evaluation. Recording the existing decision honestly *is*
the deliverable; re-deriving a settled decision as a fresh proposal is the documented failure
mode of that note.

- **Fail-open vs fail-closed on hook failure — settled since ADR-004 §2.3, now also measured
  and pinned.** No new ADR: the policy was decided, implemented and documented on day one.
  `test_doctor.py::test_fail_closed_policy_is_pinned_adr_004_s2_3` and doctor's own
  `fail-closed` check now assert it per-install.
- **`open_pr` / `run_tests` denial parsing stays DEFERRED**, with the date and the reason: no
  observed-need evidence exists anywhere in the repo or the evaluation, and the vocabulary's
  design rule 4 / ADR-004 §2.2 make observed need the trigger. `capability-rules.v1.yaml` is
  unchanged and `rules_version` stays 1.

---

### Not shipped, deliberately

Named here so they are choices on the record rather than things nobody noticed.

- **The knowledge-substrate adapter** (`AGENT-TASKS.md` 3.4). No `baron.knowledge`
  entry-point group, no semantic-memory adapter, and **no vendor named anywhere under
  `cli/src/baron/`** — asserted by test. 3.4 is gated on **3.3**, the governed-memory
  evaluation harness, which does not exist; building the adapter first inverts the project's
  own measure-first rule on the exact task where that rule is written down. Two further tests
  pin the boundary: runtime dependencies are still exactly `["typer", "pyyaml"]`, and
  `baron.forges` is still the only entry-point group. ADR-022 does not change this — it
  answers *may we ever*, not *may we now*.
- **The project-level rules loader.** `baron rules validate --file` / `diff --file` parse a
  candidate document, but **validating a file does not activate it**. Every enforcer still
  loads the PACKAGED artifact only — no `.baron/rules.yaml` discovery, no merge, no
  precedence — pinned by `test_guard_reads_packaged_data_only`. ADR-016 §5 records the
  one-way doors that need their own ADR first: add-only/deny-only, explicit supported version
  ranges on *both* artifacts, refuse-don't-ignore on a malformed project file, `load_rules()`
  cache safety once it is path-dependent, and the `.baron/` (machine state) vs root-level
  `.baron-waivers.yaml` (human config) convention collision. **Project-defined verbs are a
  separate, unmade decision** (§6.1).
- **An aggregate over `baron.enforcement` in the audit skill.** `harden/otel` had one; it is
  not ported. It needs the `enforcement == "enforced"` filter applied before grouping, and no
  consumer has asked. ADR-021 §5.
- **A code-puppy event producer.** It has no PreToolUse equivalent, so it is deliberately
  absent from `guard.KNOWN_RUNTIMES` and this change does not invent one — emitting from a
  post-hoc log would imply an adjudication that never happened. Pinned by a test so the tuple
  grows with a landed adapter and never with an intention.
- **The per-runtime capability matrix** (DECISIONS-FOR-REVIEW §F1). `baron rules list` prints
  one label per verb; the honest answer is a 4 adapters × 10 verbs grid. The harness ADR-020
  needed (`cli/tests/omission.py`) is keyed on the `(adapter, verb)` pair for exactly this
  reason and is already shaped for it. Deferred because it is a user-visible output redesign,
  not a measurement gap, and doing it inside a consolidation pass would smuggle a product
  decision through a merge.
- **Delivery-verified `instructed`** (§F2). Today `instructed` means baron emitted the
  sentence into the kit — verified at *emission*, never at *receipt*. A silently-ignored
  `AGENTS.md` is indistinguishable from a heeded one. Upgrading it needs a live runtime in CI
  and is a **new claim class** deserving its own ADR, not a quiet third value. This is the
  honest ceiling on the `instructed` label, and the 0.53 fidelity number lives here.

### Added — [ADR-023](docs/adr/ADR-023-reserved-filenames.md): the emitted config filenames are governed artifact types

Third instance of the ADR-002/ADR-008 promotion pattern, and the first to concern
the framework's **own output** rather than persona behaviour. `baron init` emits a
fixed set of config filenames — `CONVENTIONS.md`, `COORDINATION.md`, `CLAUDE.md`,
`BOOTSTRAP*.md`, the entry-point docs — and nothing in the emitted
`CONVENTIONS.md` told an agent those names are taken. **Accepted 2026-08-12 and
applied to the emitted template** (both copies; drift guard green).

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
they disagree on CONVENTIONS-vs-COORDINATION.

**Rev. 2 recommends keeping the template's order and changing the vault** — and
records that this **reverses rev. 1**, which recommended the opposite. The reversal
came from asking *what kind of rule* each chain orders: most-specific-wins is right
for **configuration**, most-general-wins for **constraints**. The two orders disagree
most sharply on the per-agent file (`AGENT.md` last vs `CLAUDE.md` first) — and every
agent's write zone includes its own workspace, so the vault's order lets the file an
agent edits itself outrank the never-list and the claims ladder. Self-service escape
hatch from governance, no bad intent required. The template's posture is corroborated
three ways inside its own text (*"don't auto-fix shared config"*; the never-list binding
personas to their `AGENT.md` scope; `AGENT.md` edits gated behind a PR).

Field survey settles the open risk from rev. 1: **both live scaffolded repos carry the
template's order verbatim** (`vanar-collab`, `baddie-analyzer-collab`) and **no persona
`AGENT.md` overrides a `CONVENTIONS.md` rule** — 17 files grepped, one benign hit. The
vault is a population of one, so changing it breaks no downstream dependency.

Recommendation is **(a) refined by (c)**: adopt one stated axis in *both* documents —
**constraints resolve most-general-wins; operational detail resolves
most-specific-wins.** Neither document says this today, which is what let the orders
drift apart unnoticed. This makes §4.3 a **template edit as well as a vault fix**,
larger than rev. 1 scoped.

Evidence base is deliberately marked thin — **one first-party incident**, against
ADR-002's and ADR-008's multi-persona pilot runs. The argument for promoting anyway
is structural, not statistical: `baron init` creates the namespace, so the exposure
is universal even where the observation is singular. §7 keeps *"wait for a second
instance"* as a legitimate owner call.

## [1.10.0] — 2026-08-09

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
`decisions/`. **Accepted with changes (Vikram, 2026-08-02 / 2026-08-04) — not yet implemented.**

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
