# LEARNINGS — Barony

Lessons from the ADR-001 §10 dogfood (the v0→v1 story itself lives in ADR-001 + `CHANGELOG.md`).

> **Scope note:** this is the minimum-viable lessons index — enough to anchor the references
> that cite it. The comprehensive self-hosting outcome notes (which verbs surfaced from
> observed need, where the spec bent, what was discarded) are at
> [`references/v1-self-hosting-notes.md`](../skills/barony/references/v1-self-hosting-notes.md).

## Lessons (`Lx`)

- **L1 — A runtime-neutral persona spec is viable.** The adapter spike confirmed a single
  abstract `persona.yaml` can hydrate working behavior contracts on different runtimes; the
  runtime-specific surface collapses to one `HYDRATE.md` per runtime.
- **L2 — Enforceability is a property of the runtime, not the capability.** The same
  capability verb is whole-tool-enforceable on a runtime that allow-lists tools and only
  instruction-enforceable on one that doesn't. The canon describes intent; the adapter decides
  how much of it the runtime can actually guarantee.
- **L3 — Instruction-only (sub-tool) guardrails still add real value when whole-tool
  enforcement isn't possible.** When a denial lives inside a shared tool (git/gh/tests via the
  shell, path-scoped writes), the runtime can't make the action impossible — but rendering the
  denial as an explicit instruction in the persona body demonstrably catches real mistakes.
  This is why the spec mandates rendering sub-tool denials as instructions rather than dropping
  them as unenforceable.

## Proven (`Proven #N`)

- **Proven #1 — One adapter folder per runtime stays Open/Closed-clean.** Adding a runtime is
  a new `adapters/<runtime>/` folder; the canon and personas are untouched.
- **Proven #2 — The v1 capability vocabulary earned every verb (YAGNI held).** No v1 verb was
  added speculatively. Each one entered the vocabulary only because a real persona on a real
  adapter task needed it — which is why the frozen v1 list is short. Backs the "additions
  require observed need" design rule in
  [`references/capability-vocab.v1.md`](../skills/barony/references/capability-vocab.v1.md).
