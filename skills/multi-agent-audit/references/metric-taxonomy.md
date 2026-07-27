# Metric taxonomy + 1–5 scoring rubric

Universal definitions for the Step 1 metrics and how to score each axis in Step 3. **Framework-neutral** — these definitions apply whether the audited project is Barony, CrewAI, LangGraph, AutoGen, or a custom loop. *Where* the data lives varies; *what* the metric means does not.

## Confidence labels (apply per metric)

- **measured** — verified from an independent, reproducible source. The command/query is in the report.
- **inferred** — proxy-based, sample-based, or computed from incomplete data. Useful but note the assumption.
- **not measurable** — the platform doesn't expose the data, or the data wasn't generated. Don't fabricate.

Aggregate skill-level: at the end of the audit, report `measured: N | inferred: M | not measurable: K` across all numeric values. An audit where more than half the metrics are `inferred` or `not measurable` should say so in the executive summary.

---

## Category 1 — Throughput and flow

| Metric | Definition | Compute |
|---|---|---|
| `tasks_opened_per_week` | Issues created per ISO week | `gh issue list --search "created:>=<W-start>..<W-end>"` |
| `tasks_closed_per_week` | Issues closed per ISO week | same query with `closed:` |
| `backlog_growth_rate` | (opened − closed) / week | derived |
| `commits_per_author_per_week` | Per canonical actor (post-resolution) | `git log --since=... --format='%an' \| sort \| uniq -c` |
| `prs_opened` | PRs opened in window | `gh pr list --state all --search "created:>=..."` |
| `prs_merged` | PRs merged in window | `--state merged --search "merged:>=..."` |
| `prs_rejected` | Closed-without-merge | `--state closed --search "closed:>=..."` minus merged |
| `prs_abandoned` | Opened >N days ago, no activity in N days, still open. Default N=14 | derived |
| `cycle_time_pr_p50_p90` | PR open → merge | from `gh pr view <n> --json createdAt,mergedAt` |
| `cycle_time_issue_p50_p90` | Issue create → close | from `gh issue view <n> --json createdAt,closedAt` |

### Score — Throughput

| Score | Pattern |
|---|---|
| 5 | Sustained cadence; backlog flat or shrinking; PR cycle p50 < 2 days |
| 4 | Sustained; healthy cycle (p50 < 5 days); minor backlog growth |
| 3 | Irregular but moving; backlog stable |
| 2 | Bursty with long stalls (>14 days idle); backlog growing |
| 1 | Stalled; no merges in the recent half of the window; runaway backlog |

---

## Category 2 — PR review and review-agent activity

| Metric | Definition | Compute |
|---|---|---|
| `reviews_total` | Total review submissions | `gh api repos/.../pulls/<n>/reviews` per PR |
| `reviewers_distinct` | Distinct reviewer logins (incl. bots) | aggregated from above |
| `review_rounds_p50_p90` | Reviews per PR distribution | per-PR review count |
| `review_latency_p50` | PR opened → first review | per-PR latency |
| `merge_latency_p50` | Last approving review → merge | per-PR latency |
| `pct_prs_with_zero_reviews` | Merged with no review submission | rate |
| `pct_self_merges` | Author = merger | rate |

### Score — PR review

| Score | Pattern |
|---|---|
| 5 | Every PR reviewed; review latency p50 < 1 day; <5% self-merge |
| 4 | >90% PRs reviewed; review p50 < 2 days; <15% self-merge |
| 3 | 60–90% PRs reviewed; review p50 < 5 days |
| 2 | <60% PRs reviewed; reviewer pool of 1; >50% self-merge |
| 1 | Effectively no review gate — direct merges dominate; review is theater |

---

## Category 3 — Autonomy split + INTERVENTION TAX (headline)

This is the centerpiece. **Two numbers, reported together.**

### Autonomy split

Fraction of "tasks" initiated by autonomous (or hybrid acting autonomously) actors:

```
autonomy_split = autonomous_initiated_tasks / all_initiated_tasks
```

A *task* here is a unit of action — count whichever your project's primary unit is, but be consistent across audits:

- **PR-centric projects**: each PR = 1 task.
- **Commit-centric projects** (e.g., trunk-based with frequent direct commits): each non-merge commit = 1 task.
- **Handoff-centric projects**: each `_handoff/` file with `from:` = 1 task.

Pick one; report which.

