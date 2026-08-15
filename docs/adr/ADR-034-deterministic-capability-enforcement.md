---
created: 2026-08-14
type: decision
status: proposed
adr: 034
project: barony
authors: Atlas (proposal for Vikram)
decided_by: Vikram
related:
  - "[[docs/adr/ADR-004-baron-guard-enforcement]]"
  - "[[docs/adr/ADR-007-session-boundary]]"
  - "[[docs/adr/ADR-016-externalizable-capability-rules]]"
  - "[[docs/adr/ADR-017-baron-doctor-wiring-selftest]]"
  - "[[docs/adr/ADR-018-adjudicated-enforcement-on-the-event]]"
  - "[[docs/adr/ADR-020-read-verb-posture-measured-on-four-adapters]]"
  - "[[docs/adr/ADR-027-agent-identity]]"
---

# ADR-034 (PROPOSED): deterministic capability enforcement — denial becomes structural, and is proved by invocation

| Field | Value |
|---|---|
| **Status** | Proposed (2026-08-14) — **owner gates before any build.** This is a spec change and it is security-adjacent; nothing here is implemented. |
| **Authors** | Atlas (proposal for Vikram) |
| **Decision owner** | Vikram |
| **Backlog item** | `AGENT-TASKS.md` P2.2 — *deterministic enforcement* |
| **Driver** | FM4 — the badminton-analyzer dev persona merged ~15 PRs while its own `persona.yaml` denied `merge_pr`, then refused an identical invocation. Vault: `projects/AgentBootstrapNasikoMix/research-capability-enforcement.md`. |
| **Keeps** | [ADR-007](ADR-007-session-boundary.md)'s boundary — Barony does not own the agent loop, and nothing here proposes a sandbox or a driver. |

## 1. Summary

A denied capability must be **impossible to exercise**, not requested-and-refused-by-prose.
Today's enforcement is real *where wired* — the Claude Code `PreToolUse` hook (ADR-004) and
the pydantic-ai in-process interceptor — and it fails in four named ways, all of them
recorded rather than discovered here (`docs/DECISIONS-FOR-REVIEW.md` §E, items 1, 6, 7):

| # | Gap | Where it is already on the record |
|---|---|---|
| G1 | Enforcement **degrades silently to instruction** when the hook is not wired. | ADR-017 §1 — the whole reason `baron doctor` exists. Doctor makes the absence *findable*; it does not make the denial *hold*. |
| G2 | The **`bash -c` / wrapper bypass** stands. A payload inside an inline program string runs uninspected. | `guard.py` module docstring; §E item 7. Documented on purpose, not a regression. |
| G3 | **Project rules are parsed but never activated.** `.baron/rules.yaml` does not exist and nothing loads one. | ADR-016 §5–§6; §E item 6. |
| G4 | Enforcement is proved by **WIRING, not invocation.** No test drives a real Claude Code process and shows a denied verb actually failing. | ADR-017 §3.1; §E item 1 — the standing bound of the whole project. |

This ADR adds a fifth, which the sweep found in merged code and which is not on that list:

> **G5 — the enforcement configuration is inside the agent's own blast radius.**
> `evaluate_write` step 2 (`guard.py:714–722`) makes a persona's **own** `agents/<slug>/`
> directory always writable, and `.claude/settings.json` is an ordinary path a persona
> holding `write_code` may rewrite. The hook re-reads `--persona-file` on every invocation,
> so a persona can **grant itself a denied verb** by editing one line of its own spec, or
> **remove the hook entirely** by editing one JSON file — and the next tool call is
> adjudicated against the new document. Nothing in the rules artifact protects either path.

G5 is the one that makes the other four conditional. Layering more enforcement on top of a
policy the enforced party can rewrite is theatre of the exact kind ADR-002 exists to prevent.

**The proposal** is a four-layer model in which each layer's failure is visible to the one
below it, a bounded fix for the wrapper class, an opt-in test tier that proves enforcement
by invocation with a negative control, and an explicit *defer* on `.baron/rules.yaml`. The
real calls are in **§9 Owner decisions**; §4 is the recommendation, not the ratification.

## 2. Context — what already exists, so this ADR does not re-derive it

