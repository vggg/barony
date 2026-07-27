# decisions/

Project-level decisions for {{PROJECT_NAME}}.

## What goes here

**Project decisions** with the full content — strategy choices, scoping calls, persona changes, process changes. Filename: `YYYY-MM-DD-HHMM-<slug>.md`.

**ADR pointers** — when an architectural decision meets the ADR trigger (per `COORDINATION.md § ADR rules`), the full ADR goes in the code repo at `docs/adr/ADR-NNN-slug.md`; this folder holds a pointer stub. Filename: `ADR-NNN-slug.md`.

## Format — project decision

```markdown
---
created: YYYY-MM-DD
type: decision
status: accepted | proposed | superseded
decided_by: <PersonaName | owner>
---

# <Title>

**Decision:** <One-paragraph crisp statement of what was decided.>

## Context
<Why this came up.>

## Decision
<Detail.>

## Rationale
<Why this over alternatives.>

## Implications
<What this changes; what unblocks.>
```

## Format — ADR pointer stub

```markdown
---
adr: NNN
title: <title>
status: accepted | proposed | superseded
date: YYYY-MM-DD
repo_path: docs/adr/ADR-NNN-slug.md
---

# ADR-NNN: <Title>

One-sentence summary. Full content at `{{CODE_REPO}}/docs/adr/ADR-NNN-slug.md`.
```

## Lifecycle

Decisions are append-only. To supersede a previous decision: write a new decision file, set the old one's `status: superseded`, link forward and back.
