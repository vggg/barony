# Runbook — provisioning per-persona forge identity

> **Who does this:** the project owner. **Not** an agent, and **not** baron.
>
> Baron builds the *mechanism* that consumes per-persona credentials by name
> ([ADR-027](../adr/ADR-027-agent-identity.md)). Creating accounts, apps and tokens is
> deliberately outside that boundary: baron never issues, stores, or logs a credential,
> and it must never grow a token-minting path (ADR-027 §4).

## Why

Every persona already commits under its own git author. But without this, **every forge
action — opening the PR, posting the verdict, merging — happens under whoever is
ambiently logged in**, which is you. That makes an autonomous merger indistinguishable
from you on the code host, and it means branch protection cannot tell the two apart.

You are provisioning so that `merger` is a *different account than you*, and so the rule
"only the merger merges" becomes expressible.

## What baron does and does not touch

| | |
|---|---|
| In the repo (committed, public) | `identity.forge.login` — the account handle; `identity.forge.token_env` — the **name** of the variable |
| In the environment (never committed) | the token **value** |
| baron ever sees | the variable name, and whether it is set |

**Never put a token in `persona.yaml`, `manifest.yaml`, or any file in the collab repo.**

---

## Step 0 — see what needs provisioning

```bash
baron identity --collab /path/to/collab
```

`baron init` pre-fills a proposed handle per persona (`<project>-<slug>`), so this
output *is* your checklist:

```
identity — /path/to/acmeproj-collab
  rex: git Rex <rex@acmeproj.local> · forge github:acmeproj-rex via $BARON_FORGE_TOKEN_REX UNRESOLVED (unset — acts under ambient credentials)
  mo:  git Mo  <mo@acmeproj.local>  · forge github:acmeproj-mo  via $BARON_FORGE_TOKEN_MO  UNRESOLVED (unset — acts under ambient credentials) · required
```

The handles are a *proposal*. Change `identity.forge.login` in the persona spec if you
prefer different account names — just keep them distinct per persona.

---

## Option A — machine accounts + fine-grained PATs (recommended default)

Do this once **per persona that touches the forge**.

1. **Create the account.** A separate GitHub account named to match the handle above
   (e.g. `acmeproj-mo`). Use a `+`-addressed alias of your own mailbox
   (`you+acmeproj-mo@example.com`) so you keep recovery, and enable 2FA.

   > Machine/bot accounts are permitted, but the exact wording of GitHub's terms is
   > worth reading before you scale past a couple — and they must not be used to work
   > around per-account limits. That check is yours to make; this runbook does not
   > settle it.

2. **Grant it access.** Invite the account to the code repo and the collab repo (or to
   the org) with the **least role that persona's capabilities justify**:

   | Persona | Repo role | Why |
   |---|---|---|
   | reviewer | **Read** (+ ability to comment) | reads code, posts verdicts; must not push |
   | dev / autonomous-cron | **Write** | pushes branches, opens PRs |
   | librarian | **Write** on collab, **Read** on code | maintains the wiki + indexes |
   | merger | **Write** | merges PRs — and nothing else should have this |

3. **Issue a fine-grained PAT** *while logged in as that account*
   (Settings → Developer settings → Personal access tokens → Fine-grained tokens).
   Scope it to **only** the repos that persona needs, and grant only:

   | Persona | Repository permissions |
   |---|---|
   | reviewer | Contents: Read · Pull requests: **Read and write** (to comment) |
   | dev / cron | Contents: Read and write · Pull requests: Read and write |
   | librarian | Contents: Read and write (collab) · Pull requests: Read and write |
   | merger | Contents: Read and write · Pull requests: Read and write |

   Set the shortest expiry you will actually rotate. Put a calendar reminder in now —
   an expired token surfaces as `UNRESOLVED`, or as a `--require-identity` refusal, not
   as a mystery.

4. **Export it**, by the name `baron identity` printed:

   ```bash
   export BARON_FORGE_TOKEN_MO='…'     # the merger's token
   export BARON_FORGE_TOKEN_REX='…'    # the dev's token
   ```

   For an unattended sidecar, put these where its launcher can read them — the
   emitted `agents/<slug>/sidecar.sh` is the right place to source them from your
   secret store (`op run`, `pass`, `gh secret` in CI, a launchd `EnvironmentVariables`
   plist). Baron reads the process environment and nothing else.

5. **Verify.** `baron identity --collab …` should now show every persona `resolved`.

### Naming

The variable is `BARON_FORGE_TOKEN_<SLUG>` — slug upper-cased, non-alphanumerics folded
to `_` (`code-reviewer` → `BARON_FORGE_TOKEN_CODE_REVIEWER`). Override per persona with
`identity.forge.token_env` if your secret store dictates a different name.

---

## Option B — a GitHub App (production-grade target)

Better than option A on every axis except setup: fine-grained scopes, short-lived
installation tokens, revocation at the installation, no per-persona password/2FA
lifecycle, and `…[bot]` attribution that reads correctly to a human.

1. Register one App per persona (or one App with per-persona installations), grant it
   the same least-privilege permissions as the table above, and install it on the repos.
2. Set `identity.forge.login` to the bot handle as it appears on the forge (e.g.
   `acmeproj-mo[bot]`).
3. Mint an **installation token** from the App's private key and export it under the same
   `BARON_FORGE_TOKEN_<SLUG>` variable. Installation tokens expire in an hour, so do this
   in the launcher, per cycle — this is exactly the kind of thing the sidecar's
   project-owned slot is for.

**Nothing in baron changes between A and B.** Baron only ever resolves a named variable,
so switching is a provisioning change, not a code change (ADR-027 §3.2).

---

## Step N — turn attribution into enforcement

Attribution alone is an audit improvement. The reason to do any of this is what it lets
you switch on afterwards:

1. **Branch protection on the code repo's default branch:** require pull requests,
   require review, and restrict who may merge to the **merger account**. Your own
   account no longer merges unattended — the distinction that did not exist before.
2. **Fail the merger closed.** The scaffolded merger already ships
   `identity.forge.required: true`; deploy it with `--require-identity` too, so a cycle
   whose credential is missing or expired **refuses to run** rather than quietly merging
   as you:

   ```bash
   baron sidecar run mo --collab … --require-identity
   ```
3. **Declare the project done provisioning**, so `baron validate` holds the line for
   every persona added later:

   ```yaml
   # manifest.yaml
   identity:
     require_forge: true
   ```

   The missing-`identity.forge` warning becomes an error from then on.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `forge identity UNRESOLVED ($BARON_FORGE_TOKEN_X unset)` | the variable is not in the process environment | export it where the *launcher* runs — a shell export does not reach a launchd/cron job |
| A cycle refuses with "requires its own forge identity" | `required: true` and no credential | provision it, or drop `required` for now |
| Forge actions still attribute to you | the variable is set but the persona's `gh` was already authenticated | baron sets `GH_TOKEN`/`GITHUB_TOKEN`, which `gh` prefers over a stored login — check you are looking at a persona-run cycle, not your own shell |
| `push rejected: 403` | the machine account lacks write, or the PAT omits Contents: Read and write | re-check step 2 and step 3 |
| Two personas act identically on the forge | they share `identity.forge.login` | `baron validate` warns about this — give them distinct handles |

## See also

- [ADR-027](../adr/ADR-027-agent-identity.md) — the decision, the options weighed, and the boundary
- [ADR-026](../adr/ADR-026-persona-sidecar.md) — the sidecar this credential is resolved for
- [ADR-010](../adr/ADR-010-baron-notify-wake.md) §5.5 — the wake gate, which distinct accounts would let become authentication rather than detection