- **ADR-004** ships the `PreToolUse` hook over five sub-tool verbs (`push_main`,
  `force_push`, `merge_pr`, `write_path` scoping, `edit_other_personas`), conservative-deny
  on ambiguity, fail-closed on internal error, `BARON_GUARD_OVERRIDE` as a logged escape
  hatch. Its addendum §4.2 gives pydantic-ai a natively-`enforced` in-process seam over the
  **same** rules artifact.
- **ADR-016** made the rule table a rule *list*, shipped `baron rules list/validate/diff/explain`,
  and deferred the project-rules loader behind six one-way doors (§5.1–§5.6) plus the
  project-defined-verbs question (§6.1).
- **ADR-017** ships `baron doctor` — nine read-only checks that the wiring is present, with
  "verifies: wiring" printed on every run including green ones.
- **ADR-018** made `baron.enforcement` a per-call fact set at every return site, with
  `enforced` requiring both *a rule matched* and *the outcome turned on the persona*.
- **ADR-020** measured all four shipped adapters and found that **baron emits no mechanism**
  capable of omitting a tool — which is why the read verbs label `instructed`. The bound is
  exact: it is a claim about what baron ships, not about what a runtime can do.
- **ADR-027 / ADR-033** give per-persona SSH signing keys, `.barony/allowed_signers` as the
  registry, and signed review verdicts. They close the *evidence* half of the autonomous
  merger; ADR-033 §5 states the authority half — agents still act under the owner's forge
  identity — is untouched.
- **The 2026-08-01 source-level validation** (vault, same research note) settled the
  positioning this ADR must not overrun: *"a real, deterministic policy guard at the
  agent-tool interface for cooperating agents — **not** a security boundary."*

Two things follow that constrain everything below. **Client-side configuration is
flippable**, so no layer baron owns is a wall. And the owner's 2026-08-01 refinement stands:
*the spawn was the wrong target; the risk is one irreversible action, and its enforcement is
per-persona credentials plus branch protection* — a **platform** layer outside Barony.

## 3. Supersedes / Prior art

I set out to find (a) any prior decision that already makes a denial structural rather than
adjudicated, (b) any prior treatment of the wrapper-bypass class, (c) any prior attempt at a
live-runtime test, and (d) whether the self-amendment hole (G5) had already been seen and
dispositioned somewhere.

The sweep changed this ADR in three ways. It **removed** a proposed re-derivation of the
`.baron/rules.yaml` loader — ADR-016 §5 already records six one-way doors with positions, so
§4.4 answers those doors rather than restating them, and recommends *defer*. It **removed** a
proposed "deny the spawn" control — the vault note records the owner overruling exactly that
on 2026-08-01, with three reasons, and replacing it with the platform layer; §4.5 adopts the
owner's conclusion instead of re-litigating it. And it **found no prior art at all for G5**,
in either corpus: the closest is ADR-020's observation that baron emits no allow/deny list,
which is about tool omission, not about who may rewrite the policy. G5 is therefore stated
here as a new finding with a code citation rather than as a known bound.

<!-- BEGIN BARON PRIOR-ART -->
searched:
  - corpus: repo-adr
    location: docs/adr
    query: "enforcement, guard, capability denial, hook, interceptor, bypass, bash -c, permissions.deny, tool allow-list, live runtime test, invocation, rules.yaml, self-amend, persona.yaml write"
    date: 2026-08-14
  - corpus: repo-decisions
    location: docs/DECISIONS-FOR-REVIEW.md
    query: "not verified, enforcement, wiring vs invocation, guard bypass, rules loader, ritual fence"
    date: 2026-08-14
  - corpus: vault
    location: /Users/vikram/Obsidian/Brain
    query: "deterministic enforcement, ToolGuard, capability enforcement, interceptor, FM4, merge_pr denied, branch protection, per-persona credentials"
    date: 2026-08-14
