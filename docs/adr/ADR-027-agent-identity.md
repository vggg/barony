---
created: 2026-08-14
type: decision
status: accepted
accepted: 2026-08-14
adr: 027
project: barony
authors: Dev (promoting the 2026-08-04 spike for Vikram)
decided_by: Vikram
supersedes:
  - "ADR-026 §6 Q4 (the `identity via the deferred per-persona signing keys` pointer)"
related:
  - "[[docs/adr/ADR-004-baron-guard-enforcement]]"
  - "[[docs/adr/ADR-007-session-boundary]]"
  - "[[docs/adr/ADR-010-baron-notify-wake]]"
  - "[[docs/adr/ADR-026-persona-sidecar]]"
  - "[[projects/AgentBootstrapNasikoMix/research-agent-identity-lightweight]]"
---

# ADR-027 (ACCEPTED): agent identity — per-persona SSH signing keys enrolled in the repo

> **ACCEPTED 2026-08-14 (Vikram).** This ADR does not derive a design; it **promotes the
> verdict of the 2026-08-04 options survey** *Lightweight verifiable agent identity at spawn*
> (vault: `projects/AgentBootstrapNasikoMix/research-agent-identity-lightweight.md`) into a
> decision of record, and implements its §4. The survey compared fourteen options against five
> criteria; §1 of it is the verdict, §4 the implementation plan, §5 the do-not-build list.
> Where this ADR and the spike disagree, the spike wins and this file is the bug.

> **SUPERSEDES [ADR-026](ADR-026-persona-sidecar.md) §6 Q4.** That ADR answered "how does a
> sidecar get its per-persona identity?" with *"via the deferred per-persona signing keys"* —
> a forward pointer to something nobody had specified. The keys are no longer deferred and no
> longer unspecified: they are the mechanism below. ADR-026 §6 Q4 carries an inline note
> pointing here (house convention: a supersession is stated in both directions).

## 1. Problem

On **2026-08-04** an un-onboarded Codex agent committed to `vggg/barony` `main` **under the
owner's git identity**. From the repo alone the commit is unattributable — it reads as Vikram.
That is the concrete failure, and it generalises into two classes:

1. **The anonymous-artifact class.** Any process with a checkout can produce a commit, handoff
   or finding that is indistinguishable from the owner's, because git author fields are
   self-asserted strings.
2. **The misattribution class.** A `from: Iris` line in a handoff, or an `agent-dev` label on a
   PR, is likewise a claim with nothing behind it. A persona can wear another persona's name by
   typing it — including by accident, which is the common case in a fleet.

Barony's whole product thesis is *audit by diff*: the repo is the record. An unattributable
record is not a record. And the standing constraint is invariant #1 — **the repo is the only
source of truth; any hosted surface is a cache, rebuildable from `git clone`** — which rules
out an identity design that needs a server to be believed.

## 2. Decision

**Per-persona SSH signing keys, generated at spawn, enrolled once into an in-repo
`.barony/allowed_signers` file (CODEOWNERS-owned), verified offline with `git verify-commit`.**

Four load-bearing properties, all from the spike §1 / §3.1:

- **Agents keep pushing under the owner's GitHub identity.** Per-persona attribution comes from
  the **signing key**, not from a separate account, app, or token. GitHub places **no limit on
  the number of signing keys per account** and records *which key* signed each commit, which is
  the fact that dissolves "every persona shares one GitHub account" **without** provisioning
  machine accounts. No forge credential is introduced anywhere by this ADR.
- **The registry is a file in the repo.** `.barony/allowed_signers` is OpenSSH
  `authorized_keys` format — principal, then public key. It travels with the clone, so a
  stranger six months from now can verify every commit with nothing but `git clone` and no
  network. Invariant #1 holds by construction.
- **Enrollment is a one-time human gate, and that is the trust root.** An agent that mints a key
  and adds itself to the allowlist has proved nothing — self-assertion in a crypto costume.
  `baron identity init` therefore emits an **enrollment request** (a PR-ready change), never an
  enrollment, and CODEOWNERS makes `.barony/` owner-only so the agent cannot self-merge it.
- **Identity precedes work.** `baron identity init` exits non-zero until the key is present in
  `allowed_signers` **at HEAD**. A spawn hook treats non-zero as fatal.

