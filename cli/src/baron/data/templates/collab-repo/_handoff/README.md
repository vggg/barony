# _handoff/

Cross-persona async messages for {{PROJECT_NAME}}.

## Format

Filename: `YYYY-MM-DD-HHMM-<from>-<topic-slug>.md`

Required frontmatter:

```yaml
---
created: YYYY-MM-DD
status: open | done
for: <PersonaName | all>
from: <PersonaName>
priority: low | medium | high
---
```

## Lifecycle

1. Sender writes file with `status: open`
2. Receiver reads at session-start (per their `agents/<persona>/AGENT.md` ritual)
3. Receiver acts on the handoff
4. Receiver flips frontmatter to `status: done`
5. **File stays.** Never delete handoff files — the append-only model preserves coordination history.

## Routing

- Tag the specific persona (`for: Vera`) or `for: all` for broadcast messages
- The Librarian processes `for: librarian` items as part of its scheduled run
- Project owner's personal Iris (if applicable) reads `for: Iris` items via one-way bridge

## Conventions

- Keep it short — `_handoff/` is a notification surface, not a document store. If the content is long-form, write it in `findings/` or `decisions/` and link from a brief handoff.
- Don't drop handoffs for things that fit cleanly in a GitHub issue. Handoffs are for vault-side coordination (decisions, conventions, project rules) — GitHub is for work-state.
