# Legacy v0.3.x emit modes (DEPRECATED)

> Moved here from `skills/barony/SKILL.md` in v1.4.0. Deprecated and
> unmaintained — see `legacy/README.md`. New projects use the runtime-agnostic path:
> `skills/barony/assets/collab-repo/START.md`.

## Legacy emit modes (v0.3.x)

Bootstraps a multi-agent Claude Code project. Supports three modes:

| Mode | What it does | Primary user | Read |
|---|---|---|---|
| `vault-project` | Emits a vault-based five-agent project scaffold (Iris + Dev 1 + Dev 2 optional + Analyst + Designer). "Lean" pattern — all coordination lives in a personal vault. | Project owner, one-shot per new lean project | [Vault-project mode](#vault-project-mode) |
| `collab-repo-project` | Emits a dedicated collab repo per project. "Option A" pattern — collab substrate lives in its own GitHub repo, separable from the personal vault. For projects with remote collaborators. | Project owner, one-shot per new Option A project | [Collab-repo-project mode](#collab-repo-project-mode) |
| `join-collab-project` | Walks a new collaborator through clone → persona pick → git identity → workspace setup → first PR for an existing collab repo. | Remote collaborator joining an existing project | [Join-collab-project mode](#join-collab-project-mode) |

After emitting, fill every `{{...}}` placeholder before committing. `__PROJECT__` is a folder name to rename (not a token to substitute).

## Choosing a mode

- **Use `vault-project`** when: you're the only operator (or all collaborators have access to your personal vault); you want the simplest setup; the team is local; collaborators don't need each other's findings visible.
- **Use `collab-repo-project`** when: multiple remote collaborators need to see each other's work; the project has its own GitHub presence; you want trust isolation (collaborators see only the project, not your second brain).
- **Use `join-collab-project`** when: you're a new collaborator joining an existing collab repo someone else set up.

Mode-by-mode emit instructions follow. Each is self-contained — read only the section for the mode you're using.

---

# vault-project mode

Generates vault and workspace CLAUDE.md scaffolding for a new project using the five-agent pattern: Iris (librarian), Dev Agent 1, Dev Agent 2 (optional), Analyst, and Designer. All artifacts live in the personal vault.

## When to use

- Starting a new software project that will use the multi-agent Claude Code setup
- Onboarding a second project into an existing vault
- Single operator (you), or small co-located team with shared vault access

## Emit steps

**1. Create vault directories.**

Inside `{{VAULT_PATH}}`:
- `_meta/PERSONAS/` (if it doesn't exist)
- `projects/{{PROJECT_SLUG}}/`

**2. Copy vault assets.**

```
vault/_meta/CONVENTIONS.md     → {{VAULT_PATH}}/_meta/CONVENTIONS.md
vault/_meta/PERSONAS/*.md      → {{VAULT_PATH}}/_meta/PERSONAS/
vault/CLAUDE.md                → {{VAULT_PATH}}/CLAUDE.md
vault/projects/__PROJECT__/    → {{VAULT_PATH}}/projects/{{PROJECT_SLUG}}/
```

**3. Copy workspace files.**

| Agent | Source | Destination |
|---|---|---|
| Dev 1 | `workspaces/dev/CLAUDE.md` | `{{WORKSPACE_BASE}}/[ProjectDev]/CLAUDE.md` and project repo root |
| Dev 2 *(optional)* | same | `{{WORKSPACE_BASE}}/[ProjectDev-2]/CLAUDE.md` |
| Analyst | `workspaces/analyst/CLAUDE.md` | `{{WORKSPACE_BASE}}/[ProjectAnalyst]/CLAUDE.md` |
| Designer | `workspaces/designer/CLAUDE.md` | `{{WORKSPACE_BASE}}/[ProjectDesigner]/CLAUDE.md` |

Dev 1 and Dev 2 use the same template. If the project uses a shared GitHub repo for both dev workspaces, commit the repo-root CLAUDE.md once — both workspaces pull it.

**3a. Copy slash commands (recommended).**

```
../skills/barony/assets/commands/vc.md → ~/.claude/commands/vc.md
```

Installs the `/vc` slash command globally for the user. Once placed, any Claude Code session (any agent, any project) can run `/vc` to commit and push vault changes following the canonical agent-prefix convention. See `../skills/barony/assets/commands/vc.md` for the workflow.

**4. Fill placeholders.**

Substitute all `{{...}}` tokens. When done, verify none remain:
```bash
grep -r '{{' {{VAULT_PATH}}/projects/{{PROJECT_SLUG}}/ \
  {{VAULT_PATH}}/_meta/ \
  {{WORKSPACE_BASE}}/[Project]*/
```
No output means clean.

**5. Commit vault.**
```bash
git -C {{VAULT_PATH}} add _meta/ projects/{{PROJECT_SLUG}}/
git -C {{VAULT_PATH}} commit -m "iris: init | bootstrap {{PROJECT_NAME}} project"
git -C {{VAULT_PATH}} push
```

**6. Commit repo CLAUDE.md.**

Commit the dev workspace `CLAUDE.md` to the project GitHub repo root.

**7. Log it.**

Prepend to `{{VAULT_PATH}}/wiki/log.md`:
```
## [YYYY-MM-DD] init | Bootstrap {{PROJECT_NAME}} project
Initial vault + workspace scaffolding. Agents: Iris, Dev-1[, Dev-2 (optional)], Analyst, Designer.
```

## Placeholder inventory (vault-project)

| Placeholder | Fill with |
|---|---|
| `{{PROJECT_NAME}}` | Human-readable project name (e.g. "MyProject") |
| `{{PROJECT_SLUG}}` | Lowercase kebab slug (e.g. "myproject") |
| `{{USER_NAME}}` | User's first name — appears in shell command notes |
| `{{VAULT_PATH}}` | Absolute path to the vault root |
| `{{WORKSPACE_BASE}}` | Base directory for all agent workspace clones |
| `{{GITHUB_REPO}}` | `org/repo` slug on GitHub |
| `{{LIVE_URL}}` | Production URL |
| `{{TECH_STACK}}` | Tech stack — brief bullet list or inline prose |
| `{{HOT_FILES}}` | Rows for the hot-files table in COORDINATION.md (tech-stack-specific files) |

---

# collab-repo-project mode

Emits a dedicated collab repo for a multi-collaborator project. The collab repo holds CONVENTIONS, COORDINATION, agent operating manuals, handoffs, decisions, findings, and a project wiki — separable from any personal vault. Each collaborator clones the collab repo to operate.

This mode implements the "Option A" boundary documented in the Irisidian remote-agents design (see `references/collab-repo-design.md`).

## When to use

- Multiple remote collaborators need to see each other's outputs
- You want trust isolation — collaborators see only project artifacts, not your personal second brain
- The project will have autonomous agents (PR Reviewer, Backtest Runner, scheduled librarian, etc.) declared as personas

## Prerequisites

Before running this mode:
1. Decide the project name, slug, code repo URL, and collab repo URL
2. Create the (empty) collab repo on GitHub — e.g. `<owner>/<project>-collab`
3. Know the persona list (one AGENT.md per persona will be emitted):
   - One **dev** persona per human collaborator
   - One **autonomous-event** persona per GitHub-Actions-on-webhook agent (PR Reviewer, Backtest Runner, etc.)
   - One **autonomous-cron** persona per `/schedule`-triggered agent (PM+UAT, Librarian, etc.)
   - The **Librarian** is always emitted by default (one cron-triggered librarian per project)

## Emit steps

**1. Clone the empty collab repo.**

```bash
git clone {{COLLAB_REPO_SSH_URL}} {{LOCAL_COLLAB_PATH}}
cd {{LOCAL_COLLAB_PATH}}
```

**2. Copy the root scaffold.**

```
../skills/barony/assets/collab-repo/CONVENTIONS.md      → {{LOCAL_COLLAB_PATH}}/CONVENTIONS.md
../skills/barony/assets/collab-repo/COORDINATION.md     → {{LOCAL_COLLAB_PATH}}/COORDINATION.md
../skills/barony/assets/collab-repo/CLAUDE.md           → {{LOCAL_COLLAB_PATH}}/CLAUDE.md
../skills/barony/assets/collab-repo/QUICKSTART.md       → {{LOCAL_COLLAB_PATH}}/QUICKSTART.md     # NEW v0.3.1
../skills/barony/assets/collab-repo/BOOTSTRAP.md        → {{LOCAL_COLLAB_PATH}}/BOOTSTRAP.md
../skills/barony/assets/collab-repo/BOOTSTRAP-ADMIN.md  → {{LOCAL_COLLAB_PATH}}/BOOTSTRAP-ADMIN.md
../skills/barony/assets/collab-repo/README.md           → {{LOCAL_COLLAB_PATH}}/README.md
```

**3. Create subfolders with READMEs and genesis content.**

Most subfolder READMEs are pure scaffolding. v0.3.1 adds three "genesis" files (wiki/log.md, wiki/index.md, and a one-time Librarian handoff) so the Librarian's first cron run has a real `find -newer wiki/log.md` baseline instead of silently no-op'ing.

```
../skills/barony/assets/collab-repo/_handoff/README.md                                  → {{LOCAL_COLLAB_PATH}}/_handoff/README.md
../skills/barony/assets/collab-repo/_handoff/{{DATE}}-bootstrap-to-librarian-genesis.md → {{LOCAL_COLLAB_PATH}}/_handoff/{{TODAY_YYYY-MM-DD-HHMM}}-bootstrap-to-librarian-genesis.md     # NEW v0.3.1
../skills/barony/assets/collab-repo/decisions/README.md → {{LOCAL_COLLAB_PATH}}/decisions/README.md
../skills/barony/assets/collab-repo/findings/README.md  → {{LOCAL_COLLAB_PATH}}/findings/README.md
../skills/barony/assets/collab-repo/wiki/README.md      → {{LOCAL_COLLAB_PATH}}/wiki/README.md
../skills/barony/assets/collab-repo/wiki/log.md         → {{LOCAL_COLLAB_PATH}}/wiki/log.md       # NEW v0.3.1
../skills/barony/assets/collab-repo/wiki/index.md       → {{LOCAL_COLLAB_PATH}}/wiki/index.md     # NEW v0.3.1
```

**3a. Copy the workspace-template folder.**

```
../skills/barony/assets/collab-repo/workspace-template/CLAUDE.md   → {{LOCAL_COLLAB_PATH}}/workspace-template/CLAUDE.md   # NEW v0.3.1
../skills/barony/assets/collab-repo/workspace-template/AGENTS.md   → {{LOCAL_COLLAB_PATH}}/workspace-template/AGENTS.md   # NEW v0.3.1
../skills/barony/assets/collab-repo/workspace-template/setup.sh    → {{LOCAL_COLLAB_PATH}}/workspace-template/setup.sh    # NEW v0.3.1
chmod +x {{LOCAL_COLLAB_PATH}}/workspace-template/setup.sh
```

The `workspace-template/` provides a runtime-portable workspace bootstrap. Any collaborator (human or failover-runner of an autonomous persona) can `./workspace-template/setup.sh <persona-slug>` to scaffold a working workspace at `~/Workspace/{{PROJECT_NAME}}/<slug>/` with both repos cloned, per-repo git identity configured, and the thin CLAUDE.md + AGENTS.md bootstrap files in place.

Cron stub generation (for cadence-driven personas) shipped in v0.3.2 as **opt-in** behind `REGISTER_CRON=yes` (generates, does not auto-load — you load it manually after reviewing the schedule). Default `setup.sh` behavior remains workspace-only.

**4. Emit persona AGENT.md files.**

For each declared persona, pick the right archetype template and copy it to `agents/{{PERSONA_SLUG}}/AGENT.md`:

| Persona type | Template | Notes |
|---|---|---|
| Human dev | `../skills/barony/assets/collab-repo/agents/__DEV__/AGENT.md` | One per human collaborator |
| Autonomous (event-triggered) | `../skills/barony/assets/collab-repo/agents/__AUTONOMOUS_EVENT__/AGENT.md` | E.g. PR Reviewer, Backtest Runner |
| Autonomous (cron-triggered) | `../skills/barony/assets/collab-repo/agents/__AUTONOMOUS_CRON__/AGENT.md` | E.g. PM+UAT |
| Librarian | `../skills/barony/assets/collab-repo/agents/librarian/AGENT.md` + `FAILOVER.md` | Emitted by default; one per project |

Rename each `__DEV__` / `__AUTONOMOUS_EVENT__` / `__AUTONOMOUS_CRON__` folder to the persona's slug as you copy.

**For each persona, prompt for the `runtime:` field (new in v0.3.2).** The taxonomy:

| Value | When to pick | FAILOVER snippet used |
|---|---|---|
| `launchd-cron` | macOS-based default runner; cadence-driven | `_failover-cron-sections/launchd-cron.md` |
| `systemd-timer` | Linux-based default runner; cadence-driven | `_failover-cron-sections/systemd-timer.md` |
| `cloud-routine` | Anthropic-hosted always-on; cadence-driven | `_failover-cron-sections/cloud-routine.md` |
| `gh-actions-cron` | GitHub-hosted always-on; cadence-driven | `_failover-cron-sections/gh-actions-cron.md` |
| `gh-actions-event` | GitHub-hosted; event-triggered (PR webhook, etc.) | N/A — no FAILOVER.md emitted for event-triggered |

**4a. Emit per-runtime FAILOVER cron section (new in v0.3.2).**

For each persona that has a FAILOVER.md (Librarian; any other cadence-driven persona where failover is meaningful):

1. Read the `runtime:` field from the persona's `AGENT.md` frontmatter.
2. Copy `../skills/barony/assets/collab-repo/_failover-cron-sections/{{runtime}}.md` into the persona's `FAILOVER.md`, substituting the `{{FAILOVER_CRON_SECTION}}` placeholder.
3. Fill any remaining placeholders ({{PROJECT_NAME}}, {{PROJECT_NAME_LOWER}}, {{CADENCE}}, etc.).

**5. Fill placeholders.**

Substitute all `{{...}}` tokens. When done, verify none remain:
```bash
grep -r '{{' {{LOCAL_COLLAB_PATH}}/
```

**6. Add agent labels to the code repo (and the collab repo).**

For each persona, create a GitHub label that routes work to it. Run from the collab repo directory:

```bash
for persona in {{PERSONA_SLUG_LIST}}; do
  gh label create "agent-$persona" \
    --color "5319e7" \
    --description "Routes work to this persona" \
    --repo {{CODE_REPO}}
  gh label create "agent-$persona" \
    --color "5319e7" \
    --description "Routes work to this persona" \
    --repo {{COLLAB_REPO}}
done
```

Also create standard workflow labels (`feat`, `chore`, `refactor`, `docs`, `test`, `research`, `needs-discussion`) on both repos. The `bug` and `question` labels are GitHub defaults — keep them.

**7. Commit the collab repo.**

```bash
git -C {{LOCAL_COLLAB_PATH}} add -A
git -C {{LOCAL_COLLAB_PATH}} commit -m "chore: bootstrap collab repo — CONVENTIONS, COORDINATION, agents, scaffolding"
git -C {{LOCAL_COLLAB_PATH}} push origin main
```

**8. (Optional) Apply trust-gating.**

See `BOOTSTRAP-ADMIN.md` for the optional branch-protection runbook. Trust-gating is lifecycle-agnostic — apply now, later, or never depending on project trust profile.

**9. Log it (in your personal vault, if you have one).**

Prepend to `{{VAULT_PATH}}/wiki/log.md`:
```
## [YYYY-MM-DD] init | Bootstrap {{PROJECT_NAME}} collab repo
Initial Option A scaffolding for {{PROJECT_NAME}} — {{COLLAB_REPO}}. Personas: {{PERSONA_SLUG_LIST}}.
```

**10. Invite collaborators.**

Once the repo is seeded, invite each human collaborator as a GitHub collaborator on both the code repo and the collab repo. Direct them to read `BOOTSTRAP.md` first, then run the `join-collab-project` mode of this skill to claim their persona.

## Placeholder inventory (collab-repo-project)

| Placeholder | Fill with |
|---|---|
| `{{PROJECT_NAME}}` | Human-readable project name |
| `{{PROJECT_SLUG}}` | Lowercase kebab slug |
| `{{PROJECT_DESCRIPTION}}` | One-paragraph project pitch |
| `{{USER_NAME}}` | Project owner's first name (used in shell command notes) |
| `{{OWNER_HANDLE}}` | Owner's GitHub `@handle` (used for `@`-tagging in routing) |
| `{{CODE_REPO}}` | `org/repo` slug for the code repo on GitHub |
| `{{COLLAB_REPO}}` | `org/repo` slug for this collab repo |
| `{{COLLAB_REPO_SSH_URL}}` | Full SSH clone URL for the collab repo |
| `{{LOCAL_COLLAB_PATH}}` | Where the collab repo is cloned locally during bootstrap |
| `{{VAULT_PATH}}` | Owner's personal vault path (optional — only if logging the init in a vault) |
| `{{LIVE_URL}}` | Production URL (if applicable; otherwise omit) |
| `{{TECH_STACK}}` | Tech stack — brief bullet list or inline prose |
| `{{HOT_FILES_TABLE_ROWS}}` | Rows for the hot-files table in COORDINATION.md per the project's actual code shape |
| `{{PERSONA_SLUG_LIST}}` | Space-separated list of all persona slugs (e.g. `dave kris vera ivy pr-reviewer backtest-runner pm-uat librarian`) |
| `{{PERSONA_NAME}}`, `{{PERSONA_SLUG}}`, etc. | Per-persona placeholders inside each AGENT.md |

---

# join-collab-project mode

For a **human remote collaborator** joining an existing collab repo as a dev persona. Walks through cloning, claiming a persona, setting git identity, and validating the round trip with a first PR.

This mode is for *humans only*. Autonomous personas (event-triggered, cron-triggered) are managed by the project owner via the admin path (`BOOTSTRAP-ADMIN.md`); they don't onboard themselves. Librarian failover has its own runbook at `agents/librarian/FAILOVER.md` in each project's collab repo.

## When to use

- You've been invited as a collaborator to a project's collab repo
- The project owner pointed you at this skill for self-onboarding
- You have your own GitHub account and your own development machine

## Prerequisites

Before running this mode:
1. **Accept GitHub collaborator invites** for both the project's code repo and collab repo (the project owner sends them via GitHub)
2. **Have Claude Code installed** on your machine
3. **Know which persona you're claiming** — either the project owner told you, or there's an unassigned persona folder in `agents/` you can pick

## Emit steps

**1. Clone the collab repo first.**

```bash
git clone {{COLLAB_REPO_SSH_URL}} {{LOCAL_COLLAB_PATH}}
cd {{LOCAL_COLLAB_PATH}}
```

The collab repo is the right starting point because it contains your operating manual, the project rules, and the team roster.

**2. Read the orientation set in order.**

| File | Why |
|---|---|
| `README.md` | High-level project overview |
| `BOOTSTRAP.md` | Project-specific onboarding (parallel to this skill mode; project owner may have customised it) |
| `CONVENTIONS.md` | Repo-wide rules (identity, labels, routing, wikilinks, tool hierarchy) |
| `COORDINATION.md` | Multi-persona protocol, session-start checklist, hot files, ADR rules |

Don't skim. The 10–15 minutes spent here saves hours of mid-task confusion later.

**3. Pick your persona.**

Look in `agents/`. Each subfolder is a persona. Open the persona's `AGENT.md` and check the frontmatter:
- `assigned_to: <handle>` — already assigned to someone (not you, unless that's you)
- `assigned_to:` empty or absent — available to claim

If the project owner already told you which to take, use that. Otherwise:
- If there's an unassigned dev persona that matches your scope, claim it
- Otherwise drop a `_handoff/` for `@{{OWNER_HANDLE}}` asking for an assignment

**4. Claim the persona.**

Edit your chosen `agents/<persona>/AGENT.md`:
- Set `assigned_to: {{YOUR_GH_HANDLE}}` in frontmatter
- Fill any `{{HUMAN_GH_HANDLE}}` placeholders in the body with your handle
- Verify other placeholders make sense for your scope; fill where needed

Commit and push (or open a PR if the repo is trust-gated):

```bash
git add agents/<persona>/AGENT.md
git commit -m "<persona-slug>: claim | {{YOUR_GH_HANDLE}} taking <persona> persona"
# If trust-gated, open a PR; otherwise:
git push origin main
```

**5. Set git identity in the collab repo clone.**

Per-repo override so your other Git work keeps your real identity:

```bash
cd {{LOCAL_COLLAB_PATH}}
git config user.name "<your persona name from AGENT.md>"
git config user.email "<your persona email from AGENT.md>"
```

Verify:
```bash
git config user.name    # should print your persona name
git config user.email   # should print your persona email
```

**6. Clone the code repo to your workspace.**

```bash
git clone {{CODE_REPO_SSH_URL}} {{YOUR_WORKSPACE_PATH}}
cd {{YOUR_WORKSPACE_PATH}}
git config user.name "<your persona name>"
git config user.email "<your persona email>"
```

Use the workspace path declared in your `AGENT.md`. The path follows the project's `{{WORKSPACE_BASE}}` convention (e.g. `~/Workspace/Claude/<project>/`).

**7. Set up Claude Code in the workspace.**

Open the workspace in Claude Code (or `cd` into it from a Claude Code session). The workspace `CLAUDE.md` will load automatically — that's where your persona's session rules live. If there's no `CLAUDE.md` yet in the code repo workspace, copy your persona's `AGENT.md` content into a `CLAUDE.md` at the workspace root (or symlink — see `BOOTSTRAP-ADMIN.md` for the project's preferred pattern).

**8. Verify the round trip with a "hello" PR.**

```bash
# In the code repo workspace:
git checkout -b chore/hello-{{YOUR_PERSONA_SLUG}}

# Make a tiny edit — add yourself to a CONTRIBUTORS file, fix a typo, add a comment to README
# (or whatever the project's BOOTSTRAP.md suggests)

git add .
git commit -m "{{YOUR_PERSONA_SLUG}}: chore | hello — {{YOUR_PERSONA}} joins the team"
git push -u origin chore/hello-{{YOUR_PERSONA_SLUG}}

gh pr create \
  --title "{{YOUR_PERSONA_SLUG}}: chore | hello" \
  --body "Validating round trip per BOOTSTRAP step 8. Tag: @{{OWNER_HANDLE}}"
```

When the PR is merged, you're operational.

**9. Drop a Librarian handoff announcing you've joined.**

In the collab repo:

```bash
cat > _handoff/$(date +%Y-%m-%d-%H%M)-{{YOUR_PERSONA_SLUG}}-joined.md <<EOF
---
created: $(date +%Y-%m-%d)
status: open
for: librarian
from: {{YOUR_PERSONA}}
priority: low
---

# {{YOUR_PERSONA}} ({{YOUR_GH_HANDLE}}) has joined the team

Claimed the {{YOUR_PERSONA_SLUG}} persona. First hello-PR merged at {{CODE_REPO}}#<PR-number>. Ready to take on tickets.

Please update wiki/entities/team.md or equivalent on next ingest.
EOF

git add _handoff/
git commit -m "{{YOUR_PERSONA_SLUG}}: handoff | joining"
git push origin main   # or via PR if trust-gated
```

**10. Begin work.**

Look at the open backlog with your persona's label:

```bash
gh issue list --state open --label agent-{{YOUR_PERSONA_SLUG}} --repo {{CODE_REPO}}
gh issue list --state open --no-assignee --repo {{CODE_REPO}}   # available
```

Claim a ticket per your `AGENT.md`'s instructions. Welcome aboard.

## Placeholder inventory (join-collab-project)

| Placeholder | Fill with |
|---|---|
| `{{COLLAB_REPO_SSH_URL}}` | The collab repo's SSH clone URL (project owner provides) |
| `{{LOCAL_COLLAB_PATH}}` | Where you want to clone the collab repo locally |
| `{{CODE_REPO_SSH_URL}}` | The code repo's SSH clone URL |
| `{{YOUR_WORKSPACE_PATH}}` | Where you want to clone the code repo (per your `AGENT.md`'s workspace path convention) |
| `{{YOUR_GH_HANDLE}}` | Your GitHub `@handle` |
| `{{YOUR_PERSONA}}` | The persona name you're claiming (e.g. `Pranav`, `Vikash`) |
| `{{YOUR_PERSONA_SLUG}}` | The persona slug (e.g. `pranav`, `vikash`) |
| `{{OWNER_HANDLE}}` | Project owner's GitHub handle |
| `{{CODE_REPO}}` | Code repo slug (`org/name`) |

## Common issues

**"My persona has no AGENT.md yet."** Project owner hasn't set it up. Drop a `_handoff/` for `@{{OWNER_HANDLE}}` asking them to add your persona via `BOOTSTRAP-ADMIN.md § Adding a persona`.

**"I want a different persona than what's available."** Drop a `_handoff/` for `@{{OWNER_HANDLE}}` describing the persona you'd take and why. The owner decides whether to add it.

**"My hello-PR isn't getting reviewed."** Tag `@{{OWNER_HANDLE}}` in a PR comment. If the PR is trivial and the owner has been pinged, ping again after 24h.

**"I'm not sure what's in scope for my persona."** Re-read your `AGENT.md § Scope`. If it's unclear, drop a `_handoff/` for `@{{OWNER_HANDLE}}` asking for clarification.
