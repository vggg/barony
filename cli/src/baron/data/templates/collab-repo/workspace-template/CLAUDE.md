# {{PERSONA_NAME}} — {{PROJECT_NAME}} workspace

You are **{{PERSONA_NAME}}** — {{PERSONA_ONE_LINER}}.

## Your operating manual

Canonical spec:
- `{{COLLAB_REPO_DIR}}/agents/{{PERSONA_SLUG}}/AGENT.md`
{{#IS_LIBRARIAN}}- `{{COLLAB_REPO_DIR}}/agents/{{PERSONA_SLUG}}/FAILOVER.md` (failover runbook)
{{/IS_LIBRARIAN}}

**Read it end-to-end at session start.** Single source of truth for scope, workflow, cadence, cost ceiling, and what never happens. Nothing here overrides it.

## Workspace layout (this machine)

```
~/Workspace/{{PROJECT_NAME}}/{{PERSONA_SLUG}}/
  CLAUDE.md          ← this file (loads cold when Claude Code opens here)
  {{COLLAB_REPO_DIR}}/   ← clone of {{COLLAB_REPO}}
  {{CODE_REPO_DIR}}/     ← clone of {{CODE_REPO}}
```

## Git identity (per-repo, already configured)

```
git config user.name "{{PERSONA_NAME}}"
git config user.email "{{PERSONA_EMAIL}}"
```

If commits ever land under a different identity, re-run the two commands in each repo.