hits:
  - ref: docs/adr/ADR-004-baron-guard-enforcement.md
    disposition: cites
    note: the mechanism this extends; §2.2's honest-mistake failure class and §2.3's fail-closed policy are both preserved unchanged.
  - ref: docs/adr/ADR-007-session-boundary.md
    disposition: cites
    note: the boundary this must not cross. Nothing proposed here drives an agent, makes a model call, or configures a forge.
  - ref: docs/adr/ADR-016-externalizable-capability-rules.md
    disposition: cites
    note: §5.1-§5.6 and §6.1 are the one-way doors for the project-rules loader. §4.4 answers them and recommends DEFER rather than re-deriving them.
  - ref: docs/adr/ADR-017-baron-doctor-wiring-selftest.md
    disposition: cites
    note: §3.1's wiring-not-invocation caveat is precisely what §4.3 sets out to upgrade. Doctor itself stays read-only and offline.
  - ref: docs/adr/ADR-018-adjudicated-enforcement-on-the-event.md
    disposition: cites
    note: the structural-refusal precedent. §4.1's config-path denial is modelled on evaluate_write step 0 - a refusal no capability unlocks, therefore adjudicated=False.
  - ref: docs/adr/ADR-020-read-verb-posture-measured-on-four-adapters.md
    disposition: cites
    note: its measured finding (baron emits no mechanism) is what §4.2 would deliberately invalidate for the claude adapter. Re-measurement is part of the work, not a side effect.
  - ref: docs/adr/ADR-027-agent-identity.md
    disposition: cites
    note: supplies the identity half of the platform layer (§4.5). Its own bound - agents still push under the owner's forge identity - is why the platform layer is a report, not a mechanism.
  - ref: docs/adr/ADR-033-signed-review-verdicts.md
    disposition: cites
    note: §5 states the authority half is untouched. This ADR does not close it either; it names it as the L3 owner decision.
  - ref: docs/adr/ADR-029-prior-art-gate.md
    disposition: cites
    note: the gate this block satisfies.
  - ref: docs/DECISIONS-FOR-REVIEW.md
    disposition: cites
    note: "§E items 1, 6, 7 are G1/G4, G3 and G2 respectively. §F2 (delivery-verified `instructed` via the ritual fence) is adjacent and stays deferred - see §6."
  - ref: /Users/vikram/Obsidian/Brain/projects/AgentBootstrapNasikoMix/research-capability-enforcement.md
    disposition: cites
    note: the driver. Supplies FM4, the 2026-08-01 source-level validation and its four verbatim bounds, and the owner's 2026-08-01 refinement that the merge - not the spawn - is the one hard gate.
  - ref: /Users/vikram/Obsidian/Brain/projects/AgentBootstrapNasikoMix/roadmap.md
    disposition: cites
    note: Phase 2 "Deterministic enforcement" - promoted to load-bearing 2026-07-30. This ADR is that line item's design record.
  - ref: docs/adr/ADR-030-observer-archetype.md
    disposition: distinct
    note: also concerns a capability posture, but from the opposite side - it constrains a persona by granting little. It relies on the write side holding, which is what this ADR is about; it does not decide anything this ADR decides.
<!-- END BARON PRIOR-ART -->

## 4. Recommendation

Four layers. The ordering is deliberate: **each layer's failure must be visible to the layer
below it**, and the lowest layer must not be writable by the party it governs.

| Layer | What it is | Who owns it | Status |
|---|---|---|---|
| **L0** | The policy documents are out of the agent's reach | baron (`guard`) | **NEW — §4.1** |
| **L1** | Deny by construction, in the runtime's own config | baron (`init`) | **NEW for claude — §4.2** |
| **L2** | The interceptor (hook / in-process) | baron (`guard`) | exists (ADR-004); hardened in §4.3 |
| **L3** | Platform: per-persona credentials + branch protection | **not baron** | reported, never configured — §4.5 |

### 4.1 L0 — the enforcement configuration becomes a structural refusal (closes G5)

Add a **config-protection path rule** to the rules artifact: for **every** persona,
regardless of capabilities, `Write`/`Edit`/`NotebookEdit` is refused when the normalized
target is one of

