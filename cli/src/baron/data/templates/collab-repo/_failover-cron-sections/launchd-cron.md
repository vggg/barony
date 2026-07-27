<!-- launchd-cron (macOS) — emitted into FAILOVER.md when AGENT.md frontmatter runtime: launchd-cron -->

### 2. Enable the cron on your machine (macOS / launchd)

The Librarian runs via **launchd** — a plist registered with the user-level LaunchAgents directory. Setup script generates the plist; you load it with `launchctl`.

```bash
# From the collab repo root on your machine:
./workspace-template/setup.sh librarian
# That generates ~/Workspace/{{PROJECT_NAME}}/librarian/com.{{PROJECT_NAME_LOWER}}.librarian.plist
# with the schedule from agents/librarian/AGENT.md cadence.

# Load it:
launchctl bootstrap gui/$(id -u) ~/Workspace/{{PROJECT_NAME}}/librarian/com.{{PROJECT_NAME_LOWER}}.librarian.plist

# Verify:
launchctl list | grep {{PROJECT_NAME_LOWER}}.librarian
```

**Cron time:** the plist uses local time, not UTC. If `AGENT.md` cadence says `daily 22:00 UTC` and your machine is in PDT, the plist fires at 15:00 local. If DST ends and you move to PST, the same plist now fires at 22:00 UTC + 1 hour effective. Either accept the seasonal drift (cadence float is usually fine for "afternoon after market close" type runs) or update the plist twice a year.

**To unload (when the original runner returns):**

```bash
launchctl bootout gui/$(id -u) ~/Workspace/{{PROJECT_NAME}}/librarian/com.{{PROJECT_NAME_LOWER}}.librarian.plist
```

**Wrapper script:** the plist invokes a wrapper at `~/Workspace/{{PROJECT_NAME}}/librarian/run-librarian.sh` that cd's into the workspace and runs `claude -p "Run your daily cycle." --dangerously-skip-permissions`. The `--dangerously-skip-permissions` flag is required for unattended runs (no human to approve tool calls); the persona's AGENT.md scope is the trust boundary.