### Intervention tax

```
intervention_tax = human_intervention_events / autonomous_initiated_tasks
```

Where `human_intervention_events` counts:

| Event | How to detect |
|---|---|
| **Unblock messages** | Human comment on an autonomous PR/issue containing question/clarification language (`?`, `please`, `should I`, `which`) |
| **Corrections** | Human-authored commits that follow an autonomous commit on the same files within 24h |
| **Redos** | Human-led PR superseding a closed-without-merge autonomous PR within 7 days (default; configurable) on overlapping files |
| **Fix-up commits** | Human commits with message matching `^fix:`, `^hotfix:`, `^revert:`, `chore: fix` that follow an autonomous commit on the same files within 7 days |

A *low* intervention tax (< 0.3 — i.e., fewer than 1 human touch per 3 autonomous tasks) means autonomy is earning its keep. A *high* tax (> 1.0 — more than 1 human touch per autonomous task) means the human is doing the work and the autonomy is theater plus latency.

### Score — Autonomy (low tax)

| Score | Pattern |
|---|---|
| 5 | Autonomy split ≥0.5 with intervention tax <0.3 |
| 4 | Autonomy split ≥0.3, tax <0.5 |
| 3 | Autonomy split 0.2–0.5, tax 0.5–1.0 |
| 2 | Autonomy split high (>0.3) but tax ≥1.0 — false-win territory |
| 1 | Autonomy nominal; human is doing the work + reviewing the agent's work |

**False-win callout.** When `autonomy_split > 0.5` AND `intervention_tax > 1.0`, the report must say: *"The multi-agent setup is doing MORE work than a single-agent or pure-human flow would have. Consider whether the overhead is earning its keep."*

---

## Category 4 — Coordination overhead + network

Detail in `references/advanced-metrics.md`. Headline metrics here:

| Metric | Definition |
|---|---|
| `handoffs_total` | `_handoff/` files (or equivalent) created in window |
| `handoffs_open_age_p90` | 90th percentile of `(now − created)` for `status: open` files |
| `cross_persona_pr_comments` | PR comments where commenter ≠ PR author |
| `centrality_top` | Actor with highest betweenness centrality in the coordination network |

### Score — Coordination

| Score | Pattern |
|---|---|
| 5 | Handoff volume proportionate to throughput; no SPOF; open-handoff age low |
| 4 | Healthy coordination with one moderate-centrality node |
| 3 | Some open-handoff staleness; coordination overhead noticeable |
| 2 | Coordination drowning throughput (handoff count > PR count); one high-centrality SPOF |
| 1 | Project is mostly handoffs; little actual work moves |

---

## Category 5 — DORA and flow

Detail in `references/advanced-metrics.md`. Headline:

| Metric | Definition |
|---|---|
| `lead_time_p50` | First commit on branch → merged |
| `deploy_frequency` | Merges to main (or release tags) per week |
| `change_failure_rate` | (reverts + hotfixes) / total deploys |
| `mttr_p50` | Time from bad-change-merged to fix-merged |
| `merge_gate_wait_p50` | PR ready-for-review → merged |
| `wip` | Open PRs over time (snapshot) |

### Score — Quality/rework (DORA + rework, combined axis)

| Score | Pattern |
|---|---|
| 5 | Lead time p50 < 1 day; deploy freq daily; CFR <5%; MTTR < 1 hour; low rework |
| 4 | Lead time p50 < 3 days; deploy 2–5x/week; CFR <15%; MTTR < 1 day |
| 3 | Weekly deploys; moderate rework (10–25%); MTTR < 1 week |
| 2 | Slow lead time (>1 week); CFR >25%; rework dominates new work |
| 1 | Failure mode: hotfixes replace forward progress |

---

## Category 6 — Quality and rework

Some overlap with DORA; these are the rework-specific lenses:

| Metric | Definition | Compute |
|---|---|---|
| `coverage_delta` | (end-window coverage) − (start-window coverage) | from coverage reports if any |
| `defect_count` | Issues with `bug` label opened in window | `gh issue list --label bug --search created:>=...` |
| `rework_rate` | `git log --grep='revert\|hotfix\|fix-up\|chore: fix'` / total commits | derived |
| `code_churn` | Lines added+removed / lines net-added | `git log --shortstat` aggregated |
| `acceptance_hit_rate` | Sample N closed PRs; for each, did the merged code match the issue's stated acceptance criteria? | manual sample; report N and method |

