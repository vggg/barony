---
created: 2026-08-14
type: decision
status: accepted
accepted: 2026-08-14
adr: 030
project: barony
authors: Atlas (proposal for Vikram)
related:
  - "[[docs/adr/ADR-013-observation-plane-events-and-sinks]]"
  - "[[docs/adr/ADR-020-read-verb-posture-measured-on-four-adapters]]"
  - "[[docs/adr/ADR-024-fleet-health]]"
  - "[[docs/adr/ADR-026-persona-sidecar]]"
---

# ADR-030 (ACCEPTED): the `observer` archetype — a strictly read-only watcher with one zone

> **RATIFIED 2026-08-14.** The owner gated this one, and accepted it as written. The
> `observer` archetype has been live on `main` since CLI 0.13.0 and ships in **v1.19.0**,
> so this changes the record rather than the code. Nothing below is rewritten — including
> the open questions and the honest limits on what a read-only watcher can actually
> establish.

| Field | Value |
|---|---|
| **Status** | Accepted (2026-08-14) — ratified by the owner; shipping in v1.19.0 |
| **Scope note** | Renumbered **029 → 030** at queue integration (2026-08-14): 029 was already taken by the prior-art gate (PR #49), which was opened first. 027 is the identity ADR (PR #48), 028 the merge gate (PR #46). Numbers are never reused; see `README.md § Numbering`. |
| **Decision owner** | Vikram |

## 1. Problem

The coordination substrate now emits more than anyone reads. `baron status` computes stalls,
`baron health` (ADR-024) rolls up verdict metrics, the ADR-013 event plane records what
happened, the ledgers and `_handoff/` carry the governance record — and all of it is pull-only.
Nobody is *watching*. The owner's scope note (`_handoff/tasks/2026-08-13-1500-atlas-observer-agent-todo.md`)
names the intent: **as the substrate comes online, employ a first agent — an independent
observer that continuously watches the whole setup and keeps notes.**

It is also the cheapest possible first fleet member: **a persona that cannot change anything
has no blast radius.** If the archetype is wrong, the cost is a directory of notes.

## 2. Decision

Add a sixth shipped archetype, **`observer`**: strictly read-only, cron-triggered, with one
write zone of its own.

```yaml
capabilities:
  allow: [read_code, read_collab, write_path: [observations, _handoff]]
  deny:  [write_code, write_path: [wiki, findings, decisions],
          open_pr, run_tests, merge_pr, push_main, force_push, edit_other_personas]
```

Template: `agents/__OBSERVER__/{persona.yaml,AGENT.md}`. CLI surface:
`baron init --personas observer:<slug>` (`scaffold.ARCHETYPE_TEMPLATES`).

### 2.1 Why the profile is shaped this way

- **Reads everything, deliberately.** The value is breadth: handoffs, ledgers, wiki, personas,
  git and PR activity, the event plane, the health rollups. Narrowing the read side would only
  make the notes wrong.
- **Writes one zone.** `observations/` is its own single-writer surface. `_handoff/` is allowed
  so it can raise something to the Librarian — the only escalation path it has.
- **No numbering authority.** `findings/` and `decisions/` stay the Librarian's single-writer
  surface. An observation that deserves a number is *proposed* by handoff and numbered by the
  Librarian. This is why `observations/` is a **dated, unnumbered** zone and not a ledger with
  an `O<N>` allocator: giving a read-only persona a second numbering authority would recreate
  the exact coupling the archetype exists to avoid.
- **No `run_tests`.** An observer that runs the suite is producing new state, not reading
  existing state, and its notes stop being reproducible from a `git clone`.

### 2.2 What is actually enforceable (and what is not)

The **write** boundary is mechanical. With `write_code` denied and `write_path` allowing only
`[observations, _handoff]`, `baron guard`'s file-op precedence
(`capability-rules.v1.yaml § file_ops`, rules 3–5) denies every other path, and its command
rules deny `merge_pr` / `push_main` / `force_push`. That is enforcement, not prose — subject to
guard's own documented bound (static parsing, honest-mistake class, the `bash -c` bypass).

The **read** breadth is *not* enforced and needs no enforcement: per ADR-020, read verbs are
`instructed` on all four shipped adapters anyway, and here the grant is total, so there is
nothing to deny. The archetype's read-only-ness therefore rests entirely on the write side —
which is the half a mechanism can actually hold.

## 3. What it surfaces

Five classes, in the order the note ranks them:

1. **Stalls** — branches unmerged and ageing, PRs without movement, handoffs past SLA, a
   persona that produced nothing this cycle. Mostly already computed by `baron status`; the
   observer's contribution is saying which one matters.
2. **Ledger / handoff drift** — a handoff still `status: open` whose subject already merged; a
   finding with no resolution note after the fix landed; `wiki/log.md` unmoved while the repo
   moved.
3. **Claim-integrity slips** — a claim the substrate does not support: a verdict SHA that is
   not the head, a "green" naming no run, a metric with no denominator, a label standing in for
   evidence.
4. **Re-derivation / contradiction** — a new decision, ADR, or proposal covering ground an
   accepted or in-flight record already covers, without naming and reconciling it. This pairs
   with the prior-art gate being built in parallel: **the gate blocks at the door; the observer
   notices what got past it, what predates it, and what was never gated.** The first live pass
   found one (§6).
5. **Producing into a void — the VANAR pattern** — output accumulating with no path to a
   consumer: a coordination repo with no remote, a sink nobody reads, a ledger nobody cites. A
   fleet can be green on every stall metric and still be shouting into a drawer. The first live
   pass found this too, at the top of the list.

**How it raises them:** the note is the default and usually the whole loop. A `_handoff/` to the
Librarian is the escalation, used only when someone must act. An observer that pages on
everything gets muted, and a muted observer *is* the void it exists to detect.

## 4. Where the notes live

`observations/` in the collab repo (per project, beside `findings/` and `decisions/`), emitted
by `baron init` **only when the roster carries an observer** — an empty single-writer zone in a
project with no writer is a surface nobody owns. Dated notes, `YYYY-MM-DD-<slug>.md`,
append-only: a note that turns out to be wrong is still an accurate record of what the substrate
looked like at the time, so it is corrected forward in the next cycle, never rewritten.

`observations` joins the named `write_path` convenience scopes. Scopes are data, not vocabulary
(`capability-vocab.v1.md` Q1), so **the frozen v1 verb list is untouched**.

## 5. Cadence — recommended, not wired

**A daily cron sweep**, via a persona sidecar (ADR-026): `agents/<slug>/sidecar.sh`, stateless
per cycle — re-read git as truth every pass, or the audit-by-diff guarantee is forfeited
(ADR-026 §4). Rationale: every drift class in §3 is measured in days, and an event-per-commit
or continuous `--watch` observer produces a note nobody reads, which is a self-inflicted §3.5.
`--watch` is the right form later *if* a specific class turns out to need sub-day latency; none
does today.

**This ADR wires no scheduler.** ADR-007 holds — baron does not own the loop. The recommendation
is a default in the template's `runtime.trigger`, and the deployment stays the operator's.

## 6. Evidence — the first live pass

Run 2026-08-14 over `~/Workspace/fleet-coordination` (`_meta` + `barony`) and recent `vggg/barony`
activity, read-only, before this archetype existed anywhere but in the branch:
`docs/notes/observer-first-pass-2026-08-14.md`. It found, in rank order, a substrate with no
remote (§3.5), two live proposals on the same subject with no cross-reference (§3.4), an open
handoff whose PR merged, a finding with no resolution note although its fix shipped, and two
wiki logs still on their genesis entry. Each names a re-checkable evidence path. The pass is the
argument that the five classes are real and cheaply detectable — one agent, one hour, no writes
to anything but its own note.

## 7. Honest bound

**A read-only observer reports what it can see in the substrate. It is not a guarantee of
correctness and it enforces nothing** — that is the guard's and the gate's job. A surface it
cannot see is unknown coverage, not health, and its notes are only as good as what the fleet
chose to write down. Every note is required to carry its own coverage bound for exactly this
reason: an empty section must never read as "all clear" (the same failure ADR-024 §5 names for
`baron health`, one level up).

## 8. Alternatives considered

- **Fold it into the Librarian.** Rejected: the Librarian *acts* — it numbers, it writes the
  wiki, it pushes. Observation done by the actor is self-review, and the Librarian's drift is
  itself one of the things worth watching (the first pass found it).
- **A numbered `O<N>` observations ledger.** Rejected — §2.1.
- **`baron observe`, a CLI command instead of a persona.** Rejected: the deterministic half is
  already `baron status` / `baron health`. What is missing is judgement over their output, which
  is a persona, not a subcommand.

## 9. Supersedes / Prior art

The sweep this ADR records under [ADR-029](ADR-029-prior-art-gate.md), which merges ahead of
it. Written at queue integration on 2026-08-14. This ADR is `status: proposed`, so the gate
treats it as **exempt** — the block is written anyway, because an ADR that acquires its prior
art at the moment somebody accepts it has the discipline backwards.

The sweep changed one thing: the relationship to ADR-029 needed stating in both directions
(§3 already claimed the observer catches what the prior-art gate misses; the gate's own record
now needs to not claim the reverse), and the number moved from 029 to 030.

<!-- BEGIN BARON PRIOR-ART -->
searched:
  - corpus: repo-adr
    location: docs/adr
    query: "observer, read-only persona, watcher, monitoring, drift detection, archetype, observation plane"
    date: 2026-08-14
  - corpus: repo-decisions
    location: STATUS.md, AGENT-TASKS.md, CHANGELOG.md, open PRs on vggg/barony
    query: "observer archetype, read-only agent, sixth archetype, observations zone"
    date: 2026-08-14
  - corpus: vault
    location: /Users/vikram/Obsidian/Brain
    query: "observer agent, first agent, watch the setup, keep notes, fleet observer"
    date: 2026-08-14
hits:
  - ref: _handoff/tasks/2026-08-13-1500-atlas-observer-agent-todo.md
    disposition: cites
    note: >-
      the owner's own scope note in the vault, and the reason this archetype exists — "as
      the substrate comes online, employ a first agent that watches the whole setup and
      keeps notes". This ADR is that note promoted, per ADR-029 rule (a).
  - ref: docs/adr/ADR-013-observation-plane-events-and-sinks.md
    disposition: distinct
    note: >-
      also called an "observation" surface, and the closest naming collision in the corpus.
      Distinct because ADR-013 is a machine event plane — structured rows emitted by
      instrumented code paths. This is a persona exercising judgement over that plane's
      output and everything beside it. The observer READS ADR-013's plane; it is not a
      second one. §2.1 keeps them apart by refusing the observer a numbered ledger.
  - ref: docs/adr/ADR-024-fleet-health.md
    disposition: distinct
    note: >-
      `baron health` computes the same drift signals this archetype watches for, and the
      first pass used it. Distinct because health is a pull-only deterministic report with
      no reader; the archetype is the reader. §1 makes exactly this argument — the gap is
      not more computation, it is that nobody is looking.
  - ref: docs/adr/ADR-026-persona-sidecar.md
    disposition: cites
    note: the deployment shape (§2 — stateless per cycle, a daily cron sweep, recommended not wired).
  - ref: docs/adr/ADR-020-read-verb-posture-measured-on-four-adapters.md
    disposition: cites
    note: >-
      why the read half of this archetype is honestly unenforced — read verbs are
      `instructed` on all four adapters. §1's bound rests on this.
  - ref: docs/adr/ADR-029-prior-art-gate.md
    disposition: cites
    note: >-
      adjacent and complementary, stated in both directions. The gate blocks
      re-derivation at the door for ADRs; the observer catches what got past it,
      predates it, or was never gated (§3). The gate is a mechanism, the observer is
      judgement — neither substitutes for the other. This ADR renumbered 029 -> 030
      because the gate took 029 first.
  - ref: docs/adr/ADR-004-baron-guard-enforcement.md
    disposition: cites
    note: >-
      the write-side denials that make read-only mechanical rather than promised;
      `cli/tests/test_observer.py` asserts them against a real guard subprocess.
<!-- END BARON PRIOR-ART -->

## 10. Decision record

- [ ] Approved as written
- [ ] Approved with changes
- [ ] Needs revision
- [ ] Rejected
