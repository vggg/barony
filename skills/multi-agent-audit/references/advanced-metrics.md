# Advanced metrics — DORA + network analysis

Deep dive on the two metric families that need more than a one-line definition: DORA (lead time / deploy freq / change-fail / MTTR + extensions) and coordination network analysis.

## DORA four

Industry-standard delivery metrics. The audit reuses them with proxy adaptations because the audited project may not have a formal CI/CD pipeline.

### Lead time for changes

**Definition:** time from first commit on a feature branch to merge into `main`.

**Compute:**

```bash
# For each merged PR in window
gh -R <o>/<r> pr view <n> --json commits,mergedAt | jq '{
  first_commit: .commits[0].authoredDate,
  merged_at: .mergedAt
}'
```

`lead_time = merged_at − first_commit`. Take p50, p90 across the window.

**Proxy if no PR workflow:** for trunk-based-direct-commit projects, `lead_time` ≈ time from local commit to push (not knowable from `git log`). Mark as `not measurable` and explain.

### Deploy frequency

**Definition:** how often code reaches production per week.

**Compute (in priority order):**

1. **Release tags** — `git tag --sort=-creatordate | head -50` + filter dates in window. One tag per deploy is the cleanest signal.
2. **Merges to main** — if no release process exists, every merge to main is treated as a "deploy candidate." Count distinct merge commits per week.
3. **GitHub deployments API** — `gh api "repos/<o>/<r>/deployments?per_page=100"` if a Deployments integration is configured.

Report which proxy was used. If the project has neither tags nor a Deployments record nor a clean main-as-prod model, mark `not measurable`.

### Change failure rate

**Definition:** fraction of deploys that result in a rollback, hotfix, or production-noticed bug fix.

**Compute:**

```bash
# Reverts in window
git -C <repo> log --since="<W-start>" --grep="^Revert " --format='%H|%s'

# Hotfix-pattern commits
git -C <repo> log --since="<W-start>" --grep="^hotfix:\|^fix:.*urgent\|^fix:.*p0\|^fix:.*prod" --format='%H|%s'
```

```
change_failure_rate = (reverts + hotfixes) / total_deploys
```

If `total_deploys` was `not measurable`, this rolls up to `not measurable` too.

### Mean time to recovery (MTTR)

**Definition:** for each failed deploy, time from "bad change merged" to "fix merged."

**Compute:**

For each revert commit found above, find the commit it reverts (`git log --grep="reverts <sha>"` or parse the revert commit's body for `This reverts commit <sha>`). Compute `revert_commit.date − reverted_commit.date`.

Take p50, p90. Be honest about the sample size — MTTR p50 on 3 incidents is `inferred`, not `measured`.

## Extended DORA

### Merge-gate wait

**Definition:** how long a PR sits ready-to-merge before actually merging.

```
merge_gate_wait = merged_at − last_approving_review_at
```

Per-PR from the reviews endpoint. Distinguish from cycle time:

- Cycle time = total elapsed; includes idle WIP.
- Merge-gate wait = the human-attention-required tail; should be near zero in healthy projects.

A high merge-gate wait suggests the reviewer/merger is a bottleneck.

### Work in progress (WIP)

**Definition:** open PRs at a given point in time.

**Compute:** sample weekly during the window:

```bash
gh -R <o>/<r> pr list --state open --limit 1000 \
  --search "created:<=<sample-date>" \
  --json number,createdAt | jq 'length'
```

Track over weeks. Rising WIP without rising throughput = the project is starting work it can't finish.

## Network analysis

A multi-agent project's coordination is a graph. Build it, then read it.

### Building the network

**Nodes** — canonical actors from `references/actor-resolution.md`.

**Edges** — three types, each weighted by frequency:

| Edge | What it represents | Source |
|---|---|---|
| **review** | A reviewed B's PR | `gh api .../pulls/<n>/reviews` per PR |
| **handoff** | A sent a handoff to B | `_handoff/*.md` `from:` / `for:` frontmatter |
| **merge** | A merged B's PR | PR `mergedBy.login` |

Aggregate over the window. The output is an edge list:

```
edge_type | from_actor | to_actor | count
review    | Vikram     | Dave     | 18
review    | Vikram     | Kris     | 14
handoff   | Dave       | Iris     | 12
handoff   | Vera       | Iris     | 8
merge     | Vikram     | Dave     | 14
merge     | Vikram     | Kris     | 11
...
```

### Centrality measures

Compute betweenness centrality per node. (Quick library: Python `networkx`; or by hand on small graphs.)

**Betweenness centrality** ≈ "fraction of shortest paths between other nodes that pass through this node." A high score means *removing this node fragments the coordination network.*

**Read the result:**

- **One node with centrality dominantly higher than the rest** → single point of failure. Usually the project owner or the librarian.
- **No node above the threshold** → distributed coordination; healthy.
- **Multiple high-centrality nodes** → either healthy redundancy or a too-many-cooks coordination overhead. Look at total edge volume to disambiguate.

For the Barony layout, Iris (the librarian) is *expected* to have moderately high centrality on handoff edges, since all agents emit handoffs to her. That's by design. Flag as drift only if her centrality on *review* or *merge* edges is also high — the librarian shouldn't be the merger.

### Single point of failure threshold

A practical heuristic:

```
spof = centrality[top_node] / mean(centrality[all_nodes]) > 2.5
```

If the top-centrality node is more than 2.5× the mean, the audit flags `single point of failure: <actor>` in the Coordination axis.

### Visualization

In the HTML dashboard, render the network as a force-directed graph. Edges colored by type:

- review = blue
- handoff = green
- merge = orange

Node size proportional to total degree.

## Putting metrics together

The report's Metric tables (Section 5) get one sub-table per category. Each sub-table has columns:

| Metric | Value | Confidence | Note |
|---|---|---|---|

Where `Note` is a one-line explanation if the value isn't self-explanatory (e.g., *"From a sample of 100/412 PRs, stratified by week"*).

The axis scores (Section 9) reference these tables — every score's one-line justification cites the specific metric value(s) that drove it.

## Methodology section reminders

The report's Methodology section captures:

- Time window and rationale.
- Sources used (`gh api`, `git log`, branch protection API, etc.).
- Sample method if any (size, criterion).
- Identity resolution rule (what disambiguation rules were applied).
- Confidence summary: `measured: N | inferred: M | not measurable: K`.

These let a re-audit reproduce the numbers and let trend comparisons stay apples-to-apples.
