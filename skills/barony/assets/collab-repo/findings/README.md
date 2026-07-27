# findings/

Investigations, dev logs, UAT reports, research outputs for {{PROJECT_NAME}}.

## What goes here

**Investigations** — any persona's deep-dive into a question, problem, or area of the system. Filename: `YYYY-MM-DD-<persona>-<topic-slug>.md`.

**Dev logs** — per-persona daily summary of work. Recommended subfolder: `<persona-slug>-dev-log/YYYY-MM-DD.md`.

**UAT reports** — structured UAT outputs (typically from an analyst persona). Filename: `YYYY-MM-DD-<topic>-uat.md`.

**Research outputs** — synthesised research that doesn't fit `wiki/` (which is the Librarian's domain). Filename: `YYYY-MM-DD-<topic>-research.md`.

## Format

Minimum frontmatter:

```yaml
---
created: YYYY-MM-DD
type: finding | dev-log | uat | research
status: active | resolved | archived
author: <PersonaName>
---
```

## Lifecycle

Findings stay forever. They're the team's institutional memory. The Librarian reads new findings on each scheduled run and synthesises wiki-worthy ones into `wiki/log.md`, `wiki/entities/`, or `wiki/concepts/`.

If a finding becomes a GitHub issue, add `github_issue: <number>` to its frontmatter. If it becomes a decision, link forward to the `decisions/` file.
