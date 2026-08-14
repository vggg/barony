---
created: 2026-08-01
type: decision
status: proposed
adr: 003
project: demo
---

# ADR-003 (PROPOSED): observation-plane sinks, and what the default should be

| Field | Value |
|---|---|
| **Status** | **Proposed** — the owner decision on the shipped default is open |
| **Date** | 2026-08-01 |

## Proposal

Event sinks are discoverable plugins. Two built-ins ship: a null sink and a disk
sink writing newline-delimited rows.

## Open question

Whether the shipped default is `null` (a project emits nothing until an operator
opts in) or `disk`. This ADR proposes; it does not decide.
