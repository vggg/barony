# Librarian — Failover Runbook

The Librarian for {{PROJECT_NAME}} is centralized with documented failover. Only one Librarian instance runs at any given time. The default runner is **{{DEFAULT_RUNNER_HANDLE}}**'s machine.

If the default runner is offline for more than {{LIBRARIAN_FAILOVER_THRESHOLD}}, any team member can take over.

## When to fail over

- Default runner is offline > {{LIBRARIAN_FAILOVER_THRESHOLD}}
- `wiki/log.md` hasn't been updated in {{LIBRARIAN_FAILOVER_STALENESS}} despite team activity
- Default runner announces they're stepping away

## Who can take over

Any human team member who has:
1. Write access to the collab repo (`{{COLLAB_REPO}}`)
2. A working `/schedule` skill on their machine
3. Their own Claude Code installation

You do not need to be a specific persona — the Librarian identity is reused; only the runtime machine changes.

## How to take over

### 1. Announce the takeover

Drop a `_handoff/` to all personas before starting:

```yaml
---
created: YYYY-MM-DD
status: open
for: all
from: {{YOUR_PERSONA}}
priority: medium
---

# Librarian failover — {{YOUR_PERSONA}} taking over

{{DEFAULT_RUNNER_HANDLE}} is offline / unavailable. Taking over Librarian duty effective YYYY-MM-DD.

I'll run the Librarian cron from my machine until {{DEFAULT_RUNNER_HANDLE}} returns or we agree to a different rotation.

Cadence: {{LIBRARIAN_CRON_CADENCE}} (matching the default).
```

Also post in the team's async channel (Slack, Discord, etc.) so anyone offline still hears about it.

{{FAILOVER_CRON_SECTION}}

> The cron section above is per-runtime. The Librarian's runtime is declared in `agents/librarian/AGENT.md` frontmatter `runtime:` field. Supported values: `launchd-cron` (macOS), `systemd-timer` (Linux), `cloud-routine` (Anthropic-hosted), `gh-actions-cron` (GitHub Actions). The skill picks the right snippet at scaffold time. If you need to change runtimes, update `runtime:` in `AGENT.md` and re-run `./workspace-template/setup.sh librarian` to regenerate the cron stub.

### 3. Set git identity to the Librarian persona on your machine's collab-repo clone

```bash
cd <your local collab repo clone>
git config user.name "Librarian"
git config user.email "librarian@{{IDENTITY_DOMAIN}}"
```

This is a per-repo override — your other git work keeps your normal identity. The Librarian's commits land under the Librarian identity regardless of which machine runs them.

### 4. Run a first manual cycle

Before relying on the cron, run one full cycle manually so you know it works:

```
Open a Claude Code session in your collab repo clone. Read agents/librarian/AGENT.md. Execute the "What you do on each run" steps. Commit and push when done.
```

This catches setup issues (missing labels, broken paths, etc.) while you're paying attention.

### 5. Update the `default_runner` field in `agents/librarian/AGENT.md`

In the frontmatter:

```yaml
default_runner: {{YOUR_GH_HANDLE}}
```

Commit the change. This signals to others that you currently hold the role.

## When the original runner returns

1. Original runner pulls the latest collab repo (sees the failover handoff and updated `default_runner`).
2. Original runner drops a handoff announcing they're resuming.
3. Failover holder disables their `/schedule` cron entry.
4. Original runner updates `agents/librarian/AGENT.md` frontmatter `default_runner` back to their handle.

## Special case — cross-project bridge

When the project owner is the runner, the Librarian has a unique read-bridge into the owner's personal vault (one-way; see `AGENT.md`). This bridge is **unavailable** during failover. While someone else holds the role:

- Cross-project synthesis paused
- Project-internal wiki ingest continues normally
- Owner can manually run a one-shot Librarian session on their machine to do cross-project synthesis when convenient

Tell the team if you need this restored sooner — it might be worth bumping `default_runner` back to the owner for a one-off run.

## What never happens

- Two team members running the Librarian cron concurrently (merge hell on `wiki/log.md`)
- Failing over without dropping the announcement handoff
- Changing the Librarian's git identity (it's the persona's identity, not yours)
- Writing to `wiki/` from your normal persona during failover — write as the Librarian
