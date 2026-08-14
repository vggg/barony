---
created: 2026-08-14
type: decision
status: accepted
accepted: 2026-08-14
adr: 033
project: barony
authors: Dev (design + implementation for Vikram)
decided_by: Vikram
supersedes:
  - "ADR-028 §7 Q4 (`how does a verdict become attributable at all?` — answered here, route 2)"
related:
  - "[[docs/adr/ADR-002-ways-of-working-2026-07]]"
  - "[[docs/adr/ADR-008-ways-of-working-2026-07-31]]"
  - "[[docs/adr/ADR-027-agent-identity]]"
  - "[[docs/adr/ADR-028-mechanized-merge-gate]]"
  - "[[projects/AgentBootstrapNasikoMix/research-identity-attestation]]"
---

# ADR-033 (ACCEPTED): signed review verdicts — the merge gate proves WHO approved

> **SUPERSEDES [ADR-028](ADR-028-mechanized-merge-gate.md) §7 Q4.** That question —
> *"How does a verdict become attributable at all?"* — named two candidate routes,
> designed neither, and closed with the line *"this is the real blocker on an autonomous
> merger, and it is nobody's open item until it is somebody's."* It is now somebody's.
> This ADR takes **route 2** (a signed verdict artifact in-repo), which §7 Q4 itself
> called the option that *"composes with what Barony actually built and keeps the record
> in git, which is the standing preference"*. ADR-028 §7 Q4 carries the reciprocal
> forward-note (house convention: a supersession is stated in both directions).

## 1. Problem

ADR-028 §4 stated the hole in its own words, and this ADR does not improve on the
phrasing:

> baron can verify that a `REVIEW:PASS` exists at the current head. It **cannot verify
> who posted it.** The dev whose code is under review can post its own `REVIEW:PASS`,
> and the gate — correctly, given its inputs — returns exit 0.

Two facts make it structural rather than an oversight:

1. **A verdict is a PR comment** — *forge* state, not repo state. It carries no
   signature, and nothing in git records it.
2. **Every persona shares one forge login** (ADR-002 §1). So even the forge's own author
   field attributes to `vggg`, for the reviewer and the dev alike.

And ADR-027 does not reach it, which ADR-028 §4 was corrected at integration to say
plainly: ADR-027 attributes **commits, tags, handoffs and findings** — artifacts that
live in git and can carry a signature. It makes the *code* under review attributable and
leaves the *verdict on* that code exactly as self-asserted as before.

This matters more than a missing feature. Barony's wedge is **separation of duties among
agents**: the Reviewer reviews in a fresh context, the Merger is a gate and not a button,
and an author does not approve its own work. Every one of those is currently a claim in a
persona file. FM4 is the standing counter-evidence for what a claim in a persona file is
worth — a dev merged ~15 PRs with `merge_pr` *denied in its own config*. A separation of
duties that cannot be checked from the repo is a separation of duties that has not been
established.

## 2. Decision

**The reviewer SSH-signs its verdict into the repo, and `baron merge check` verifies
that signature offline — requiring a reviewer-capable signer distinct from the persona
that signed the head commit.**

```
.barony/verdicts/pr-<n>-<sha12>.md        the verdict — canonical bytes
.barony/verdicts/pr-<n>-<sha12>.md.sig    ssh-keygen -Y sign, namespace barony-verdict
```

verified with `ssh-keygen -Y verify` against the **same** `.barony/allowed_signers` that
already backs commits and handoffs. Nothing new is trusted, no new mechanism is authored
(ADR-027 §4.3: no bespoke envelope), and no network is involved — a stranger with a bare
clone can establish who approved any commit, which is invariant #1 holding by
construction.

The artifact's first line is the **existing** contract, `REVIEW:PASS <40-hex>` (ADR-002
§4, ADR-008 §1). One format is parsed everywhere; the reviewer template did not have to
learn a second one.

### 2.1 The four legs, and why each exists

