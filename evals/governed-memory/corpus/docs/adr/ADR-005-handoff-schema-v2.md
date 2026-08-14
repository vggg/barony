---
created: 2026-07-28
type: decision
status: accepted
adr: 005
project: demo
supersedes: ADR-002
---

# ADR-005 (ACCEPTED): handoff frontmatter schema v2 — priority becomes a field

| Field | Value |
|---|---|
| **Status** | **Accepted** — supersedes ADR-002 |
| **Date** | 2026-07-28 |

## Decision

Handoff frontmatter is `created`, `from`, `for`, `status`, `priority`. Priority
is one of `low`, `medium`, `high` and is a required field, not prose. This is
the current handoff schema; ADR-002 describes the retired one.

## Consequences

`baron handoff list` can sort and filter the queue without opening notes.
Existing v1 notes are read with `priority` defaulting to `medium` and are not
rewritten.
