---
created: 2026-07-02
type: decision
status: accepted
adr: 001
project: demo
---

# ADR-001 (ACCEPTED): one collab repo per project, code repos stay clean

| Field | Value |
|---|---|
| **Status** | **Accepted** |
| **Date** | 2026-07-02 |

## Decision

Governance state — personas, ledgers, handoffs, locks — lives in a dedicated
collab repository. The code repository carries code and nothing else. A project
is the pair.

## Consequences

Every governed artifact is reachable from a single `git clone`, and a code repo
can be handed to someone with no interest in the fleet without leaking
coordination state.