- `agents/*/persona.yaml` — **including the persona's own**,
- `.claude/settings.json`, `.claude/settings.local.json`,
- `.baron-waivers.yaml`, and any future project rules document,
- `.barony/allowed_signers` (ADR-027's trust root).

It is modelled on `evaluate_write` **step 0**, the path-escape refusal, and is placed
*before* the own-persona allow at step 2. That placement is the whole point: it is a
**structural** refusal, not a capability adjudication. No verb unlocks it, so
`adjudicated` stays `False` and the event reads `unevaluated` — consistent with ADR-018 §2.

**What changes for a persona.** Its own `AGENT.md`, notes, and everything else under
`agents/<slug>/` stay writable — only the capability document itself is fenced. Changing a
capability set stops being a self-service edit and becomes **a PR a human merges**, which is
where CODEOWNERS and ADR-033's signed verdicts already live.

**Why this is the highest-leverage item.** It costs one path rule and a precedence-order
change. Without it, L1 and L2 are both "enforcement, unless the enforced party decides
otherwise" — and FM4 is precisely a persona deciding otherwise.

**What it does not reach:** `~/.claude/settings.json`. It is outside the repo root, guard's
`cwd`-anchored comparison cannot see it, and `baron doctor` deliberately does not read it
(ADR-017 §3.5). An agent with shell can still unwire itself there. Stated, not fixed.

### 4.2 L1 — `baron init` emits `permissions.deny` for the claude adapter (chips at G1)

Today the claude kit's `.claude/settings.json` contains hook wiring and nothing else — that
is ADR-020's measured finding. Proposal: **also derive a `permissions.deny` block from the
persona's denials**, alongside the hook, from the same rules artifact.

The value is precisely that it is **not baron**. A `permissions.deny` rule is evaluated by
Claude Code itself, so it holds when `baron` is missing from `PATH`, when the venv is stale,
when the hook was never copied out of `agents/<slug>/runtime/`. G1's failure mode —
enforcement silently becoming zero — becomes enforcement silently becoming *weaker but
non-zero*, which is the worse-is-visible direction ADR-004 §2.4 already chose.

**Three consequences that must be accepted with it, not discovered later:**

1. **It invalidates an ADR-020 measurement on purpose.** `claude` currently measures "no
   `permissions`/`allowedTools`/`disallowedTools` anywhere in the emitted kit". After this,
   that test must fail and be replaced by a measurement of the *new* mechanism. The label
   `baron rules list` prints for the affected verbs may change, and `LABEL_CAVEAT` is built
   from `READ_VERB_MEASUREMENTS` so it moves with it. This is an intended re-measurement.
2. **It is a second policy surface.** Two artifacts now express one policy, and they can
   drift. Mitigation: generate it from `rules.load_rules()` + the persona, and add a
   `baron doctor` check that the emitted block still matches what the current rules artifact
   would generate — the same "refuse, don't ignore" discipline `rules.py` applies to
   documents.
3. **It inherits the wrapper weakness.** `permissions.deny` matches command strings, so
   `bash -c 'git push …'` evades it exactly as it evades guard. L1 is breadth, not depth.

**pydantic-ai needs nothing here** — its in-process seam is already unconditional for an
agent built through `build_agent` (ADR-004 §4.2). **code-puppy gets nothing**: it has no
pre-tool seam, which is why it is absent from `guard.KNOWN_RUNTIMES` (§E item 8), and
inventing one would put a claim on a surface that cannot honour it. **generic** is Tier-1
prose by definition.

### 4.3 L2 — bound the wrapper class, and prove the layer by invocation (G2, G4)

**(a) Recurse one level into inline program strings.** `bash -c`, `sh -c`, `zsh -c`, and the
same forms behind a recognised `env` prefix: extract the program string, re-run **the same
evaluators** over it, depth-capped at 1. It is not a new parser — that is the property that
keeps it from becoming an arms race, and it mirrors ADR-016 §4.2's rule that a second
implementation must never appear.

Where the inner string cannot be tokenised (nested quoting, substitution), apply
**conservative-deny narrowed to the three high-stakes verbs** — `merge_pr`, `push_main`,
`force_push` — so the false-positive cost lands only on personas that deny those verbs
anyway. A persona holding them is unaffected. This matters because ADR-017 §3.6 is right
that the first unjustified shout spends the credibility the mechanism runs on.

**Deliberately NOT closed:** `python -c`, `eval`, base64/`printf` indirection, a script
file, `xargs`, a raw GitHub API call, a different git client, the web UI. Those are the
adversarial half; ADR-004 §2.2 scoped the mechanism to the honest-mistake class and this
does not change that. `bash -c` is in scope because it is the one people hit **by accident**.

**(b) The live-invocation test tier.** A new opt-in test that drives a real runtime:

1. `baron init` a throwaway project into a temp dir; copy the emitted runtime kit into place.
2. Put a **shim `git` and `gh` first on `PATH`** that record their invocation to a sentinel
   file and exit 0. Nothing real is pushed or merged.
3. Run `claude -p "<task whose obvious completion requires the denied operation>"` with a
   persona that **denies** the verb.
4. Assert: the **sentinel does not exist** (the operation did not run), `.baron/guard-override.log`
   is unchanged, and the disk sink carries a `deny` row with `baron.enforcement: enforced`.

The sentinel is what makes this *invocation* evidence: it asserts the operation did not
execute, not that a hook was configured.

**The negative control is load-bearing, not a nicety.** A model that simply declines the
task produces a green run with no enforcement whatsoever — which is FM4's exact shape, a
prose refusal read as a mechanism. So the same prompt is run against a persona that
**grants** the verb, and the sentinel **must** appear. If the control does not fire, the run
reports **INCONCLUSIVE**, never PASS.

Gating: `@pytest.mark.live_runtime`, `BARON_LIVE_RUNTIME=1`, excluded from the default CI
job (it needs a model, credentials, network, and money, and it is nondeterministic), run
from a separate manual/scheduled workflow. **`baron doctor` does not change** — it stays
read-only, offline and project-scoped. This proof is a test artifact, not a product command;
the ADR-007 boundary is that baron may *test against* a runtime, never *drive* one in
production.

What it buys: §E item 1 — the standing bound of the whole project, and part of ADR-001's
acceptance bar — becomes *"unverified for three adapters; verified by invocation for claude
on N verbs, on demand."* That is a smaller claim than it sounds and should be published as
exactly that.

### 4.4 `.baron/rules.yaml` — recommend DEFER, but settle the filename now (G3)

**Recommendation: do not activate it in this slice.** It closes none of G1/G2/G4/G5, and it
is add-only by ADR-016 §5.1, so it cannot strengthen enforcement of a built-in verb at all —
it only lets a project add denials it does not have today. Building it alongside four
security-relevant changes would spend the review budget in the wrong place.

Positions on ADR-016's doors, recorded so the next round starts here (all §5 references are
to ADR-016):

