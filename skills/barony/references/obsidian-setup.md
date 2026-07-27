# Obsidian + Vault Setup

Practical steps for wiring up the vault so Claude Code agents and Obsidian work together.

## Create the vault

1. Open Obsidian → "Open folder as vault" → choose or create a directory at `{{VAULT_PATH}}`.
2. Obsidian writes its config to `{{VAULT_PATH}}/.obsidian/`.

## Initialise git

```bash
git init {{VAULT_PATH}}
git -C {{VAULT_PATH}} add .
git -C {{VAULT_PATH}} commit -m "init: vault bootstrap"
```

Create a private GitHub repo and push:
```bash
git -C {{VAULT_PATH}} remote add origin git@github.com:<your-org>/<vault-repo>.git
git -C {{VAULT_PATH}} push -u origin main
```

## What to gitignore

```
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.trash/
```

Commit `.obsidian/app.json` and `.obsidian/plugins/` if you want plugin config to travel with the vault.

## Why git for the vault

Other agents (e.g. an office assistant or briefing agent running on a different machine) can clone the vault repo and read files without direct filesystem access. They pull at session start. This makes the vault a readable source of truth across environments.

## How Claude Code reads vault files

Claude Code reads and writes vault files using `Read`, `Write`, and `Edit` tools at the absolute path `{{VAULT_PATH}}/...`. No Obsidian plugin or MCP server is needed. Obsidian renders the same files — they stay in sync automatically because both tools operate on the same filesystem.

## Daily git rhythm

At session end, Iris commits and pushes:
```bash
git -C {{VAULT_PATH}} add <changed files>
git -C {{VAULT_PATH}} commit -m "iris: <operation> | <description>"
git -C {{VAULT_PATH}} push
```

Remote agents pull at their own session start:
```bash
git -C <local-vault-path> pull origin main
```

## Obsidian plugins worth enabling

- **Templater** — optional; useful for Obsidian-native templates alongside Claude Code skills
- **Obsidian Git** — optional; lets you commit from within Obsidian on mobile

No other plugins are required for the Claude Code multi-agent pattern to work.
