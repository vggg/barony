<!-- gh-actions-cron — emitted into FAILOVER.md when AGENT.md frontmatter runtime: gh-actions-cron -->

### 2. Enable the cron in the code repo (GitHub Actions)

The Librarian runs as a **GitHub Actions scheduled workflow** in `{{CODE_REPO}}` — fully GitHub-hosted, no laptop dependency, always-on (subject to GitHub's free-tier minute quotas). This runtime has **no per-machine failover** — the workflow lives in the repo and runs regardless of which human is "default runner." Failover is conceptually different: it's about who maintains the workflow, not who runs the cron.

```yaml
# .github/workflows/librarian.yml (in {{CODE_REPO}})
on:
  schedule:
    - cron: '{{LIBRARIAN_CRON_GITHUB_FORMAT}}'   # e.g. "0 22 * * *" for daily 22:00 UTC
  workflow_dispatch: {}

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          repository: {{COLLAB_REPO}}
          token: ${{ secrets.LIBRARIAN_PAT }}
      - run: |
          # Run Claude Code headless with the librarian persona prompt
          # (See agents/librarian/AGENT.md for the full cycle)
          ...
```

**GitHub auth:** requires a `LIBRARIAN_PAT` secret in the code repo with push access to the collab repo (since the Librarian writes to `wiki/`).

**To disable:** delete the workflow file or set the cron to a never-firing value.

**Cron format:** GitHub Actions uses 5-field cron (UTC). `daily 22:00 UTC` → `0 22 * * *`. No DST drift.

**Why this and not local cron:** zero per-machine setup, fully reproducible. The trade-off: paid private-repo minutes on GitHub at higher cadences; less flexibility for ad-hoc runs (manual `workflow_dispatch` works but isn't as fluid as `claude -p` locally).