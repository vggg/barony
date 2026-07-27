# {{PROJECT_NAME}} — Bootstrap

Welcome. This walks you through joining {{PROJECT_NAME}} as a remote collaborator manually, step by step. Plan for 30–60 minutes the first time.

> **Using an AI coding agent (Claude Code, code-puppy, etc.)?** Skip to [QUICKSTART.md](QUICKSTART.md) — same content, but the agent does the heavy lifting and you confirm each step. ~30 min instead of ~45.

## What this project is

{{PROJECT_DESCRIPTION}}

The project runs as a small distributed team. Each collaborator (you) operates one or more *personas* — durable team identities backed by their own git config, ticket label, and operating manual. The team coordinates async via two GitHub repos:

- **Code repo** ([`{{CODE_REPO}}`](https://github.com/{{CODE_REPO}})) — the application code, PRs, issues.
- **Collab repo** ([`{{COLLAB_REPO}}`](https://github.com/{{COLLAB_REPO}}), this one) — persona manuals, conventions, coordination, decisions, findings, the project wiki.

## The team

| Role | Persona | GitHub | Owns |
|---|---|---|---|
| Project owner | {{USER_NAME}} | `@{{OWNER_HANDLE}}` | Final calls, cross-cutting decisions |
| (one row per persona — fill from `agents/<persona>/AGENT.md`) | | | |

**Important:** autonomous personas (PR Reviewer, Backtest Runner, Librarian, etc.) do **not** have their own GitHub accounts. They run as automation (GitHub Actions, scheduled cron) and you communicate with them via `agent-<persona>` labels on issues/PRs. Only humans get `@`-tagged.

## Step 1 — pick (or claim) your persona

Look in `agents/` for available persona slots. Each subfolder is a persona that's either:
- **Assigned** to a specific human (see the persona's `AGENT.md` frontmatter `assigned_to` field)
- **Unassigned** — available to claim

If the project owner has already told you which persona to take, use that. Otherwise, drop a `_handoff/` for `@{{OWNER_HANDLE}}` asking for an assignment.

## Step 2 — read your persona's AGENT.md

Your persona's `AGENT.md` (at `agents/<your-persona>/AGENT.md`) tells you:
- Your git identity (name + email)
- Your ticket label
- Your commit message prefix
- Your workspace path (where to clone the code repo locally)
- Your session-start ritual
- Your ADR rules
- Your end-of-session ritual

**Read it end-to-end before doing anything else.**

## Step 3 — fire up your {{PROJECT_NAME}} workspace

Set up a single folder on your machine that holds both repos. Mirrors the standard pattern; matches what autonomous agents use.

```bash
# Pick a base path — recommended:
mkdir -p ~/Workspace/{{PROJECT_NAME}}/<your-slug>
cd ~/Workspace/{{PROJECT_NAME}}/<your-slug>

# Clone both repos
git clone git@github.com:{{CODE_REPO}}.git
git clone git@github.com:{{COLLAB_REPO}}.git

# Set per-repo git identity in each clone
cd <code-repo-folder>
git config user.name "<PersonaName>"
git config user.email "<your verified GitHub email>"
cd ../<collab-repo-folder>
git config user.name "<PersonaName>"
git config user.email "<your verified GitHub email>"
```

The per-repo override means your other Git work (personal projects, employer repos) keeps your real identity. {{PROJECT_NAME}} commits land under your persona.

### Optional — workspace bootstrap for Claude Code / code-puppy / other AI agents

If you use an AI coding agent, drop a thin bootstrap file at the workspace root so your agent loads project context on each session. Create `~/Workspace/{{PROJECT_NAME}}/<your-slug>/CLAUDE.md` (for Claude Code) or `AGENTS.md` (for code-puppy and similar):

```markdown
# <PersonaName> — {{PROJECT_NAME}} dev workspace

You are assisting **<PersonaName>**, a dev on {{PROJECT_NAME}}.

## Operating manual

Read these at session start:
- `<collab-repo>/agents/<your-slug>/AGENT.md` — <PersonaName>'s rules and rituals
- `<collab-repo>/CONVENTIONS.md` — repo-wide rules
- `<collab-repo>/COORDINATION.md` — multi-persona protocol, hot files
```

The canonical persona spec is the same `agents/<your-slug>/AGENT.md` regardless of which AI runtime you use; only the bootstrap filename changes.

## Step 4 — read the orientation set

In order:

1. `CONVENTIONS.md` (this repo) — repo-wide rules
2. `COORDINATION.md` (this repo) — multi-persona protocol, session-start checklist, hot files
3. `wiki/log.md` (this repo) — recent project activity, what's in flight (may be sparse early on)

## Step 5 — open your first "hello" PR

Pick a small, low-stakes ticket from the code repo (or just open a "Hello, I'm <persona>" trivial PR — add a comment to the README or fix a typo). The point is to validate the round trip end-to-end: branch, push, PR, review, merge.

```bash
cd ~/Workspace/{{PROJECT_NAME}}/<your-slug>/<code-repo-folder>
git checkout -b chore/hello-<your-slug>
# (make a tiny edit)
git add .
git commit -m "<your-prefix>: chore | hello — <PersonaName> joins the team"
git push -u origin chore/hello-<your-slug>
gh pr create --title "<your-prefix>: chore | hello" --body "Validating round trip per BOOTSTRAP step 5. cc @{{OWNER_HANDLE}}"
```

Tag `@{{OWNER_HANDLE}}` in the PR description. Once it's merged, you're operational.

## Step 6 — announce yourself to the Librarian

Drop a `_handoff/` so the Librarian picks you up on the next run and the wiki updates:

```bash
cd ~/Workspace/{{PROJECT_NAME}}/<your-slug>/<collab-repo-folder>
cat > _handoff/$(date +%Y-%m-%d-%H%M)-<your-slug>-joined.md <<'EOF'
---
created: <YYYY-MM-DD>
status: open
for: librarian
from: <PersonaName>
priority: low
---

# <PersonaName> joined the team

Joined {{PROJECT_NAME}} today. Available for scope discussion. Currently exploring <area-of-interest-or-leave-blank>.
EOF

git add _handoff/
git commit -m "<your-prefix>: handoff | <PersonaName> joined"
git push origin main
```

`_handoff/` files may be direct-pushed to main per `CONVENTIONS.md § _handoff/ lifecycle`. The Librarian processes the handoff on the next scheduled run and adds you to `wiki/entities/personas.md`.

## Bootstrap checklist

```
[ ] Accept GitHub collaborator invites (this repo + code repo)
[ ] Pick / claim a persona (Step 1)
[ ] Read your agents/<your-slug>/AGENT.md end-to-end (Step 2)
[ ] Create your {{PROJECT_NAME}} workspace folder (~/Workspace/{{PROJECT_NAME}}/<your-slug>/) (Step 3)
[ ] git clone both repos into the workspace; set per-repo git identity in each
[ ] (Optional) drop a workspace CLAUDE.md / AGENTS.md for your AI coding agent
[ ] Read CONVENTIONS.md, COORDINATION.md, wiki/log.md (Step 4)
[ ] Open your first "hello" PR and get it merged (Step 5)
[ ] Drop a "joined" handoff to the Librarian (Step 6)
```

When you hit your first blocker or question, drop a `_handoff/` or open a GitHub issue with the right `agent-*` label. Don't sit on it.

Welcome aboard.
