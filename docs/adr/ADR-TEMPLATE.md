---
created: <YYYY-MM-DD>
type: decision
status: proposed
adr: <NNN>
project: barony
authors: <who wrote it>
decided_by: Vikram
related: []
---

# ADR-NNN (PROPOSED): \<title\>

> Copy this file to `ADR-NNN-slug.md` and delete this banner. Numbers are never reused —
> check [`README.md`](README.md) § Numbering, **including the numbers reserved by unmerged
> branches**.

| Field | Value |
|---|---|
| **Status** | Proposed (\<date\>) |
| **Authors** | \<who\> |
| **Decision owner** | Vikram |

## 1. Summary

\<One paragraph: what is being decided, and what changes if it is accepted.\>

## 2. Context

\<Why this came up. What is broken, or what fork is open.\>

## 3. Supersedes / Prior art

**Required before this ADR may be marked `status: accepted`** — [ADR-029](ADR-029-prior-art-gate.md)
§4b. `baron adr check` refuses an accepted ADR without a populated block below, and CI runs it.

Prose first: what you set out to find, and what the sweep changed about this ADR. That
paragraph is the part a reader uses; the block is the part the gate checks.

Search at minimum **this repo's `docs/adr/`** and **the owner's vault**
(`/Users/vikram/Obsidian/Brain`) — a decision already taken in the vault is prior art even
though the vault is not canonical (ADR-029 §4a). Run `baron adr scaffold` to print this block.

<!-- BEGIN BARON PRIOR-ART -->
searched:
  - corpus: repo-adr
    location: docs/adr
    query: "<the terms you actually searched>"
    date: <YYYY-MM-DD>
  - corpus: vault
    location: /Users/vikram/Obsidian/Brain
    query: "<the terms you actually searched>"
    date: <YYYY-MM-DD>
hits: []          # `[]` means the sweep found nothing — say it, never omit it
# hits:
#   - ref: docs/adr/ADR-0NN-slug.md
#     disposition: supersedes | cites | distinct
#     note: <required for `distinct`: why the prior art does not apply>
<!-- END BARON PRIOR-ART -->

## 4. Decision

\<What is decided. State it so a reader who disagrees knows exactly what to argue with.\>

## 5. Honest bound

\<What this does NOT do. Every mechanism in this repo has one; an ADR that claims none is
usually the one that needs this section most.\>

## 6. Alternatives considered

| Alternative | Why rejected |
|---|---|
| \<A\> | \<why\> |

## 7. Open questions for the owner

\<Numbered, and blocking-or-not stated. Delete the section only if there are genuinely none.\>

## 8. Decision record

- [ ] Approved as written
- [ ] Approved with changes
- [ ] Needs revision
- [ ] Rejected
