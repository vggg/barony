# {{PROJECT_NAME}} — Conventions

Project-wide conventions that apply to every persona on the team. These are the rules of the road. Read once; reference when needed.

## Recent changes

<!-- 3 entries max, most recent first -->

---

## Single-account constraint (first principle)

All personas commit under **one human GitHub account**. GitHub cannot tell personas apart —
it sees one author, one merger, one reviewer. Two consequences, project-wide (ADR-002 §1):

- **Every gate is enforced by persona capability** (`capabilities.allow`/`deny` in
  `persona.yaml`), **never by GitHub permissions.** CODEOWNERS, required reviewers, and
  per-user branch rules enforce nothing here; don't reach for them.
- **Persona review verdicts are PR comments, not platform approvals** — GitHub blocks
  approving your own PR, and every persona is "you." See `COORDINATION.md § Review and merge`.

---

## Repo split

| Repo | Owns | Your access |
|---|---|---|
| `{{CODE_REPO}}` | Application code, migrations, tests, PR/issue work state | Per persona (see your `agents/<you>/AGENT.md`) |
| `{{COLLAB_REPO}}` (this repo) | Persona manuals, conventions, coordination, decisions, findings, wiki | Per persona — typically write-via-PR for collaborators during trust-gating; direct push afterward |

GitHub is authoritative for **work state** (issues, PRs, merges). This repo is authoritative for **why** (decisions, findings, conventions).

---

## Identity, labels, and routing

Each persona has a row in this table. The project owner assigns persona slots to humans (one human → one or more personas).

| Persona | GitHub handle | Git identity | Commit prefix | Routing label |
|---|---|---|---|---|
| {{OWNER_HANDLE}} (owner) | `@{{OWNER_HANDLE}}` | (real human identity) | n/a (uses persona prefixes when running an agent) | `@{{OWNER_HANDLE}}` direct |
| (one row per persona — fill from `agents/<persona>/AGENT.md`) | | | | |

**Routing convention:**
- Autonomous personas (PR Reviewer, Backtest Runner, Librarian, etc.) **do not have GitHub accounts**. Tag them via the `agent-<persona>` label on the relevant issue or PR. The persona's session-start grep picks it up.
- Human collaborators **do** have GitHub accounts and can be `@`-tagged. Prefer the label-routing convention for async asks (more durable than @-mentions); reserve `@`-tag for "I need a synchronous response from this specific human."

---

## Wikilinks and file references

Use wikilinks (`[[folder/filename]]`) for vault-internal references between files in this repo. Use Markdown links (`[label](path)`) for GitHub-rendered display (READMEs, PR descriptions).

---

## Capabilities, not tool names

Work in this repo is described as abstract CAPABILITIES, never a specific runtime's tools.
Your runtime maps each capability to concrete tools via `adapters/<runtime>/HYDRATE.md`.

| Task | Capability |
|---|---|
| Read or write a file | `read_*` / `write_*` (see `references/capability-vocab.v1.md`) |
| Search content | covered by `read_code` / `read_collab` |
| Git operations | sub-tool of the runtime's shell capability |
| Work-state (issues, PRs) | `open_pr` and the project's backlog source (see `manifest.yaml`) |

The repo is a plain Markdown filesystem — it does not depend on any runtime's vault plugin or
integration layer. If your runtime offers such integrations, that is an adapter detail, not a
project convention.

---

## `_handoff/` lifecycle

All cross-persona async messages go through `_handoff/`. Filename: `YYYY-MM-DD-HHMM-<from>-<topic-slug>.md`.

Required frontmatter:
```yaml
---
created: YYYY-MM-DD
status: open
for: <PersonaName | all>
from: <PersonaName>
priority: low | medium | high
---
```

**Lifecycle:** receiver reads → acts → sets `status: done`. **Never delete handoff files.** The append-only model preserves coordination history.

**Push policy:** `_handoff/` files (both creation and status-flip) **may be direct-pushed to `main`** — they're coordination metadata, not substantive changes. Substantive changes (code, persona `AGENT.md` edits, `decisions/`, `CONVENTIONS.md`, `COORDINATION.md`, `wiki/` entries authored by the Librarian) require a PR per each persona's working rules. This exception keeps the coordination surface cheap; the PR gate stays on the things that benefit from review.

### Everything material gets a handoff

**If it's material to the project — a finding, a decision, or a correction — it gets a
`_handoff/`. No exceptions.** A PR description is not a substitute; merging the code is not
filing the finding. (ADR-002 §2 — the rule exists because findings that lived only in PR
bodies were missed by the documented handoff scan, one of them a *correction* to an
already-published finding, and the gap caused a numbering collision.)

What counts as material — if unsure, file one; the cost is a file:

- Any **finding** — every spike, experiment, or measurement. **Honest negatives especially.**
- Any **decision** that binds future work — including a decision *not* to do something.
- Any **correction** to an already-recorded finding or decision — the highest-value handoffs
  in the system and the easiest to skip, because the work already merged.

**Do not self-assign finding/decision numbers.** A number in a PR body is not a claim; only a
handoff is. Propose a number if you like ("F12 (candidate)") and route it to the Librarian —
numbering is a single-writer surface precisely so collisions have one place to be resolved.
The Librarian still sweeps merged PRs as a **backstop** and logs anything found that had no
handoff; the net catching something means the handoff was missed, not that the net is the
mechanism.

---

## Machine-local persona state

State a persona needs that must **not** travel with a clone (runtime secrets, tokens,
per-persona scratch state) lives in a stable per-user directory outside every repo —
`~/.claude/agent-state/<project>/<persona>/` on Claude Code; the equivalent stable per-user
location on other runtimes. Never in the clone (it leaks machine specifics and dies on
re-clone) and never in the runtime's install dir (clobbered on update). Pair with a
snapshot-restore practice so failover = re-clone + restore state. (ADR-002 §7.)

---

## Contradictory rules

If two documents in this repo contradict each other, the precedence order is:

1. `CONVENTIONS.md` (this file) — vault mechanics + repo-wide rules
2. `COORDINATION.md` — multi-persona protocol + workflow
3. Persona `AGENT.md` — persona-specific rules

If you find a contradiction, drop a `_handoff/` for the owner (`for: {{OWNER_HANDLE}}`) describing the conflict. Don't auto-fix shared config.

---

## What never happens

- `git push --force` to `main` on either repo
- Deleting `_handoff/` files
- Writing to `wiki/` from a non-Librarian persona
- Committing secrets (`.env`, credentials, API keys)
- A persona acting outside the scope declared in its `AGENT.md`
