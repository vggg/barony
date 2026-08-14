---
created: 2026-08-14
type: decision
status: accepted
accepted: 2026-08-14
adr: 027
project: barony
authors: Claude (design proposal for Vikram)
decided_by: Vikram
related:
  - "[[docs/adr/ADR-007-session-boundary]]"
  - "[[docs/adr/ADR-010-baron-notify-wake]]"
  - "[[docs/adr/ADR-026-persona-sidecar]]"
  - "[[docs/adr/ADR-002-ways-of-working-2026-07]]"
---

# ADR-027 (ACCEPTED): agent identity — per-persona forge credentials via named indirection

| Field | Value |
|---|---|
| **Status** | Accepted (2026-08-14) — owner gave go to proceed on the recommendation |
| **Authors** | Claude (design proposal for Vikram) |
| **Decision owner** | Vikram |
| **Answers** | [ADR-026](ADR-026-persona-sidecar.md) §6 Q4 (how a sidecar gets its per-persona identity + runtime credential) |
| **Constrained by** | [ADR-007](ADR-007-session-boundary.md) — baron owns governed identity *resolution*, not the agent loop, and not credential *issuance* |
| **Unblocks** | the autonomous merge-only agent; the self-driving dev loop; the ADR-010 §5.5 wake gate becoming authentication rather than detection |

## 1. The problem — git identity is solved, forge identity is not

Every persona already commits under its own git author (`identity.git_name` /
`identity.git_email`, conventionally `<slug>@<project>.local`). That half works, and
`git log` reads as a team.

Everything at the **forge layer** does not. A fleet runs under a single ambient `gh`
credential — the human owner's — so:

- the PR was opened by `vggg`, not by `dev`;
- the review verdict was posted by `vggg`, not by `reviewer`;
- **the merge was performed by `vggg`**, not by `merger`;
- `repository_dispatch` was fired by `vggg`, not by whoever `--from` claimed.

Two concrete consequences, both hit live in Stage 2 of the dogfood:

1. **An autonomous merger is untrustworthy.** It merges *with the owner's authority* and
   is, on the forge, indistinguishable from the owner. There is no audit line that
   separates "the human decided to merge this" from "a cron job did". Branch protection
   cannot tell them apart either, so the one control that would bound an autonomous
   merger — "only the merger account may merge" — is unexpressible.
2. **Per-actor attribution is destroyed for the whole pipeline.** ADR-010 §5.5 already
   states this plainly and works around it: the wake gate cannot use `github.actor`
   "under the single-account constraint (ADR-002 §1) every persona is the same GitHub
   account", so it falls back to reading committed frontmatter, which that ADR is careful
   to call **detection and audit, not authentication**. That honesty is a symptom of this
   gap, not a fix for it.

So: git-commit identity is solved. **Forge identity is the gap**, and it is the
critical-path dependency for anything autonomous that acts on the forge.

## 2. Options evaluated

| # | Option | Real attribution? | Revocable / least-privilege | Setup cost | Verdict |
|---|---|---|---|---|---|
| A | **Per-persona GitHub accounts + PATs** (one machine account per persona) | **Yes** — `github.actor` genuinely differs; branch protection can name the merger | Yes, per fine-grained PAT | N machine accounts; ToS considerations; N logins to keep alive | **Recommended default** |
| B | **GitHub App / per-persona bot identity** | **Yes** — real `…[bot]` attribution | **Best** — fine-grained scopes, installation-scoped, short-lived tokens, revoke at the install | App registration + private-key custody + JWT→installation-token exchange | **Production-grade target** |
| C | **Fine-grained PATs scoped per persona under ONE account** | **No** — every token still resolves to the one account | Yes (scopes), no (identity) | Lowest | **Rejected as a solution to *this* problem** |
| D | **Per-persona GPG signing keys (git layer) + one of the above (forge layer)** | Git layer only | Key custody cost | High | **Deferred (again), see §6** |

**Option C is the trap.** It looks like the cheap answer and is the one most likely to be
reached for, but scoping tokens under a single account narrows *what* a persona may do
while leaving *who did it* unchanged — and "who did it" is the entire problem statement.
It is worth having as a **capability** control alongside A or B; it is not an identity
control. Recording this explicitly so it is not re-proposed.

**Option D is orthogonal, not alternative.** Signing proves key custody, which is a
different claim from forge attribution, and it does nothing for "who merged". ADR-026 §6
Q4 pointed at the deferred signing keys as the identity answer; that pointer is
**superseded here** — the answer is the forge credential, and signing stays deferred on
its own merits (§6).

## 3. Decision

### 3.1 Recommended posture (owner-facing)

