---
created: 2026-08-04
type: decision
status: proposed
adr: 011
project: barony
related:
  - "[[docs/adr/ADR-002-ways-of-working-2026-07]]"
  - "[[docs/adr/ADR-003-baron-cli]]"
  - "[[docs/adr/ADR-004-baron-guard-enforcement]]"
  - "[[docs/adr/ADR-007-session-boundary]]"
---

# ADR-011 (PROPOSED): agent identity at spawn — signed artifacts, an in-repo registry, no PKI

| Field | Value |
|---|---|
| **Status** | **Proposed** — no code, no owner decision yet. §9 lists what blocks acceptance |
| **Date** | 2026-08-04 |
| **Authors** | Claude (design proposal for Vikram) |
| **Supersedes** | — (extends ADR-002 §2; constrained by [ADR-007](ADR-007-session-boundary.md); shares the honesty discipline of [ADR-004](ADR-004-baron-guard-enforcement.md)) |
| **Evidence base** | The 2026-08-04 un-onboarded-agent incident (`a4d1d66`) + an options survey of NANDA / ANS / A2A / SPIFFE / DID / Sigstore |
| **Decision owner** | Vikram |

## 1. The problem

**Barony's core noun is attribution — "who did what" — and today it rests entirely on convention.**

On 2026-08-04 an un-onboarded OpenAI Codex agent committed directly to this repo's `main` branch.
It had no registry entry, no declared capabilities, filed no handoff, and committed **under the
owner's git identity**. Reviewing the repo afterwards, it was not possible to tell agent from owner
from the commit history alone. Nothing in the repo could have prevented it: `main` was unprotected
at the time, and every persona in every Barony project shares a single GitHub account.

This is not one bad commit. It is a structural hole under three shipped claims:

1. **The audit's headline claim** — intervention tax and operational fidelity are computed from
   attributed git and review events. If `from:` and the git author are self-asserted, the audit
   grades a record anyone can forge.
2. **Provable two-party review** — reviewer/merger separation is the product's answer to
   "who checked this?" With one account it is a naming convention, not a separation.
3. **The handoff protocol** — `from:` in frontmatter is a bare string. A ChatGPT stand-in wrote
   `from: Iris` trivially on 2026-08-01. Nothing detected it; a human noticed later.

The existing plan for this — a GitHub App or bot account per persona — is real but heavyweight, and
is currently blocked behind an unresolved sequencing debate. **This ADR proposes a cheaper mechanism
that is orthogonal to that debate and does not require it to be settled.**

## 2. Decision

**Every persona generates an SSH signing key at spawn, is enrolled once into an in-repo
`.barony/allowed_signers` file, signs every commit and handoff it produces, and is verified offline
at the gate with `git verify-commit`.**

Three properties make this the right shape for Barony specifically:

- **It is a file in the repo.** The registry is `.barony/allowed_signers`, committed. Verification
  needs a `git clone` and nothing else — no server, no CA, no network, no vendor. This is the only
  surveyed option that does not violate the invariant *the repo is the only source of truth*.
- **It is native, not invented.** Git has signed with SSH keys since 2.34 (Nov 2021). We use
  `git verify-commit` and `ssh-keygen -Y sign/verify` verbatim. No bespoke signature format.
- **It dissolves the shared-account problem without bot accounts.** GitHub imposes no limit on
  signing keys per account and records *which key* signed each commit. Per-persona attribution
  therefore works today, on the one `vggg` account, with no provisioning.

Cost to adopt: `ssh-keygen` runs in under a second with zero dependencies, and enrollment is one
human-approved PR per persona, roughly thirty seconds, once.

## 3. The flow

Three parts: **enrol once** (human), **sign always** (automatic), **verify at the gate**
(automatic, offline).

### 3.1 Scaffolding — one time per project

```
.barony/
  allowed_signers          # principal → public key. THE registry. CODEOWNERS-protected.
  personas/<slug>.yaml     # existing persona declarations
```

`.github/CODEOWNERS`:
```
/.barony/allowed_signers   @<owner>
```

`allowed_signers` uses OpenSSH's `authorized_keys`-style principal + key format:
```
carson@barony ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA… carson (enrolled 2026-08-04)
```

Committing the allowlist is what makes the scheme rebuildable from a clone.

### 3.2 At spawn — `baron identity init`

Runs before any work. Steady state is step 1 only; steps 2–3 run on a persona's first spawn.

1. **Check.** If a key exists at `~/.barony/keys/<persona>.key` *and* its public half is in
   `.barony/allowed_signers` at HEAD → configure git, proceed to work.
2. **Generate** if absent:
   `ssh-keygen -t ed25519 -N "" -f ~/.barony/keys/<persona>.key -C "<persona>@barony"`
3. **Configure repo-local git identity** (repo-local, never `--global`): `gpg.format=ssh`,
   `user.signingKey=<pubkey>`, `commit.gpgsign=true`, `tag.gpgsign=true`,
   `gpg.ssh.allowedSignersFile=.barony/allowed_signers`.

