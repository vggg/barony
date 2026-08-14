---
created: {{DATE}}
type: decision
status: proposed
adr: NNN
project: {{PROJECT_NAME}}
authors: <persona or owner>
decided_by: {{OWNER_HANDLE}}
related: []
---

# ADR-NNN (PROPOSED): \<title\>

> **Template.** Copy into the code repo at `docs/adr/ADR-NNN-slug.md`, delete this banner,
> and leave a pointer stub here per `../COORDINATION.md § ADR rules`. ADR numbers are never
> reused.

| Field | Value |
|---|---|
| **Status** | Proposed (\<date\>) |
| **Authors** | \<persona\> |
| **Decision owner** | {{OWNER_HANDLE}} |

## 1. Summary

\<One paragraph: what is being decided, and what changes if it is accepted.\>

## 2. Context

\<Why this came up. What is broken, or what fork is open.\>

## 3. Supersedes / Prior art

**Required before this ADR may be marked `status: accepted`.** `baron adr check` REFUSES an
accepted ADR whose prior-art block is missing, malformed, or incomplete — exit 1, not a
warning. Wire it into CI:

```bash
baron adr check docs/adr            # add --require repo-adr if this project has no vault
```

Prose first: what you set out to find, and what the sweep changed about this ADR. Then the
machine-checked block — run `baron adr scaffold` to print it:

<!-- BEGIN BARON PRIOR-ART -->
searched:
  - corpus: repo-adr
    location: docs/adr
    query: "<the terms you actually searched>"
    date: <YYYY-MM-DD>
  - corpus: repo-decisions
    location: decisions/
    query: "<the terms you actually searched>"
    date: <YYYY-MM-DD>
hits: []          # `[]` means the sweep found nothing — say it, never omit it
# hits:
#   - ref: docs/adr/ADR-0NN-slug.md
#     disposition: supersedes | cites | distinct
#     note: <required for `distinct`: why the prior art does not apply>
<!-- END BARON PRIOR-ART -->

**Corpora** (`corpus:` is a closed vocabulary): `repo-adr`, `repo-decisions`, `vault`,
`external`. **Dispositions**: `supersedes` (this overrides it), `cites` (it stands and
informs this), `distinct` (found it, does not apply — needs a `note`).

**What this gate does and does not do.** It enforces that a search was *recorded*, not that
it was thorough. It turns "I forgot to check" from silent into blocked; it cannot tell you
the searcher found everything.

## 4. Decision

\<What is decided. State it so a reader who disagrees knows exactly what to argue with.\>

## 5. Honest bound

\<What this does NOT do.\>

## 6. Alternatives considered

| Alternative | Why rejected |
|---|---|
| \<A\> | \<why\> |

## 7. Open questions for the owner

\<Numbered, and blocking-or-not stated.\>

## 8. Decision record

- [ ] Approved as written
- [ ] Approved with changes
- [ ] Needs revision
- [ ] Rejected
