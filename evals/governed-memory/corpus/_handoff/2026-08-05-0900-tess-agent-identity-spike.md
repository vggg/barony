---
created: 2026-08-05
status: open
for: Vikram
from: Tess
priority: high
---

# Agent identity — options spike is done, a decision is needed

F4 is a hole in the thesis, not a bug. The survey is written up outside this repo
as the note `wiki/research-agent-identity-lightweight`; this handoff is the
citable pointer to it.

**Recommendation carried from the spike:** per-persona SSH signing keys generated
at spawn, enrolled once into an in-repo signers file behind an owner gate,
verified offline. The runner-up (keyless signing rooted in an identity provider)
is stronger cryptography and a weaker answer, because it signs as whatever
account the persona authenticates with.

**Owner action:** sign or reject. If signed this becomes ADR-027.
