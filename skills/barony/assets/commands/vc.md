---
description: Vault commit — stage, commit, and push vault changes to origin/main with the canonical agent-prefix convention
allowed-tools: Bash, Read
argument-hint: [optional commit message — overrides auto-generation]
---

Run the vault commit workflow against `{{VAULT_PATH}}`.

## Steps

1. **Check state:**

   ```bash
   git -C {{VAULT_PATH}} status --short
   git -C {{VAULT_PATH}} log --oneline origin/main..HEAD 2>/dev/null | head -5
   ```

   If the working tree is clean and nothing is ahead of origin, stop and report "vault clean — nothing to commit."

2. **Stage thoughtfully.** Use `git add <specific files>` — never `git add -A` or `git add .`, which risk staging sensitive files (`.env`, credentials) or stray work-in-progress. Print the file list you're staging so the user can see what's going in the commit.

3. **Compose the commit message** using the per-agent prefix convention. Determine prefix from the calling agent's persona — read its workspace `CLAUDE.md` or the persona file in `{{VAULT_PATH}}/_meta/PERSONAS/` if uncertain.

   Convention: prefix is the lowercase persona name. Examples (replace with your project's persona names):

   | Calling agent | Prefix |
   |---|---|
   | Librarian persona | `<librarian-name>:` (e.g. `iris:`) |
   | Worker personas (dev / analyst / designer / writer / etc.) | `<persona-name>:` (e.g. `dave:`, `vera:`) |
   | Direct user commits | pick prefix from the calling persona |

   Format: `<prefix> <operation> | <short description>`

   Operations are short verbs: `ingest`, `wiki`, `config`, `init`, `correct`, `synthesis`, `handoff`, `approve`, `review`, `outcome`, `posted`.

   If the user supplied `$ARGUMENTS`, use it as the commit message verbatim. If it lacks a prefix, prepend the appropriate one.

4. **Commit + push:**

   ```bash
   git -C {{VAULT_PATH}} commit -m "<message>"
   git -C {{VAULT_PATH}} push origin main
   ```

   For multi-line messages, use a HEREDOC pattern:

   ```bash
   git -C {{VAULT_PATH}} commit -m "$(cat <<'EOF'
   <prefix> <operation> | <short description>

   <longer body if useful>
   EOF
   )"
   ```

5. **Verify the push landed** by checking GitHub:

   ```bash
   VAULT_REMOTE=$(git -C {{VAULT_PATH}} remote get-url origin | sed -E 's|.*[:/]([^/]+/[^/]+)(\.git)?$|\1|' | sed 's|\.git$||')
   LOCAL_SHA=$(git -C {{VAULT_PATH}} rev-parse HEAD)
   REMOTE_SHA=$(gh api "repos/$VAULT_REMOTE/commits/main" --jq '.sha')
   echo "local:  $LOCAL_SHA"
   echo "remote: $REMOTE_SHA"
   ```

   The two SHAs should match. Report the new short-SHA range (`<old>..<new>`).

## Hard rules

- **Never** force-push, amend, or rebase against `main`.
- **Never** include `--no-verify` unless the user explicitly says so. If a pre-commit hook fails, investigate and fix.
- **Never** commit `.env`, credential files, or anything that looks sensitive — surface it and ask the user.
- If the message is auto-generated and unclear about what changed, prefer brevity but ensure the *operation* and *target* are named (e.g. `iris: ingest | dev-log for 2026-05-27` beats `iris: ingest | updates`).

## Argument behaviour

User-supplied message (if any): $ARGUMENTS

- If `$ARGUMENTS` is empty, generate a message from the staged diff using the conventions above.
- If `$ARGUMENTS` is provided and starts with a known persona prefix (e.g. `iris:`, `dave:`, `vera:`), use verbatim.
- If `$ARGUMENTS` is provided without a prefix, prepend the calling-agent's prefix.
