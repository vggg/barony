# legacy/ — the deprecated v0.3.x path

This directory holds the **legacy v0.3.x template-emit path**: the original Claude-Code-only
flows (`vault-project`, `collab-repo-project`, `join-collab-project`) and the template trees
only they consume. Quarantined here in v1.4.0 so the repo has **one front door** — the
runtime-agnostic path at `skills/barony/assets/collab-repo/START.md`.

**Status: deprecated, unmaintained.** Kept only so existing projects scaffolded by v0.x can
still consult the instructions that built them. No new features land here; do not use this
path for new projects.

## Contents

| Path | What it is |
|---|---|
| `SKILL-v0.3.md` | The three legacy emit modes, verbatim from the pre-v1.4 `SKILL.md` dispatcher |
| `vault/` | `vault-project` mode templates (personal-vault five-agent scaffold) |
| `workspaces/` | `vault-project` mode per-agent workspace `CLAUDE.md` templates |

Path note: `SKILL-v0.3.md` references `vault/` and `workspaces/` relative to this directory.
The `collab-repo-project` and `join-collab-project` modes shared their templates with the
runtime-agnostic path; those still live at `skills/barony/assets/collab-repo/`
(referenced from here as `../skills/barony/assets/collab-repo/`) and continue
to evolve with the v1 path — the emit *instructions* here are what is frozen.

For why the runtime-agnostic path replaced this one, see
`../docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md` and `../CHANGELOG.md`.
