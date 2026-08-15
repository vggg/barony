---
created: 2026-08-15
type: decision
status: proposed
adr: 035
project: barony
authors: Dev (proposal for Vikram)
decided_by: Vikram
related:
  - "[[docs/adr/ADR-004-baron-guard-enforcement]]"
  - "[[docs/adr/ADR-007-session-boundary]]"
  - "[[docs/adr/ADR-013-observation-plane-events-and-sinks]]"
  - "[[docs/adr/ADR-017-baron-doctor-wiring-selftest]]"
  - "[[docs/adr/ADR-018-adjudicated-enforcement-on-the-event]]"
  - "[[docs/adr/ADR-027-agent-identity]]"
  - "[[docs/adr/ADR-034-deterministic-capability-enforcement]]"
---

# ADR-035 (PROPOSED): the admin / override role — authority rooted outside the enforced party, spent as evidence

| Field | Value |
|---|---|
| **Status** | **Proposed (2026-08-15).** Design only. **No code is proposed on this branch**, and §5 records that deliberately: three of the seven owner questions in §7 are one-way doors that change what gets built. |
| **Authors** | Dev (proposal for Vikram) |
| **Decision owner** | Vikram |
| **Depends on** | **ADR-034** — deterministic capability enforcement (PR #57, in review; not in `docs/adr/` on this branch, which is why it is named here rather than linked). If L0 is not merged, §4.4 has nothing to compose with and this ADR should be re-read rather than re-scoped. |
| **Keeps** | [ADR-007](ADR-007-session-boundary.md)'s boundary. Nothing here drives an agent, mints a forge credential, or configures a platform. |

## 1. Summary

Barony already has an admin, and already has an override. Neither is named.

The **admin** is the owner, de facto, assembled out of three unrelated mechanisms:
CODEOWNERS on `/.barony/`, branch protection on `main`, and — once ADR-034 lands — L0, which
makes every `persona.yaml` structurally unwritable so a capability change becomes a PR a human
merges. That is a real authority boundary. It is nowhere described as one, so it cannot be
reasoned about, reported on, or extended.

The **override** is `BARON_GUARD_OVERRIDE` (ADR-004 §2.3): an environment variable that turns
**every** denial into an allow, for **every** verb, for **the whole process**, for **an
unbounded time**, attributed to **nobody**, justified by a free-text string. It appends to the
tracked `.baron/guard-override.log`, which is the good half and the reason this ADR extends it
rather than replacing it — overrides are already treated as evidence. But the evidence says
*that* an override happened, not *who* authorised it. Anyone who can set an env var can set
that one, including the agent being governed.

**This ADR proposes to name the admin role and give the override a root.** Concretely:
an **admin principal** — a key enrolled in a CODEOWNERS-gated in-repo registry, reusing
ADR-027's trust root and introducing no new one — and a **signed, scoped, expiring break-glass
grant** that guard honours in place of a blanket env flag. `BARON_GUARD_OVERRIDE` survives,
demoted to an explicitly *unattributed* tier, so the fail-closed-but-not-brick property that
ADR-004 chose on purpose is not spent buying attribution.

What changes if it is accepted: an override stops being an anonymous act and becomes a
**signed record naming a principal, a verb, a target and an expiry** — and the question "who
may override" acquires an answer that is a file in the repo rather than "whoever has a shell".

## 2. Context — the tension, stated plainly

An admin capability that the enforced party can grant itself dissolves the entire guarantee.

That is not an abstract worry. It is **FM4** (a persona exercising a verb its own spec denied)
and it is the **self-modifiable-policy hole G5** that ADR-034 §4.1a just closed by fencing
`agents/<slug>/` entirely. Adding an "admin" on top of that, done carelessly, re-opens G5
through a door marked *authorised*: a persona that can set `admin: true` on itself, or a
break-glass path that can rewrite the document defining break-glass, is exactly the policy the
governed party rewrites — with a signature on it.

So three invariants bind every design below. They are stated as invariants, not goals, because
a design that fails any one of them is not a weaker version of this ADR — it is the thing this
ADR exists to prevent.

| # | Invariant | What violating it would look like |
|---|---|---|
| **I1** | **Not self-grantable.** Admin authority is rooted OUTSIDE the enforced party — an owner-held key, a CODEOWNERS-gated assignment, a signed token. Never a verb a persona can turn on for itself, and never a document a persona can write. | `admin: true` in `persona.yaml`; an `__ADMIN__` archetype a dev can spawn; a registry file no fence covers. |
| **I2** | **Attributable and logged as evidence, never silent.** Every override extends `.baron/guard-override.log` and the ADR-013 plane, and carries the principal that authorised it. The override is a *record*, not a bypass of the record. | An override that clears the log; a grant with no signer; a "quiet mode". |
| **I3** | **Composes with L0; does not tunnel under the audit.** A grant is an input to *adjudication*. It may turn a capability `deny` into an `allow`. It may **not** unlock a structural refusal — those are `adjudicated: False` by construction (ADR-018 §2) and no verb unlocks them, which is the property that makes them worth having. | A grant that lets a persona write its own `persona.yaml` "just this once". |

The positioning that bounds all of it is unchanged and is quoted rather than restated: the
2026-08-01 source-level validation settled that Barony is *a real, deterministic policy guard
at the agent-tool interface for cooperating agents — not a security boundary*. An admin role
does not upgrade that claim. It makes an existing, already-exercised authority **legible and
attributable**, which is a governance property, not a security one.

## 3. Supersedes / Prior art

I set out to find (a) any prior decision that already defines an admin, superadmin, or
elevated role; (b) any prior treatment of the existing override escape hatch beyond ADR-004
§2.3; (c) any prior mechanism for a *scoped, expiring* relaxation of a rule, so this ADR does
not invent a second one; and (d) whether the self-grant hazard had already been named
somewhere, in either corpus.

The sweep changed this ADR in four ways, and one of them changed the recommendation.

It **found the override already fully dispositioned** across four records — ADR-004 §2.3
(the escape hatch and the tracked log), ADR-013 §5 (the log stays TRACKED while the event
stream is gitignored, decided deliberately at the `.baron/` vs `.baron/events/` level),
ADR-017 §3.3 (an exported `BARON_GUARD_OVERRIDE` is its own FAIL; the log's writability is
INFO-only), and `events.py`'s `guard.override` kind. So §4.5 **extends** that machinery and
introduces no second log, no second event kind, and no second policy about what is tracked.
An earlier draft of this ADR proposed a `.baron/admin-actions.log`; the sweep deleted it.

It **found the expiring-relaxation mechanism already built and already argued** —
`.baron-waivers.yaml` (ADR-003 §5.3), where **expiry is mandatory** specifically so waivers
cannot rot, an expired waiver stops matching and is itself reported. §4.3 adopts that
reasoning verbatim for grant expiry rather than re-deriving it, and §6 records the one place
the analogy breaks (a waiver relaxes a *report*; a grant relaxes a *decision*, which is why
ADR-016 §5.4's refuse-don't-soft-fail posture applies to grants and not the waiver posture).

It **found the trust root already built** — ADR-027's `.barony/allowed_signers` under
CODEOWNERS, with the argument this ADR needs stated better than I would have stated it: *an
agent that mints a key and adds itself to the allowlist has proved nothing — self-assertion in
a crypto costume.* That sentence is I1. §4.2 therefore reuses that registry's trust root and
its CODEOWNERS gate, and proposes no new root.

And it **found the admin role itself already anticipated in the vault, twice**, which is the
finding that changed the recommendation. The Jon-Rav Shende operations-plane conversation names
*"superadmin or coordinator"* as a role in the fleet and puts *"human override and kill
switch"* in the ops-plane feature table beside authz, commit control and audit — i.e. the role
is on the record as an expected surface, not a novelty. More sharply,
`research-capability-enforcement.md` §"persona-spawn is a privilege-escalation vector" argues
that a party which can instantiate a more-privileged party has **route-around** authority even
with the tool boundary intact — and then records the owner's 2026-08-01 refinement overruling
the obvious fix. That is directly load-bearing for §4.6: it is why a *delegable* admin persona
is not the default here, and it is also why the delegation question is an owner decision rather
than an author's call — the owner has already ruled once in this exact area, in the direction
of "don't police the spawn, control the irreversible action".

No prior art was found for the specific mechanism (a signed, scoped, expiring grant honoured by
guard). It is stated below as new.

<!-- BEGIN BARON PRIOR-ART -->
searched:
  - corpus: repo-adr
    location: docs/adr
    query: "admin, superadmin, override, BARON_GUARD_OVERRIDE, escape hatch, break glass, elevated, privilege, escalation, self-grant, self-promote, waiver, expiry, CODEOWNERS, allowed_signers, trust root, human gate"
    date: 2026-08-15
  - corpus: repo-decisions
    location: docs/DECISIONS-FOR-REVIEW.md
    query: "override, override log tracked, escape hatch, admin, elevated, unevaluated, bypass"
    date: 2026-08-15
  - corpus: vault
    location: /Users/vikram/Obsidian/Brain
    query: "admin, superadmin, coordinator, human override, kill switch, privilege escalation, elevated authority, break glass, persona spawn, per-persona credentials, branch protection, capability enforcement"
    date: 2026-08-15
hits:
  - ref: docs/adr/ADR-004-baron-guard-enforcement.md
    disposition: cites
    note: "§2.3 IS the existing override — fail-closed with a logged escape hatch, the tracked .baron/guard-override.log, each override expected to become a _handoff. This ADR extends that record and preserves §2.3's fail-closed-but-not-brick property explicitly (§4.5); it does not replace the env hatch."
  - ref: docs/adr/ADR-013-observation-plane-events-and-sinks.md
    disposition: cites
    note: "§5 decided the override log stays TRACKED while the event stream is gitignored, and why the .gitignore sits inside .baron/events/ rather than at .baron/. The `guard.override` kind already exists in the v1 registry. §4.5 adds attributes to that kind rather than a new kind or a new sink."
  - ref: docs/adr/ADR-017-baron-doctor-wiring-selftest.md
    disposition: cites
    note: "Check 8 (`override-env` FAIL when BARON_GUARD_OVERRIDE is exported) and check 9 (`override-log` INFO-only) are unchanged by this ADR. §4.7's proposed admin checks are additive and follow check 9's INFO posture, per §3.6's warning that the first unjustified shout spends the mechanism's credibility."
  - ref: docs/adr/ADR-018-adjudicated-enforcement-on-the-event.md
    disposition: cites
    note: "The adjudicated/unevaluated distinction is what makes I3 expressible. A grant may only move an adjudicated deny; a structural refusal is adjudicated=False by construction and no grant may reach it."
  - ref: docs/adr/ADR-027-agent-identity.md
    disposition: cites
    note: "Supplies the whole trust root: .barony/allowed_signers, CODEOWNERS-owned, verified offline from a clone; ssh-keygen -Y sign/verify with a namespace (§2.3) is the exact primitive §4.3 reuses for grants. Its enrollment argument — a self-added key is self-assertion in a crypto costume — is invariant I1, and this ADR does not restate the case."
  - ref: docs/adr/ADR-034-deterministic-capability-enforcement.md
    disposition: cites
    note: "The precondition. §4.1a's L0 fences agents/<slug>/ and .barony/allowed_signers by trailing-component match, which is what makes an in-repo admin registry non-self-writable; §4.4 below states the one addition L0 needs. §6's honest bound (a hostile workspace wins; ~/.claude/settings.json is out of reach) carries over unchanged and is NOT re-argued here."
  - ref: docs/adr/ADR-003-baron-cli.md
    disposition: cites
    note: "§5.3's .baron-waivers.yaml is the prior expiring-relaxation mechanism: expiry mandatory so waivers cannot rot, an expired waiver stops matching and is reported. §4.3 adopts that reasoning for grant TTL; §6 records where the analogy stops (a waiver relaxes a report, a grant relaxes a decision)."
  - ref: docs/adr/ADR-016-externalizable-capability-rules.md
    disposition: cites
    note: "§5.4 — a malformed rules document REFUSES rather than soft-failing, deliberately unlike waivers. §4.3 applies the same posture: an unparseable or unverifiable grant is not a grant, and the denial stands."
  - ref: docs/adr/ADR-007-session-boundary.md
    disposition: cites
    note: "The boundary. Issuing a grant is a CLI act by a human under their own key; baron does not drive an agent, mint a credential, or configure a forge. §4.6's human-only default follows from this, not from a security claim."
  - ref: docs/adr/ADR-023-reserved-filenames.md
    disposition: cites
    note: "Any new governed filename (.barony/admins, .baron/grants/) is an artifact type with an owner, not an incidental string. OD-2 is the naming decision that record requires; §4.2 does not settle it unilaterally."
  - ref: docs/adr/ADR-029-prior-art-gate.md
    disposition: cites
    note: "The gate this block satisfies."
  - ref: docs/adr/ADR-028-mechanized-merge-gate.md
    disposition: cites
    note: "§4.7 proposes that `baron merge check` see an override in the PR's commit range. That is an addition to its finding set, not a change to its fail-closed contract; recommended as advisory (OD-6)."
  - ref: /Users/vikram/Obsidian/Brain/projects/AgentBootstrapNasikoMix/research-capability-enforcement.md
    disposition: cites
    note: "The privilege-escalation section is the direct prior art for §4.6: a party that can instantiate a more-privileged party has route-around authority. It also records the owner's 2026-08-01 refinement (don't police the spawn; control the irreversible action at the platform layer), which is why delegation is OD-1 and not an author's call."
  - ref: "/Users/vikram/Obsidian/Brain/projects/AgentBootstrapNasikoMix/Agent Operations Plane - Conversation with Jon-Rav Shende.md"
    disposition: cites
    note: "Names 'superadmin or coordinator' as a fleet role and puts 'human override and kill switch' in the ops-plane feature table alongside authz, commit control and audit. Establishes the role as an anticipated surface; supplies no mechanism, which is what this ADR adds."
  - ref: /Users/vikram/Obsidian/Brain/projects/AgentBootstrapNasikoMix/research-agent-identity-lightweight.md
    disposition: cites
    note: "The fourteen-option survey behind ADR-027. Its rejection of per-persona GitHub App/bot accounts (human provisioning, org admin, not verifiable from a clone) is why §4.2 puts the admin registry in the repo rather than on the forge."
  - ref: docs/adr/ADR-030-observer-archetype.md
    disposition: distinct
    note: "The most recent archetype addition, and the natural template if admin were an archetype — but it is the opposite case. The observer is a persona constrained by holding little; an admin would be a persona empowered by holding much, and §7's alternatives table rejects the archetype form precisely because a persona is the enforced party. It decides nothing this ADR decides."
  - ref: docs/adr/ADR-033-signed-review-verdicts.md
    disposition: distinct
    note: "Also signs an in-repo artifact against the ADR-027 registry, so the file shapes will rhyme. But it signs an OBSERVATION (a reviewer's verdict, evidence for a gate) whereas a grant is an INSTRUCTION consumed by the guard at decision time. The verification plumbing is shared; the authority question is not, and §5's authority-half bound is untouched by this ADR."
<!-- END BARON PRIOR-ART -->

## 4. Proposed design

### 4.1 Admin is neither a verb nor an archetype — it is a KEY

The two obvious shapes both fail I1, for the same underlying reason, and it is worth stating
once because it also explains the shape that is left.

**Not a capability verb.** The v1 vocabulary is frozen at ten verbs, which is reason enough,
but not the real reason. A verb is a field in `persona.yaml`, and `persona.yaml` is a document
*the guard reads to decide*. An `admin: true` field would be a policy document declaring its
own exemption — the guard consulting the governed party about whether to govern it. Even with
L0 making that document unwritable in-repo, the category error stands: authority would be
asserted by the same artifact whose authority is in question.

**Not an archetype.** An archetype is a persona template, and a persona is the enforced party
by definition. An `__ADMIN__` persona would put override authority *inside* the fleet's blast
radius — and, per the vault's privilege-escalation finding, a dev able to spawn it would hold
its authority transitively.

What is left is the shape ADR-027 already uses for identity: **authority is possession of a
key**, and the registry that says which keys count is a CODEOWNERS-gated file in the repo. A
key is not a document the governed party writes, and enrolling one is a human merge.

### 4.2 The admin registry

**Proposal:** `.barony/admins` — a plain list of principals, one per line, each of which
**must also** appear in `.barony/allowed_signers`. Two files, two questions:
`allowed_signers` answers *who exists*; `admins` answers *which of them may authorise an
override*. Both live under `/.barony/`, which CODEOWNERS already assigns to the owner (see
`skills/barony/assets/collab-repo/.github/CODEOWNERS`), so enrolling an admin is a PR the
owner merges — the same one-time human gate ADR-027 §2 established, reused rather than
rebuilt.

Splitting the two rather than overloading `allowed_signers` with a principal-naming convention
is a recommendation, not a settled question — see **OD-2**, and ADR-023, which says a new
governed filename is an artifact type with an owner rather than a string somebody picked.

### 4.3 Break-glass: a signed, scoped, expiring grant

```
baron grant issue --persona dev --verb merge_pr \
                  --target 'gh pr merge 412' \
                  --expires 2026-08-16T09:00:00Z --reason "release cut, merger sidecar down"
```

Run **by a human, on their own machine, under their own key.** It writes a **tracked**
`.baron/grants/<id>.json` plus a detached `<id>.json.sig` produced by
`ssh-keygen -Y sign -n barony-grant` — the same primitive ADR-027 §2.3 already uses for
handoffs and findings, with its own namespace.

Guard consults grants **only on a path it is about to deny**, and honours one only when all of:

1. the signature verifies against `.barony/allowed_signers`, **and**
2. the resolved principal appears in `.barony/admins`, **and**
3. the grant names this persona and this verb, **and** its target bound matches this call, **and**
4. `expires` is in the future, **and** the grant's use budget is not spent.

Then the call is allowed, `.baron/guard-override.log` gains a line, and a `guard.override`
event carries the grant id and the signing principal. Any failure — bad signature, unknown
principal, expired, malformed, `ssh-keygen` absent — is **not** a grant, and **the denial
stands**. That is ADR-016 §5.4's refuse-don't-soft-fail posture, and it is the safe direction:
a broken grant costs an allow, never a deny.

**Both bounds are mandatory, and that is the waiver precedent, not a new idea.** `expires` is
required (ADR-003 §5.3 made waiver expiry mandatory precisely so relaxations cannot rot), and
the default use budget is **`uses: 1`** — break-glass is a specific act on a specific call, and
a grant that outlives its incident is a standing capability change wearing a temporary label.
If a persona needs a verb durably, the designed path is a PR against its `persona.yaml`, which
L0 already forces and CODEOWNERS already gates. A recommended hard TTL cap sits in **OD-4**.

**A grant needs no fence, and that is a property worth noticing.** The file is
self-authenticating: a persona holding `write_code` can create `.baron/grants/anything.json`
and it will be ignored, because it cannot produce a signature that resolves to an enrolled
admin principal. Deleting a grant only removes permission. The only file that must be fenced
is the registry — §4.4.

### 4.4 How it composes with L0 (invariant I3)

Two requirements, both small, both load-bearing.

**(a) L0 must fence `.barony/admins`.** ADR-034 §4.1a fences `.barony/allowed_signers` by
trailing-component match; the admin registry needs the identical treatment in the same
`file_ops` list. A registry the governed agent can edit is not a registry — the same sentence
ADR-034 §4.4 wrote about the deferred rules document, and the same fix. This is the one change
to merged (or in-review) behaviour that this ADR's eventual implementation requires.

**(b) A grant may never unlock a structural refusal.** L0 refusals are `adjudicated: False` —
no verb unlocks them, and that is the whole point of the layer. A grant is an input to
*adjudication*; it can move a capability `deny` to an `allow`, and it stops at the structural
fence. Concretely: **there is no grant that lets a persona write its own `persona.yaml`.**
Allowing one would re-open G5 through a door marked *authorised*, and the cost of holding the
line is near zero, because the owner is not the enforced party — an owner editing a persona
spec does it on their own machine, in a PR, outside any guarded agent session. The guard hook
governs agents; it was never in the owner's way. This is **OD-3**, and the recommendation is
*never*.

### 4.5 What happens to `BARON_GUARD_OVERRIDE`

**It survives, demoted.** Removing it would buy attribution with a property ADR-004 §2.3 chose
deliberately: *fail-closed but not brick.* The env hatch is what rescues a repo when guard is
wrong, when `ssh-keygen` is missing, when the grant path itself is broken — the exact moments a
mechanism that needs a working signature cannot help.

So the two coexist and the **evidence tells them apart**, which is the entire improvement:

| | `BARON_GUARD_OVERRIDE` | signed grant |
|---|---|---|
| Scope | every verb, whole process | one persona, one verb, one target bound |
| Lifetime | until the process exits | until `expires`, or the use budget is spent |
| Authority | anyone who can set an env var | a principal enrolled in `.barony/admins` |
| Evidence | log line + `guard.override` event, **`baron.override.tier: env`, principal `unattributed`** | same log, same event kind, **`tier: grant`** + grant id + signing principal |
| Doctor | check 8 FAILs when it is exported — **unchanged** | new INFO check (§4.7) |

One log, one event kind, one added attribute. ADR-013 §5's tracked-vs-gitignored decision is
untouched. **OD-5** asks whether the owner wants the env tier retired once grants exist; the
recommendation is no.

### 4.6 Human-only, or delegable to a persona?

**Recommendation: human-only by default; delegation deferred behind one named condition.**

The mechanism itself is indifferent — it verifies a signature and checks a registry, and it
cannot tell a human's key from an agent's. That indifference is exactly why the *policy* has to
be stated rather than left implied. The reason to keep it human is not that agents are
untrustworthy; it is that an admin key held by a persona is **inside the blast radius it is
supposed to be outside of**. ADR-034 §6's bound is unchanged and decisive: an agent with a
shell can read files. A key on the same disk as the agent it authorises over is authority
rooted *inside* the enforced party, and I1 fails silently — nothing looks different in the log.

The condition under which delegation becomes coherent is therefore specific and is not a
Barony property: **the admin key is in a store the agent's process cannot read** (hardware
token, an agent-inaccessible keychain, a signing service). That is a platform layer, ADR-007
says Barony reports platform layers rather than building them, and §4.7 proposes exactly that
report.

