# Drift analysis (Step 0.5 — Dual-Lens scorecard)

For every dimension of the project, report **three values**:

| Lens | Source | Question |
|---|---|---|
| **INTENDED** | Declarations: CONVENTIONS.md, persona.yaml, manifest.yaml, roster files, COORDINATION.md, AGENT.md | What does the project say it does? |
| **ACTUAL** | Observations: git history, gh API, file content, runtime evidence | What does the auditor verify is happening? |
| **GAP** | The delta | In plain language, what's different? |

Plus a **confidence label** per row: `measured | inferred | not measurable`.

**Never collapse declared into observed.** The whole value of this step is in surfacing where what's *said* and what's *done* diverge.

## Dimensions to cover

For each, drive both lenses with a concrete query or document source. If a dimension has no declaration, the INTENDED column reads "not declared" — that's itself diagnostic.

### 1. Agents

| Lens | Source |
|---|---|
| INTENDED | Declared roster (Step 0) |
| ACTUAL | Observed actor inventory **across ALL identity substrates** (Step 0.5 actor resolution, `references/actor-resolution.md`) |

> ⚠️ **Critical rule (lesson from v1.2.0 GardenTwin audit):** the Agents dimension uses **ALL identity substrates the project actually uses**, not `git log` alone. A project where personas identify themselves via GitHub `agent-*` labels + handoff frontmatter + dev-log frontmatter + EOD frontmatter is **operationally per-persona-identified** even if `git log` shows one author. Identity collision in `git log` is the RULE for multi-agent projects driven by a single human (Vikram-as-operator pattern), NOT pathological drift. Score the Agents dimension on **the union of substrates**, and surface the collision-in-git-log as a minor convenience gap, not as the main Agents-row finding.

Identity substrates to enumerate per project (use whichever exist):

1. **Git author identity** (`git log %an %ae`) — one substrate; expect collision when personas share a driving human
2. **GitHub `agent-*` labels** on issues/PRs — primary attribution substrate for Barony projects
3. **Vault `_handoff/` `from:` / `for:` frontmatter** — cross-persona coordination substrate
4. **Per-session output frontmatter** — dev-log `agent:`, EOD `agent:`, session-log `agent:` declarations
5. **Persona-prefix commits** (`iris:`, `dave:`, `kris:`, etc.) — when used; Barony v1.x repos may or may not use these (the canonical repo uses Conventional Commits instead)

A persona is **operationally identified** if it appears consistently in ≥2 of these substrates with frequency proportional to its declared role.

GAP examples (revised):

- *"5 declared; 5 operationally identified (via labels + handoffs + dev-logs); 1.5 distinct in `git log` — identity collision in git is expected for this layout, not drift."* → score as **healthy**, note the git-collision as a convenience gap, score row credit ~0.8.
- *"5 declared; 4 operationally identified across substrates; 1 declared persona (librarian) has 0 commits, 0 wiki writes, 0 handoffs, 0 dev-logs — appears dormant."* → score as **real drift**, credit ~0.5.
- *"3 declared; 5 observed across substrates. 2 undeclared (one CI bot, one human contributor)."* → score as **observed-but-undeclared drift**, credit ~0.5.

### 2. Autonomy

| Lens | Source |
|---|---|
| INTENDED | Each persona's declared `trigger:` / `runtime:` (per Barony v1.x), or equivalent "autonomous vs interactive" flag |
| ACTUAL | Observed runtime pattern — does the cron persona actually run on cron? does the webhook persona actually fire on webhooks? |

How to verify ACTUAL autonomy:

- For declared cron personas, look for commits with regular cadence (same time of day, same day of week) and machine-shaped commit messages.
- For declared webhook personas, check `gh api repos/<owner>/<repo>/actions/runs` for the relevant workflow's recent runs.
- For interactive personas, expect bursty commit patterns clustered around human-active hours.

GAP examples:

- *"Librarian declared as cron (cloud-routine, daily 15:00 PT); last commit was 8 days ago — cron not firing."*
- *"PR Reviewer declared as gh-actions-event; observed 0 review comments from the action's bot account in the window — workflow may be missing or misconfigured."*

### 3. Reviewers

| Lens | Source |
|---|---|
| INTENDED | Declared reviewers (CODEOWNERS, COORDINATION.md, persona scope) |
| ACTUAL | `gh api repos/<owner>/<repo>/pulls/<n>/reviews` aggregated over the window |