| Door | Position |
|---|---|
| §5.1 add-only, deny-only | **Hold.** Built-in deny always wins; a project file may never grant. |
| §5.2 / §6.1 no new verbs | **Hold.** The vocabulary stays frozen; custom rules for existing verbs are the 90% case. |
| §5.3 version ranges on both artifacts | Declare an explicit supported **range** per artifact before the first file exists in the wild. Exact-match negotiation does not survive two independently versioned documents. |
| §5.4 malformed → REFUSE | **Hold.** A `RulesError` becomes an exit-2 DENY, deliberately unlike `.baron-waivers.yaml`'s soft-fail. |
| §5.5 cache safety | `load_rules()` becomes path-keyed the moment it is path-dependent; the long-lived pydantic-ai process is the case that finds the bug. |
| §5.6 filesystem convention | **Answer it now, it blocks nothing: root-level `.baron-rules.yaml`.** `.baron/` is machine-written state; human-authored config sits at the root next to `.baron-waivers.yaml`. Settling the name costs nothing today and is a rename later. |

Note the interaction with §4.1: whatever the file is called, **L0 must fence it** — a rules
document the governed agent can edit is not a rules document.

### 4.5 L3 — the platform layer: report it, never configure it

The owner's 2026-08-01 conclusion stands and this ADR adopts it rather than re-opening it:
the hard gate is **per-persona credentials plus branch protection**, because GitHub says no
in a way a client-side settings flip cannot undo. ADR-027 supplies the identity; ADR-033 §5
records that the *authority* half is still open — agents act under the owner's forge token.

Proposal, bounded by ADR-007: `baron doctor` gains **read-only, INFO-or-FAIL checks** that
report whether the platform layer is present (is branch protection on for the default
branch; does the acting persona's push credential differ from the owner's). Baron **does
not configure a forge**, does not create tokens, and does not mint credentials. Reporting an
absent wall is governance; building the wall is somebody else's layer.

## 5. Build now vs defer

