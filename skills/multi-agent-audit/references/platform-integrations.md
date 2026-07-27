# Platform integrations (read-only)

How to mine the metrics from Step 1 using `gh`, `git`, and platform APIs — **only GET-class operations**. Never `POST`, `PUT`, `PATCH`, or `DELETE`. Never `gh pr merge`, `gh issue close`, `gh pr create`, `gh issue create`, or `gh issue edit`.

## Preflight

Before any platform query:

```bash
gh auth status                              # confirm auth is live
gh -R <owner>/<repo> repo view --json name  # confirm read access
git -C <local-clone> rev-parse HEAD         # confirm local clone is valid
```

If `gh auth status` fails, **stop and surface the auth gap to the user** — don't try to re-authenticate inside the audit session.

## Throughput queries

### PRs in a window

```bash
# Opened
gh -R <owner>/<repo> pr list --state all --limit 1000 \
  --search "created:>=<YYYY-MM-DD>" \
  --json number,createdAt,author,state,mergedAt

# Merged
gh -R <owner>/<repo> pr list --state merged --limit 1000 \
  --search "merged:>=<YYYY-MM-DD>" \
  --json number,createdAt,mergedAt,author,mergedBy

# Closed without merge (rejected/abandoned)
gh -R <owner>/<repo> pr list --state closed --limit 1000 \
  --search "closed:>=<YYYY-MM-DD>" \
  --json number,createdAt,closedAt,mergedAt,author
# filter where .mergedAt == null
```

### Issues in a window

```bash
gh -R <owner>/<repo> issue list --state all --limit 1000 \
  --search "created:>=<YYYY-MM-DD>" \
  --json number,createdAt,closedAt,labels,author,assignees,state
```

### Cycle times

For each PR, compute `mergedAt − createdAt` (PR cycle) and for each issue `closedAt − createdAt` (issue cycle). Take p50 and p90.

For commit-centric projects, `git log --format='%H|%ad'` over the window and compute commit cadence.

## PR review queries

The review data is in a separate endpoint per PR — loop carefully:

```bash
# Reviews for a single PR
gh api "repos/<owner>/<repo>/pulls/<n>/reviews" \
  --jq '.[] | {user: .user.login, state, submitted_at}'

# Review comments (line-level discussion)
gh api "repos/<owner>/<repo>/pulls/<n>/comments" \
  --jq '.[] | {user: .user.login, created_at, body_length: (.body | length)}'

# Issue-style PR comments (general discussion)
gh api "repos/<owner>/<repo>/issues/<n>/comments" \
  --jq '.[] | {user: .user.login, created_at, body_length: (.body | length)}'
```

For each PR in the window, sum reviews, distinct reviewers, latency to first review, latency from last approval to merge.

**Rate limits.** Default authenticated `gh api` is 5000 requests/hour. For windows with >1000 PRs, paginate carefully and consider sampling. Note the sampling method in the report's methodology.

## Issue / backlog queries

```bash
# Open backlog snapshot
gh -R <owner>/<repo> issue list --state open --limit 1000 \
  --json number,createdAt,labels,assignees

# Issues by label (e.g., bug count for defect metric)
gh -R <owner>/<repo> issue list --state all --limit 1000 \
  --search "label:bug created:>=<YYYY-MM-DD>" \
  --json number,createdAt,closedAt

# Issues by agent-* label (claim tracking)
gh -R <owner>/<repo> issue list --state open --label "agent-<name>" \
  --json number,assignees,labels
```

For Barony layouts, the `agent-<name>` labels are the claim mechanism — count claimed vs unclaimed.

## CI / Actions queries

```bash
# Recent workflow runs
gh api "repos/<owner>/<repo>/actions/runs?per_page=100" \
  --jq '.workflow_runs[] | {id, name, conclusion, run_started_at, head_branch}'

# Specific workflow (e.g., the librarian cron)
gh api "repos/<owner>/<repo>/actions/workflows/<workflow-id>/runs?per_page=50" \
  --jq '.workflow_runs[] | {id, conclusion, run_started_at}'

# Workflow files (read the declarations)
ls .github/workflows/
```