Acceptance hit rate is the only metric that requires light judgment — be explicit about the sample and the criterion. Default N=10. Reviewer judgment is `met | partial | not met`.

---

## Category 7 — Guardrail and ritual efficacy

| Metric | Definition | Compute |
|---|---|---|
| `force_pushes_observed` | Force-pushes to protected branches | `gh api .../branches/main/protection` for status + reflog if accessible |
| `add_dash_a_proxy` | Commits touching ≥20 files (proxy for `git add -A` use) | `git log --shortstat \| awk` |
| `direct_main_pushes` | Non-PR commits on main | `git log main --not --remotes='*/!main'` heuristic |
| `out_of_scope_writes` | Commits writing outside declared persona scope | join actor inventory + git log |
| `declared_deny_enforcement_rate` | (declared-denies-with-tool-level-block) / (total declared-denies) | derived from drift analysis |
| `dev_log_adherence` | (dev-logs filed) / (active dev-days) | counted from `dev-log/YYYY-MM-DD.md` files |
| `handoff_done_rate` | (status:done) / (status:done + status:open older than 7 days) | grep frontmatter |
| `decision_filing_rate` | (decisions/ files) / (PRs with arch-relevant changes) | sample-based |

### Score — Guardrail integrity

| Score | Pattern |
|---|---|
| 5 | Declared deny-lists are all enforced; zero observed violations; rituals followed |
| 4 | One observed violation explained and remediated; rituals mostly followed |
| 3 | Mixed enforcement (some declared denies are instruction-only); rituals 60–80% adherence |
| 2 | Most declared denies are markdown-only; multiple observed violations |
| 1 | Guardrail declarations decorative; project relies on goodwill |

### Score — Knowledge capture (rituals + drift)

| Score | Pattern |
|---|---|
| 5 | Dev-logs, decisions, wiki all current and useful |
| 4 | Two of three current; some drift; surfaceable on demand |
| 3 | One stream current, others stale |
| 2 | Knowledge artefacts exist but unread; new joiners can't onboard from them |
| 1 | No durable knowledge — everything in chat history |

---

## Operational fidelity — weighting (v1.3+)

Default fidelity formula (from v1.0) treated all dimensions equally. v1.3 introduces an **optional weighted** formula for projects where some dimensions matter more than others.

### Default — equal weight

```
operational_fidelity = sum(dimension_credits) / N_dimensions_scored
```

Each scored dimension contributes a credit in [0.0, 1.0] (see `drift-analysis.md`). N_dimensions_scored excludes dimensions marked `n/a` or `not measurable`.

### Weighted (opt-in)

If the user supplies dimension weights, use:

```
operational_fidelity = sum(weight_i * credit_i) / sum(weight_i)
```

Where weights are positive numbers (relative; do not need to sum to 1.0 — the formula normalizes).

Sensible default weights when the user opts into weighting without specifying:

| Dimension | Default weight | Rationale |
|---|---|---|
| Agents | 1.0 | Foundation — without identity attribution, nothing else can be scored |
| Autonomy | 1.0 | Headline of the skill |
| Reviewers | 1.5 | Review gate is the most-frequent operational drift |
| Guardrails | 2.0 | Enforced-vs-instructed gap has direct security/correctness impact |
| Routing/ownership | 1.0 | |
| Backlog/workflow | 1.0 | |
| Rituals | 0.5 | Soft signal; ritual adherence is usually a leading indicator, not a load-bearing rule |

The auditor MUST surface the weighting choice in §11 Methodology so trend-mode comparisons stay apples-to-apples.

## Score rollup

**Do NOT collapse the 7 axis scores into a single number.** A single composite hides the failure mode. Instead, the report's executive summary names the dominant pattern:

- *great-design / faithful* — all axes ≥4, operational fidelity ≥0.85.
- *great-design / low-fidelity* — design quality (Guardrail integrity, Coordination, Knowledge capture) high, but operational fidelity <0.7 — the project lives differently than it claims.
- *weak-design / faithful* — operational fidelity high but Throughput / Autonomy / Quality axes weak — what's running is what was declared, but it shouldn't have been declared this way.
- *weak-design / low-fidelity* — both sides weak. Consider whether the multi-agent overhead is earning its keep.

Cite each axis score in the verdict's evidence chain.
