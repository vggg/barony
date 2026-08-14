# Runbook — agent identity signing (owner actions)

> **These are Vikram's actions.** They change GitHub account settings and repository
> rulesets, which is exactly the point: the human gate is the trust root of
> [ADR-027](../adr/ADR-027-agent-identity.md). Until this runbook is done,
> `baron identity init` refuses every persona and `.barony/allowed_signers` is
> empty — which is fail-closed, not broken.

Time: about 10 minutes once, plus ~30 seconds per persona thereafter.

## The commands, and what they do not change

Each numbered step below has a `baron identity` command that performs it. They are a
convenience over the clicking, **not** a change to who decides:

| Step | Command | Default |
|---|---|---|
| 2.4 — register a signing key | `baron identity register --persona <slug>` | **dry run** |
| 2.2 — open the enrollment PR | `baron identity enroll --persona <slug>` | **dry run** |
| 3 — the `main` ruleset | `baron identity protect` | **dry run** |

- **Dry run is the default for all three.** Each prints the exact `gh` argv and JSON
  payload it would send, and exits without sending it. `--apply` is the only thing
  that executes.
- **They run under your existing `gh auth` session.** baron does not accept a
  `--token` flag, does not read one from the environment, does not store one and does
  not print one. The authority exercised is yours, by your tool.
- **`enroll` opens the request and stops.** There is no `--merge` flag and there will
  not be one. Step 2.3 — you reading the PR and merging it — is the trust root, and a
  persona that could approve its own enrollment could mint peers.
- `register` and `protect` are **owner actions** even so: an agent running
  `--apply` on them would be changing your account and your repo's security settings.
  Step 2.1 (`baron identity init`) is the only step an agent runs on its own.

---

## 0. What you are setting up

Each persona gets its own **SSH signing key**, generated at spawn. The public half is
enrolled — by you, via a merged PR — into `.barony/allowed_signers`, a file in the repo.
Every commit, handoff and finding is then signed with that key, and anyone with a clone
can verify it offline.

**Agents keep pushing under your GitHub identity.** There are no machine accounts, no
GitHub Apps, and no per-persona tokens anywhere in this design. Per-persona attribution
comes from the **key**, and GitHub places no limit on signing keys per account.

**Honest bound, so nothing here is oversold:** this establishes attribution among
*cooperating* agents. Private keys sit unencrypted in each agent's workspace, so it does
**not** defend against a hostile actor with write access there.

---

## 1. Fill in CODEOWNERS (once per project)

`baron init --owner <your-handle>` writes it. For an existing project, edit
`.github/CODEOWNERS` and replace the placeholder:

```
/.barony/               @vggg
/.github/CODEOWNERS     @vggg
```

This is what stops an agent enrolling itself. It only bites when **Require review from
Code Owners** is on in the ruleset (step 3).

## 2. Enroll each persona's key (~30s each, repeated per persona)

1. The persona runs `baron identity init --persona <slug>`. It generates
   `~/.barony/keys/<slug>.key`, configures repo-local git, appends a request line to
   `.barony/allowed_signers`, and **exits non-zero** — it will not work until enrolled.
2. It opens a PR with that line and, for a new persona, its `agents/<slug>/persona.yaml`
   in the same PR — so you approve the key and its declared capabilities together:

   ```bash
   baron identity enroll --persona <slug>            # prints the branch/commit/push/PR plan
   baron identity enroll --persona <slug> --apply    # opens the PR — and stops there
   ```

   It warns if `agents/<slug>/persona.yaml` is missing, because `baron verify identity`
   requires a registry entry and would refuse that persona's commits even once enrolled.
3. **You review and merge.** Check the slug matches the persona you expect. That merge
   is the entire trust root; everything downstream is automatic. baron cannot do this
   step and has no flag that would.
4. Register the same public key on your GitHub account as a **signing key**:

   ```bash
   baron identity register --persona <slug>           # prints the exact API call
   baron identity register --persona <slug> --apply   # POST /user/ssh_signing_keys
   ```

   Equivalently by hand: *Settings → SSH and GPG keys → New SSH key → Key type:
   **Signing Key*** (paste `~/.barony/keys/<slug>.key.pub`). Note the key **type** —
   a key added under *Authentication* grants push access and badges nothing, and the
   two lists look identical at a glance. The command uses the signing endpoint, which
   is one reason to prefer it.

   There is no limit on the number of signing keys, and GitHub records **which key**
   signed each commit — one account, N distinguishable personas. This step buys the
   Verified badge; the CI check in step 3 does not depend on it.

Verify with `baron identity show`. Re-running `register` is safe: it detects a key
already on the account and skips.

## 3. Turn on the ruleset for `main` (once per repo)

```bash
baron identity protect            # prints the ruleset payload it would POST
baron identity protect --apply    # creates it
```

**Enroll your personas first (step 2).** Once `required_signatures` is active, an
unenrolled persona cannot land anything — including its own enrollment PR. And the
`verify-identity` workflow must already be publishing that check on PRs: a ruleset
requiring a check nothing reports blocks every merge, permanently. `baron identity
protect` warns about both before it will apply, and refuses to stack a second ruleset
if one by the same name already exists.

The equivalent by hand — *Settings → Rules → Rulesets → New branch ruleset*, targeting
the default branch:

- [x] **Require a pull request before merging** — and *Require review from Code Owners*
- [x] **Require status checks to pass** → add **`verify-identity`**
      *(this is the real gate — a check that can be merged around is a report)*
- [x] **Require signed commits**
- **Allowed merge methods: Squash and/or Merge commit. NOT "Rebase and merge."**
      Rebase-merge adds head-branch commits to the base **without** signature
      verification — a documented platform gap, and it would silently defeat the
      require-signed-commits rule.

## 4. Verify it works

Open a throwaway PR with one unsigned commit. Expect: `verify-identity` red, merge
blocked. Then a signed commit from an enrolled persona: green.

---

## Recurring tasks

**Rotation.** Generate a new key, PR it into `allowed_signers`, and **keep the old line**
(annotate it with a retirement date) so historical commits still verify. That is the
whole lifecycle — there is no vault, no escrow, no automation, by decision
(ADR-027 §4).

**Revocation.** Delete the line, merge, and delete the key from your GitHub account.
Commits already signed with it stop verifying — which is the correct outcome for a
compromised key, and the reason retirement (keep the line) and revocation (drop it) are
different actions.

**A refused handoff.** `baron handoff verify` and `baron handoff close` refuse an
artifact whose `.sig` does not verify and record it as a **finding**. Read the finding:
either the key is unenrolled (enroll it) or the artifact was altered after signing
(re-sign it, and ask why).

## What is deliberately NOT here

No Barony CA or PKI, no hosted registry or identity API, no custom signature format, no
key escrow or rotation automation, no DID method, no machine-account sprawl. See
ADR-027 §4 for why each one is refused.
