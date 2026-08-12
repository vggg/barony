---
created: 2026-08-12
accepted: 2026-08-12
type: decision
status: accepted
decided_by: Vikram
adr: 023
project: barony
related:
  - "[[docs/adr/ADR-002-ways-of-working-2026-07]]"
  - "[[docs/adr/ADR-008-ways-of-working-2026-07-31]]"
  - "[[docs/adr/ADR-006-baron-init-template-packaging]]"
---

# ADR-023: The emitted config filenames are governed artifact types

| Field | Value |
|---|---|
| **Status** | **Accepted** (2026-08-12) |
| **Date** | 2026-08-12 |
| **Authors** | Vikram + Iris (Claude) |
| **Extends** | [ADR-002](ADR-002-ways-of-working-2026-07.md), [ADR-008](ADR-008-ways-of-working-2026-07-31.md) — same promotion mechanism |
| **Evidence base** | A single first-party incident in the Irisidian vault, 2026-08-12 (§6) |
| **Decision owner** | Vikram |

> **Numbering.** 010–022 are claimed on unmerged branches (PRs #29, #32, #35). This record takes
> **023** and does not reuse a reserved number, per the convention in `docs/adr/README.md`. That
> README does not exist on `main` — it arrives with PR #35 — so **this ADR adds no index row.**
> Whoever lands #35 should add one. Flagged rather than silently skipped.

---

## 1. Summary

[ADR-002](ADR-002-ways-of-working-2026-07.md) established the pattern, and
[ADR-008](ADR-008-ways-of-working-2026-07-31.md) repeated it: when a coordination failure happens in
the field and the fix is proven there, promote it from a project-local rule to a framework default,
so the next bootstrapped project starts with it.

This is a third instance, and it differs from the first two in a way worth naming. ADR-002 and
ADR-008 promoted rules about *how personas behave*. This one promotes a rule about **the framework's
own output**: `baron init` emits a fixed set of config filenames, and nothing tells an agent that
those names are taken.

The failure mode is not a persona misreading a rule. It is an agent **creating a file whose name
already means something**, and thereby acquiring authority it was never granted — because in a
precedence chain, **position is authority**.

## 2. The failure

On 2026-08-12, an agent (Iris, in the Irisidian vault) was asked to write a briefing document for a
second assistant joining the machine. It wrote the briefing to **`/COORDINATION.md` at the vault
root**.

Two things were wrong, and only the second is obvious in hindsight:

1. **The content conformed to no schema.** `COORDINATION.md` is an emit-time template — 213 lines,
   with a defined shape: cross-agent protocol, hot files, lock mechanics, review-and-merge. The
   briefing was prose. It shared a filename with fourteen conforming instances across
   `vanar-collab`, `baddie-analyzer-collab`, `walmart-seller-api-collab`, `projects/GardenTwin`,
   `barony-demo`, and the vendored copies.

2. **Its position granted it authority.** That vault's `CONVENTIONS.md § Contradictory rules` places
   `COORDINATION.md` *above* `CONVENTIONS.md` in the precedence chain. A briefing at the root would
   therefore have been read by any agent resolving a rule conflict as **governing protocol for the
   whole vault**.

The agent had **flagged the collision in the document's own text** — and shipped it to that path
anyway. That detail matters for choosing the remedy: this was not a knowledge gap. Naming a risk in
prose did nothing, because nothing consumed the prose. Which is the same conclusion ADR-004 reached
about capability denials, and ADR-008 §1 reached about labels.

Caught by the owner, in one sentence. **No mechanism caught it.**

## 3. Why this generalizes past one vault

The obvious objection: one vault, one agent, one bad path — why is this a framework concern?

Because **Barony is what creates the collision surface.** `baron init` emits, into every scaffolded
project:

```
CONVENTIONS.md   COORDINATION.md   CLAUDE.md   README.md
BOOTSTRAP.md     BOOTSTRAP-ADMIN.md   START.md   ORCHESTRATE.md
PARTICIPATE.md   QUICKSTART.md      manifest.example.yaml
```

Every adopter inherits that namespace, and the emitted `CONVENTIONS.md` tells personas the
precedence order without ever telling them **which files are allowed to hold those names**. The rule
that would have prevented this is *exactly* the kind of rule ADR-002 exists to promote: proven in the
field, absent from the default.

It compounds in the two-repo layout ADR-001 §4 defines. `COORDINATION.md` legitimately exists at the
collab-repo root **and** at `<vault>/projects/<name>/`. An agent that has seen one has no way to know
whether a third location is legitimate or invented.

## 4. Decisions

### §4.1 — Reserved filenames

**Decision.** Add to the emitted `CONVENTIONS.md`: these filenames are **governed artifact types with
schemas**, not free names.

| Filename | What it is |
|---|---|
| `CONVENTIONS.md` | Project-wide rules of the road |
| `COORDINATION.md` | Multi-persona protocol + workflow |
| `CLAUDE.md` | Per-workspace agent config |
| `AGENT.md` | Persona-specific rules (per-persona directory) |
| `BOOTSTRAP.md` / `BOOTSTRAP-ADMIN.md` | Collaborator / owner onboarding |
| `START.md`, `ORCHESTRATE.md`, `PARTICIPATE.md`, `QUICKSTART.md` | Entry-point docs |

**Before creating a file with one of these names, confirm it conforms to the template that emitted
it.** If the content does not fit that schema, it needs a different filename — match the genre
instead: briefings and onboarding in a meta location, inter-agent messages in `_handoff/`, working
notes in the project area.

### §4.2 — A reserved name is scoped to its emitted location

**Decision.** State that the precedence chain names the file **at its emitted location**, not any
file bearing that name. Concretely, for the emitted scaffold:

- `COORDINATION.md` means the collab-repo root copy, or `<vault>/projects/<name>/COORDINATION.md`.
- **No other `COORDINATION.md` may be created**, and in particular none at a *vault root* — a vault
  root is not a project, so a file there claims authority over every project in it by position alone.

Precedent worth citing in the emitted text: **this repo makes the same choice deliberately.**
`CLAUDE.md` states there is no `CONVENTIONS.md` / `COORDINATION.md` / `agents/` at the repo root,
because Barony does not dogfood its own multi-persona pattern. That is a considered absence, and it
should read as one.

### §4.3 — The precedence orders are inverted

**A defect found while drafting this ADR, not a proposal. Resolved by owner decision 2026-08-12:
option (a) refined by (c) — the template's order stands, the Irisidian vault changes to match, and
both documents gain the constraints/detail axis.**

The two precedence chains currently in use disagree:

| Source | Order |
|---|---|
| **Emitted `CONVENTIONS.md`** (`skills/barony/assets/collab-repo/CONVENTIONS.md § Contradictory rules`) | `CONVENTIONS.md` → `COORDINATION.md` → persona `AGENT.md` |
| **Irisidian vault** (`_meta/CONVENTIONS.md § Contradictory rules`) | workspace `CLAUDE.md` → `COORDINATION.md` → `CONVENTIONS.md` |

They are **opposite on CONVENTIONS-vs-COORDINATION**. The template says the rules file wins; the
vault says the coordination file wins. Both are live, and an agent that has read both has no
consistent answer.

`observed` — I read both files today; this is not inferred.

Three ways out:

- **(a) Template is right** — most-general-wins. `CONVENTIONS.md` is repo-wide, `COORDINATION.md` is
  protocol, `AGENT.md` is local. Fix the vault to match.
- **(b) Vault is right** — most-specific-wins, which is what the vault's own sentence says it is
  doing (*"the more specific file wins"*). Fix the template to match.
- **(c) They are different chains for different things** and both are correct in context. Then say so
  explicitly in both, because today neither does.

#### Recommendation: **(a), refined by (c). Change the vault, not the template.**

> **Reversal, recorded.** Rev. 1 of this ADR recommended **(b)** — on the grounds that *"the more
> specific file wins"* is the stated principle and the template does not implement it. That was
> wrong, and it was wrong because I had not asked **what kind of rule** each chain orders. Rev. 2
> reverses it. The original reasoning survives only in the narrow form kept at §4.3.3.

**4.3.1 — Most-specific-wins is correct for configuration and wrong for constraints.**

The vault's principle is sound in isolation. It is the standard config cascade — CSS specificity,
`.gitconfig` layering — and it is right whenever narrower scope means *better-informed*.

But these files do not only carry configuration. They carry **constraints**, and constraints cascade
the other way. A firewall does not let the local process override the org policy. Most-specific-wins
answers *"which database do I use"*; it is exactly wrong for *"never delete `_handoff/` files."*

**4.3.2 — The two orders disagree most sharply on the one file that makes this dangerous.**

Look at what sits at the ends of each chain:

| | Template | Vault |
|---|---|---|
| Per-agent file | persona `AGENT.md` — **bottom, loses** | workspace `CLAUDE.md` — **top, wins** |

Those are the analogous file. And **every agent's declared write zone includes its own workspace**
(`_meta/AGENTS.md`, seven personas — `observed`). So under the vault's order, *the file an agent can
edit itself outranks the file holding the `## Never` list and the claims ladder.*

That is a self-service escape hatch from governance, and it does not require bad intent: a
workspace `CLAUDE.md` written for local convenience silently outranks a vault-wide constraint, and
nothing surfaces the conflict. It is the **Otto incident** shape — an agent operating outside
governance through a mechanism nobody had closed. (That incident is what put branch protection on
`main`; the identity work it triggered is ADR-011, reserved on the unmerged `adr-011-agent-identity`
branch and therefore not linkable from here.)

**4.3.3 — The template's order is considered, not accidental.**

Three independent signals in the emitted `CONVENTIONS.md` itself:

- `§ Contradictory rules` closes with **"Don't auto-fix shared config"** — shared config is
  explicitly not the persona's to change.
- The never-list includes **"a persona acting outside the scope declared in its `AGENT.md`"** — the
  persona file **binds** the persona; it does not empower it. A leash, not a license.
- `§ _handoff/ lifecycle` gates **`AGENT.md` edits behind a PR** while letting `_handoff/` push
  direct — the local file is treated as substantive precisely because it is load-bearing.

Every one of those is consistent with `AGENT.md` ranking last. The template implements a coherent
governance posture; the vault implements a coherent *configuration* posture. Barony is a governance
framework.

**4.3.4 — The field has already voted, and the vault is the outlier.**

`observed`, 2026-08-12 — surveyed every Barony-scaffolded collab repo on this machine:

| Repo | Order |
|---|---|
| `vanar-collab` | `CONVENTIONS` → `COORDINATION` → `AGENT.md` (template order, verbatim) |
| `baddie-analyzer-collab` | `CONVENTIONS` → `COORDINATION` → `AGENT.md` (template order, verbatim) |
| `walmart-seller-api-collab` | *no `§ Contradictory rules` section* — predates it |
| Irisidian vault | **inverted** |

**No live persona `AGENT.md` overrides a `CONVENTIONS.md` rule** in either repo — I grepped all 17
persona files for override language; the single hit was `yukti/AGENT.md` using "supersedes" about an
old cron schedule. So **(a) has no downstream dependency to break**, which was the open risk in
rev. 1. The vault is a population of one.

**4.3.5 — The refinement, and the actual defect.**

Adopting (a) alone would leave the real problem in place: **neither file says what kind of rule it is
ordering.** That ambiguity is what let the two orders drift apart unnoticed for months. So (a) should
land with (c)'s explicitness — one axis, stated in both:

> **Constraints resolve most-general-wins. Operational detail resolves most-specific-wins.**

`CONVENTIONS.md`'s never-list and claims ladder bind everyone and cannot be locally overridden.
Which tools an agent uses, which paths it writes, which database it points at — local, and should
win locally. Today both documents pretend a single chain covers both kinds, and it does not.

**Consequence for scope:** this makes §4.3 a **template edit too**, not just a vault fix. That is
larger than rev. 1 contemplated — see §5.

**4.3.6 — A weak but real confirmation.** Under the template's order, `CONVENTIONS.md` outranks
`COORDINATION.md`, so the misplaced briefing that triggered this ADR would have been *subordinate* to
the rules file rather than superior to it. The template's order would have contained the blast
radius; the vault's order is what turned a misplaced file into a governance problem. Weak evidence —
a single incident, and not the reason to prefer (a) — but it points the same way.

## 5. Scope of the change — **accepted and applied 2026-08-12**

Deliberately small. No code, no CLI surface, no schema change.

| Surface | Change |
|---|---|
| `skills/barony/assets/collab-repo/CONVENTIONS.md` | New subsection under `§ Contradictory rules`; `Recent changes` entry (3-entry cap). **If §4.3 is accepted:** also rewrite `§ Contradictory rules` itself to state the constraints/detail axis (§4.3.5). The order does not change — the template's order is the one being kept — but it gains the sentence that says *why*. |
| `cli/src/baron/data/templates/collab-repo/CONVENTIONS.md` | **Identical edit.** The two copies are byte-identical today (`md5 5901c1d3…`, verified) and a CI drift guard enforces it — ADR-006. Editing one and not the other fails CI. |
| `CHANGELOG.md`, `STATUS.md` | Per the docs-with-code rule in `CONTRIBUTING.md` |
| Version | Patch or minor — owner's call; it is a new template section, which `CLAUDE.md § versioning` reads as **minor**. |

**Not proposed: lint enforcement.** A test could assert no unexpected `COORDINATION.md` exists in a
scaffolded tree. It is deliberately left out — same posture the vault's claims ladder took, and for
the same reason: the cheap first move is to say the rule, and whether saying it changes behaviour is
the open question. Adding a mechanism now would answer a question nobody has asked yet.

## 6. Evidence

| Claim | Strength | Basis |
|---|---|---|
| `COORDINATION.md` is an emit-time template with a fixed schema | `observed` | `skills/barony/assets/collab-repo/COORDINATION.md`, 213 lines |
| ~14 conforming instances exist on this machine | `observed` | `find` across `/Users/vikram/Workspace` + the vault, excluding `.git` and worktrees |
| The two template copies are byte-identical and drift-guarded | `observed` | `md5 -q` on both → `5901c1d31193356235769b5bf2b6ceef`; guard per ADR-006 |
| The precedence orders are inverted (§4.3) | `observed` | Read both `§ Contradictory rules` sections, 2026-08-12 |
| Both live collab repos carry the template's order verbatim | `observed` | `vanar-collab`, `baddie-analyzer-collab`, read 2026-08-12. `walmart-seller-api-collab` has no such section. |
| No live persona `AGENT.md` overrides a `CONVENTIONS.md` rule | `observed` | Grepped all 17 persona files in both repos for override language; one hit (`yukti`), benign — "supersedes" about a cron schedule |
| Every agent's write zone includes its own workspace | `observed` | `_meta/AGENTS.md`, seven personas |
| Most-general-wins is the right posture for constraints (§4.3.1/§4.3.5) | `inferred` | Reasoning about what these documents are *for*. Neither file states this axis today — it is a proposal, not a reading. |
| This repo has no root-level COORDINATION.md by design | `observed` | This repo's `CLAUDE.md`, line 31 |
| The rule would have prevented the incident | `inferred` | It addresses the stated cause; not tested |
| Adopters other than this machine have hit this | **not claimed** | No evidence. One incident, first-party. |

The last row is the honest limit of this ADR. **The evidence base is a single incident in one
vault** — thinner than ADR-002's or ADR-008's, both of which promoted findings from a multi-persona
pilot under real load. What argues for promoting anyway is not frequency but **structure**: the
namespace is created by `baron init`, so the exposure is universal even though the observation is
singular. If that is not enough, the honest alternative is §7's *"wait for a second instance"* — and
that is a legitimate owner call, not a failure of the proposal.

## 7. Alternatives considered

- **Fix the vault only, promote nothing.** Cheapest, and correct if the collision really is
  vault-specific. Rejected because the namespace is emitted, not local — but it is the alternative
  with the strongest claim if you weigh the thin evidence base heavily.
- **Wait for a second occurrence.** Consistent with not over-fitting to one event. The cost of being
  wrong is asymmetric though: the rule is three sentences in a template, and the failure it prevents
  is an agent silently acquiring vault-wide authority.
- **Enforce in lint instead of stating in prose.** Stronger, and tempting given that the agent *did*
  name the risk in prose and proceed anyway. Deferred, not rejected — see §5. If §4.1 lands and a
  second collision still happens, that is the evidence that prose is insufficient, and it becomes its
  own ADR.
- **Rename the emitted files to something less collidable** (e.g. `barony-coordination.md`).
  Rejected: breaks every adopter, and the names are good names. The problem is that they are
  *undeclared*, not that they are wrong.

## 8. Open questions

1. ~~**§4.3 — which precedence order is canonical?**~~ **Resolved 2026-08-12** — (a) refined by (c).
   Template order stands; the Irisidian vault inverted its chain to
   `_meta/CONVENTIONS.md` → project `COORDINATION.md` → workspace `CLAUDE.md`, and both documents
   gained the constraints/detail axis. Applied in the same pass, not deferred.

   Recorded for the record: the recommendation **reversed** between rev. 1 and rev. 2 of this ADR.
   The reversal and its cause are inline at §4.3 rather than quietly edited.

   **Consequence worth restating, because it is bigger than a reordering:** in the Irisidian vault,
   workspace `CLAUDE.md` moved from **first to last**. Any agent that was relying on its own
   workspace file to override a vault rule has lost that ability — which is the intent. The survey
   at §4.3.4 found no such reliance in the collab repos, but it did **not** cover every workspace
   `CLAUDE.md` on the machine. Residual risk, stated rather than closed.
2. **Does the claims ladder get promoted in the same pass?** The Irisidian vault adopted
   *"a claim of verification is not verification"* on 2026-08-05, and that convention explicitly
   noted that folding it into the emitted `CONVENTIONS.md` needs its own ADR. It is still unpromoted.
   Two pending template promotions now exist. They could land as one `ways-of-working-2026-08` ADR in
   the ADR-002/008 family. **Deliberately not bundled here** — bundling would be a scope decision
   made on the owner's behalf, and the claims ladder is the larger of the two.
3. **Should `AGENTS.md` be on the reserved list?** It is a governed type in the Irisidian vault
   (`_meta/AGENTS.md`, the agent registry) but is **not** part of the emitted collab-repo scaffold —
   personas are declared per-directory in `AGENT.md`. Listed here as a question rather than added to
   §4.1's table, because I could not establish it is a Barony artifact.
4. **Do existing scaffolded projects need an audit?** Two non-conforming instances are already known
   in the Irisidian vault (`_meta/archive-jarvis/alfred/`, 26 lines; `work/02 - Projects/
   multiagent-brownbag/`, 69 lines — both far short of the 213-line template). Neither sits at a root
   position, so neither is harmful. Not proposed as part of this ADR.
