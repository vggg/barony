---
created: 2026-08-14
type: decision
status: proposed
adr: 028
project: barony
authors: Claude (design + implementation for Vikram)
decided_by: Vikram
related:
  - "[[docs/adr/ADR-002-ways-of-working-2026-07]]"
  - "[[docs/adr/ADR-007-session-boundary]]"
  - "[[docs/adr/ADR-008-ways-of-working-2026-07-31]]"
  - "[[docs/adr/ADR-027-agent-identity]]"
---

# ADR-028 (PROPOSED): `baron merge check` — the merge decision becomes a fail-closed gate

| Field | Value |
|---|---|
| **Status** | Proposed (2026-08-14) |
| **Authors** | Claude (design + implementation for Vikram) |
| **Decision owner** | Vikram |
| **Mechanizes** | [ADR-002](ADR-002-ways-of-working-2026-07.md) §4 (the Merger's preconditions) and [ADR-008](ADR-008-ways-of-working-2026-07-31.md) §1/§3 (verdict-not-label; strip-stale-verdict) |
| **Constrained by** | [ADR-007](ADR-007-session-boundary.md) — baron provides the governed check; the runtime decides to invoke it |
| **Blocked by, for the autonomous case** | Per-persona **forge** identity — which [ADR-027](ADR-027-agent-identity.md) deliberately does **not** provide. See §4, corrected. |

## 1. Summary

The `__MERGER__` archetype has always been specified as **a gate, not a button**: four
preconditions, all of which must hold, and a loud refusal naming the one that failed. That
specification lived entirely in persona prose.

Prose is the weakest enforcement tier Barony has, and the project's own evidence says so:
FM4 recorded a dev persona merging ~15 PRs with `merge_pr` *denied in its own config*, then
refusing identically when asked about it. A merge decision written as an instruction is a
decision the model can talk itself past — usually while producing an entirely convincing
account of why this particular PR was fine.

This ADR moves the checkable half of the gate out of prose and into code:
**`baron merge check <pr>`** evaluates the preconditions against the forge and returns a
verdict — exit 0 (allowed) or exit 1 (REFUSE, with the failing precondition, a stable reason
slug, and the sha it checked). The refusal is a **return value**, not a paragraph.

It does not merge. There is deliberately no `baron merge do` — see §6.

## 2. Decision

### §2.1 — The gate, and what each precondition means

`baron merge check` scores four preconditions **in order**, against **one PR snapshot**:

| # | Precondition | Passes when |
|---|---|---|
| 1 | `pr_open` | state OPEN, not a draft, and the head resolves to a full 40-hex sha |
| 2 | `verdict_at_head` | a well-formed `REVIEW:PASS <sha>` comment exists whose sha **equals the current head** |
| 3 | `no_changes_requested` | no `REVIEW:FAIL` at the current head, and no platform changes-requested review |
| 4 | `ci_green` | every check run on the head sha succeeded, and at least one actually ran |

Exit 0 only when all four hold. The **first** failing precondition is *the* refusal — a
merger that gets four complaints starts triaging; one named blocker is an instruction.

**One snapshot, not four queries.** Verdict, labels and checks all come from a single
`gh pr view`. Assembled from separate calls, a push landing mid-check could produce a
verdict that "matches" a head whose CI never ran — reconstructing, at the mechanism layer,
the exact stale-verdict merge the gate exists to prevent.

### §2.2 — Fail-closed is the whole point

Every unknown is a refusal, each with its own reason slug: `no_verdict`, `stale_verdict`,
`verdict_malformed`, `changes_requested`, `platform_changes_requested`, `ci_not_green`,
`ci_pending`, `ci_absent`, `ci_unknown_state`, `pr_not_open`, `pr_draft`, `head_unknown`,
`forge_unavailable`, `unevaluated`.

Four consequences worth stating because each was a choice:

- **No CI is not green.** An empty check-run list refuses (`ci_absent`), as does a set where
  everything was skipped or neutral — nothing ran, so there is nothing to be green about.
- **Pending is not green.** In-flight checks refuse rather than wait.
- **An uninterpretable check state refuses** (`ci_unknown_state`). baron does not guess at a
  state it does not recognize, and a new forge state must not arrive as an implicit pass.
- **Preconditions that could not be reached are recorded as FAILED, not skipped.** A skipped
  check renders as an absence, and a reader rounds an absence down to "fine".

An unreachable forge — `gh` missing, an API error, a forge implementation without the
`get_pr` extension — is `forge_unavailable`, a refusal. This is a deliberate departure from
[ADR-009](ADR-009-baron-decision-reconciliation.md) §4's three-state model, where an
unverifiable check is amber rather than red. That model is right for a *report*. A merge is
an *action*, and for an action amber is red.

### §2.3 — A label is an input to nothing

Review-state labels are **collected and reported as ignored**, never scored, in both
directions: an approval label cannot rescue a stale verdict, and a `changes-requested`
label cannot block a clean head. Only the SHA-bound verdict comment counts (ADR-008 §1).

Reporting them is not scoring them. Naming the misleading signal that was present and
deliberately unused is what makes a refusal legible to the human reading it — and it is a
better answer than silence to the merger about to argue that the label said approved.

### §2.4 — The sha comparison is exact

A verdict naming an abbreviated sha is **refused**, not prefix-matched (`verdict_malformed`),
even though the abbreviation is very probably the head. Two commits can share a prefix, and
prefix-matching would make the equality test the entire gate rests on approximate. The
reviewer template already says to carry the full sha; this makes it a contract.

A verdict whose sha simply differs from the head is `stale_verdict` — the strip-stale-verdict
discipline (ADR-008 §3), now *evaluated* rather than trusted to a workflow that only strips
labels.

### §2.5 — A block at the head is decisive, even beside a PASS

A `REVIEW:FAIL` at the current head refuses **even when a later `REVIEW:PASS` names the same
sha**. Same sha means the same code: a later PASS does not answer the FAIL, it disagrees with
it, and baron does not resolve a disagreement by taking the newer of two opinions. Push the
fix; get a verdict on the new head.

Platform reviews are asymmetric, deliberately: a platform `CHANGES_REQUESTED` **blocks**, a
platform `APPROVED` **never authorizes**. ADR-002 §4 makes the comment the verdict surface,
so an approval arriving through the wrong surface is not a verdict — but ignoring a human's
explicit block because it arrived through the wrong surface would not be fail-closed.

## 3. What the gate deliberately does not check

The merger has four preconditions; this mechanizes **two** (CI and the verdict). It says so
in its own output, and the persona template carries the split.

| Not checked | Why, and what covers it |
|---|---|
| Precondition 3 — record obligations | "Every material finding/decision has a `_handoff/`" needs a judgement about materiality. Not mechanizable without inventing a heuristic that would be wrong in both directions. Stays the persona's. |
| Precondition 4 — hot-file collision | Needs the PR's changed paths crossed against `Lock` patterns. Mechanizable, and worth doing — deferred to keep this ADR to one claim. `baron lock list` is today's answer. |
| Merge conflicts | The forge refuses the merge itself; GitHub computes mergeability asynchronously, so an `UNKNOWN` would produce spurious refusals. |
| ~~Who wrote the verdict~~ | ~~**Not possible today.** See §4.~~ **Now checked** — [ADR-033](ADR-033-signed-review-verdicts.md) added the `verdict_signed` precondition. Still true of the *comment* surface, which ADR-033 §2.3 demotes to an index; the signed in-repo artifact is what attributes. |

Exit 0 therefore means *"preconditions 1 and 2 hold"*, never *"merge it"*. Stating that
plainly is the point: a gate that quietly covers half of what its name suggests is worse than
one that covers half and says so.

## 4. The honest bound — live autonomous merging is NOT unblocked by ADR-027

> **Corrected 2026-08-14, at queue integration.** This section was drafted against an earlier
> ADR-027 that proposed **per-persona forge credentials** (machine accounts / PATs). That
> design was rejected; the accepted [ADR-027](ADR-027-agent-identity.md) is **SSH commit
> signing**, and it introduces **no forge credential anywhere** (its §4.8 rules machine
> accounts and PATs out as the attribution mechanism, and its §3 states plainly that nothing
> in it is an authorization mechanism). The claim that ADR-027 unblocks the autonomous merger
> was therefore **wrong**, and is withdrawn rather than quietly reworded.

**The gate logic is identity-independent to build and to test.** It is pure preconditions
over a PR snapshot; the test suite exercises the pass path and every refusal path with
fixtures and a fake forge, and none of it needs a credential. That part is unchanged.

**Deploying it as an autonomous merger is not — and stays blocked after ADR-027 ships.**
Every persona still pushes and comments under one shared forge login. So:

> baron can verify that a `REVIEW:PASS` exists at the current head. It **cannot verify who
> posted it.** The dev whose code is under review can post its own `REVIEW:PASS`, and the
> gate — correctly, given its inputs — returns exit 0.

**Why ADR-027 does not close this.** ADR-027 attributes **commits, tags, handoffs and
findings** — artifacts that live in git and can carry a signature verified against
`.barony/allowed_signers`. A `REVIEW:PASS` verdict is a **PR comment**: forge state, not repo
state, with no signature and no per-persona login behind it. The two do not meet. ADR-027
makes the *code* under review attributable; it leaves the *verdict on* that code exactly as
self-asserted as it is today.

Closing it needs one of two things, neither of which is decided and neither of which this ADR
or ADR-027 does — recorded as §7 Q4:

1. **per-persona forge identity** (machine accounts, Apps, or the platform's own review API
   with distinct logins) — the heavyweight authorization question ADR-027 §4.8 explicitly
   left live *on its own merits*; or
2. **moving the verdict into the substrate** — a signed verdict artifact in-repo under
   ADR-027 §2.3's detached-signature scheme, which the gate would verify instead of trusting
   a comment. This is the option that composes with what ADR-027 actually built, and it is
   not designed anywhere yet.

> **UPDATE 2026-08-14 — option (2) landed as [ADR-033](ADR-033-signed-review-verdicts.md).**
> Everything above this note still describes the **comment** surface accurately and is
> left standing rather than rewritten: a `REVIEW:PASS` comment remains unattributable,
> which is exactly why ADR-033 §2.3 demotes it to an index and puts the record in a
> signed in-repo artifact. The two bullets below are amended in place.

Until one of them lands:

- `baron merge check` is **owner-in-the-loop**: the merger runs it and reports; the human
  performs the merge (or approves it). **Still true after ADR-033** — it closed the
  evidence half, not the authority half (ADR-033 §5).
- `--verdict-author <login>` exists and refuses verdicts from anyone else
  (`verdict_author_unverified`). It is *useless* under one shared account — every login
  matches — and becomes load-bearing only if option (1) above is ever taken. Shipping it now
  means that work would flip a flag rather than reopen the gate. It does **not** become
  useful when ADR-027 lands. **After ADR-033 it is the weaker of two overlapping
  mechanisms**: it filters on a forge *login*, while the signed verdict attributes to a
  *persona* — which is the thing that actually differs under one account.

Anything else would be enforcement theater of the exact kind ADR-003 was written against:
a mechanism whose refusal is real and whose *evidence* is forgeable by the party it
constrains.

## 5. Alternatives considered

**Prose hardening in the merger template.** The status quo, and what P1.3 already did. FM4 is
the counter-evidence: a persona overrode a config-level denial ~15 times. The v1.9 template
is *good* prose; the failure mode is not bad prose.

**A GitHub required-status-check / branch-protection rule.** Real enforcement, and worth
having — but it cannot express "a comment naming the current head sha", it is per-repo
configuration rather than a portable Barony artifact, and it silently does nothing on repos
that never configured it. The gate is forge-portable (Forge Protocol) and refuses loudly when
it cannot see.

**`baron merge do` — mechanize the merge itself.** Rejected for now on two grounds. ADR-007:
baron provides the governed check, the runtime decides to invoke it. And §4: performing an
autonomous merge under the owner's token is exactly the ambient-authority problem. Note that
ADR-027 does **not** fix it (§4): it attributes artifacts, it does not scope authority.
Reconsider once §7 Q4 is answered — the gate is already the hard half.

**Three states (discharged / outstanding / unverifiable), as `baron decision check` uses.**
Rejected for an *action* surface. See §2.2.

## 6. Consequences

- The merger's decision is checkable and reproducible: same snapshot, same verdict, by
  anyone, without reading a persona file.
- Refusals become uniform and machine-readable (`--json` carries the failing precondition and
  reason slug), so a wrapper can route them without parsing prose.
- The two unmechanized preconditions are now *conspicuously* unmechanized — visible in the
  command's own output rather than lost in a template.
- Precondition 4 (hot-file collision) is the obvious next increment.
- A new forge implementation must add the `get_pr` optional extension to support the gate;
  without it the gate refuses rather than degrading, per §2.2.

## 7. Open questions for the owner

1. **Should `baron merge do` ever exist**, or does the merge stay a runtime action that
   calls the check (ADR-007's line)? This ADR assumes the latter and does not foreclose the
   former. The trigger is no longer "once ADR-027 lands" — see §4 and Q4.
2. **Should precondition 4 fold into this command** (`baron merge check` cross-referencing
   `baron lock list` against the PR's changed paths), or stay a separate call the persona
   composes?
3. **Should `--verdict-author` default to the manifest's reviewer persona** if per-persona
   forge logins ever exist, rather than staying opt-in? Defaulting would make the strongest
   form the automatic one, at the cost of breaking projects whose reviewer slug and forge
   login differ.
4. **How does a verdict become attributable at all?** §4 names two candidate routes —
   per-persona forge identity (the authorization question ADR-027 §4.8 left live), or a
   **signed verdict artifact in-repo** verified under ADR-027 §2.3's detached-signature
   scheme. The second composes with what Barony actually built and keeps the record in git,
   which is the standing preference; neither is designed. This is the real blocker on an
   autonomous merger, and it is nobody's open item until it is somebody's.

   > **SUPERSEDED BY [ADR-033](ADR-033-signed-review-verdicts.md) (2026-08-14).** It is
   > somebody's. ADR-033 takes **route 2** — the reviewer SSH-signs an in-repo verdict
   > artifact, and `baron merge check` gains a `verdict_signed` precondition that verifies
   > it offline against `.barony/allowed_signers`, requiring a `reviewer`-archetype signer
   > **distinct from the persona that signed the head commit**. Reviewer≠author becomes a
   > property of the repo rather than a rule in a persona file.
   >
   > What that closes and what it does not: it closes the **evidence** half of the
   > autonomous merger. It does **not** close the **authority** half — merging still means
   > acting under the owner's token, which is the ambient-authority ground §5 rejected
   > `baron merge do` over. `baron merge check` stays owner-in-the-loop. See ADR-033 §5,
   > which exists because reading a green attribution check as permission is the specific
   > mistake available at this moment.

## 8. Supersedes / Prior art

The sweep this ADR records under **ADR-029** (the prior-art gate — on another branch at the
time of writing, referenced by number). Recorded **retrospectively**, at the queue
integration on 2026-08-14, and it earned its keep immediately: it is what surfaced that §4's
central claim was written against a **rejected** ADR-027 and was false. That correction is
marked inline in §4 rather than silently reworded.

This ADR is `status: proposed`, so the gate treats it as **exempt** rather than gated. The
block is written anyway — the sweep either happened or it did not, and an ADR that acquires
its prior art only at the moment someone accepts it has the discipline backwards.

<!-- BEGIN BARON PRIOR-ART -->
searched:
  - corpus: repo-adr
    location: docs/adr
    query: "merge gate, merger preconditions, verdict at head, stale verdict, fail-closed, required check"
    date: 2026-08-14
  - corpus: repo-decisions
    location: docs/, STATUS.md, AGENT-TASKS.md, CHANGELOG.md, open PRs on vggg/barony
    query: "merge_pr, merger persona, FM4, review verdict, label vs verdict"
    date: 2026-08-14
  - corpus: vault
    location: /Users/vikram/Obsidian/Brain
    query: "merge gate, autonomous merger, review verdict, agent identity for merge"
    date: 2026-08-14
hits:
  - ref: docs/adr/ADR-008-ways-of-working-2026-07-31.md
    disposition: cites
    note: >-
      §1 (verdict-not-label) and §3 (strip-stale-verdict) are the rules this mechanizes.
      §2.3 and §2.4 are those two rules turned into evaluated preconditions.
  - ref: docs/adr/ADR-002-ways-of-working-2026-07.md
    disposition: cites
    note: §4 specifies the Merger's four preconditions; this mechanizes two of them and §3 says which.
  - ref: docs/adr/ADR-009-baron-decision-reconciliation.md
    disposition: distinct
    note: >-
      also a fail-or-report gate over governance state, but deliberately three-state
      (discharged / outstanding / unverifiable). Distinct because that is a report and this
      is an action — §2.2 records the departure and argues it rather than inheriting it.
  - ref: docs/adr/ADR-027-agent-identity.md
    disposition: cites
    note: >-
      §4's identity bound. NOTE the correction: the ADR-027 this section originally cited
      was a rejected forge-credential design. The accepted ADR-027 (SSH signing) does NOT
      unblock the autonomous merger — §4 and §7 Q4 carry the corrected claim.
  - ref: docs/adr/ADR-007-session-boundary.md
    disposition: cites
    note: the reason there is no `baron merge do` — baron provides the check, the runtime invokes it.
  - ref: docs/adr/ADR-017-baron-doctor-wiring-selftest.md
    disposition: distinct
    note: >-
      also verifies-and-refuses rather than acting, but over local enforcement wiring rather
      than a forge PR snapshot. No shared surface; noted because a reader may expect one.
<!-- END BARON PRIOR-ART -->
