---
created: 2026-07-22
accepted: 2026-07-22
type: decision
status: accepted
decided_by: Vikram
adr: 002
project: barony
related:
  - "[[docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap]]"
---

# ADR-002: July-2026 Ways of Working (field-proven on badminton-analyzer)

| Field | Value |
|---|---|
| **Status** | Accepted (2026-07-22) |
| **Date** | 2026-07-22 |
| **Authors** | Vikram + Claude |
| **Supersedes** | — (extends ADR-001) |
| **Evidence base** | `vggg/baddie-analyzer-collab` (2026-07-13 → 2026-07-16), a real project running the v1.0 runtime-agnostic path |
| **Decision owner** | Vikram |

## 1. Summary

During the 2026-07 badminton-analyzer collaboration, a run of coordination innovations landed
in that project's `CONVENTIONS.md` / `COORDINATION.md` / persona specs. Each one exists
because a concrete failure happened (or was demonstrably imminent) and the fix was proven in
the field. This ADR promotes them from project-local rules to framework defaults, so future
bootstrapped projects start with them instead of re-discovering them. The template changes
land in `assets/collab-repo/` alongside this ADR.

## 2. Decisions

### §1 — The single-GitHub-account constraint is a first principle

**Decision.** State up front, in the emitted `CONVENTIONS.md`: all personas commit under ONE
human GitHub account. GitHub cannot tell personas apart. Therefore **every gate is enforced
by persona capability (`capabilities.allow`/`deny` in `persona.yaml`), never by GitHub
permissions.**

**Rationale / evidence.** This one fact explains most of the rest of this ADR: CODEOWNERS
cannot work (§3); self-approval of PRs is blocked by GitHub itself, so persona review needs a
different verdict surface (§4); "who merges" is spec, not a GitHub permission (§4). On
badminton-analyzer every PR showed `mergedBy=vggg` regardless of which persona did the work —
the platform is structurally blind to personas, and pretending otherwise produces gates that
enforce nothing.

### §2 — Everything material gets a handoff

**Decision.** Every material finding, decision, and **correction** routes through `_handoff/`
— a PR description is not a substitute. Corollary: **a number in a PR body is not a claim;
only a handoff is** — finding/decision numbering stays a single-writer (Librarian) surface.
PR-sweeping remains a Librarian *backstop* for catching missed handoffs, never the source of
a number.

**Rationale / evidence.** Two failures in one day (2026-07-15): findings F44/F46 existed only
in code-repo PR descriptions — the documented Librarian ritual is a handoff scan, so a
routine pass would have missed both, and F46 *corrected a finding published an hour earlier*
(a correction that never reaches the record is worse than the original error). And it caused
a numbering collision: with no handoff to read, the Librarian assigned F45 to work that had
already claimed F45 elsewhere — the third such collision (F38/F39, F40/F41, F44/F45), all
from numbers claimed outside the single-writer surface.

### §3 — Locking via open-PR + CI guard, not CODEOWNERS

**Decision.** For `Lock`-pattern hot files: **the open PR is the lock** (claim early with a
draft PR or `lock:*` label; release is automatic on merge/close), backed by a **CI guard**
that fails a PR touching a Lock path while another open PR touches the same path. For
`Owner`-pattern files: an **evidence gate** (required label + linked ADR/handoff), not a
human approver. CODEOWNERS is explicitly rejected. Where a write-capability denial already
enforces ownership (e.g. `wiki/` is Librarian-only via `write_path`), keep it — capability
denial is strictly stronger than any review gate.

**Rationale / evidence.** Branch protection is unavailable on free private repos (GitHub API:
`Upgrade to GitHub Pro or make this repository public to enable this feature`, HTTP 403), and
CODEOWNERS only enforces anything *through* branch protection — so it would have bought zero
enforcement while making the owner a required reviewer on the busiest seam. Meanwhile the
manual `_handoff/` lock protocol is itself race-prone: two personas grep, both see no lock,
both claim — exactly the D14 contract-fork condition the mechanism exists to prevent. A CI
Action closes that race window with **no human in the loop**. Honest limitation, carried into
the templates: without branch protection a red check does not physically block a merge — it
is enforcement by convention plus a visible alarm, still strictly better than a silent grep.

