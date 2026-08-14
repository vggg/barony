# observations/

The Observer's zone for {{PROJECT_NAME}}. One dated note per observation cycle.

**Single-writer.** Only the `observer` persona writes here; every other persona reads it.
That is a capability, not an etiquette rule: the Observer's `write_path` allows
`observations` and `_handoff` and nothing else, and no other archetype's spec lists this
scope. See `agents/<observer-slug>/persona.yaml` and ADR-029.

## What goes here

`YYYY-MM-DD-<slug>.md` — what the fleet actually did this cycle, what it stopped doing, and
where the record and reality disagree. Stalls, ledger/handoff drift, claim-integrity slips,
re-derivation of settled ground, and output accumulating with no consumer.

## What does NOT go here

- **Numbered records.** Findings and decisions are the Librarian's single-writer surface. An
  observation that deserves an `F<N>` is proposed via `_handoff/`; the Librarian numbers it.
- **Verdicts and gates.** An observation is evidence, not a decision and not a block.
- **Fixes.** The Observer has no `write_code`. It names things; someone else acts.

## Format

```yaml
---
created: YYYY-MM-DD
type: observation
author: <PersonaName>
cycle: <what was swept — repos, refs, date window>
---
```

Body: a two-line summary; observations most-severe first, each naming the evidence path
(file, SHA, PR number, or command output) anyone can re-check; and a **coverage bound**
section — which surfaces were read, which were not, and what a clean board here does and
does not prove.

## Lifecycle

Append-only, like `findings/`. Notes are never rewritten to match how things turned out —
an observation that was wrong is itself a useful record of what the substrate looked like at
the time. Correct it in the next cycle's note, linking back.