### 2.1 The three-way cross-check — why this also closes misattribution

`baron verify identity` runs over a PR's commit range and, per commit, asserts:

```
git verify-commit <sha>                     # signature verifies against allowed_signers
%G?  == G                                   # trust status good (not B/U/N/E)
%GS  == <principal>                         # the principal the signature resolves to
```

and then the part that matters:

**signature principal ↔ persona claimed (routing label / commit trailer) ↔ `persona.yaml`
registry entry** — all three must name the same persona. A commit signed by a *genuinely
enrolled* key but *labelled* as another persona fails. That is the `from: Iris` class, closed
by the same gate that closes the anonymous class, at no extra cost.

### 2.2 The three-layer gate

In increasing order of "cannot be bypassed" (spike §4.3):

| Layer | What it is | Honest strength |
|---|---|---|
| **(a) Local pre-commit hook** | refuses to commit when `user.signingKey` is unset or unenrolled | fast feedback; **trivially bypassable**; catches honest misconfiguration, is not a control |
| **(b) `baron verify identity` in CI** | the commit-range check above, fail-closed | **the real gate** — make it a *required status check* so it cannot be merged around |
| **(c) GitHub ruleset on `main`** | require a PR, require the check, **require signed commits** | platform backstop; has a known gap — *rebase-merge* adds head-branch commits to the base **without** signature verification, so use squash or merge commits |

### 2.3 Handoffs and findings

Same key, detached signatures: `ssh-keygen -Y sign -n barony-handoff` writes `<file>.sig` beside
the artifact; `ssh-keygen -Y verify` checks it against the same `allowed_signers`. A handoff's
`from:` stops being a bare self-assertion. The librarian's ingest path (`baron handoff verify`,
and `baron handoff close`, which is where a librarian discharges a handoff) **refuses an
unverifiable handoff and logs it as a finding** rather than dropping it silently — an
attribution failure becomes evidence, which is what the audit product needs.

## 3. Honest bounds (stated here, and in the command output)

Carried verbatim in spirit from spike §3.1/§4.1/§5.6, in the same voice as `baron guard`:

- **This establishes attribution among *cooperating* agents. It does not defend against a
  hostile actor with write access to an agent's workspace.** The private key sits unencrypted
  in that workspace; whoever holds it is that persona. Overclaiming here is the fastest way to
  lose the credibility the audit product depends on.
- **Enrollment is trust-on-first-use, gated once by a human.** What signing buys is not "this
  agent is trustworthy" — it is *"this artifact was produced by the key enrolled as Carson, and
  nobody else, and you can prove it from a clone."*
- **The Verified badge still reads "Vikram Godbole"** — it names the *account*. Per-persona
  attribution comes from the **key**, which is why the CI check (which reads the key) matters
  more than the badge (which reads the account).
- **Nothing here is an authorization mechanism.** It answers *who produced this artifact*, not
  *may this actor push*. The ADR-010 §5.5 wake gate remains **detection, not authentication**,
  unchanged.
- **Rotation is manual and deliberately dumb**: generate a new key, PR it into
  `allowed_signers`, keep the old line so historical commits still verify, annotated with a
  retirement date. That is the entire lifecycle.

## 4. What we explicitly do NOT build (spike §5, adopted verbatim as policy)

Barony's standing discipline for identity and crypto is **"integrate, do not author."**

1. **No Barony CA, key server, or PKI.** No certificate issuance, no revocation service, no
   trust-root ceremony. If real PKI is ever needed, integrate Sigstore or the platform's.
2. **No hosted Barony agent registry or identity API.** The registry is
   `.barony/allowed_signers` in the repo. The moment identity needs a network call, invariant #1
   is broken and `cat` stops being sufficient.
