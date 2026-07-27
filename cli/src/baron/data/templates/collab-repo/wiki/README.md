# wiki/

The {{PROJECT_NAME}} project wiki. Synthesised by the **Librarian** persona from team activity.

## Important — only the Librarian writes here

Per `CONVENTIONS.md § What never happens` and `COORDINATION.md`, only the Librarian writes to this folder. Other personas write findings, decisions, handoffs; the Librarian reads those and synthesises wiki entries.

If you want something captured in the wiki, drop a `_handoff/` for `for: librarian` with the source artifact reference. The Librarian processes these on its scheduled run.

## Structure

| File / folder | Purpose |
|---|---|
| `log.md` | Append-only reconciliation log — most recent entry at top. Read this first to orient on "what's been happening." |
| `index.md` | Catalog of all wiki pages, organised by category. Updated whenever a new wiki page is created. |
| `entities/` | Durable entities — people, components, integrations, external services. One file per entity. |
| `concepts/` | Design concepts, strategies, patterns, architectural decisions made into living docs. |
| `sources/` | Source summaries — long reads, external docs the team referenced, summaries of important inputs. |

## Reading the wiki

If you're new to {{PROJECT_NAME}} or returning after time away:

1. Top of `log.md` — last few weeks of activity
2. `index.md` — what's documented in the wiki
3. Entity pages relevant to your work (the team's surface area)
4. Concept pages for patterns you'll touch

10–15 minutes of reading should get you to "current state."