**Per-persona machine account + fine-grained PAT (option A) as the shipped default; a
GitHub App (option B) as the production-grade target.**

Rationale, in order of weight:

1. **A is the cheapest thing that actually solves the stated problem.** It is the
   low-friction path to a genuinely different `github.actor` per persona, which is what
   makes an autonomous merger bounded: with a `merger` account, branch protection can
   require that merges come from it, and the owner's own account can be *removed* from
   the set of things that merge unattended.
2. **B is strictly better and strictly more setup.** Short-lived installation tokens,
   revocation at the installation, no password/2FA lifecycle per persona, and `[bot]`
   attribution that reads correctly to a human. It is the right end state; it is not the
   right first step while the fleet is one owner on one machine.
3. **The choice is reversible at zero code cost — and that is the load-bearing design
   property**, not a nicety. See §3.2: baron never learns which of the two it is holding.

**Honest costs the owner should weigh (not settled by this ADR):** N machine accounts
must be created, secured and kept alive; GitHub's terms permit machine accounts but the
current wording is the owner's to confirm before scaling past a couple, and they must not
be used to work around per-account limits; N PATs expire and must be rotated. B trades
all of that for one App registration plus private-key custody. Both are **owner actions**
— see §5.

### 3.2 What baron builds — named indirection, and nothing else

**Baron consumes credentials by NAME. It never issues, stores, prints, logs, serializes
or commits a credential value.** The persona spec references an *environment variable
name*; the value exists only in the process environment of the acting cycle.

```yaml
# agents/<slug>/persona.yaml
identity:
  git_name: Rex
  git_email: rex@myproject.local
  commit_prefix: "rex:"
  routing_label: agent-rex
  forge:                                   # NEW (v1.3 of persona.schema.md) — optional
    provider: github                       # default: github
    login: myproject-rex                   # the forge handle — attribution, NOT a secret
    token_env: BARON_FORGE_TOKEN_REX       # optional; default derived from slug
    required: false                        # true = a cycle refuses to run unresolved
```

- `login` is the **public** account/app handle. It is attribution data, belongs in git,
  and is what makes a `baron` report legible ("merger acts as `myproject-merger`").
- `token_env` **names** the variable. Default: `BARON_FORGE_TOKEN_<SLUG>` with the slug
  upper-cased and non-alphanumerics folded to `_`. Nothing in the repo ever holds a value.
- Whether that variable holds a machine-account PAT (option A) or a GitHub App
  installation token (option B) is **invisible to baron** — which is exactly why §3.1's
  recommendation is reversible: moving A→B changes what the owner exports, not one line of
  baron.

**Resolution at cycle start.** When a persona acts, baron resolves its identity once and
applies it for the whole cycle, so *every* git and forge call the cycle makes — baron's
own, and the runtime's — carries the same actor:

| Layer | Mechanism |
|---|---|
| git authorship | `GIT_AUTHOR_NAME/EMAIL` + `GIT_COMMITTER_NAME/EMAIL` from `identity.git_*` |
| `gh` / forge API | `GH_TOKEN` + `GITHUB_TOKEN` from the named variable |
| git push over HTTPS | a per-invocation `credential.helper` that reads the **same variable by name** — the value never reaches `argv`, a config file, or the disk |

### 3.3 Degrade, and say so — with a fail-closed opt-in