There is a narrower delegation worth putting in front of the owner rather than deciding here,
because the vault records the owner ruling in this area once already (don't police the spawn;
control the irreversible action): an **admin whose issuing scope is itself bounded** — e.g. a
persona that may issue grants for `run_tests` or `open_pr` but never for `merge_pr`,
`push_main`, or `force_push`. That preserves I1 for the verbs where I1 matters and buys real
autonomy for the ones where it does not. It is **OD-1**, and it is blocking, because a
per-admin issuing scope is a registry-format decision that must exist before the first
`.barony/admins` file does.

### 4.7 Reporting — `baron doctor`, `status`, and the merge gate

All additive, all read-only, all following check 9's INFO posture rather than check 8's FAIL,
because ADR-017 §3.6 is right that the first unjustified shout spends the credibility the
mechanism runs on:

- **doctor** — `.barony/admins` exists and every principal in it resolves in
  `allowed_signers` (FAIL if it names a principal that does not: that is a broken registry, not
  a posture); unexpired grants are listed (INFO); an admin principal's **private** key found
  readable inside the repo tree (INFO, loud) — the §4.6 hazard, reportable but not enforceable.
- **status / health** — unexpired grants surface beside waivers. A standing grant is an
  outstanding obligation of the same family, and it should age visibly.
