---
created: 2026-08-14
type: observation
author: Observer (first pass — archetype defined in the same PR, ADR-030)
cycle: >-
  fleet-coordination @ 4ac05d2 (_meta + barony, all 23 commits, 2026-08-13→14);
  vggg/barony @ 1a657a8 (origin/main, open PRs #32/#46/#47, merged #40–#45);
  .baron/events/2026-08-14.jsonl; baron status + baron health, portfolio scope.
---

# Observation 2026-08-14 — the fleet is working; the substrate it works into is a drawer

The fleet is producing real, high-quality output — two findings this cycle, a live SHA-bound
verdict, four PRs merged in a day. Two things are wrong with where it lands: **the coordination
repo has no remote** (nothing the fleet coordinates through exists off this laptop), and **two
open PRs propose the same subject without either naming the other**.

Ranked most severe first. Every item names a path anyone can re-check.

---

## 1. `fleet-coordination` has no git remote — the substrate is local-only (VANAR)

**Evidence:** `git -C ~/Workspace/fleet-coordination remote -v` → empty.
`git log @{u}..HEAD` → `fatal: no upstream configured for branch 'main'`. 23 commits,
2026-08-13→2026-08-14, none pushed anywhere.

This is the void pattern, in its purest form. Every governance guarantee the design rests on —
audit by `git clone`, a shared substrate, "git is the bus", the Librarian and the owner reading
the same record — is currently satisfied by one working copy on one machine. `baron status`
cannot flag it: it checks branches against `origin/main` *in the code repo* and reports the
collab side green, so this failure is invisible to exactly the tool that looks healthiest.

Worth stating plainly because everything below is downstream of it: the fleet is not idle and
not sloppy. It is producing well, into a drawer.

**Suggested (owner's call):** give the monorepo a remote and push, or record deliberately that it
is a local-only experiment so a green board stops implying durability.

## 2. Two live proposals on agent identity, neither citing the other

**Evidence:** PR **#32** — *"ADR-011 (PROPOSED) — agent identity at spawn (P2.9)"*, open since
2026-08-04, branch `adr-011-agent-identity` (`5cb4e98`, +263 lines at
`docs/adr/ADR-011-agent-identity-at-spawn.md`). PR **#47** — *"ADR-027: agent identity —
per-persona forge credentials by named indirection"*, opened 2026-08-14. Full body of #47
searched for `ADR-011`, `adr-011`, `#32`, `identity at spawn`: **0 occurrences of each.**
`docs/adr/README.md` reserves 011 for "agent identity at spawn" and points at PR #32.

The two may well be complementary — #32 is identity *at spawn*, #47 is *forge credentials* — and
that is precisely the reconciliation nobody has written down. As it stands the repo has two
unmerged proposals on one subject, ten days apart, and a reader arriving at either has no signal
the other exists. This is the re-derivation class: not a duplicate, but settled-or-pending ground
re-entered without naming what was already there.

> **RESOLVED 2026-08-14, after this pass — recorded here, not rewritten above.** The
> observation stands as written; its *hypothesis* did not, and that is worth preserving rather
> than tidying away. The reconciliation was performed and the answer is **supersession, not
> complementarity**. The reasoning above guessed the boundary from PR titles — "#32 is identity
> *at spawn*, #47 is *forge credentials*" — and reading both records in full showed there is no
> such boundary. #47 was closed and replaced by **PR #48**, whose ADR-027 proposes *the same
> mechanism as ADR-011*: SSH signing keys at spawn, an in-repo `allowed_signers` under
> CODEOWNERS, the signature ↔ registry ↔ claimed-persona cross-check, the same three-layer
> gate, the same rejection table — both being readings of the same 2026-08-04 vault spike.
> **ADR-027 supersedes ADR-011**, annotated in both directions ([ADR-027](../adr/ADR-027-agent-identity.md)
> §9 dispositions ADR-011's five blocking questions); PR #32 is closed as superseded.
>
> Two corrections this pass earned, both about *its own* method: the note read PR bodies and
> titles rather than the ADR files on the branches, which is what produced the wrong boundary —
> a coverage bound the note did not state and now does. And the finding under-counted: it framed
> the ADR-027 miss as a **vault** miss, when the session also missed **ADR-011, an open PR in
> this repo's own `docs/adr/` corpus** ([ADR-029](../adr/ADR-029-prior-art-gate.md) §2 carries
> the corrected incident record). The observer found the right problem and got the size and the
> shape of it wrong — which is §7's honest bound arriving on the first pass, and the reason the
> archetype escalates by handoff instead of adjudicating.

This is the case the prior-art gate is being built to catch at the door. Noting it here is the
other half: #32 predates the gate and would never have been gated.

## 3. Persona identity is claimed in commit subjects but not in commit authorship — 20 of 23

**Evidence:** `git log --format='%an <%ae>|%s'` over the whole monorepo history. 20 of 23
commits carry a persona prefix (`atlas:`, `dev:`, `reviewer:`, `librarian:`, `baron:`) with
author `Vikram Godbole <Vikram.Godbole@shalkiengineers.com>`. Only three carry a persona
identity: `8e14e33` (`Dev <dev@barony.local>`), `ed97055` and `8d54b94`
(`Atlas <atlas@meta.local>`).

This matters right now because PR #47's premise is that *"git-commit identity was already
solved — every persona commits as `<slug>@<project>.local`"*, and forge identity is the
remaining gap. In the one live fleet, the git half is **13% adopted**. The claim is true of the
design and not of the substrate; a design decision resting on it should know which.

The prefix convention is doing real work — attribution is legible in `git log --oneline`. But a
prefix is a string in a subject line, and per-actor attribution that a tool can verify is the
author field. Same shape as `CONVENTIONS.md § A label is not evidence`, one layer down.

## 4. An open handoff whose PR merged five hours ago

**Evidence:** `barony/_handoff/2026-08-14-1332-dev-pr-44-carries-a-live-review-pass-at-9f960bf-ready-for-the-merge-gate.md`
is `status: open`, `for: owner`. PR #44 merged 2026-08-14T15:29:40Z (`e728ecf` on origin/main).
The handoff is well-formed and its evidence checks out — head/verdict SHAs equal at `9f960bf`,
CI green, no labels leaned on. It was simply never closed.

Low severity on its own. It matters as a pattern: the handoff channel is where "this needs a
human" lives, and an open item that is actually done trains readers to skim the channel. The
close-on-merge step is the one part of the loop still done by hand — three `baron: handoff |
close` commits this cycle, all manual.

## 5. F2 shipped a fix; the ledger entry doesn't know

**Evidence:** `barony/findings/index.md` § F2 (*review.verdict events written to the monorepo
root, read from the project subdir — `baron health` always reports 0 verdicts*), severity
**high**, no resolution note. PR #45 — *"fix: baron health read a plane nobody writes to in a
monorepo"* — merged 2026-08-14T16:27:16Z (`3c68df1`). Verified live: `baron health` now rolls up
`1 verdict(s) recorded` at portfolio level, which is the fixed behaviour.

The finding reads as open and high-severity; the substrate says it is fixed. Findings are
append-only and stay forever, which is correct — but a fix that lands without a forward link
leaves the ledger overstating the open-defect count. (F1 has the same shape: fixed in `ed97055`,
no note on the entry.)

## 6. Both wiki logs are still on their genesis entry

**Evidence:** `barony/wiki/log.md` and `_meta/wiki/log.md` each contain exactly one entry,
`## [2026-08-14] genesis` and `## [2026-08-13] genesis`. Last content change to either:
2026-08-13, via the `add project` / subtree-graft commits. Meanwhile 16 commits touched
`barony/`, two findings were filed, and four PRs merged.

The Librarian is behind on both projects — and on `_meta` it has produced nothing at all since
scaffold: ledgers empty, its own genesis handoff (`_meta/_handoff/2026-08-13-bootstrap-to-iris-genesis.md`)
still `status: open` after a day, instructing the reader to close it. `baron status` reports
`_meta/ (green)`, because green there means "no divergence", not "the persona ran".

## 7. Stalls, for the record — 13 unmerged branches, 4 of them ≥ 10 days

**Evidence:** `baron status` from the monorepo root: 14 red. `p1-pilot-hardening-foldin` (14d),
`backup-main` (14d), `p1-closeout-nb1-nb5` (12d), `p2-3-runtime-drift` (12d),
`p2-baron-decision-adr` (12d), `release-1.9.0` (12d), `release-1.10.0` (10d),
`ritual-surface-guard` (10d), `roadmap-synthesis-2026-08-02` (10d), `harden/otel` (5d), plus
today's three. Also `worktree:dev /Users/vikram/Workspace/barony-worktrees/dev` — 4 commits
behind `origin/main`, **never pulled**.

Two release branches sitting unmerged for 10–12 days is the one worth a human's attention: those
either shipped by another route (and the branches are litter) or did not ship (and the version
line is ambiguous). The dev worktree that has never pulled is a session that will start from a
stale base whenever it next runs.

---

## Coverage bound

**Read this cycle:** the full `fleet-coordination` working tree and its 23-commit history; both
projects' `_handoff/`, `findings/`, `decisions/`, `wiki/`, `manifest.yaml`, `agents/*/persona.yaml`;
`.baron/events/2026-08-14.jsonl` (1 row); `baron status` and `baron health` at portfolio scope;
`vggg/barony` `origin/main`, its branch list, open PRs #32/#46/#47 (bodies), merged #40–#45
(titles/dates); the body and diffstat of `adr-011-agent-identity`.

**Not read:** PR review threads and inline comments (only #47's body was fetched in full);
CI run logs; the code repo's own working tree beyond git metadata; any runtime session
transcript; the vault. Nothing outside `git`/`gh` read APIs was touched, and nothing was written
anywhere except this note.

**What a clean board here would and would not prove.** The event plane holds **one** row, so
every verdict-derived metric in `baron health` has a denominator of 1 — mutation-kill is `0/0`,
"0 claim drift" means one reviewer, once. Absence of a signal is not a good signal (ADR-024 §5).
Four of the seven items above are drift between the record and reality, which is only detectable
where a record exists at all; a persona that writes nothing produces no drift and looks perfect.
`_meta` is the worked example: green on every check, and its Librarian has not run.

**Standing bound.** This is an observer's read of the substrate. It enforces nothing, verifies no
claim beyond what a path or a SHA can settle, and is not a correctness guarantee — that is the
guard's and the gate's job.

---

## Would escalate (proposed, not filed)

Nothing here was filed, numbered, or fixed — an observer proposes and the Librarian decides.
Two items are worth a `_handoff/` on a real deployment:

- **§1 to the owner** — the remote is a decision, not a defect.
- **§2 to the Librarian** — two live records on one subject need reconciling by whoever owns the
  ADR index; possibly one finding.

§3–§6 belong in the next Librarian reconciliation pass, not in anyone's inbox.