### §4 — Adversarial Reviewer + Merger personas with SHA-bound verdicts

**Decision.** Ship two optional persona archetype templates
(`agents/__REVIEWER__/`, `agents/__MERGER__/`):

- **Reviewer** — adversarial, fresh-context ("find reasons to reject"), judgement-not-mechanics
  (CI already runs tests/lint), read-only (`write_path: [_handoff]` only). Publishes a
  **verdict as a PR comment bound to the exact head SHA reviewed** — never the platform's
  approve.
- **Merger** — holds the project's **only** `merge_pr`. A gate, not a button: verifies
  preconditions (CI green on the *current* head SHA; a REVIEW:PASS naming the *current* head
  SHA; record obligations met; no hot-file collision) and merges, or refuses naming the failed
  precondition. Never judges code quality.

**Rationale / evidence.** Under §1, GitHub's native review is unusable as a persona verdict:
"Can not approve your own pull request" (verified live, 2026-07-15). A comment naming the head
SHA gives the Merger something *verifiable* — a verdict is about a commit, not a PR; a new
push makes it stale. The Merger exists because merge capability previously had no home except
the human owner (every dev persona denies `merge_pr`), making the owner the bottleneck for
every merge.

### §5 — Persona-spec validation in CI

**Decision.** Bootstrapped projects validate `agents/*/persona.yaml` in CI: it parses, and
required fields (per `references/persona.schema.md`) are present; capability verbs are drawn
from the frozen v1 vocabulary. This skill repo applies the same discipline to its own
templates and fixtures via `tests/` + `.github/workflows/ci.yml`.

**Rationale / evidence.** On badminton-analyzer a persona.yaml silently didn't parse
(unquoted `priority: high` — YAML footgun). A ~10-line `safe_load` + required-fields check
catches this class for free; an invalid canonical spec is worse than a missing one because
every adapter hydrates from it.

### §6 — Librarian spec corrections

**Decision.** The librarian archetype template (`agents/librarian/persona.yaml`) allows
`open_pr`; its indexing instructions handle a frozen-memory split (historical record =
one-line pointers; new entries = full entries); prefer **event-triggered on merge** for
reconciliation with cron as a backstop.

**Rationale / evidence.** Denying `open_pr` made the badminton-analyzer Librarian unable to
deliver its own work (it writes PR-only paths). Cron-only reconciliation lagged the record
behind merges.

### §7 — Portability conventions: snapshot-restore + agent-state directory

**Decision.** Emitted conventions name a standard home for machine-local persona state that
must not travel with a clone (runtime secrets/config, per-persona state files): a stable
per-user directory — `~/.claude/agent-state/` on Claude Code; the equivalent stable per-user
location on other runtimes — plus a snapshot-restore practice so a persona can be rebuilt on
a new machine (failover = re-clone + restore state).

**Rationale / evidence.** Badminton-analyzer field practice: install-dir state was
clobber-prone and clone-local state leaked machine specifics into the repo (the F7
absolute-path lesson, extended to state). A stable, documented location makes failover
mechanical.

## 3. Universal vs. opt-in

Per the source TODO's split: §1, §2, §5, §6 are **universal** (baked into the emitted
templates); §3, §4, §7 are **opt-in modules** (templated, adopted per project — small teams
without contested seams may not need a Merger or a lock guard).

## 4. Consequences

- Positive: new projects inherit fixes for every coordination failure badminton-analyzer
  actually suffered (record loss, numbering collisions, lock races, merge bottleneck, silent
  spec corruption).
- Negative / costs: more moving parts in the emitted templates (two new personas, a CI guard
  pattern); the honest-limitation caveat (§3) must travel with the lock guard so projects
  don't oversell it.
- The capability vocabulary is unchanged — all of the above compose from the frozen v1 verbs
  (`merge_pr` scoping, `write_path` scoping, `open_pr`), which is itself evidence the v1
  contract held under field pressure.

## 5. Decision record

- [x] Approved as written

**Notes (Vikram, 2026-07-22):** promoted from
`TODO-sync-ways-of-working-2026-07.md` (vault) with `baddie-analyzer-collab`'s
`CONVENTIONS.md` / `COORDINATION.md` / `agents/{reviewer,merger}/persona.yaml` as the
reference implementation. Template changes shipped with v1.4.0.
