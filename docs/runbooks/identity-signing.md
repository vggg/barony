# Runbook — agent identity signing (owner actions)

> **These are Vikram's actions. No agent can do them.** They change GitHub account
> settings and repository rulesets, which is exactly the point: the human gate is the
> trust root of [ADR-027](../adr/ADR-027-agent-identity.md). Until this runbook is
> done, `baron identity init` refuses every persona and `.barony/allowed_signers` is
> empty — which is fail-closed, not broken.

Time: about 10 minutes once, plus ~30 seconds per persona thereafter.

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
   in the same PR — so you approve the key and its declared capabilities together.
3. **You review and merge.** Check the slug matches the persona you expect. That merge
   is the entire trust root; everything downstream is automatic.
4. Register the same public key on your GitHub account as a **signing key**:
   *Settings → SSH and GPG keys → New SSH key → Key type: **Signing Key***.
   (Paste `~/.barony/keys/<slug>.key.pub`.) There is no limit on the number of signing
   keys, and GitHub records **which key** signed each commit — one account, N
   distinguishable personas. This step buys the Verified badge; the CI check in step 3
   does not depend on it.

Verify with `baron identity show`.

## 3. Turn on the ruleset for `main` (once per repo)

*Settings → Rules → Rulesets → New branch ruleset*, targeting the default branch:

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
