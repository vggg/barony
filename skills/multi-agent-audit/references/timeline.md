# Timeline view (Step 4 — report enhancement)

A **timeline of important events** in the audited project, rendered chronologically in both the markdown report (text + table) and the HTML dashboard (horizontal SVG/Chart.js visualization). Helps a reviewer see *when* things changed alongside the *what*.

## What counts as an "important event"

Not every commit. Not every PR. The timeline filters down to events that materially shaped the project — declared inflections, roster changes, releases, major incidents.

**Always include:**

1. **Project creation** — first commit on the audited code repo (or coordination repo if different).
2. **Release tags** — every git tag matching a semver-shaped pattern (`v?\d+\.\d+\.\d+`).
3. **Major decisions** — ADRs filed (`docs/adr/ADR-*.md` files; gather creation date from `git log --diff-filter=A`).
4. **Roster changes** — new personas added, removed, paused. Detect from:
   - `manifest.yaml` `agents:` array diffs over the window (per v1.x bootstrap layout)
   - vault memory frontmatter `status: on-break` / `status: active`
   - `wiki/log.md` entries matching `restructure | team-change | persona-added | persona-removed`
   - `_handoff/` files with subject lines like `restructure | role-update | on-leave`
5. **Workforce changes** — declared persona on long break / returned. Detect from `status: on-break` / `on-break-since:` / `returned:` frontmatter.
6. **Architecture decisions** — ADR files with `status: accepted` flipping; large file rewrites (`>200 lines` in a single ADR file).
7. **Significant incidents** — production rollbacks (revert commits to `main`), declared incidents in `incidents/`, hotfix commit clusters (≥3 fix commits within 4 hours).
8. **CONVENTIONS.md / COORDINATION.md changes** — rule changes that shape downstream behavior. Detect via `git log <coord-files>`.
9. **Audit snapshots** — every previous audit run for this project (so trend context lands visually).

**Optionally include** (when explicitly requested):

10. **Large feature ships** — PRs ≥500 lines that merged within the window.
11. **Persona-level milestones** — first commit by each declared persona; first persona handoff.

**Don't include:**

- Every commit, every PR, every issue.
- Internal documentation tweaks that don't change rules.
- Routine merges.

The timeline is signal, not log replay.

## Detection rules per event type

| Event type | Detection signal | Source |
|---|---|---|
| Project creation | `git log --reverse --format='%H %ad %s' --date=short \| head -1` | code repo |
| Release tag | `git tag --sort=creatordate --format='%(refname:short) %(creatordate:short)'` filtered by date in window | code repo |
| ADR filed | `git log --diff-filter=A --name-only --format='%ad %H' docs/adr/ADR-*.md` | code repo + coordination repo |
| ADR accepted | grep `status: accepted` in ADR file; first-seen commit date for that change | code repo |
| Roster change | diff `manifest.yaml` `agents:` array across window OR `wiki/log.md` entries matching restructure terms | coordination repo / vault |
| Persona on-break | `on-break-since:` frontmatter in `user_agent_*.md` memories OR vault `_handoff/` "on leave" handoffs | vault memories + handoff folder |
| Persona returns | `returned:` frontmatter OR `status: active` flip in same memory | same |
| Convention change | substantive diff (>20 lines added/changed) to `CONVENTIONS.md`, `COORDINATION.md`, or workspace `CLAUDE.md` files | git log on those paths |
| Incident | revert commits to `main` (`git log --grep='^Revert '`); files in `incidents/`; hotfix clusters | code repo |
| Audit snapshot | every prior `snapshots/*.json` in the audit output folder; read `audit_run.timestamp` | output folder |
| Large feature | merged PR with `+lines ≥ 500`; titled `feat:` or labelled `feature`/`epic` | gh pr list |

## Output format — markdown timeline

In the report (after §9 Scores, before §10 Trend), insert a new section:

