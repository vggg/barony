---
created: 2026-08-14
type: decision
status: accepted
adr: 027
project: demo
related:
  - "[[wiki/research-agent-identity-lightweight]]"
---

# ADR-027 (ACCEPTED): per-persona signing keys enrolled in the repo

| Field | Value |
|---|---|
| **Status** | **Accepted** |
| **Date** | 2026-08-14 |

## Context

F4 recorded that an un-onboarded agent landed work on `main` under the owner's
git identity, and that the repository alone could not say who had done it. The
options survey that led here is the spike note held outside this repo; it is
cited in the handoff that promoted it, not reproduced.

## Decision

Each persona generates an Ed25519 keypair at spawn and signs every commit and
every handoff with it. Public halves are enrolled once into an in-repo
`allowed_signers` file behind an owner-gated review; after that one gate,
enrolment and signing are automatic.

Verification is offline: `git verify-commit` against the in-repo file. No
server, no certificate authority, no network call, no vendor.

## What this buys, stated exactly

Not "this agent is trustworthy". It buys: *this artifact was produced by the key
enrolled under that persona name, and nobody else, and a stranger can prove it
from a clone.* That is precisely the property the incident in F4 lacked.

## Rejected alternative

Keyless signing rooted in an identity provider is cryptographically the stronger
story, but it inherits the shared-account problem rather than solving it: if
every persona authenticates as the same subject, every persona signs as that
subject and attribution is exactly as absent as it is today.
