# Discovery (Step 0)

Profile the audited project. **Don't assume layout.** A project may not match any framework you've seen before. Record what you find — and what's missing.

The output of Step 0 is a **project profile** that Steps 0.5 and 1 build on. If Step 0 is sloppy (e.g., you assumed a `_handoff/` folder exists without checking), every downstream metric will be skewed.

## What to identify

### 1. The declared agent roster

Where to look (in priority order; stop at the first that yields data):

1. **`actors.yaml`** (or `actors.yml`) at the repo root or in `audit/` — if the user declared a roster for this audit.
2. **`manifest.yaml`** (Barony v1.x) — `agents:` section.
3. **`agents/<name>/persona.yaml`** (Barony v1.x) — one file per persona, declares identity + capabilities + scope.
4. **`agents/<name>/AGENT.md`** (Barony v0.x or v1.x dev personas) — markdown persona descriptions.
5. **`CONVENTIONS.md` or `COORDINATION.md`** — Roles section, write-ownership table.
6. **`_meta/PERSONAS/`** (vault-project layout).
7. **`.crew/` / `.langgraph/` / `.autogen/`** — framework-specific conventions for other stacks.
8. **README.md** — search for an "Agents" or "Team" section as a last resort.

If none of the above exist, the project has **no declared roster**. Record this as a finding; don't fabricate one from `git log`.

For each declared actor, capture:

- Name / slug.
- Declared class (`human | autonomous | hybrid`).
- Declared runtime (Claude Code, code-puppy, GitHub Actions, cron, manual, n/a).
- Declared capabilities or write-ownership scope (file paths, repos, labels).
- Declared identity binding (git author email, GitHub login, persona prefix on commits).

### 2. How work is tracked

Identify the **backlog source**. One of:

- **GitHub issues** — the most common. `gh issue list --repo <owner>/<repo>` will work.
- **Linear / Jira / Notion** — out of scope for v1.x of this skill; record as "external backlog (not minable from this audit's tools)."
- **Vault-tracked** — issues in markdown files under `findings/` or `questions/` (Barony pattern).
- **Branch labels** — work tracked by branch prefix only.
- **None** — the project has no formal backlog. Record as a finding.

For each, capture how a task moves from "open" → "in progress" → "done." If GitHub issues, look for the standard transitions (open → assigned → closed via PR `Closes #N` syntax).

### 3. How agents coordinate

Look for the coordination substrate:

- **`_handoff/` directory** (Barony) — file-based async messages with `for:` / `from:` / `status:` frontmatter. Count the files; sample a few to confirm the protocol is active (not just declared).
- **`COORDINATION.md`** — describes the cross-agent protocol.
- **PR comments** — `gh api repos/<owner>/<repo>/pulls/<n>/comments` for review/discussion comments.
- **Issue comments** — discussion threads on tickets.
- **Slack / Discord / Teams** — not minable without explicit auth; record as "external channel (not measurable from this audit)."

For Barony layouts, the canonical coordination surface is `_handoff/` + the issue tracker. For other layouts, you may need to discover heuristically.

### 4. How autonomy is driven and gated

For each autonomous actor identified in step 1, find out:

- **Trigger** — cron schedule, webhook event, manual invocation, chained from another agent's output.
- **Runtime location** — local machine, GitHub Actions, Anthropic-hosted `/schedule`, custom server.
- **Approval gates** — does the autonomous agent require human approval before it can write/merge? Where is the gate? Is it a tool-level block or an instruction?
- **Rate limits / cost ceilings** — declared budget per run; what happens at the ceiling.

Sources to check:

- **GitHub Actions** — `.github/workflows/*.yml` for cron and event triggers.
- **`agents/<name>/FAILOVER.md`** (Barony) — failover runbook, includes runtime/cron details.
- **`agents/<name>/persona.yaml`** — `runtime:` field declares the runtime; `trigger:` field declares interactive/event/cron.
- **`manifest.yaml`** — `runtime:` taxonomy.

Note: **a declared trigger isn't proof that the trigger fires.** If the project declares a librarian cron runs daily at 15:00, check whether the librarian has actually committed/written in the recent window. This becomes a drift in Step 0.5.