GAP examples:

- *"Analyst declared as PR reviewer for design-labelled PRs; 0 reviews observed on 14 design-labelled PRs in the window."*
- *"Owner declared as final reviewer for all merges; observed 22/30 merges with no review (likely self-merge bypassing the gate)."*

### 4. Guardrails

| Lens | Source |
|---|---|
| INTENDED | Deny-lists / "Never" sections in CONVENTIONS.md, AGENT.md `deny:` fields, branch protection declarations |
| ACTUAL | (a) Branch protection rules (`gh api repos/<owner>/<repo>/branches/main/protection`); (b) tool allow-lists in persona files; (c) observed violations in git history |

The hardest part of this dimension: **enforced vs instructed**. A declared deny is meaningfully different from an enforced one.

#### Enforced guardrails (tool-level)

These the runtime cannot bypass:

- Branch protection on `main` → prevents direct pushes.
- Tool allow-list omitting `Bash` → prevents shell commands.
- Tool allow-list omitting `Edit` → prevents file modifications.
- GitHub App scope restrictions.

Check: does the rule, declared in CONVENTIONS.md or persona file, correspond to an enforcement at the tool/permission layer? If yes → enforced. If only the markdown declaration exists → instructed.

#### Instructed-only guardrails

These rely on the agent following the instruction:

- *"Never force-push"* in CONVENTIONS.md, when the runtime has `Bash` granted (so `git push --force` is technically possible).
- *"Never `git add -A`"* in a CLAUDE.md, when the runtime has full file access.
- *"Don't run schema migrations while another agent's PR is open"* — pure protocol; tool-level enforcement is impossible.