For declared cron-runtime personas, find the matching workflow and check actual run history. If declared daily but observed runs are weekly, that's drift.

## Coverage / test data

No platform-universal query. Look in the audited project for common coverage report formats:

- `coverage/coverage-summary.json` (Istanbul / nyc / vitest)
- `coverage/lcov.info` (LCOV format)
- `coverage.xml` (Cobertura)
- `htmlcov/index.html` (Python coverage)

If found, parse to get current coverage. For *delta*, find the same file in a commit at the start of the window (`git show <start-sha>:coverage/coverage-summary.json`).

If no coverage data, mark `coverage_delta: not measurable | reason: no coverage reports found`.

## Branch protection

```bash
gh api "repos/<owner>/<repo>/branches/main/protection" \
  --jq '{
    required_reviews: .required_pull_request_reviews,
    required_status_checks: .required_status_checks,
    enforce_admins: .enforce_admins,
    restrictions: .restrictions
  }'
```

A 404 here means **no branch protection exists** — every declared "no direct push to main" guardrail is then instructed-only, not enforced. Surface immediately in the drift scorecard.

## CODEOWNERS

```bash
cat .github/CODEOWNERS 2>/dev/null || cat CODEOWNERS 2>/dev/null || echo "(not present)"
```

CODEOWNERS is the enforced reviewer-declaration mechanism. If the project declares "Vera reviews design-labelled PRs" in CONVENTIONS.md but CODEOWNERS doesn't route design-labelled paths to Vera, that's instructed-only routing.

## Git mining (local clone)

Use the local clone for everything that doesn't require the platform:

```bash
# Commits by author in window
git -C <repo> log --since="<YYYY-MM-DD>" --format='%H|%an|%ae|%ad|%s' --date=short

# Commits by file path (who writes where)
git -C <repo> log --since="<YYYY-MM-DD>" --format='COMMIT|%H|%an' --name-only \
  | awk '/^COMMIT/{sha=$2; author=$3} !/^COMMIT/ && NF{print author"|"$0}'

# Lines added/removed by author
git -C <repo> log --since="<YYYY-MM-DD>" --shortstat --format='AUTHOR|%an'

# Reverts and fix-up commits
git -C <repo> log --since="<YYYY-MM-DD>" --format='%H|%an|%s' \
  | grep -iE '^[^|]+\|[^|]+\|(revert|hotfix|fix-up|chore: fix)'
```

**Use HTTPS** for any clone the audit needs to fetch:

```bash
git clone https://github.com/<owner>/<repo>.git /tmp/audit-<project>
```

Don't `cd` into the audited clone; use `git -C <path>` for every command so the audit process's working directory stays outside the audited project.

## Repo metadata

```bash
gh -R <owner>/<repo> repo view --json \
  createdAt,pushedAt,defaultBranchRef,visibility,licenseInfo,isArchived
```

If the repo is archived or the default branch isn't `main`, note in the methodology.

## What you must NOT do

Never invoke any of these inside the audit:

- `gh pr create`, `gh pr merge`, `gh pr close`, `gh pr review`
- `gh issue create`, `gh issue close`, `gh issue edit`, `gh issue comment`
- `gh release create`, `gh repo create`, `gh repo edit`
- `gh api -X POST`, `gh api -X PUT`, `gh api -X PATCH`, `gh api -X DELETE`
- `git commit`, `git push`, `git tag`, `git rebase`, `git merge`, `git reset --hard`

The default `gh api <endpoint>` is a GET — that's fine. The moment a `-X` flag appears, stop. If the user asks for one of these mid-audit, the subagent declines and surfaces in the report's caveats.

## Pagination and large windows

For windows with >1000 results, paginate:

```bash
gh api --paginate "repos/<owner>/<repo>/pulls?state=all&per_page=100"
```

Or sample with a stated method:

> *Sampled 100 PRs from the 412 merged in the window via stratified random by week. Confidence: inferred.*

Don't quietly cap at 1000 and pretend that's the population.