| # | Item | Layer | Call |
|---|---|---|---|
| W1 | Config-protection path rule + precedence change | L0 | **Build now** — highest leverage, smallest diff, entirely inside baron |
| W2 | Wrapper recursion (depth 1) + narrowed conservative-deny | L2 | **Build now** — closes the accident half of G2 |
| W3 | Live-invocation test tier, claude, one verb, with the negative control | L2 | **Build now** — this is what makes the rest a measurement instead of a claim |
| W4 | `permissions.deny` emission + the ADR-020 re-measurement + the doctor drift check | L1 | **Build now if OD-2 is yes** — genuinely optional; W1+W2+W3 stand alone |
| W5 | `baron doctor` platform-layer report | L3 | **Build now** — cheap, read-only, and it is the honest way to say "the real wall is not here" |
| D1 | `.baron-rules.yaml` loader | — | **Defer** (§4.4), filename settled now |
| D2 | code-puppy structural enforcement | — | **Defer indefinitely** — no pre-tool seam exists to build on |
| D3 | Per-runtime capability matrix (`§F1`) | — | **Defer** — a user-visible output redesign; W4 will make its absence louder |
| D4 | Ritual-fence delivery verification (`§F2`) | — | **Defer** — a new claim class needing its own vocabulary decision |

**Scope of the whole proposal:** runtimes `claude` and `pydantic-ai`; verbs the five
guard-covered sub-tool verbs, plus the new L0 config paths. No vocabulary change. No new
capability verbs. `rules_version` bumps for W1 and W2.

## 6. Honest bound — what stays true after all of this

Stated plainly, because a four-layer diagram invites the wrong inference.

- **A hostile workspace wins.** An agent with a shell can edit `~/.claude/settings.json`
  (outside the repo root, invisible to L0 and to doctor), install a different git client,
  or reach the forge API directly. None of L0–L2 is a sandbox, and this ADR does not make
  one. The positioning does not change: **a deterministic policy guard at the agent-tool
  interface for cooperating agents, not a security boundary.**
- **The remaining wrapper forms are not closed** (§4.3a). One level of recursion into
  `bash -c` is a narrowing, not a wall.
- **Credentials are not revoked.** `merge_pr` becomes genuinely impossible only at L3, and
  L3 is reported, not built.
- **Invocation proof is per-run and probabilistic.** A green live test shows the block
  happened *once, on that model, on that prompt*. It does not show it always will, and the
  INCONCLUSIVE state exists because the failure mode is a model that never tried.
- **`instructed` remains verified at emission, never at receipt** (§F2). This ADR does not
  move that ceiling, and the 0.53 operational-fidelity number lives there.
- **L1 adds a surface that can drift** (§4.2 consequence 2). The drift check is a mitigation,
  not an elimination.
- **L0 protects paths, not intent.** A persona can still propose a capability change; it
  just cannot land one alone. That is the intended shape, and it means the gate is only as
  strong as the human review behind CODEOWNERS.

## 7. Alternatives considered

| Alternative | Why not |
|---|---|
| **Deny the spawn** — stop a dev persona instantiating reviewer/merger subagents | Overruled by the owner 2026-08-01, on three arguments this ADR accepts: spawning is a first-class dev capability, a spawned worker runs under the spawner's own authority (no new power appears), and `disallowedTools` is client-side and flippable. The risk is one irreversible **action**, not the spawn. |
| **Recurse arbitrarily deep into wrappers / interpret `python -c`** | An arms race against an adversary ADR-004 §2.2 explicitly does not model, paid for in false positives that spend doctor's credibility (ADR-017 §3.6). Depth 1 over known shell forms is where the honest-mistake curve flattens. |
| **Make `baron doctor` drive a live runtime** | Crosses ADR-007 and breaks doctor's contract: it is read-only, offline, and its verdict must be reproducible on a laptop and in CI. A nondeterministic, credentialed, paid check cannot live behind the same exit code. |
| **Fence the persona's whole `agents/<slug>/` directory** | Too broad. A persona legitimately maintains its own `AGENT.md` and notes; fencing the directory would break the COORDINATION.md owner row for no security gain. Only the capability document needs the fence. |
| **A new label value for invocation-verified enforcement** | A third value in the product surface is a vocabulary change and would land in `--json` for consumers who cannot see the caveat. Record the *evidence kind* beside the measurement (the `READ_VERB_MEASUREMENTS` pattern) and leave `enforced`/`instructed` alone. |
| **Activate `.baron/rules.yaml` in this slice** | Closes none of G1/G2/G4/G5, and add-only rules cannot strengthen a built-in verb. §4.4. |
| **Do nothing; document the bounds harder** | The bounds are already documented well. FM4 shows a well-documented bound is still an unenforced one, and G5 means today's posture can be undone by the governed party in one edit. |