Instructed-only guardrails can still add value (the L3 honesty boundary from Barony's LEARNINGS.md), but the audit must classify them honestly. Report the percentage of declared deny-lists that map to enforced blocks.

GAP examples:

- *"Force-push: declared, instructed-only (no branch protection in place). Observed 2 force-pushes to main in window."*
- *"`git add -A` deny: declared, instructed-only. Observed 6 commits with ≥20 files changed — proxy suggests `add -A` use, unverified."*

### 5. Routing / ownership

| Lens | Source |
|---|---|
| INTENDED | Write-ownership tables (CONVENTIONS.md), per-persona declared scope (`persona.yaml > capabilities > write_*`), folder ownership maps |
| ACTUAL | Observed git history: which actor writes to which file paths |

Concrete query (for the Barony layout):

```bash
git -C <repo> log --since="<window>" --format='%an|%H' --name-only \
  | awk '<aggregate (actor, path) → count>'
```

Then compare each actor's observed write paths against their declared scope.

GAP examples:

- *"Analyst (declared read-only on code) — observed 3 commits touching `src/` files."*
- *"Designer (declared write area: `ClaudeDesigner/marketing/`) — observed 0 writes to that folder, 4 writes to `ClaudeDesigner/prds/` (also declared). Healthy."*

### 6. Backlog / workflow

| Lens | Source |
|---|---|
| INTENDED | Declared ticket lifecycle (COORDINATION.md ticket flow: open → claim → branch → PR → merge → close) |
| ACTUAL | Observed PR ↔ issue linkage; PR closes-issue rate; orphan PRs |

Concrete query:

```bash
gh -R <owner>/<repo> pr list --state merged --limit 500 \
  --search "merged:>=<window-start>" \
  --json number,body \
  | jq '.[] | select(.body | test("Closes #|Fixes #|Resolves #") | not) | .number'
```

GAP examples:

- *"Declared: every PR closes an issue via `Closes #N`. Observed 18/45 PRs without an issue link — 40% orphan rate."*
- *"Declared: tickets must be claimed via `agent-<name>` label before code starts. Observed 8 commits on feature branches whose issue had no agent label at the time of branch creation."*

### 7. Rituals

| Lens | Source |
|---|---|
| INTENDED | Declared session-start checklist (CLAUDE.md/COORDINATION.md), dev-log conventions, handoff protocols, decision-filing rules |
| ACTUAL | Observed adherence — do dev logs exist in the declared format? are handoffs being read and marked `done`? are decisions filed where declared? |

Concrete checks:

- **Dev-log adherence** — count dev-log files in the declared path; compare against count of distinct dev-active days in `git log`. A dev who committed 14 days but wrote 8 dev-logs has 57% ritual adherence.
- **Handoff lifecycle** — `_handoff/` files with `status: open` older than X days (default 7) → either stale-and-unread, or the recipient ignored them.
- **Decision-filing** — count of `decisions/` files vs count of merged PRs that introduced architectural changes (proxy: PRs labelled `arch:` or `feat:` with > N lines changed).

GAP examples:

- *"Declared: dev writes a dev-log per session. Observed 12 active dev-days, 7 dev-logs filed (58% adherence)."*
- *"Declared: handoffs must be marked `status: done` once acted on. Observed 8 `status: open` handoffs older than 14 days — recipients may not be reading."*

## The drift scorecard format

Produce a table like this for the report (one row per dimension):

```markdown
## Drift scorecard

| Dimension | INTENDED | ACTUAL | GAP | Confidence |
|---|---|---|---|---|
| Agents | 5 declared (Dave, Kris, Vera, Ivy, Iris) | 6 observed (+1 dependabot, undeclared); Ivy 0 commits/handoffs in window | +1 shadow agent; 1 declared agent dormant | measured |
| Autonomy | Iris cron daily 15:00 | Last Iris cron-style commit: 8 days ago | Cron not firing as declared | measured |
| Reviewers | All PRs reviewed by Vikram before merge | 22/30 PRs merged with 0 reviews | 73% of merges bypass declared review gate | measured |
| Guardrails | No force-push; no direct push to main | Branch protection: not enabled; 2 force-pushes observed | Force-push declared deny is instructed-only; observed violations | measured |
| Routing/ownership | Analyst read-only on code | 3 code commits by Analyst identity | Boundary breached 3x | measured |
| Backlog/workflow | Every PR closes an issue (`Closes #N`) | 18/45 PRs orphan (40%) | Workflow declared but partially followed | measured |
| Rituals | Dev-log per session | 7 logs / 12 active days (58%) | Ritual declared but inconsistent | inferred |
```

## The operational fidelity score

Compute a single number: **fraction of declared model verifiably running.**

Formula (simple version):

```
operational_fidelity = (# dimensions where ACTUAL fully matches INTENDED) / (# dimensions tested)
```

For a partial-match dimension (declared follows the convention some of the time), score it as a fractional credit:

- *"Dev-log written 58% of declared sessions"* → 0.58 credit on the Rituals dimension.
- *"PR-closes-issue 60% of the time"* → 0.60 credit on Backlog/workflow.
- For a binary dimension (force-push policy declared but violated) → 0.0 if any violation, 1.0 if none.

Sum the fractional credits, divide by the number of dimensions you scored. Round to two decimals. Range: 0.00–1.00.

Surface the score prominently in the executive summary. Examples of interpretation:

- **0.90+** — the project lives as it claims. The audit's other axes are the action.
- **0.70–0.89** — meaningful drift; one or two specific gaps to close.
- **0.50–0.69** — the declared model is partially aspirational. Hard call: tighten enforcement, or revise the declarations to match reality.
- **<0.50** — the declared model and the actual project are different projects. Either the docs are aspirational fiction (rewrite them honestly) or the team is ignoring them (operational fix).

## How drift becomes opportunities

Each drift row should produce **one ranked opportunity** in the report's Ranked Opportunities section, in the form:

- **What:** the specific gap.
- **Why it matters:** the cost of the drift in days, dollars, defects, or coordination overhead.
- **How:** the smallest action that closes the gap. *Don't recommend rewriting everything.* If branch protection is missing, the recommendation is "turn it on" — not "redesign the coordination model."
- **Leverage × ease score:** 1–9 (3 × 3 grid of leverage and ease). High-leverage / easy fixes top the list.

Most projects accumulate drift faster than they close it. The audit's job isn't to fix everything; it's to surface the highest-leverage 3–5 gaps so the human can decide where to invest.

## Confidence labels

Each row in the drift scorecard gets a confidence label:

- **measured** — both INTENDED and ACTUAL were verified from independent sources.
- **inferred** — INTENDED was declared, but ACTUAL was estimated from a proxy (e.g., commit-size as proxy for `git add -A`).
- **not measurable** — INTENDED was declared, but ACTUAL is in a platform the audit can't see (e.g., declared Slack-channel discussion). Mark and surface in caveats.

If a row is `not measurable`, **don't score it** in the operational fidelity formula. Skipping it is more honest than a guess.