3. **No custom signature format or crypto envelope.** `git`'s SSH signing and `ssh-keygen -Y
   sign/verify`, verbatim. No bespoke JSON signature scheme, no hand-rolled canonicalization.
4. **No key escrow, rotation automation, or secret management.** See §3's rotation note. No vault.
5. **No DID method, resolver, or `did:barony`.** Zero value over a raw public key here.
6. **Nothing that claims to defend against a hostile actor.** See §3.
7. **No NANDA / ANS / A2A integration on speculation.** Revisit only if Barony agents must be
   discovered by agents *outside* the repo — and even then as an *export*, never a source of truth.

To which this ADR adds the one the earlier attempt got wrong:

8. **No per-persona machine accounts, GitHub Apps, or PATs as the attribution mechanism.** The
   spike surveyed both and rejected them for *this* problem: §3.4 (Apps/bot accounts) is a
   separate, heavyweight **authorization** question requiring per-persona human provisioning and
   not verifiable from a clone; §3.5 (fine-grained PATs) attributes to the *account*, not the
   persona, so it does not attribute at all. They may still be the right answer to
   *authorization*, later, on their own merits — they are not the answer here.

## 5. Alternatives considered (see the spike for the full fourteen-row table)

- **`gitsign` / Sigstore keyless — runner-up, and the natural later upgrade.** Cryptographically
  stronger (ephemeral certs, transparency log, nothing to enroll), but its identity *is* the
  OIDC subject: with one shared account every persona signs as `vggg` and per-persona
  attribution is exactly as absent as today. It **composes with** per-persona platform
  credentials; it does not substitute for them. GitHub also renders sigstore commits
  *Unverified*, which is in tension with a require-signed-commits ruleset.
- **GPG signing.** Works; worse than SSH on every axis that matters for a non-interactive agent
  (keyring state, passphrases, expiry, revocation ceremony).
- **SPIFFE/SPIRE.** Excellent attestation, wrong deployment shape: an always-on control plane
  (server + per-node agent + registration entries) is a direct violation of invariant #1.
- **`did:key` / `did:web`, A2A Agent Cards, NANDA, OWASP ANS, agent-IAM SaaS.** Either a
  vocabulary over the same raw key with no git surface, or built for *cross-organization
  discovery over a network* — a different problem needing the registry the invariant forbids.
  Maturity varies from "shipped but orthogonal" to "whitepaper".

## 6. What this would have done to the 2026-08-04 incident

The Codex commit would have been **unsigned** → rejected by the ruleset before landing on
`main`, and by CI had it arrived via PR. Signed with a self-minted key → not in
`allowed_signers` → `git verify-commit` fails → CI red. Enrolled properly → its work carries
`carson@barony` in `%GS`, is attributable forever from a bare clone, and a `persona.yaml` for it
must exist. Every row of that reconciliation is covered except ID allocation, which is a
separate mechanism.

## 7. Residual owner-decision points (NOT self-decided)

The direction is endorsed; these remain Vikram's calls and are deliberately left open:

1. **Key location.** Default is `~/.barony/keys/<slug>.key` (outside the repo, so a key is never
   committed by accident), overridable with `$BARON_KEY_DIR`. A fleet running personas in
   containers may want a mounted path instead — a manifest field, if so.
2. **Whether enrollment may ever be delegated** to an already-trusted persona (e.g. the
   librarian) rather than the human. The spike allows it ("a human *or an already-trusted
   persona*"); this implementation deliberately ships **human-only**, because a persona that can
   enroll can mint peers.
3. **`require_signed_handoffs`.** Shipped **off** by default: a missing `.sig` warns, a *present
   but invalid* `.sig` refuses. Turning the missing case into a refusal is a fleet-wide breaking
   change and should be signed, not defaulted (the ADR-013 §7.1 precedent: a default nobody
   signed and a default somebody signed look identical in a diff).
4. **Whether `baron guard` should refuse to run at all when the persona is unenrolled.** Today
   the refusal lives in `baron identity init` (spawn time). Extending it to every guarded tool
   call is a stronger posture and a louder failure mode.
5. **The platform steps in `docs/runbooks/identity-signing.md` are owner actions** — registering
   keys, the `main` ruleset, the merge strategy, CODEOWNERS. Nothing in this ADR works until
   they are done, and no agent can do them.

## 8. Evidence / relation

The trigger is first-party (the 2026-08-04 incident and its reconciliation note). The mechanism
is entirely off-the-shelf: SSH commit signing has been in git since **2.34** (Nov 2021) and
GitHub has verified it since **2022-08-23**; verified locally against git 2.50.1, where
`git log --format='%G? %GS %GK %GF'` yields status, principal, key and fingerprint per commit.
It composes with ADR-026 (the sidecar is *where* `baron identity init` runs), ADR-010 (the wake
gate stays detection), and ADR-004 (the same honest-bound voice as `baron guard`).