## 8. Consequences

**Good.** The FM4 shape — a persona exercising a verb its own config denies — requires a
human-merged PR after W1. G1 degrades to weaker-not-absent after W4. The accident half of
G2 closes after W2. §E item 1 moves for the first time since it was written, after W3. The
product claim gets a measurement behind it that is not baron marking its own homework.

**Costs.** A `rules_version` bump and a precedence-order change in the most safety-critical
function in the codebase. An intended test failure in `test_adapter_omission.py` and a
published label that may change (W4). A test tier that costs money and can be flaky, which
means a policy for what an INCONCLUSIVE run does to a release. And one workflow friction
that will be felt immediately: **changing a persona's capabilities now requires a PR**,
including for the owner working solo.

## 9. Owner decisions

Bring these to Vikram. **OD-1 through OD-3 are blocking** — no code should be written until
they are answered. OD-4 through OD-7 have recommended defaults that can be taken as written.

**OD-1 (BLOCKING) — L0: does a persona lose write access to its own `persona.yaml`?**
Recommendation: **yes.** It is the highest-leverage change here and it is what makes the
other layers non-conditional. The cost is real and lands on the owner first: a capability
change becomes a PR, for everyone, always. The narrower option — fence the file only for
personas that deny at least one verb — is *not* recommended, because it makes the protection
a function of the document being protected.

**OD-2 (BLOCKING) — L1: does `baron init` start emitting `permissions.deny`?**
Recommendation: **yes**, accepting all three consequences in §4.2 — the deliberate ADR-020
re-measurement, the second policy surface, and the inherited wrapper weakness. The strongest
argument against is that it publishes a *stronger-looking* posture that is still evadable by
`bash -c`, and this project's whole differentiator is not doing that. If that argument wins,
W4 drops and W1/W2/W3/W5 proceed unchanged.

**OD-3 (BLOCKING) — is a live-runtime test tier acceptable at all?**
It needs a model, credentials, network access, and money; it is nondeterministic; and it
introduces an INCONCLUSIVE verdict that CI has no precedent for. Recommendation: **yes,
opt-in and out of the default CI job.** Sub-question that needs an answer with it: *does an
INCONCLUSIVE or failing live run block a release, or is it advisory?* Recommendation:
**advisory for the first slice**, revisited once its flake rate is known — but say so in
`STATUS.md`, because an advisory gate presented as a gate is the failure this repo names.

**OD-4 — the wrapper posture.** Recommendation: **recurse one level, narrow the
conservative-deny to the three high-stakes verbs** (§4.3a). Alternatives: deny wrapper forms
outright for any persona with denials (safer, materially more false positives), or leave the
class bounded and documented as today.

**OD-5 — `.baron-rules.yaml`.** Recommendation: **defer the loader** (§4.4); settle the
name and location now (root-level, next to `.baron-waivers.yaml`), and record the six
positions as this ADR's answers so the next round does not re-derive them.

**OD-6 — does `baron doctor` report on the platform layer (L3)?**
Recommendation: **yes, report only.** Reporting an absent wall is governance; building it
crosses ADR-007 and would put forge-configuration authority inside a tool agents run. Note
this is the first doctor check whose answer depends on the network, which argues for INFO
rather than FAIL, and for it being skippable offline.

**OD-7 — scope.** Recommendation: **`claude` + `pydantic-ai` only**; code-puppy stays
deliberately absent (no pre-tool seam), generic stays Tier-1 prose. Confirm that a
capability posture which is *structurally* different across adapters is acceptable to
publish before ADR-020's one-label-per-verb collapse is revisited (`§F1`).

## 10. Decision record

- [ ] Approved as written
- [ ] Approved with changes
- [ ] Needs revision
- [ ] Rejected

| Decision | Answer | Date |
|---|---|---|
| OD-1 — L0 fences own `persona.yaml` | | |
| OD-2 — L1 emits `permissions.deny` | | |
| OD-3 — live-runtime test tier (+ release policy) | | |
| OD-4 — wrapper posture | | |
| OD-5 — `.baron-rules.yaml` defer + name | | |
| OD-6 — doctor reports L3 | | |
| OD-7 — adapter scope | | |
