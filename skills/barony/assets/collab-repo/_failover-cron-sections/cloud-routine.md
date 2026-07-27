<!-- cloud-routine — emitted into FAILOVER.md when AGENT.md frontmatter runtime: cloud-routine -->

### 2. Enable the cron on your account (Anthropic cloud routine)

The Librarian runs as a **cloud routine** via Claude Code's `/schedule` skill — fully cloud-hosted, no laptop dependency, always-on. Setup is per-Anthropic-account: only one routine can claim the Librarian role; failover means a different account's routine takes over.

```bash
# In Claude Code, invoke the /schedule skill:
/schedule cron='{{LIBRARIAN_CRON_CADENCE}}' \
  task='Run the {{PROJECT_NAME}} Librarian per agents/librarian/AGENT.md. Clone https://github.com/{{COLLAB_REPO}}, ingest new findings/handoffs/decisions/dev-logs into wiki/, push as the Librarian persona.'
```

**GitHub auth:** the cloud routine needs push access to `{{COLLAB_REPO}}`. Configure a PAT or GitHub App on the routine.

**To disable (when the original runner returns):**

In Claude Code, `/schedule list` to find the Librarian routine ID, then `/schedule delete <id>`.

**Cron time:** `/schedule` accepts UTC expressions natively (`cron='daily 22:00 UTC'`). No DST drift.

**Cost model:** cloud routines bill to the routine owner's Anthropic account. Coordinate with the project owner if cost ownership matters for accounting.

**Why this and not local cron:** removes the "laptop must be on" failure mode of `launchd-cron` / `systemd-timer`. The trade-off is configuration friction (GitHub auth in the cloud) and per-account billing.