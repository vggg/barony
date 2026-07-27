# {{PROJECT_NAME}} — Multi-Persona Coordination

How the personas on this project coordinate work. Read at session start.

## Recent changes

<!-- 3 entries max, most recent first -->

---

## Personas at a glance

| Persona | Archetype | Owns |
|---|---|---|
| (one row per persona — fill from `agents/<persona>/AGENT.md`) | dev / autonomous-event / autonomous-cron / librarian (+ optional reviewer / merger dev-variants) | |

Full operating manuals: `agents/<persona>/AGENT.md` (derived from `agents/<persona>/persona.yaml` — the yaml is canonical).

---

## Session-start checklist

Every persona, every session. These steps are stated as intent (capabilities, not a specific
runtime's commands). Your runtime maps each to concrete syntax via
`adapters/<runtime>/HYDRATE.md`; the capability verbs are defined in
`references/capability-vocab.v1.md`.

1. **Sync both repos** to the latest `main` — the collab repo (`{{LOCAL_COLLAB_PATH}}`) and, if
   you have code-repo write access, the code repo (`{{LOCAL_CODE_PATH}}`).
2. **Read your persona's `agents/<you>/AGENT.md`** for any updates.
3. **Check open handoffs addressed to you** (`read_collab`): in `{{LOCAL_COLLAB_PATH}}/_handoff/`,
   find entries with `status: open` and `for: <you>` or `for: all`.
4. **Read open work assigned to you** from the project's backlog source (see `manifest.yaml`):
   items labelled `agent-<you>` on both the code and collab repos.
5. **Read this file (`COORDINATION.md`)** for protocol updates.

Then: begin work.

---

## Multi-persona dev rules

- **One branch per active task.** Don't open parallel branches against the same files.
- **No direct commits to `main`** on the code repo. All changes via PR.
- **PR review:** code repo PRs are reviewed per the project's review policy (see `§ Review and merge` below and `BOOTSTRAP-ADMIN.md`); collab repo PRs go through {{OWNER_HANDLE}} during initial trust window if active.
- **Scope discipline:** for any ticket touching more than 3 files, a schema migration, or a public module boundary — write the plan in chat and stop for {{OWNER_HANDLE}}'s review before writing code.

---

## Hot files

Files that need coordination across personas. Pattern vocabulary:

- **Separation** — file is split per-persona; no shared write target. No coordination needed.
- **Owner** — single persona is the gatekeeper. Others file tickets to change.
- **Lock** — labels claim exclusive edit access. Release on merge or after 24h soft timeout.

Hot files for this project:

| File / glob | Pattern | Owner / Lock label | Notes |
|---|---|---|---|
| `CONVENTIONS.md` (this repo) | Owner | {{OWNER_HANDLE}} | Project rules; rare changes; file ticket |
| `COORDINATION.md` (this repo) | Owner | {{OWNER_HANDLE}} | Same |
| `agents/<persona>/persona.yaml` + `AGENT.md` | Owner | that persona (or {{OWNER_HANDLE}}) | Persona's own canonical spec + manual |
| `wiki/log.md`, `wiki/*` | Owner | Librarian | Enforced by capability — `write_path: [wiki]` is denied to everyone else |
| {{HOT_FILES_TABLE_ROWS}} | | | *(add tech-stack-specific hot files here — e.g. schema files, lockfiles)* |

**Lock mechanics — the open PR is the lock (ADR-002 §3; this replaces the old
markdown LOCK-commit protocol, which was itself race-prone):**
1. **Claim** with `baron lock claim <path> --reason "<why>"` — it opens a draft PR
   labeled `lock:<path>` from a `lock/<slug>` branch (one empty commit; the PR exists
   only to hold the lock), and *refuses* if an open lock PR for the same path already
   exists, showing the holder. Working without baron? Open the draft PR + `lock:<path>`
   label by hand — the label is the contract, the tool is convenience.
2. **Check** before starting: `baron lock list` (or one query of the open-PR list for
   `lock:*` labels — never a grep of coordination files).
3. **Release** with `baron lock release <path>` (closes the lock PR + deletes its
   branch); merging or closing the lock PR releases it too.
4. The **CI lock guard** (`.github/workflows/lock-guard.yml`, emitted with this repo)
   fails any *other* PR touching a locked path — the race window ("two personas check,
   both see nothing, both claim") is closed with no human in the loop. The lock PR
   itself is exempt.

**Owner mechanics — an evidence gate, not a human approver:** a PR touching an Owner path
requires the declared evidence (e.g. a `contract-change`-style label plus a linked ADR or
`_handoff/`). CI checks that the discipline was followed; the owner reviews when they want
to, not because the merge is stuck. Exception: where the Owner pattern is already enforced by
a **capability denial** (like `wiki/`), keep it — a write gate is strictly stronger than any
review gate; don't migrate it to CI.

> **Honest limitation:** without branch protection (unavailable on free private repos), a red
> check does not physically block a merge — the guard is enforcement by convention plus a
> visible alarm. That is still strictly better than a silent manual check.

---

## Review and merge (optional Reviewer/Merger module — ADR-002 §4)

Projects that adopt the reviewer + merger personas (`agents/__REVIEWER__/`,
`agents/__MERGER__/` templates) route every code-repo merge through them:

1. **Dev opens the PR** and requests review (label `agent-<reviewer-slug>` or a `_handoff/`).
2. **Reviewer** (fresh context, adversarial, read-only) reviews judgement — not mechanics CI
   already covers — and publishes a **verdict as a PR comment bound to the exact head SHA
   reviewed** (`REVIEW:PASS <sha>` / `REVIEW:FAIL <sha>`). Never the platform's approve:
   under the single-account constraint (`CONVENTIONS.md`), self-approval is blocked and the
   comment is the verdict surface. A verdict is about a **commit** — a new push makes it stale.
3. **Merger** — the only persona holding `merge_pr` — verifies preconditions and merges, or
   refuses naming the failed precondition: CI green on the *current* head SHA; a REVIEW:PASS
   naming the *current* head SHA; record obligations met (handoffs for material
   findings/decisions); no hot-file collision.

Projects without the module: per-project review policy decides, and `merge_pr` typically
stays with {{OWNER_HANDLE}}.

**Persona-spec CI validation (ADR-002 §5):** the repo's CI validates every
`agents/*/persona.yaml` on each PR — it parses, required schema fields are present, and
capability verbs come from the frozen v1 vocabulary. An invalid canonical spec is worse than
a missing one; every adapter hydrates from it.

---

## ADR rules

File an ADR when:
- Choosing between two viable technical approaches
- Deciding to break from a pattern established in a prior ADR
- Making an infrastructure or schema change that can't easily be reversed

**Format:** Full ADR lives in the code repo at `docs/adr/ADR-NNN-slug.md`. This collab repo holds a pointer stub:

```markdown
projects/decisions/ADR-NNN-slug.md
---
adr: NNN
title: <title>
status: accepted | proposed | superseded
date: YYYY-MM-DD
repo_path: docs/adr/ADR-NNN-slug.md
---
One-sentence summary of the decision.
```

Project-level (non-architectural) decisions live in `decisions/YYYY-MM-DD-HHMM-slug.md` with their full content — no code-repo pointer.

---

## Branching (code repo)

- `main` — production; protected; reviewed merges only
- Feature branches: `<persona>/<ticket-number>-<slug>` (e.g. `dave/123-add-export`)
- Rebase on `main` before opening a PR
- Use `Closes #N` in PR body to auto-close issues on merge

---

## Ticket lifecycle (code repo)

1. Analyst (or any persona) opens a GitHub issue with title, context, acceptance criteria, and label
2. Persona self-assigns the work item to itself and applies its `agent-<self>` label on the project's backlog source (the concrete command is a runtime/backlog detail — see `adapters/<runtime>/HYDRATE.md`)
3. Persona creates feature branch, opens PR when ready
4. Per-project review policy decides who approves and merges
5. Persona writes dev-log entry; closes issue via PR description

---

## Async handoff protocol

GitHub comments are for code discussion. Cross-persona coordination — task handoffs, blocking questions, completed subtask notifications, requests for input — go through `_handoff/`. See `CONVENTIONS.md § _handoff/ lifecycle` for format.

**Personal librarian extension:**
If the project owner runs a librarian-equivalent persona on their personal machine in addition to this project, they can address handoffs `for: librarian` from this repo. That persona's session-start handoff scan extends to read this repo's `_handoff/` for items addressed to it. One-way visibility — this repo doesn't see the owner's personal workspace.

---

## Conflict resolution

If two personas produce conflicting changes to the same file:
1. Stop — do not force-push
2. Drop a handoff describing the conflict; {{OWNER_HANDLE}} resolves it
3. Wait for resolution before continuing on the affected file

---

## What never happens

- A non-Librarian persona writes to `wiki/`
- A persona acts outside the scope declared in its `AGENT.md`
- Merging a PR that touches another persona's owner-locked files without that persona's approval
- Skipping a label lock on `Lock`-pattern hot files

---

## Source-of-truth split

| What | Where |
|---|---|
| Code, migrations, tests | `{{CODE_REPO}}` |
| PR state, issue backlog | GitHub (both repos) |
| Rationale, research, decisions | This repo (`{{COLLAB_REPO}}`) |
| Session history, reconciliation | `wiki/log.md` in this repo |