**If the key is not yet enrolled, `baron identity init` fails closed and the persona does not
work.** It prints the public key and the exact PR to open. This is the "identity before anything"
property: an unenrolled agent is not a degraded agent, it is a stopped one.

### 3.3 During work — automatic

With `commit.gpgsign=true`, commits and tags are signed with no further action. Handoffs and
findings get a detached signature — `baron handoff sign` writes
`ssh-keygen -Y sign -f <key> -n barony-handoff <file>` as `<file>.sig` — so `from:` stops being a
bare self-assertion and becomes a claim backed by a signature over the file.

### 3.4 At the gate — three layers

**(a) Local pre-commit hook.** Refuses to commit when `user.signingKey` is unset or unenrolled.
Fast feedback, trivially bypassable. **Explicitly not a control** — it catches honest
misconfiguration, in the same voice ADR-004 uses for `baron guard`.

**(b) `baron verify identity` in CI — the real gate.** Over the PR's commit range: every commit must
pass `git verify-commit`, its trust status (`%G?`) must be `G`, and the signer principal (`%GS`)
must **cross-check three ways — signature ↔ registry entry ↔ claimed persona.** A commit signed by a
genuinely enrolled key but *labelled* as a different persona fails. That third check is what closes
the `from: Iris` misattribution class, not merely the anonymous-commit class. Make it a required
status check so it cannot be merged around.

**(c) GitHub ruleset — the platform backstop.** On `main`: require a PR, require the
`baron verify identity` check, enable **require signed commits**. Use squash or merge-commit
strategies, **not rebase merges**, which add head-branch commits to the base without signature
verification. Register each persona's public key as a signing key on the account so GitHub renders
Verified and records the key.

**The librarian's role.** Ingest refuses any handoff whose `.sig` does not verify, and records the
rejection **as a finding rather than dropping it silently** — attribution failures become evidence,
which is what the audit product needs.

### 3.5 What this would have done to the incident

The Codex commit was unsigned → rejected by the ruleset before reaching `main`, and by CI had it
arrived via PR. Signed with a self-minted key → not in `allowed_signers` → `verify-commit` fails →
CI red. Properly enrolled → attributable forever from a bare clone, with a `persona.yaml` that had
to exist. Every row of that incident's failure table is covered **except ID allocation**, which is a
separate mechanism and stays out of scope here.

## 4. Where the boundary sits

[ADR-007](ADR-007-session-boundary.md) holds: Barony does not own the agent execution loop.
`baron identity init` is bookkeeping a persona runs *before* work; it never spawns anything.

The `integrate, do not author` line from the identity research holds too:

| Layer | Owner |
|---|---|
| Key generation, signing, verification primitives | **OpenSSH / git** (consumed verbatim) |
| The persona↔key registry as repo state | **baron** |
| Enrollment approval | **the platform** (CODEOWNERS + PR review) |
| Hard merge denial | **the platform** (rulesets, required checks) |
| Deciding *which* persona may act | **baron** (the capability vocabulary — ADR-004) |

Barony provisions and verifies. It does not become an identity broker.

## 5. Honest bounds — what this does NOT claim

Stated in the same voice as ADR-004, because overclaiming here would cost more credibility than the
feature is worth:

- **This establishes attribution among cooperating agents. It does not defend against an attacker
  with write access to an agent's workspace.** Anyone who can read `~/.barony/keys/` can sign as
  that persona. It is not a security boundary.
- **Key enrollment is not self-authenticating.** An agent that mints a key and adds itself to
  `allowed_signers` has proved nothing — that is self-assertion wearing a crypto costume, the exact
  failure mode this ADR exists to fix. The one-time human-approved PR *is* the trust root, and the
  scheme is only as strong as that gate.
- **What signing buys is narrow and worth stating precisely:** *this artifact was produced by the
  key enrolled as `<persona>`, and you can prove it from a clone.* It does not say the persona is
  trustworthy, competent, or acting within its capabilities.
- **Enforcement strength label:** `enforced-with-baron` at the CI gate; `enforced` only where a
  GitHub ruleset requires signed commits; `instructed` for the pre-commit hook.

## 6. Deliberately not built

1. **No Barony CA, key server, or PKI.** No issuance, no revocation service, no trust-root ceremony.
   This is the specific line ANS and NANDA cross, and the reason both are surveyed but not adopted.
2. **No hosted registry or identity API.** The registry is a file. The moment identity needs a
   service call, `cat` stops being sufficient and the invariant breaks.
3. **No custom signature format.** `ssh-keygen -Y` verbatim. If canonical-JSON signing is ever
   needed, use JWS/JCS as A2A does.
4. **No key escrow, rotation automation, or secret management.** Rotation is: generate a new key, PR
   it in, keep the old line so historical commits still verify, annotate it retired. That is the
   whole lifecycle. Do not build a vault.
5. **No DID method or `did:barony`.** Zero value over a raw public key here.
6. **No NANDA / ANS / A2A integration on speculation.** Revisit only when Barony agents genuinely
   need discovery by agents *outside* the repo — and then as an export, never as the source of truth.

