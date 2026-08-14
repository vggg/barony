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