`baron review verify` (and the gate's `verdict_signed` precondition) asserts all four:

| # | Leg | The attack or accident it closes |
|---|---|---|
| 1 | **The signature verifies** against the in-repo allowlist | a bare claim, or a self-minted key — "attribution in a crypto costume" |
| 2 | **The signed content binds (repo, PR, sha)** | **replay.** A genuine `REVIEW:PASS` signed for one PR, copied onto another. The signature stays perfectly valid; only the file moved |
| 3 | **The signer is a `reviewer`-archetype persona** | a **dev's key is a real enrolled key.** Without this leg it produces a real verified verdict. Enrolment says *who*; the persona registry says *what they are for* |
| 4 | **The signer is not the author** — the persona whose signature is on the head commit (`%GS`) | **self-review**, mechanically |

Two of these deserve the emphasis:

**Leg 2 re-derives the binding from the signed CONTENT, never the filename.** A filename
is not covered by a signature. Trusting `pr-7-abc.md` to mean "PR 7" would make the
entire binding forgeable with `cp`.

**Leg 4 is the one that makes reviewer≠author a property of the repo.** The author is
established *cryptographically* — the head commit's own signature principal under
ADR-027 — and deliberately **not** the git author field, which is a self-asserted string
and whose trustworthiness is precisely what the 2026-08-04 incident disproved (ADR-027
§1). An author baron cannot resolve is `verdict_author_unresolved`: fail-closed, because
an author that cannot be named is not an author that differs.

### 2.2 Posture — the ADR-027 §7.3 precedent, applied unchanged

- **A signature that is PRESENT and does not verify ALWAYS refuses**, in every posture
  and for every failure mode: bad signature, unenrolled signer, non-reviewer archetype,
  reviewer-is-author, replayed binding. Broken evidence is worse than no evidence.
- **A MISSING signed verdict warns by default and refuses under
  `--require-signed-verdict`.** Turning absence into a refusal is a fleet-wide breaking
  change — every project still on the comment path would stop merging on upgrade. That is
  a change somebody should sign, not one that arrives as a default. ADR-013 §7.1 is the
  standing precedent, in the same words: *a default nobody signed and a default somebody
  signed look identical in a diff.*
- **An unattested pass does not render as a clean pass.** It reports `UNATTRIBUTED` in
  the precondition's own detail line and in the command's closing note. A known gap that
  renders as an absence is a gap a reader rounds down to "fine" — the same argument
  ADR-028 §2.2 made for recording unreachable preconditions as FAILED rather than
  skipped.

### 2.3 The comment is demoted to an index

This is a **contract change**, and it is the same move ADR-008 §1 made for labels.
Before: the comment was the record. After: the *signed artifact* is the record, and the
comment is a human-readable index of it. `baron review sign` prints the comment text to
post, because humans read PRs — but only the artifact attributes, and the two
preconditions are scored separately (`verdict_at_head` reads the comment;
`verdict_signed` reads the artifact) so a refusal always names which surface failed.

## 3. Honest bounds

Stated here and carried in the command output, in the same voice as `baron guard` and
ADR-027 §3:

- **This establishes attribution among *cooperating* agents. It does not defend against
  a hostile workspace.** The reviewer's private key sits unencrypted in its workspace;
  whoever holds it is that reviewer and can sign anything. What ADR-033 buys is narrower
  and real: a verdict now has an author nameable from a clone, a persona cannot sign as
  another persona, and the specific accident this fleet actually produces — a dev
  approving its own work under one shared login — becomes impossible rather than
  discouraged. The distance between that sentence and *"the merge is now safe"* is where
  this project's credibility lives.
- **It does not make a verdict correct.** A reviewer-capable persona can sign a careless
  PASS. This gate answers *who judged*, never *how well* — reviewer quality is ADR-024's
  escape-rate axis and a different measurement entirely.
- **It is not authorization.** Same boundary ADR-027 §3 draws: it answers *who produced
  this attestation*, not *may this actor merge*. There is still no `baron merge do`
  (ADR-007), and §5 says why that has not changed.
- **An unpushed verdict attests nothing to anyone else.** The artifact must be committed
  and pushed; `baron review sign` says so on every run.
- **Enrollment remains the trust root**, human-gated, exactly as ADR-027 §2 left it.
  ADR-033 adds no new trust root and no new key.

## 4. What this does NOT build

Inherits ADR-027 §4 verbatim — no CA, no key server, no hosted registry, no custom
signature format, no escrow, no DID method, no per-persona machine accounts. Plus one:

9. **No verdict transparency log, and no countersigning.** A second signature over the
   merge decision, or an append-only log of all verdicts, would be the natural next
   escalation. Both are refused here: the git history of `.barony/verdicts/` **is** the
   append-only log, and the merger's own decision is already recorded by the commit it
   signs. Adding a second mechanism to attest the same fact is where "integrate, do not
   author" stops holding.

## 5. Does this unblock the autonomous merger? No — and the reason is worth stating

It closes the **evidence** half. The merger can now prove, offline, that a distinct
reviewer-capable persona approved this exact commit. That was the blocker ADR-028 §7 Q4
named.

It does not close the **authority** half. Performing the merge still means acting under
the owner's forge token — the ambient-authority problem ADR-028 §5 rejected `baron merge
do` over, and which ADR-027 §4.8 left live as a separate question on its own merits.
`baron merge check` therefore stays owner-in-the-loop, and this ADR does not touch that.

Recording the split matters because the temptation at exactly this moment is to read a
green attribution check as permission. It is evidence, and the two are different.

`--verdict-author <login>` (ADR-028 §4) is now the weaker of two overlapping mechanisms:
it filters on a forge *login*, which is uniform under the single-account constraint, and
it stays shipped for the day per-persona forge identity exists. The signed verdict
attributes to a **persona**, which is the thing that actually differs.

## 6. Alternatives considered

**Route 1 of ADR-028 §7 Q4 — per-persona forge identity** (machine accounts, GitHub
Apps, distinct review-API logins). Would attribute the comment itself, and would fix the
single-account gap generally. Rejected *for this problem* on the same grounds ADR-027
§4.8 rejected it for commits: it is a heavyweight **authorization** change requiring
per-persona human provisioning, it is not verifiable from a clone (breaking invariant
#1), and it is not needed to establish who reviewed. It remains a live question on its
own merits.

**Signature embedded in the PR comment.** Keeps one surface and needs no repo write —
and an armored SSHSIG block in a comment is not a custom format, so ADR-027 §4.3 would
not forbid it. Rejected because the record would live on the forge, which invariant #1
makes a cache: a `git clone` would no longer be sufficient to audit who approved what,
which is the property the whole product rests on.

**A verdict trailer in the merge commit.** Attributes the merger, not the reviewer, and
only *after* the merge — too late to gate on.

**Keeping the comment and adding `--verdict-author`.** The status quo. It filters logins,
and under one account every login matches. ADR-028 §4 already called it *"useless under
the single-account constraint"*.

**Requiring signed verdicts by default.** Rejected per §2.2; correct destination, wrong
way to arrive. Revisit as an owner decision once the fleet is enrolled.

## 7. Open questions for the owner

1. **Should `--require-signed-verdict` become the default**, and on what trigger — a
   manifest field, a fleet-wide flag day, or `baron doctor` reporting readiness? §2.2
   ships it off; the destination is on.
2. **Should the reviewer's `persona.yaml` need an explicit capability** rather than
   `archetype: reviewer`? Archetype is the existing machine truth and needed no vocabulary
   change (the v1 verb list stays frozen), but a `sign_verdict` verb would be more precise
   and is a spec change.
3. **Should `baron merge check` refuse when the head commit is unsigned**, rather than
   reporting `verdict_author_unresolved` only when a signed verdict is present? That is
   the stronger posture and overlaps `baron verify identity` in CI.
4. **Where do verdicts live in a split collab/code topology?** They land in the collab
   repo today, keyed by code-repo PR number, and `--code-repo` points the author leg at
   the checkout holding the head commit. A monorepo (ADR-025) has no such split; a
   two-repo project needs both checkouts present to verify leg 4.

## 8. Supersedes / Prior art

The sweep this ADR is required to record under [ADR-029](ADR-029-prior-art-gate.md), and
unlike ADR-027's and ADR-028's it was performed **before** drafting rather than
retrospectively — which is the shape ADR-029 §4 actually asks for.

It changed the framing twice. The vault's `research-identity-attestation` note turned out
to have named this exact use case as a target — *"provable separation of duties"* — and
to have proposed extending the **`signet`** sub-brand (SHA-sealed *verdicts*) to sealed
*authorship*, which is precisely what §2 does; §2.3's "the comment is an index" is the
inverse framing of that same idea, and this ADR cites it rather than re-deriving it. And
ADR-028 §7 Q4 turned out not merely to be *related* but to have **already chosen the
route**, which moved this ADR's relationship to it from `cites` to `supersedes`.

<!-- BEGIN BARON PRIOR-ART -->
searched:
  - corpus: repo-adr
    location: docs/adr
    query: "signed verdict, review verdict, reviewer identity, separation of duties, self-review, reviewer not author, attestation"
    date: 2026-08-14
  - corpus: repo-decisions
    location: STATUS.md, AGENT-TASKS.md, CHANGELOG.md, open PRs on vggg/barony
    query: "verdict signing, reviewer attribution, merge gate identity, ADR-028 Q4"
    date: 2026-08-14
  - corpus: vault
    location: /Users/vikram/Obsidian/Brain
    query: "review verdict, signed handoff, persona identity self-asserted, signet, separation of duties, declared vs verified"
    date: 2026-08-14
hits:
  - ref: docs/adr/ADR-028-mechanized-merge-gate.md
    disposition: supersedes
    note: >-
      §7 Q4 asked "how does a verdict become attributable at all?", named two routes,
      designed neither, and closed "it is nobody's open item until it is somebody's".
      This ADR takes route 2 — the in-repo signed artifact §7 Q4 itself preferred —
      so it supersedes that question rather than merely citing it. §4's honest bound
      (baron cannot verify WHO posted a verdict) is narrowed, not withdrawn: it still
      holds for the comment surface, which §2.3 demotes to an index. ADR-028 §4 and
      §7 Q4 carry the reciprocal forward-notes.
  - ref: docs/adr/ADR-027-agent-identity.md
    disposition: cites
    note: >-
      the entire mechanism. §2.3's detached-signature scheme, the same
      .barony/allowed_signers registry, the same enrolment trust root, the same
      %GS-based principal resolution, §4's do-not-build list inherited verbatim, and
      §3's honest bound restated rather than re-argued. This ADR adds no new key, no
      new registry and no new trust root.
  - ref: projects/AgentBootstrapNasikoMix/research-identity-attestation.md
    disposition: cites
    note: >-
      "Research (later) — persona identity is self-asserted, not verified". Named the
      review verdict in its declared-vs-verified family, named "provable separation of
      duties" as the stake that justifies verification, and proposed extending the
      `signet` sub-brand (SHA-sealed verdicts) to sealed AUTHORSHIP — which is what §2
      builds. Its honest floor ("does not defend against a determined impersonator")
      is §3's bound. Filed Phase-3/later; this is that work arriving.
  - ref: docs/adr/ADR-008-ways-of-working-2026-07-31.md
    disposition: cites
    note: >-
      §1's verdict-not-label demotion is the precedent §2.3 reuses one level up — the
      comment becomes to the signed artifact what the label already is to the comment.
      The REVIEW:PASS <sha> format is kept verbatim so one contract is parsed everywhere.
  - ref: docs/adr/ADR-002-ways-of-working-2026-07.md
    disposition: cites
    note: >-
      §4 specifies the Reviewer and the Merger, including reviewer-reviews-in-fresh-context
      and the comment-as-verdict-surface rule that §1 explains was forced by the
      single-account constraint. This mechanizes the reviewer≠author half of it.
  - ref: docs/adr/ADR-024-fleet-health.md
    disposition: distinct
    note: >-
      also measures reviewers, via escape rate and mutation-kill on the review.verdict
      event. Distinct axis: that asks how WELL a reviewer judged, this asks WHO judged.
      §3 states the boundary, because a green attribution check invites the inference
      that the review was good.
  - ref: docs/adr/ADR-030-observer-archetype.md
    disposition: distinct
    note: >-
      its first live pass found persona identity claimed in commit subjects but present
      in the author field for only 3 of 23 commits — corroborating evidence for the
      problem, from a different direction. It observes and enforces nothing; noted
      because a reader may expect the finding to have been actioned there.
<!-- END BARON PRIOR-ART -->
