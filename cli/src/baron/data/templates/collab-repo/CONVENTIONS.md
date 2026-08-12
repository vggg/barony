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

### A label is not evidence — in either direction (ADR-008 §1)

**Review-state labels are an index, not a record.** The record is the **verdict comment bound to a
head SHA** (`REVIEW:PASS <sha>` / `REVIEW:FAIL <sha>` — see `COORDINATION.md § Review and merge`). A
label can be stale, hand-applied, or left behind by a push that landed after the review ran; a
verdict names the commit it judged and cannot drift.

> **Scope: this rule is about *review-state* labels only** — the ones asserting a verdict
> (`reviewed-approved`, `changes-requested`, …). Other labels in this project *are* contracts and
> are unaffected: `lock:*` labels **are** the lock (`COORDINATION.md § Hot files`), routing labels
> `agent-<persona>` are how work is addressed, and Owner evidence-gate labels like
> `contract-change` are gates the owner sets and lifts. Those assert a *state someone set
> deliberately*; a review-state label asserts a *judgement about a commit*, and only the commit
> can settle whether it still holds.

This binds every persona, in **both** directions:

- **Before acting on an approval label** (`reviewed-approved` or the project's equivalent) — read the
  latest verdict comment and confirm the SHA it names equals the current head. If they differ, the
  approval is void: strip the label, say why, and stop. *(The Merger already carries this as a merge
  precondition; the rule is general.)*
- **Before concluding a block is stale** (`changes-requested` or the project's equivalent) — the same
  check on the same evidence. If the verdict names your current head, the block is **current**: the
  review ran *after* your push, and you are not waiting on another review cycle. Read the verdict and
  act on it.

**Corollary — green CI is not the gate either.** CI green plus a pushed fix does not clear a block;
only a verdict at the current head does.

**Prefer removing the ambiguity to adding a referee.** `.github/workflows/strip-stale-verdict.yml`
(scaffolded with this repo) removes review-state labels on every `synchronize`, so a label is far
less likely to outlive the commit it described. It **narrows the window; it does not close it** — the
workflow can be absent from the code repo, be edited, not cover a label this project added, or
simply not have run yet. The SHA check above is still what decides. Do not resolve a
label-vs-verdict disagreement by adding another persona to adjudicate it; check the SHA.

> **Why this rule exists (pilot evidence, 2026-07-31).** Both directions failed in production inside
> 24 hours: a merger nearly merged an unreviewed head off a label that survived a later push, and a
> dev idled ~40 minutes reporting a *current* block as "stale — the reviewer just hasn't re-run yet"
> when the verdict named its exact head and predated the report by half an hour. One root cause both
> times: substituting a cheap signal for the expensive one, because the cheap signal agreed with what
> the reader wanted.

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

### Decision & ADR intake — the Librarian RECORDS **and RECONCILES** (ADR-008 §4)

A decision is durable only when it reaches the surfaces personas pull **work** from — not just the
record. Appending to `decisions/` is the obvious half; **reconciling the surfaces the decision
contradicts is the load-bearing half.** Skipping it is why a settled direction gets silently
re-litigated across sessions: personas re-derive "what to build next" from the direction doc, the
open epics, and the backlog — never from `decisions/`.

So when a decision or ADR is made or ratified — signalled by a `for: Librarian` handoff whose topic
starts **`DECISION:`**, or by an owner ratification — the Librarian runs the **full intake**, not a
`decisions/` append alone:

1. **Record with supersession.** Append to `decisions/` (or the ADR), stating explicitly what it
   **overrides**, with a back-pointer both ways. Decisions supersede; they do not accumulate
   silently beside the thing they contradict.
2. **Reconcile the work-pull surfaces — load-bearing.** Find every open epic, backlog item, ticket,
   or roadmap line that contradicts the decision and **park or close it** (label + comment pointing
   at the decision) so no persona can claim the now-wrong work. *A decision that leaves
   contradicting work claimable will be reverted by the next persona that pulls it.*
3. **Reconcile the authoritative direction doc.** If it lives in a repo the Librarian cannot write
   (e.g. the code repo), route a docs ticket to a dev persona — never leave it stale.
4. **Broadcast.** A `for: all` handoff stating the decision and its per-persona queue impact; update
   the status board.
5. **Directional decisions** additionally get hydrated at **session start, before ticket selection** —
   a direction nobody reads before choosing work is not in force.

Personas making a decision: file the `for: Librarian` `DECISION:` handoff. Do not self-reconcile, and
do not assume "recorded in a PR body" propagates.

Like every gate here, this is discipline-in-a-doc, not a lock — it depends on the Librarian running
the intake. (Pilot evidence, 2026-07-31: a ratified direction was recorded but not reconciled, and
the contradicted epics stayed claimable — so the settled question was re-opened by later sessions
pulling from the surfaces the decision never touched.)

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

1. `CONVENTIONS.md` (this file) — repo mechanics + repo-wide rules
2. `COORDINATION.md` — multi-persona protocol + workflow
3. Persona `AGENT.md` — persona-specific rules

**Why general beats specific here (ADR-023 §4.3).** This is the opposite of a config cascade, on purpose. Most-specific-wins is right for *configuration*, where a narrower file is better informed. These documents also carry *constraints* — and constraints run the other way, because the narrowest file is the one the persona itself can edit. A persona that could override `CONVENTIONS.md` from its own `AGENT.md` would be granting itself scope, which is the one thing this repo exists to prevent. The rule of thumb:

> **Constraints resolve most-general-wins. Operational detail resolves most-specific-wins.**

Constraints are `What never happens`, the claim/evidence rules, and the review-loop gates: they bind everyone and cannot be overridden locally. Operational detail is which paths you write, which commands you run, which fixtures you use: yours to decide, and your `AGENT.md` wins. Consistent with this, your `AGENT.md` **binds** you — see `What never happens` — rather than empowering you.

If you find a contradiction, drop a `_handoff/` for the owner (`for: {{OWNER_HANDLE}}`) describing the conflict. Don't auto-fix shared config.

### Reserved filenames

These names are **governed artifact types with schemas** — they arrive with the scaffold and mean a specific thing:

| Filename | What it is |
|---|---|
| `CONVENTIONS.md` | Repo-wide rules of the road (this file) |
| `COORDINATION.md` | Multi-persona protocol + workflow |
| `CLAUDE.md` | Per-workspace agent config |
| `AGENT.md` | Persona-specific rules, one per `agents/<persona>/` |
| `BOOTSTRAP.md` / `BOOTSTRAP-ADMIN.md` | Collaborator / owner onboarding |
| `START.md`, `ORCHESTRATE.md`, `PARTICIPATE.md`, `QUICKSTART.md` | Entry-point docs |

**Before creating a file with one of these names, confirm your content conforms to the schema that name already carries.** If it doesn't, pick a different name and match the genre instead: briefings and onboarding notes belong in a meta location, inter-agent messages in `_handoff/`, working notes in your own area.

**A reserved name is scoped to its location.** `COORDINATION.md` means the collab-repo root copy, or `<vault>/projects/<name>/COORDINATION.md` — not any file bearing the name. In particular, **never create one at a vault root**: a vault root is not a project, so a file there claims authority over every project in the vault by position alone. In a precedence chain, position *is* authority.

---

## What never happens

- `git push --force` to `main` on either repo
- Deleting `_handoff/` files
- Writing to `wiki/` from a non-Librarian persona
- Committing secrets (`.env`, credentials, API keys)
- A persona acting outside the scope declared in its `AGENT.md`