- **`baron merge check`** (ADR-028) — an override recorded in the PR's commit range becomes a
  finding. Recommended **advisory**, not blocking: an override is frequently the legitimate
  reason the PR exists. **OD-6**.

## 5. Build now vs defer

**Nothing is built on this branch, and that is the proposal.** Three of the seven owner
questions change what the artifacts *are*: OD-1 changes the registry format (a bounded issuing
scope is a per-principal field, not a bare list), OD-2 changes which files exist at all, and
OD-3 changes where the check sits in guard's precedence order. Building against a guess and
renaming later would cost more than the wait, and ADR-023 exists because emitted filenames are
governed artifacts rather than strings that can be quietly changed.

| # | Item | Call |
|---|---|---|
| B1 | L0 fences `.barony/admins` (§4.4a) | **Build first, independently** — it is one entry in the same `file_ops` list, it is correct whatever OD-1/2 decide, and it must exist before the registry does |
| B2 | `.barony/admins` registry + `baron admin list/verify` | Blocked on OD-1, OD-2 |
| B3 | `baron grant issue/list/revoke` + guard's grant check | Blocked on OD-3, OD-4 |
| B4 | `tier` attribute on the override log line + `guard.override` event (§4.5) | Buildable now; small, and it makes the *existing* env overrides legible before any grant exists |
| B5 | doctor / status / merge-check reporting (§4.7) | Follows B2/B3 |
| D1 | Delegated admin with a bounded issuing scope | Deferred pending OD-1 |
| D2 | Kill switch (the vault's ops-plane table names it beside human override) | **Out of scope, deliberately.** A kill switch stops a *running* agent; Barony does not own the agent loop (ADR-007). Named so it is not read as an oversight |

## 6. Honest bound

- **A compromised admin key defeats this entirely**, and nothing here detects it. The grant
  verifies, the principal resolves, the log records a legitimate-looking override. This is
  scoped out on purpose: the design problem being solved is **attributable, non-self-grantable
  authority among cooperating agents**, not key compromise. Key custody is the owner's, and it
  is the load-bearing assumption.
- **The hostile-workspace bound is unchanged.** ADR-034 §6 stands word for word: an agent with
  a shell can edit `~/.claude/settings.json`, install a different git client, or reach the forge
  API directly. Break-glass raises the cost of an *unattributable* override from "set an env
  var" to "obtain a key" — a real change in evidence quality, and not a security boundary.
- **The env tier stays unattributable by design** (§4.5). This ADR makes it *labelled*, not
  attributable, and the label is honest about which one it is.
- **Expiry rests on the local clock**, which an agent with a shell can move. Expiry is a
  hygiene control against grants rotting into permanent capability changes — the waiver
  argument — not an adversarial control. Where the waiver analogy stops: a waiver relaxes a
  *report* and may soft-fail; a grant relaxes a *decision* and therefore refuses (§4.3).
- **`ssh-keygen` becomes a dependency of the grant path only.** Its absence must degrade to
  "no grants honoured, denials stand", never to "grants assumed valid" — and the env hatch is
  what keeps that degradation from bricking a repo.
- **This does not close ADR-033 §5's authority half.** Agents still act under the owner's
  forge identity. An admin principal authorises an override *of baron's guard*; it confers
  nothing on GitHub. A grant cannot merge a PR that branch protection refuses, and that is the
  right ordering.

## 7. Alternatives considered

| Alternative | Why rejected |
|---|---|
| An `admin` capability verb | Vocabulary frozen at ten verbs — and worse, a verb is a field in the document the guard reads, so it is a policy asserting its own exemption (§4.1). Violates I1 in principle even where L0 blocks it in practice. |
| An `__ADMIN__` archetype persona | An archetype is a persona; a persona is the enforced party. Puts authority inside the blast radius, and a dev that can spawn it holds it transitively (vault: persona-spawn is a privilege-escalation vector). Reachable only via OD-1's bounded form. |
| `BARON_ADMIN=1` — a second env tier | Reproduces the exact defect being fixed: unattributable, unscoped, unbounded. Two of them is not better than one. |
| Sign the `BARON_GUARD_OVERRIDE` reason string, change nothing else | A signature over a reason with no scope and no expiry is a permanent, all-verb grant that happens to be signed. Attribution without bounds is the weaker half of the pair. |
| Status quo — CODEOWNERS + branch protection only, no baron mechanism | Genuinely most of the answer, and it is why §1 says the admin already exists. But it governs only what reaches a PR. Local overrides never reach a PR, happen at the moment of the decision, and are exactly where attribution is missing today. |
| Grants on the forge (a GitHub App, an approval workflow) | Breaks invariant #1 — the repo is the only source of truth and a clone must be enough to verify the record. It is also the option ADR-027's fourteen-option survey already rejected for identity, for the same reason. |
| Let a grant unlock L0 for `persona.yaml` "just this once" | Re-opens G5 behind an authorised door. Costs nothing to refuse: the owner is not the enforced party and edits specs by PR, outside any guarded session (§4.4b). |

## 8. Owner decisions

Seven. Three are blocking — they change what gets built, not merely how it behaves.

| # | Question | Blocking? | Recommendation |
|---|---|---|---|
| **OD-1** | Is admin **human-only**, or may it be delegated to a persona — and if delegable, is it delegable only in the **bounded-issuing-scope** form (may issue for `run_tests`/`open_pr`, never for `merge_pr`/`push_main`/`force_push`)? | **YES** — decides the registry format | **Human-only for v1.** Keep the bounded form as the named delegation path, not shipped. An admin key on the same disk as the agent it authorises over fails I1 silently (§4.6). |
| **OD-2** | Registry shape: a new `.barony/admins` file, or a principal-naming convention inside `.barony/allowed_signers`? | **YES** — decides which files exist (ADR-023) | **`.barony/admins`.** Two files, two questions: who exists vs who may authorise. Overloading the signer registry makes the admin set a parsing artifact of a file that exists for another purpose. |
| **OD-3** | May a grant **ever** unlock an L0 structural refusal? | **YES** — decides guard's precedence order | **Never.** The line is free to hold — the owner edits specs by PR, outside any guarded session — and crossing it re-opens G5 with a signature on it (§4.4b). |
| **OD-4** | Grant bounds: mandatory `expires`, default `uses: 1`, and is there a **hard TTL cap**? | No | Mandatory expiry (waiver precedent, ADR-003 §5.3), `uses: 1` by default, and a **24h cap** overridable only by an explicit `--long-lived` flag that the doctor report then names. A grant that outlives its incident is a capability change mislabelled. |
| **OD-5** | Does `BARON_GUARD_OVERRIDE` survive once grants exist? | No | **Yes, demoted and labelled** (`tier: env`, principal `unattributed`). Retiring it spends ADR-004 §2.3's fail-closed-but-not-brick property to buy attribution the grant path already provides. |
| **OD-6** | Should `baron merge check` treat an override in the PR's commit range as blocking, or advisory? | No | **Advisory.** An override is often the legitimate reason the PR exists; ADR-017 §3.6's first-unjustified-shout argument applies. Revisit once there is override data to look at. |
| **OD-7** | Build scope now — B1 + B4 immediately (they are correct under every answer above), or hold everything until OD-1..3 land? | No | **Ship B1 + B4.** B1 (fence `.barony/admins`) must precede the registry; B4 (tier the log line) makes today's env overrides legible before any grant exists, which is value independent of the rest of this ADR. |

## 9. Decision record

- [ ] Approved as written
- [ ] Approved with changes
- [ ] Needs revision
- [ ] Rejected

Owner sign-off: ____________________  Date: ____________
