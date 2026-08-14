---
created: 2026-08-13
type: decision
status: accepted
accepted: 2026-08-13
adr: 025
project: barony
authors: Atlas (design proposal for Vikram)
decided_by: Vikram
related:
  - "[[docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap]]"
  - "[[docs/adr/ADR-006-baron-init-template-packaging]]"
  - "[[docs/adr/ADR-024-fleet-health]]"
---

# ADR-025 (ACCEPTED): the coordination monorepo — projects as subdirs, the portfolio as a `_meta` project

> **ACCEPTED 2026-08-13 (Vikram) — §7 answered as recommended:** Q1 keep `baron init` for the root +
> add `baron add-project`; Q2 `repository_dispatch` carries the `project`, gate `cd`s into that subdir;
> Q3 identity stays `<slug>@<project>.local`; Q4 monorepo is an **opt-in `--layout monorepo` mode**,
> per-project-repo remains the default for adopters. Reframes the "portfolio tier" as a topology, not a
> new abstraction.

## 1. Problem

`baron init` creates **one collab repo per project** (ADR-006), referencing a separate code repo — so
N projects is 2N repos. That default buys **multi-tenant isolation** (different access per project) and
**independent lifecycle** (archive one without touching others), which matter for teams and OSS
adopters. For a **single owner running a portfolio of fleets**, it buys mostly repo sprawl and — the
real cost — **no cross-project view**: you cannot clone one thing and ask "what is my whole fleet
doing, and what needs me across all of it?" The portfolio tier this ADR addresses was previously
treated as a missing abstraction; it is better understood as a topology the tool does not yet emit.

## 2. Decision (proposed)

A single **coordination monorepo**. Each project is a **subdirectory** carrying its own
`manifest.yaml`, `agents/`, `_handoff/`, `decisions/`, `findings/`, `wiki/`. The **portfolio/meta tier
is itself a project** — a code-less `_meta/` subdir whose "personas" are project-librarians and whose
work items are cross-project decisions. The recursion is the point: **the portfolio is a project that
coordinates projects**, governed by the same primitives one level up.

```
fleet-coordination/            # ONE collab monorepo (git)
  _meta/                       #   the portfolio project (no code repo)
    manifest.yaml  agents/  _handoff/  decisions/
  barony/                      #   project — code repo: vggg/barony
    manifest.yaml  agents/  _handoff/  ...
  badminton-analyzer/          #   project — code repo: vggg/badminton-analyzer
    manifest.yaml  agents/  _handoff/  ...
```

