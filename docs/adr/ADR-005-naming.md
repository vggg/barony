---
created: 2026-07-27
accepted: 2026-07-27
type: decision
status: accepted
decided_by: Vikram
adr: 005
project: barony
related:
  - "[[docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap]]"
  - "[[docs/adr/ADR-003-baron-cli]]"
---

# ADR-005: The name — **Barony** (product) / **baron** (CLI)

| Field | Value |
|---|---|
| **Status** | Accepted (2026-07-27) |
| **Date** | 2026-07-27 |
| **Authors** | Vikram + Claude |
| **Supersedes** | — (extends ADR-003 §2.1, which named the CLI) |
| **Decision owner** | Vikram |

## 1. Summary

The project shipped since v0.1 under the working name `agent-project-bootstrap` —
accurate for a scaffolding skill, wrong for what the repo became: a spec + runtime
adapters + an enforcing CLI + an audit rubric. Positioning is now
**"git-native governance for teams of AI coding agents"**, and the name follows the
metaphor ADR-003 already chose for the CLI:

- **Barony** — the product/framework as a whole: the canonical spec, the runtime
  adapters, the `baron` CLI, and the `multi-agent-audit` sister skill. The barony is
  the governed estate; the framework is the governance.
- **baron** — the CLI, unchanged (lowercase, code). ADR-003 §2.1's rationale stands:
  the baron keeps the estate's books without owning the work done on the land.

The naming rule, stated once and applied everywhere:
**install `barony`, run `baron`, import `baron`.**

## 2. Research summary

- **Availability** — `barony` was free as a PyPI distribution name and as an npm
  package name at decision time; the GitHub repo slug `vggg/barony` was free.
- **Collision check** — "Barony" collides with a 1993 strategy video game and generic
  feudal-history usage. Judged acceptable: no software-tooling collision, no PyPI/npm
  squatting, and search results in the developer-tools context are uncontested.
- **Burned alternatives** — considered and rejected: **troupe** (taken in adjacent
  agent-framework space), **seneschal** (unspellable/untypeable in practice),
  **reeve** (name collisions in dev tooling), **witan** (obscure; pronunciation
  ambiguity). None beat the barony/baron pair's continuity with ADR-003.
- **Sub-brand reserved: "signet"** — the name for SHA-sealed verdicts (the reviewer's
  `REVIEW:PASS <head-sha>` comment pattern of ADR-002 §4: a verdict sealed to the
  exact commit it judged). Reserved, used only where verdicts are described; not a
  package or command today.

## 3. Rename mechanics

- **Repo** — `vggg/agent-project-bootstrap` renamed to `vggg/barony` on GitHub;
  GitHub serves redirects from the old URLs (clones, remotes, and links keep working).
  Docs now cite `github.com/vggg/barony`.
- **Package** — the PyPI distribution `baron-cli` becomes **`barony`** at CLI
  version 0.4.0. The console script stays `baron`; the import package stays `baron`
  (`pip install barony`, then `import baron`). The optional extra is now
  `barony[pydantic-ai]`.
- **Skill directory** — `skills/agent-project-bootstrap/` renamed to
  `skills/barony/` (git mv, history preserved); the skill's frontmatter `name:` is
  `barony`; plugin manifest `name` is `barony`. The sister skill keeps its name:
  `multi-agent-audit`.
- **History** — CHANGELOG entries, ADR bodies, and other historical records keep the
  old name where they describe the past; only the canonical-URL frontmatter, live
  paths, and current-identity statements were updated.

## 4. Consequences

- Positive: one coherent naming system (Barony the estate, baron the clerk); a
  publishable, memorable PyPI/npm identity; the product name finally matches the
  governance positioning rather than the v0.x scaffolding origin.
- Negative / costs: a one-time ecosystem rename (links, installs, muscle memory);
  the residual risk that "Barony" reads as the game to a minority of searchers; any
  pre-rename external references to `baron-cli` on PyPI must be migrated by hand
  (the old distribution name was never published, so no PyPI-side redirect is
  needed).