## 7. Alternatives considered

| Option | Why not |
|---|---|
| **gitsign / Sigstore keyless** | Cryptographically stronger — ephemeral keys, transparency log, nothing to enrol. But it **inherits the shared-account problem**: its identity is the OIDC subject, so if every persona authenticates as `vggg`, every persona signs as `vggg`. Also renders **Unverified** on GitHub (CA not in GitHub's trust root), and offline verification is self-labelled experimental. **The right Phase-3 upgrade once per-persona platform credentials exist — it composes with the heavyweight plan rather than replacing it.** |
| **GitHub App / bot account per persona** | The existing heavyweight plan and the strongest *authorization* story. Not rejected — deferred. Requires human provisioning per persona and is not verifiable from a clone. This ADR is cheaper and orthogonal; shipping it first makes the App work more valuable, since Apps can later replace the *enrolment* trust root while the registry, CI check, and handoff signatures stay unchanged. |
| **GPG signing** | Equivalent trust, ergonomically hostile to automation — keyring setup, passphrase handling, expiry. |
| **Fine-grained PAT per persona** | Attributes to the account, not the persona. Human-created, expiry churn. |
| **GitHub OIDC workload identity** | Automatic, but only inside Actions. No identity for a laptop-spawned agent. |
| **SPIFFE / SPIRE** | Excellent and CNCF-graduated, but no lightweight profile exists — the server is not optional. Wrong shape for a git repo. |
| **`did:key` / `did:web`** | `did:key` adds vocabulary, not mechanism, over a raw keypair; the persona-binding problem remains identical. `did:web` needs a live HTTPS endpoint. Neither has a native git or GitHub surface. |
| **A2A Agent Cards** | Genuinely shipped and signed (JWS since v0.3), but solves **discovery**, not artifact provenance. Verifies the card, not the commit. |
| **Project NANDA / NANDA Index** | Prototype-stage; no stable public registry found to depend on. Structurally wrong regardless — an external index violates the source-of-truth invariant. |
| **OWASP Agent Name Service** | A finalized whitepaper (May 2025) plus community reference implementations; no production deployment found. Requires a CA and central registry Barony has resolved never to run. |

The whole "agent identity" product category targets *cross-organization discovery over a network* —
a different problem, requiring exactly the always-on registry the invariant forbids.

## 8. Consequences

**Good.** Attribution becomes provable offline and permanently. The audit's core claim gets a real
foundation. `from:` misattribution becomes detectable. It composes with, rather than competing
against, the per-persona-credential plan. Adoption cost is near zero for a project already using
git.

**Cost.** One human-approved PR per persona, forever. Signing must be configured repo-locally by
every adapter, which is a new failure surface — and per ADR-008's lesson, a token added to one
renderer and not the others fails silently, so `baron validate` must check enrollment the way it now
checks spec↔runtime drift. Agents that lose their key can no longer act until re-enrolled, which is
correct but will feel abrupt the first time.

**Neutral.** Historical unsigned commits stay unsigned. This is forward-only; do not rewrite history
to backfill signatures.

## 9. Open questions for the owner (blocking implementation)

1. **Is the one-time human-approved enrollment PR acceptable as the trust root?** It is the load-
   bearing manual step. If the answer is "no, it must be zero-touch," this design does not hold and
   the honest fallback is per-persona GitHub Apps — which trades a different manual step for it.
2. **Where do private keys live?** Proposal is `~/.barony/keys/`, outside the repo, never committed.
   Worktrees and CI runners need an answer: does a cloud runner get its own enrolled key, or does it
   only *verify* and never sign?
3. **Does this ship before, after, or alongside the per-persona GitHub App work?** §7 argues before,
   because it is orthogonal and cheap. That intersects the open identity-sequencing fork recorded in
   `AGENT-TASKS.md`, and this ADR does not presume to settle it.
4. **Scope: Barony's own repo first, or the emitted templates too?** Dogfooding argues this repo
   first (it is P3.1 "Barony governs Barony" in miniature). Adopter value argues the templates.
5. **Does `baron validate` gain an enrollment check now or later?** Consequences §8 argues it is
   required to avoid a silent-degradation class, which would make it part of the first cut rather
   than a follow-up.

## 10. Verification needed before build

Carried from the research's uncertainty register — none of these blocks the design, but each should
be confirmed against current tooling rather than trusted from this document:

- **The exact current `sigstore/gitsign` release** if the §7 comparison is ever revisited; the
  version cited in secondary sources was v0.13.0-era and was not verified directly.
- **Whether GitHub's REST API exposes the signing-key fingerprint** in a machine-readable field.
  The proposed CI check deliberately avoids depending on this by verifying locally with git
  (`%G?` / `%GS`), which is confirmed working — but a dashboard would want the API.
- **Rebase-merge behaviour** under "require signed commits" should be confirmed empirically on a
  scratch repo before the ruleset is recommended to adopters.

Full survey, scoring, and sources:
`projects/AgentBootstrapNasikoMix/research-agent-identity-lightweight.md` in the Iris vault.
