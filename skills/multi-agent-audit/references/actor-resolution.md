# Actor resolution (Step 0.5 — Agent Inventory)

Enumerate every actor that touches the project, classify each, and resolve identity collisions. The goal is a canonical roster of "actors who actually did something in the window" that we can compare against the declared roster.

**Why this matters:** if you under-count actors, the autonomy split inflates and the intervention tax is underestimated. The classic miss is **non-committing agents** — a PR-review bot or cron librarian whose work doesn't show in `git log` but shapes the project profoundly.

## Step 1 — Enumerate from ALL sources

Don't just run `git log --all --format='%an'`. Pull from each of these sources independently, then merge:

### 1a. Git committers

```bash
git -C <repo> log --since="<window-start>" --format='%an|%ae|%H' | sort -u
```

Per-commit detail (so you can join later):

```bash
git -C <repo> log --since="<window-start>" --format='%H|%an|%ae|%s|%ad' --date=short
```

### 1b. PR authors and mergers (GitHub)

```bash
gh -R <owner>/<repo> pr list --state all --limit 1000 \
  --search "merged:>=<window-start>" \
  --json number,author,mergedBy,createdAt,mergedAt
```

Capture: `author.login`, `mergedBy.login`. Both are actors. The merger is often a different actor than the author — and often a human while the author was autonomous.

### 1c. PR reviewers (often missed)

For each PR in the window, list its reviewers. This is where review-bots become visible:

```bash
gh api "repos/<owner>/<repo>/pulls/<n>/reviews" \
  --jq '.[] | {user: .user.login, state: .state, submitted_at: .submitted_at}'
```

Loop across PRs in the window. Aggregate: `{reviewer_login → review_count}`.

A reviewer who never commits but reviews 50 PRs is a **non-committing agent** — likely a bot, App, or human reviewer-only persona. Surface them.

### 1d. Issue commenters and triagers

```bash
gh -R <owner>/<repo> issue list --state all --limit 1000 \
  --search "updated:>=<window-start>" \
  --json number,author,assignees,labels
```

Pay attention to `assignees` (who was working on it) and `labels` (especially `agent-<name>` labels in Barony layouts — these reveal claimed work).

### 1e. CI / bot / App accounts

GitHub Apps have logins ending in `[bot]` (e.g., `dependabot[bot]`, `github-actions[bot]`). They appear in `gh api` results but don't have human email addresses. Capture them — they're real actors with real impact (auto-merging, security alerts, CI status).

### 1f. The declared roster

From Step 0's project profile. Each declared actor gets a row.

### 1g. The coordination substrate

For Barony layouts:

```bash
# Handoff senders and recipients
grep -h '^from:\|^for:' <coordination-repo>/_handoff/*.md \
  | sort -u
```

For other layouts, search for analogous fields (e.g., dev-log `agent:` frontmatter).

## Step 2 — Classify each actor

For every actor you found in Step 1, assign a class:

| Class | Definition | Examples |
|---|---|---|
| **human** | A real person acting through their own account. May use AI tools, but the actions are human-driven. | Vikram, Pranav, an external contributor. |
| **autonomous** | An agent that acts without immediate human direction — cron jobs, webhook handlers, scheduled bots, AI agents running on their own loop. | A cron-driven librarian, a webhook-triggered PR reviewer, dependabot. |
| **hybrid** | An AI agent that runs in human-initiated sessions but acts substantially independently within a session — Claude Code dev agents, code-puppy agents. The human triggers; the agent decides. | Dave, Kris, Vera, Ivy, code-puppy-rc. |

**Hybrid is not a copout class.** It captures the meaningful middle: the agent doesn't run unattended, but the human's role is "kick off and review" rather than "instruct every action." Most Claude Code dev agents are hybrid, not autonomous.

When in doubt, look at:

- Does the actor's session require human re-prompting per task? → hybrid.
- Does the actor run on a timer or webhook with no human in the loop? → autonomous.
- Is the actor a real person typing? → human.

### Classification sources

If `actors.yaml` is provided, use its declared classes as the authoritative INTENDED lens. Compare against your observation to compute drift.

If not, classify heuristically:

- **Bot login (`*[bot]`)** → autonomous (App-based).
- **Persona-prefixed commits** (e.g., `iris:`, `dave:`, `kris:`) → hybrid (the prefix is convention from Barony).
- **Real-name commits** with no automation signal → human.
- **Cron-shaped commit patterns** (same time of day, regular cadence, machine-generated messages) → autonomous.

## Step 3 — Resolve identity collisions

The same persona often has multiple identities. Examples:

- A persona that commits under both `dave@trellisiq.online` and `vikram@example.com` (real case from the GardenTwin project — when Vikram commits *as* Dave through a Claude Code session).
- A persona named "Iris" in COORDINATION.md but committing as `Vikram <vikram@example...>` from the vault.
- An autonomous persona with both a GitHub App identity and a fallback email.

