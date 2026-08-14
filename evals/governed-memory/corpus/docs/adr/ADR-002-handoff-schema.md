---
created: 2026-07-09
type: decision
status: superseded
adr: 002
project: demo
superseded_by: ADR-005
---

# ADR-002 (SUPERSEDED by ADR-005): handoff frontmatter schema v1

| Field | Value |
|---|---|
| **Status** | **Superseded** by ADR-005 |
| **Date** | 2026-07-09 |

## Decision

A handoff note carries `created`, `from`, `for`, `status`. Priority is written
in the body prose rather than a field.

## Why this was superseded

Prose priority could not be sorted, filtered, or counted, so the queue could not
be triaged without reading every note. ADR-005 replaces this schema; do not
write new handoffs against it.
