<!-- systemd-timer (Linux) — emitted into FAILOVER.md when AGENT.md frontmatter runtime: systemd-timer -->

### 2. Enable the cron on your machine (Linux / systemd)

The Librarian runs via **systemd-timer** — a `.service` unit plus a `.timer` unit registered with `systemctl --user`. Setup script generates both; you enable them via systemctl.

```bash
# From the collab repo root on your machine:
./workspace-template/setup.sh librarian
# That generates two units in ~/.config/systemd/user/:
#   {{PROJECT_NAME_LOWER}}-librarian.service  (the job that runs claude)
#   {{PROJECT_NAME_LOWER}}-librarian.timer    (the schedule from agents/librarian/AGENT.md cadence)

# Enable and start:
systemctl --user daemon-reload
systemctl --user enable --now {{PROJECT_NAME_LOWER}}-librarian.timer

# Verify:
systemctl --user list-timers | grep {{PROJECT_NAME_LOWER}}-librarian
systemctl --user status {{PROJECT_NAME_LOWER}}-librarian.timer
```

**Cron time:** systemd `OnCalendar` accepts UTC explicitly (e.g. `OnCalendar=*-*-* 22:00:00 UTC`). The generated timer uses the literal UTC time from `AGENT.md` cadence, so it doesn't drift across DST.

**To disable (when the original runner returns):**

```bash
systemctl --user disable --now {{PROJECT_NAME_LOWER}}-librarian.timer
```

**Wrapper script:** the `.service` unit invokes a wrapper at `~/Workspace/{{PROJECT_NAME}}/librarian/run-librarian.sh` that cd's into the workspace and runs `claude -p "Run your daily cycle." --dangerously-skip-permissions`. The `--dangerously-skip-permissions` flag is required for unattended runs (no human to approve tool calls); the persona's AGENT.md scope is the trust boundary.

**Lingering note:** by default, `--user` units only run while the user is logged in. To run after logout, enable `loginctl enable-linger <username>`.