Map *N identities → 1 canonical actor*. Output a resolution table:

```markdown
| Canonical actor | Class | Observed identities |
|---|---|---|
| Iris | hybrid | `iris@vault.local`, `Vikram <vikram@example.com>` (when prefix is `iris:`) |
| Dave | hybrid | `Dave <dave@trellisiq.online>`, persona prefix `dave:` |
| Vikram | human | `Vikram <vikram@example.com>` (default), `vggg` (GitHub) |
| dependabot | autonomous | `dependabot[bot]` |
```

**Disambiguation rules:**

1. **Persona prefix wins over email.** If a commit is `iris: ingest | ...` even though the email is Vikram's, attribute it to Iris. The prefix is the declared persona of action.
2. **Co-author trailers count.** Commits with `Co-Authored-By: Claude ...` trailers — attribute primarily to the persona prefix; note the co-authorship as an autonomous-assist signal.
3. **Same email + different displayed name** → same identity; pick the canonical display name (usually the one in `actors.yaml` or the persona file).
4. **Same name + different emails** → could be one human moving between machines, or two distinct personas sharing a name. Look at the work pattern; if uncertain, flag for human review and treat as two actors with a `?merged?` note.

## Step 4 — The actor inventory output

Produce a table for the report:

```markdown
## Agent inventory

| Actor | Class | Declared? | Observed? | Identities | Commits | PRs opened | PRs reviewed | Handoffs sent | Confidence |
|---|---|---|---|---|---|---|---|---|---|
| Iris | hybrid | yes | yes | iris@vault.local, vikram@example... (prefix:iris) | 47 | 0 | 0 | 12 | measured |
| Dave | hybrid | yes | yes | dave@trellisiq.online | 38 | 14 | 6 | 8 | measured |
| Kris | hybrid | yes | yes | kris@trellisiq.online | 22 | 9 | 11 | 5 | measured |
| Vera | hybrid | yes | yes | analyst@trellisiq.online | 19 | 0 | 18 | 14 | measured |
| Ivy | hybrid | yes | yes | designer@trellisiq.online | 11 | 0 | 0 | 6 | measured |
| dependabot | autonomous | no | yes | dependabot[bot] | 0 | 4 | 0 | 0 | measured |
| Vikram | human | yes | yes | vggg, vikram@example... | 28 | 8 | 23 | 31 | measured |
```

Add a `Notes` column for callouts: *"Declared as autonomous but observed pattern is hybrid"*, *"Non-committing — review-only"*, *"Identity resolved from 3 emails"*, etc.

This table feeds:

- The report's Agent Inventory section.
- The Autonomy Split metric (sum-of-tasks-by-autonomous-actors / sum-of-all-tasks).
- The Intervention Tax computation (which requires knowing which commits are autonomous vs human).
- The Drift Scorecard's `Agents` and `Autonomy` rows (INTENDED roster vs ACTUAL observed).

## Non-committing agents — the special case

The classic audit failure mode is missing actors whose work doesn't show in `git log`. Three common cases:

1. **PR-review-only bots/personas.** Find them via `gh api .../pulls/<n>/reviews`. Tag as `commits: 0, reviews: N`. If they have N > 0 and were not in the declared roster, they're a **shadow reviewer** — surface as drift.
2. **Cron librarians whose output is non-code.** A librarian that writes to a wiki or vault may commit, but a librarian that writes to an external system (Notion, Confluence, an iris-digest file synced elsewhere) may have 0 commits in the audited repo. Check the declared substrate from Step 0.
3. **Approval-gate humans.** A human who reviews and approves PRs but never commits to feature branches. Tag as `commits: 0, reviews: N, merges: M`. Often the project owner.

If any of these are missing from your inventory, the intervention-tax denominator is wrong (you're not counting their work) and the autonomy-split numerator may be wrong (you're crediting an autonomous PR that was really gated by a human reviewer).

## When the declared roster lies

If `actors.yaml` declares an actor that doesn't appear in any observed source — no commits, no PRs, no reviews, no handoffs — that's a **declared-but-not-operationalized** actor. This is a drift, not an error. Record:

- In the inventory: `Declared? yes | Observed? no | Commits 0 | …`.
- In the drift scorecard: row `Agents` → GAP includes the unmaterialised declarations.

Do not omit the actor from the inventory. The report's value is in showing exactly this kind of gap.

## Practical limits

- For very large projects (>10k commits in the window), sample. State the sampling method in the report's methodology section.
- For projects with private platforms (Bitbucket, GitLab self-hosted), if `gh` doesn't apply, declare it in the caveats: *"PR review data not minable from this audit's tooling."* Don't pretend the data is just missing — say what's blocking.