An **absent** variable does not crash. Baron applies no overlay, the cycle proceeds under
ambient credentials (today's behaviour), and the report says so by name:

```
forge identity: UNRESOLVED (BARON_FORGE_TOKEN_MERGER unset) — acting under ambient
                gh credentials, so forge actions will attribute to whoever is logged in
```

This keeps every existing project working unchanged. But "quietly acts as the owner" is
precisely the failure this ADR exists to end, so the strong posture is one field away:
`identity.forge.required: true` (or `--require-identity`, or `BARON_REQUIRE_IDENTITY=1`)
turns an unresolved credential into a **refusal to run the cycle**. The merger is the
archetype that should set it.

*Why not fail closed by default:* it would break every project on upgrade for a
credential the owner has not been asked for yet, and would make baron's first act after
this ADR a broken fleet. Default off, documented, and set to `true` in the provisioning
runbook for the personas that matter.

### 3.4 `baron validate` gates the CONFIG, not the environment

A persona whose `capabilities.allow` contains a forge verb — `open_pr`, `merge_pr`,
`push_main`, `force_push` — and which declares **no `identity.forge` block** is a
**warning**, promoted to an **error** by `baron validate --require-identity` or by
`manifest.identity.require_forge: true`.

*Severity is deliberate, and an earlier draft of this ADR got it wrong.* Erroring by
default reads as the principled choice, but "no `identity.forge`" describes **every
project that predates this ADR** — the drafted error broke 101 of baron's own tests on
the first run, which is a faithful preview of what it would do to a user's fleet on
upgrade. That directly contradicts §3.3's posture, so it is a warning until the owner
declares provisioning done. A project that has finished provisioning sets
`require_forge: true` **once, in the substrate**, rather than depending on every caller
remembering a flag.

A **declared** block that omits `login` is an error unconditionally: that is a malformed
declaration rather than an un-migrated one, so no existing project can trip it.

Whether the variable is *set* is machine-local, so validate does **not** check it — the
same reasoning that keeps the runtime-drift check separately gated (`validate.py`
`runtime_drift`). Environment readiness is answered by `baron identity` (§3.5), which
reports presence as a boolean and never a value.

Two personas declaring the **same** `forge.login` is a **warning**: it is legal (a shared
bot across projects is a real configuration) but it silently collapses the attribution
this ADR buys, so it is worth saying out loud.

### 3.5 `baron identity` — the operator's surface

```
baron identity [--collab DIR] [--persona SLUG] [--json]
```

Per persona: git author, forge provider + login, the **variable name**, and whether it is
currently set. **Never the value, not even redacted-with-a-prefix** — a prefix is a value.
This is the command the runbook (§5) tells the owner to run to confirm provisioning.

## 4. The boundary (ADR-007), stated precisely

Baron **resolves governed identity**: it reads the declared mapping from the substrate,
turns it into process environment for one cycle, validates the declaration, and reports
what it found. That is coordination-layer work of exactly the kind ADR-007 §3 blessed —
deterministic bookkeeping around the loop.

Baron does **not**, and must not grow to:

- create accounts, apps or tokens;
- mint, exchange or refresh tokens (a GitHub App's JWT→installation-token exchange is the
  owner's tooling or the App's — if baron ever gains a token-minting path it has become a
  credential broker and crossed this line);
- store or cache credentials anywhere on disk;
- read a credential out of anything other than the process environment.

**Provisioning is an owner action, deliberately.** Baron builds the mechanism that
*consumes* per-persona credentials; §5 tells the owner what to create.

## 5. Owner runbook (summary — full version in `docs/runbooks/forge-identity.md`)

Per persona that touches the forge: create a machine account, invite it to the repos,
issue a fine-grained PAT with the **narrowest scopes that persona's capability set
justifies**, export it as `BARON_FORGE_TOKEN_<SLUG>`, and record the handle as
`identity.forge.login`. Then `baron identity` should report every persona resolved.

The step that turns attribution into **enforcement** — and the reason to do this at all —
is branch protection: once `merger` is a distinct account, require merges to come from it
and drop the owner's unattended merge path.

## 6. What this ADR deliberately does NOT do

- **Per-persona GPG/SSH signing keys stay deferred** (ADR-026 §6 Q4's original pointer is
  superseded, not adopted). Signing proves key custody; it does not answer "who merged",
  and every persona currently runs on one machine under one operator, so the marginal
  attribution gain over §3.2 is small against real key-custody cost. Revisit when
  personas run on separate hosts, or when a downstream consumer requires verified commits.
- **No credential storage, no secret manager integration, no `baron secrets`.** The
  process environment is the interface. A project that wants 1Password/Vault/`gh secret`
  populates the environment from it — which is a launcher concern, and the emitted
  `sidecar.sh` is the launcher.
- **No new capability verb.** The frozen v1 10-verb vocabulary is untouched (ADR-007:
  commands are not permissions). Identity says *who acts*; capabilities say *what may be
  done*. They compose; neither subsumes the other.
- **No change to the ADR-010 §5.5 wake gate** in this ADR. Distinct forge accounts make
  `github.actor` meaningful for the first time, so the gate *could* become genuine
  authentication — but that is a change to the emitted workflow with its own failure
  modes, and it should land against a fleet that actually has provisioned accounts.
  Recorded here as the follow-on it unblocks, not smuggled in.

## 7. Consequences

- An autonomous merger becomes bounded rather than owner-equivalent: it acts as
  `<project>-merger`, and branch protection can say so.
- Per-actor attribution is real end-to-end — PR author, verdict author, merger, dispatcher.
- The fleet gains a provisioning prerequisite it did not have. `baron identity` exists so
  that prerequisite is checkable in one command rather than discovered at 3am.
- Existing projects are unaffected until they opt in: absent config, absent variables,
  unchanged behaviour, one honest line in the report.

## 8. Decision record

- [x] Approved to proceed on the §3.1 recommendation (owner, 2026-08-14)
