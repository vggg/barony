---
created: 2026-08-03
type: decision
status: parked
adr: 004
project: demo
---

# ADR-004 (PARKED): a second telemetry transport for guard decisions

| Field | Value |
|---|---|
| **Status** | **Parked** — branch kept as history, nothing deleted, nothing merged |
| **Date** | 2026-08-03 |

## Why parked

The transport is a second, incompatible observation plane alongside the one in
ADR-003. Running both would mean two answers to "what happened", and the project
has no need that the first plane cannot serve. Parked rather than rejected: if a
consumer appears that the disk sink cannot feed, the work is on a branch.