### 5. Declared guardrails

Find what the project says it *won't* allow:

- **`CONVENTIONS.md`** — *What never happens* sections, push policy, force-push rules, file-staging discipline.
- **`COORDINATION.md`** — multi-agent dev rules, hot files, schema migration discipline.
- **`agents/<name>/AGENT.md`** or `persona.yaml` — per-persona `deny:` lists or "never" sections.
- **GitHub branch protection rules** — `gh api repos/<owner>/<repo>/branches/main/protection` (read-only).
- **Code-owners** — `.github/CODEOWNERS`.
- **Tool allow-lists** — for Claude Code persona files, the `tools:` frontmatter; for code-puppy, the agent's JSON definition. These are **enforced** guardrails; declarative-only deny-lists in markdown are **instructed** guardrails. Note the distinction for Step 0.5.

Record absences. *"The project has no declared force-push policy"* is itself a finding worth surfacing.

## Output of Step 0

A **project profile** with the following structure (you'll feed this forward into Step 0.5 and the final report):

```markdown
## Project profile

- **Project name:** <name>
- **Code repo:** <url or path>
- **Coordination/collab repo:** <url or path, or "single-repo">
- **Layout family:** Barony v1.x | Barony v0.x | vault-project | CrewAI | LangGraph | AutoGen | Copilot agents | custom | unclassified
- **Declared roster:**
  - <actor 1> (<class>, <runtime>, <scope>)
  - <actor 2> (...)
  - ...
- **Backlog source:** github-issues | vault-tracked | external | none
- **Coordination substrate:** _handoff/ | PR-comments | mixed | none
- **Autonomy triggers observed:** cron | webhook | manual | n/a — per autonomous actor
- **Guardrails declared:**
  - Force-push policy: <yes/no/silent>
  - Push-to-main policy: <yes/no/silent>
  - Tool allow-lists (enforced): <list> or "none"
  - Markdown deny-lists (instructed): <list> or "none"
  - Branch protection: <enabled / disabled / n/a>
- **Layout-adapter loaded:** bootstrap-adapter | heuristic | none
- **Time window for the audit:** <YYYY-MM-DD> to <YYYY-MM-DD>
```

Save this profile to the report's working draft — it becomes the "Designed model" section of the final report.

## When discovery is incomplete

It's expected that some fields will be unknowable from a cold audit. Mark them `"not declared"` or `"unknown — see caveats"`. **Don't guess.** A missing roster is a missing roster, not an opportunity to invent one from `git shortlog -sn`.

The exception: if `actors.yaml` is provided and conflicts with what you observe in the repo, **report both** in Step 0.5's drift scorecard. The user-declared roster is the INTENDED lens; the observed actors are the ACTUAL lens.

## Layout detection heuristics

Quick checks to classify the project's layout family:

| If you find | Layout is likely |
|---|---|
| `manifest.yaml` with `agents:` + `adapters/` directory | Barony v1.x |
| `agents/<name>/AGENT.md` files + no `manifest.yaml` | Barony v0.x |
| `_meta/PERSONAS/*.md` + Obsidian vault structure | vault-project (early Barony) |
| `crew.py` or `crew.yaml` | CrewAI |
| `graph.py` + LangChain/LangGraph imports | LangGraph |
| `groupchat.py` + AutoGen imports | AutoGen |
| `.github/copilot-agent.yml` or `copilot.yml` | Copilot agents |
| None of the above | custom or unclassified — proceed heuristically |

If you detect Barony v1.x or v0.x, load `references/bootstrap-adapter.md` next — it gives you the exact mining commands for that layout.

## Time window

The default audit window is **the last 90 days**. Justify deviations:

- **Last 30 days** for fast-iterating projects where recent state matters more than historical drift.
- **All-time** for new projects (< 90 days old) or for the first audit of a long-lived project.
- **Custom** when the user wants to grade a specific phase (e.g., "the v1.x development period 2026-05-29 to 2026-06-08").

Record the chosen window and the rationale in the profile. The window affects all downstream metric counts.
