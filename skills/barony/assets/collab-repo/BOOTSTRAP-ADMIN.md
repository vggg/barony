# {{PROJECT_NAME}} — Admin Bootstrap

Owner-only operations for managing the {{PROJECT_NAME}} collab repo. Not visible to collaborators in normal use.

## Adding a persona

1. Decide the persona's archetype: **dev**, **autonomous-event** (GitHub Actions on PR webhook), **autonomous-cron** (scheduled), or **librarian** (only one per project; already emitted by default).
2. Copy the matching template from the `barony` skill at `assets/collab-repo/agents/<archetype>/AGENT.md` into `agents/<persona-slug>/AGENT.md` in this repo.
3. Fill the placeholders for the new persona (slug, name, git identity, etc.).
4. Update the **Personas at a glance** table in `COORDINATION.md` and the **Identity, labels, and routing** table in `CONVENTIONS.md`.
5. Create the GitHub label for the persona on both repos:
   ```bash
   gh label create "agent-<persona-slug>" \
     --color "5319e7" \
     --description "Routes work to this persona" \
     --repo {{CODE_REPO}}
   gh label create "agent-<persona-slug>" \
     --color "5319e7" \
     --description "Routes work to this persona" \
     --repo {{COLLAB_REPO}}
   ```
6. If the persona is human: invite their GitHub user as a collaborator on both repos, point them at `BOOTSTRAP.md`.
7. If the persona is autonomous: set up the runtime (GitHub Actions workflow file for event-triggered; `/schedule` cron entry for cron-triggered).
8. Drop a `_handoff/` to all personas announcing the addition.
9. Commit the changes via PR (if you're in a trust-gated window) or direct push.

## Removing a persona

1. Set `status: archived` in their `AGENT.md` frontmatter — **don't delete the folder**. Past commits and handoffs reference the persona; archive preserves history.
2. Remove their row from `CONVENTIONS.md` and `COORDINATION.md` tables (or move to an "Archived" section).
3. Revoke their GitHub collaborator access on both repos.
4. Drop a `_handoff/` to all personas announcing the removal.

## Trust-gating — optional, lifecycle-agnostic

Trust-gating (PR-only with required review on `main`) is optional and can be applied at any project lifecycle phase. There is no required default — choose what fits the project's trust profile.

### When to consider enabling it

- New collaborator joining (first 2–4 weeks)
- Sensitive period (pre-launch, major refactor, compliance window)
- Specific persona you want to gate (e.g., autonomous agents only get merged after human review)
- Permanently, for production-critical projects

### How to enable

GitHub branch protection on `main` of both repos:

```bash
# Require PR + 1 review before merge on main
gh api -X PUT repos/{{CODE_REPO}}/branches/main/protection \
  -f required_pull_request_reviews.required_approving_review_count=1 \
  -f required_pull_request_reviews.dismiss_stale_reviews=true \
  -f enforce_admins=false \
  -f required_status_checks=null \
  -f restrictions=null

gh api -X PUT repos/{{COLLAB_REPO}}/branches/main/protection \
  -f required_pull_request_reviews.required_approving_review_count=1 \
  -f required_pull_request_reviews.dismiss_stale_reviews=true \
  -f enforce_admins=false \
  -f required_status_checks=null \
  -f restrictions=null
```

`enforce_admins=false` keeps you (admin) able to push hotfixes. Flip to `true` if you want full enforcement.

### How to disable

```bash
gh api -X DELETE repos/{{CODE_REPO}}/branches/main/protection
gh api -X DELETE repos/{{COLLAB_REPO}}/branches/main/protection
```

### Per-persona / per-path gating

GitHub CODEOWNERS can enforce that PRs touching certain paths require specific persona/owner approval. Place a `.github/CODEOWNERS` file in either repo:

```
# Example: any change to agents/ requires owner approval
agents/*   @{{OWNER_HANDLE}}

# Example: changes to CONVENTIONS or COORDINATION require owner approval
CONVENTIONS.md   @{{OWNER_HANDLE}}
COORDINATION.md  @{{OWNER_HANDLE}}
```

CODEOWNERS only takes effect when branch protection's "Require review from Code Owners" is enabled (toggle via GitHub UI or branch protection API).

## Setting up labels (initial bootstrap)

If the bootstrap step didn't run all label-creation commands, here's the canonical list:

```bash
# Persona routing labels
for persona in {{PERSONA_SLUG_LIST}}; do
  for repo in {{CODE_REPO}} {{COLLAB_REPO}}; do
    gh label create "agent-$persona" --color "5319e7" \
      --description "Routes work to this persona" --repo "$repo"
  done
done

# Workflow type labels (GitHub defaults bug + question are retained)
for label in feat:00ff00 chore:cccccc refactor:f9d0c4 docs:0075ca test:bfdadc research:c2e0c6 needs-discussion:fbca04; do
  name="${label%:*}"; color="${label#*:}"
  for repo in {{CODE_REPO}} {{COLLAB_REPO}}; do
    gh label create "$name" --color "$color" --description "Workflow label" --repo "$repo"
  done
done
```

## Librarian failover

If the default Librarian runtime (the machine running the `/schedule` cron) is offline for more than a working day:
1. See `agents/librarian/FAILOVER.md` for the runbook
2. Any team member can take over by enabling the `/schedule` cron on their machine
3. Coordinate via the team's async channel (Slack, Discord, etc.)

## Renaming a persona

Don't. Personas have identity. Rather, archive the old persona (per "Removing a persona" above) and add a new one with the desired name. Past history (commits, handoffs, PRs) preserves the old identity.