```markdown
## 9.5 Timeline

Important events in the audit window, in chronological order:

| Date | Event | Type | Source |
|---|---|---|---|
| 2026-03-14 | Window start | — | — |
| 2026-03-22 | Release v0.9.3 | release | tag v0.9.3 |
| 2026-04-11 | ADR-018 — SMS / Twilio integration | adr | docs/adr/ADR-018-twilio.md |
| 2026-04-29 | Embedding pipeline overhaul shipped (PRs #620-#627) | feature | PR cluster |
| 2026-05-15 | Kris joined as dev-agent-2 | roster | user_agent_kris.md memory |
| 2026-05-22 | CONVENTIONS.md → vault commits via /vc workflow | convention | git log _meta/CONVENTIONS.md |
| 2026-05-26 | trellisiq.online domain outage (registrar lock) | incident | findings/2026-05-26-domain-outage |
| 2026-05-28 | iOS scoping greenlit; Pranav joins as iOS dev (separate repo) | roster | wiki/log.md entry |
| 2026-05-30 | ADR-001 accepted (runtime-agnostic bootstrap, Barony repo) | decision | tag v1.0.0 |
| **2026-06-10** | **Team restructure — Dave + Ivy on long break; Kris sole dev; Vera analyst+designer** | **roster** | **handoff + user_agent_dave/designer memories** |
| 2026-06-12 | First audit (this snapshot) | audit | this snapshot |
| 2026-06-12 | Audit window end | — | — |
```

Highlight the restructure (or other pivotal events) with bold rows. Keep entries terse — one line per event.

## Output format — HTML timeline

In the dashboard, render as a **horizontal SVG timeline** below the verdict card, above the headlines grid. Each event becomes a colored marker on a date-axis line, with hover tooltips and labels for the most-significant events.

Visual rules:

- **Markers** colored by event type: release (emerald), adr/decision (sky), roster (amber), convention (gray), incident (rose), audit (purple).
- **Labels** shown for events scoring ≥7 on the importance heuristic; others available on hover.
- **Vertical lines** at week boundaries; bold line at window-start and window-end.
- **Connector** between consecutive related events (e.g., ADR filed → ADR accepted → release implementing it).

A reference rendering is in `assets/report-template.html` under the `<svg id="timeline">` element (added in v1.3).

## Importance heuristic

When the timeline gets crowded (>15 events in window), rank by importance score 1–10:

| Signal | Score contribution |
|---|---|
| Release tag (major) | +5 |
| Release tag (minor/patch) | +3 |
| ADR accepted | +4 |
| ADR filed (proposed) | +2 |
| Roster change | +5 |
| Workforce change (on-break / return) | +5 |
| Convention change (>50 lines) | +4 |
| Convention change (≤50 lines) | +2 |
| Incident (revert to main) | +5 |
| Incident (hotfix cluster) | +3 |
| Large feature (≥1000 lines merged) | +3 |
| Audit snapshot | +2 |

Show events with score ≥4 by default; full list available via `--all` flag. The visual dashboard always shows everything but labels only the ≥7s.

## Implementation

A reference Python helper ships at `scripts/extract_timeline.py`. It:

- Takes `--repo <path>` (code repo) and `--coordination <path>` (vault or collab repo, optional)
- Takes `--window-start` / `--window-end`
- Emits machine-readable JSON: `[{date, type, title, importance, source}, ...]`
- Markdown formatter: `--format md` produces the §9.5 table
- HTML formatter: `--format html` produces the SVG block ready to embed

Invocation:

```bash
python3 scripts/extract_timeline.py \
  --repo path/to/code-repo \
  --coordination path/to/collab-repo \
  --window-start 2026-03-14 --window-end 2026-06-12 \
  --format json > timeline.json
```

The auditor invokes this during Step 4 report generation, pastes the markdown output into §9.5, and the HTML output goes into the dashboard.

## Snapshot integration

Timeline events are NOT persisted in the snapshot JSON (they'd bloat it). They are re-extractable from the repos at any time. The snapshot only records:

```json
"timeline_metadata": {
  "events_total": 24,
  "events_with_importance_ge_4": 18,
  "highest_importance_event": "2026-06-10 team restructure (importance: 9)"
}
```

This lets trend-mode compare event density and surface pattern shifts ("the post-restructure period had 0 incidents vs 3 in the prior 90 days") without storing the full event list.