Code repos stay **separate and per-project** (each subdir's manifest points at its own). Only the
*coordination* substrate is unified. `baron status` / `baron health` / the decision brief now run
**portfolio-wide** by walking the subdirs.

## 3. What it costs (stated, not hidden)

- **Access is all-or-nothing.** A monorepo cannot grant per-project access. Fine for a solo owner;
  a blocker for the multi-tenant case, so this is a **mode**, not a replacement for per-project collab.
- **Actions routing.** Emitted workflows (`baron-notify.yml`, lock-guard, strip-stale-verdict) fire
  repo-wide; they must become **path-scoped per project subdir**, and `repository_dispatch` must carry
  the project so the gate resolves the right subdir. This is the main net-new engineering.
- **A different `init` surface.** `baron init` currently = one collab repo. The monorepo needs
  `baron add-project <name>` to graft a subdir into an existing coordination repo (see §7 Q1).

## 4. §7 — Owner decisions (not self-decided)

1. **`init` reshaped, or a new `baron add-project`?** Recommend: keep `baron init` for the first
   project / the monorepo root, add `baron add-project` for subsequent subdirs.
2. **Dispatch routing:** does `repository_dispatch` carry a `project` in the payload, and the gate
   `cd` into that subdir? (Needed for per-project wake in a monorepo.)
3. **Persona namespacing:** identity becomes `<slug>@<project>.local` scoped by subdir — confirm the
   git-identity/commit-prefix scheme survives unchanged.
4. **Mode flag:** is monorepo an explicit `--layout monorepo` mode, with per-project-repo remaining the
   default for adopters? (Recommend yes — keep the isolation default; make monorepo opt-in.)

## 5. Evidence / relation

First-party: Vikram's own portfolio (Barony, badminton, Nasiko, GardenTwin, VANAR) — 5+ fleets, no
unifying coordination surface today. Relates to ADR-024 (`baron health` becomes portfolio-wide) and to
the control-plane pilot, which is naturally the **`_meta` project — the monorepo's first brick.**

## 6. Amendment (2026-08-14) — what the first real monorepo found

The topology was implemented in PR #42 and immediately dogfooded: `fleet-coordination`
stood up as a coordination monorepo, with Barony itself grafted in as the first
non-`_meta` project. Two defects made it unusable and five made it unpleasant. All are
recorded here because §3 promised the costs would be stated, not hidden — and these were
costs §3 did not anticipate.

**The two that mattered shared a failure mode: they failed silently upward.**

1. **The self-aliasing code repo.** `add-project barony --code-repo <url>` emitted
   `repos[].path: ../barony`. A URL names no local path, so baron assumes the
   conventional sibling clone — but the sibling of a monorepo *subdir* is one level
   further up than the sibling of a standalone collab repo. From `<root>/barony/`,
   `../barony` resolves to the project subdir itself. Every path then existed and was
   inside a git work tree, so `baron status` reported the code repo **green** with
   nothing ever cloned. A false green is worse than a red: a red starts an
   investigation and a green ends one. Fixed by re-basing the assumed sibling for the
   nesting level, and by refusing outright any `--code-repo` that resolves to the
   coordination repo, inside it, or containing it — a code repo is a *separate* repo
   (§2), so aliasing is never a valid spelling of anything.

2. **The absent `notify:` block.** `add-project` emitted no `notify:`, so
   `notify.wake_allowed` was empty and the monorepo wake gate failed closed: a grafted
   project could never be woken. Fail-closed is correct (ADR-010 §5.5 — a project that
   has not decided who may spend money does not spend money), but **absent and empty
   are not the same thing to a reader**. Absent gives you nothing to search for. The
   block is now emitted always, empty-with-instructions, and `--wake-allowed` makes
   opening the gate one explicit flag rather than a hand-edit nobody knows to make.
   This corrects a §2 assumption: reusing `baron init`'s emitters "verbatim" only
   inherits what those emitters actually emit, and `init` did not emit this either.

The rest:

3. **Portfolio dirt was mis-attributed.** `git status --porcelain` reports the whole
   work tree regardless of which subdir it runs in, so one uncommitted file made every
   project dirty (`_meta` was flagged for an edit to `barony/manifest.yaml`). The
   dirty check is now path-scoped. Generalization worth keeping: **any single-project
   check that shells out to git needs re-auditing for a shared work tree** — the
   monorepo turns "the repo" and "the project" into different things, and every place
   that conflated them is a latent version of this bug.
4. **Archetype provenance was thrown away.** The `__REVIEWER__` and `__MERGER__`
   templates hard-coded `archetype: dev`, so a scaffolded roster read back as
   indistinguishable devs. They are dev-*shaped* — same hydration mechanics, narrower
   capabilities — but dev-shaped is not the same claim as `dev`. `reviewer` and
   `merger` are now first-class enum values (warning-severity, so nothing downstream
   breaks) and the templates record them.
5. **A nested `.github/` is inert and silent.** GitHub resolves workflows from the
   repository root only, so a `.github/` in a project subdir fires never while reading
   like working CI to anyone in that subdir. The failure mode is believing you have a
   lock guard. Both commands now warn; neither deletes.
6. **No migration path.** `add-project` scaffolds and refuses a non-empty target, so an
   existing collab repo had no way in — the dogfood did the subtree graft by hand and
   hand-edited the marker. `baron adopt-project` closes this. It deliberately does
   **not** wrap the graft: `git subtree add` preserves history and `mv` does not, and
   choosing between them is the owner's call, not baron's. Baron picks up where git
   leaves off — verify, register, re-render, commit.
7. **Persona names collide across projects in one clone.** `dev`/`reviewer`/`merger`/
   `librarian` are the default slugs, so two projects in one monorepo clone fight over
   the same agent names when a runtime resolves personas globally. **Deferred to its
   own ADR/PR** — the fix spans the persona spec, all four adapters and the drift
   checker, and the honest scope is "how does persona registration become
   project-local", not a patch to `add-project`. Until then the workaround is
   per-project slugs (`--personas dev:fern,librarian:iris`), which the docs already
   recommend for unrelated reasons.

**What this says about the topology:** none of these are arguments against projects-as-
subdirs. Every one is an instance of the same root cause — code written when "the collab
repo" and "the git repo" were the same directory, run in a world where they are not. §2's
claim that "a monorepo subdir is an ordinary Barony project, which is what lets every
other command ignore the distinction" holds for the *data* and fails for anything that
shells out to git or assumes its own nesting depth. That boundary is now explicit.
