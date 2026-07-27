# {{PROJECT_NAME}} — Quickstart

Fast path to operational. If you'd rather follow each step manually, see [BOOTSTRAP.md](BOOTSTRAP.md) — same content, expanded.

## Prerequisites

- Both GitHub collaborator invites accepted (`{{CODE_REPO}}` + `{{COLLAB_REPO}}`)
- Your **persona slug** (assigned by `@{{OWNER_HANDLE}}` — check `BOOTSTRAP.md § The team` or ask)
- Your **verified GitHub email** (so commits link to your account)

## Agent-led onboarding (recommended if you use an AI coding agent)

```bash
git clone git@github.com:{{COLLAB_REPO}}.git ~/Workspace/{{PROJECT_NAME}}/<your-slug>/<collab-repo-folder>
cd ~/Workspace/{{PROJECT_NAME}}/<your-slug>
# Open Claude Code (or code-puppy / your agent of choice) in this folder, then paste the prompt below.
```

### Onboarding prompt

```
Onboard me to {{PROJECT_NAME}} per <collab-repo-folder>/BOOTSTRAP.md.

I'm <YourName>, persona slug <your-slug>, GitHub email <your verified email>.

Walk me through:
- Cloning the code repo ({{CODE_REPO}}) alongside the collab repo
- Setting per-repo git identity in both clones
- (Optional) dropping a workspace CLAUDE.md / AGENTS.md for future sessions
- Reading my agents/<your-slug>/AGENT.md end-to-end
- Reading CONVENTIONS.md, COORDINATION.md, wiki/log.md
- Drafting the first "hello" PR per BOOTSTRAP step 5
- Dropping a "joined" handoff to the Librarian per BOOTSTRAP step 6

Pause for my confirmation before any push or PR creation.
```

The agent reads `BOOTSTRAP.md` as the canonical source and walks you through each step. Plan ~30 minutes start to first PR merged.

## Manual onboarding

If you don't use an AI agent (or prefer to read each step yourself), follow [BOOTSTRAP.md](BOOTSTRAP.md) end-to-end. Plan ~45 minutes.

## After you're operational

Drop a `_handoff/` for `@{{OWNER_HANDLE}}` to discuss scope.

Welcome aboard.
