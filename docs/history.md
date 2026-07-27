# How Barony got here — v0.3 → v1.8

The short version: a Claude-Code-only scaffolding skill kept meeting real
coordination failures on real projects, and each failure became a mechanism.
The full decision trail lives in the ADRs; release-by-release detail is in the
[CHANGELOG](../CHANGELOG.md).

## v0.x — a Claude Code skill that emitted markdown (2026-05)

The project began as `agent-project-bootstrap`: a Claude Code skill with three
emit modes (`vault-project`, `collab-repo-project`, `join-collab-project`) that
produced multi-agent scaffolding — `CONVENTIONS.md`, `COORDINATION.md`,
per-persona `AGENT.md`, `_handoff/`, `decisions/`, `findings/`, `wiki/`, and a
`/vc` commit command. The *patterns* were valuable and largely runtime-neutral
already: three-tier write ownership, the append-only handoff protocol, persona
archetypes, the librarian pattern. The *packaging* was not — Claude tool names,
`CLAUDE.md`, plugin manifests, and Obsidian references ran through everything.
That generation is preserved, deprecated, in [`legacy/`](../legacy/).

## v1.0 — the runtime-agnostic turn (2026-06, ADR-001)

The forcing function was concrete: the work environment ran **code-puppy**, the
home stack ran Claude Code, and porting the skill would have traded one lock-in
for another.
[ADR-001](adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md) adopted the
canonical-spec + self-adapting-agents architecture: a runtime-neutral canon
(role recipes, `persona.yaml`, `manifest.yaml`, the capability vocabulary) that
each runtime hydrates through an **adapter**, self-selecting the highest
fidelity tier it supports — with the human never choosing a runtime or a mode.
Two decisions that looked like human choices (markdown personas vs. native
subagents; orchestrate vs. participate) were resolved deterministically instead:
by the runtime's own capabilities, and by the state of the target directory.
v1.0–v1.1 shipped the canon, the claude/code-puppy/generic adapters, Claude
Tier-3 subagent rendering, and the bi-runtime acceptance harness. Canonicality
also moved: the repo (not the personal vault) became the single source of truth.

## v1.2–v1.3 — the audit half (2026-06)

`multi-agent-audit` landed as the sister skill: read-only, framework-neutral
grading of multi-agent projects, with the **intervention tax** as headline
metric and the dual-lens declared-vs-actual drift pass. Its first real audit
promptly found 13 substantive failures in the audit skill itself; v1.3 closed
all 13 within a day. The audit's operational-fidelity score later became the
"enforcement theater" receipt that motivated Phase 2.

## v1.4 — one front door, honest artifacts (2026-07-22, ADR-002)

The credibility-debt release. `SKILL.md` became a thin router to
`START.md` → `ORCHESTRATE.md`/`PARTICIPATE.md`; the v0.3 emit path was
quarantined in `legacy/`; the acceptance test was rewritten to parse the
adapters' real capability maps instead of testing itself; repo lint (dead
links, placeholders, version sync) and CI arrived. Alongside:
[ADR-002](adr/ADR-002-ways-of-working-2026-07.md) promoted the July-2026 ways
of working — field-proven on a real pilot project — into the templates: the
single-GitHub-account constraint as first principle, everything-material-gets-a-
handoff, lock-via-open-PR + CI guard (CODEOWNERS explicitly rejected), and the
adversarial reviewer + merger personas with SHA-bound verdicts.

## v1.5–v1.6 — conventions become mechanisms (2026-07-23, ADR-003/004)

The field record said convention alone was not enough: three finding-number
collisions, the 2026-07-22 triple-stranding incident, racing markdown lock
commits, 18/40 handoffs rotting open, and a measured operational fidelity of
0.53. [ADR-003](adr/ADR-003-baron-cli.md) answered with the **`baron` CLI** —
a disciplined reader/writer over the same markdown/git substrate (never a
second store): `validate`, `status`, race-safe ledger allocation, the handoff
lifecycle, PR-as-lock, worktree tooling, expiry-honest waivers.
[ADR-004](adr/ADR-004-baron-guard-enforcement.md) added `baron guard` —
deterministic capability enforcement as a PreToolUse hook, upgrading five
sub-tool denials from instructed to enforced on Claude Code, with honest
degradation when baron is absent. v1.6 externalized guard's rule table into the
versioned `capability-rules.v1.yaml` artifact and added **pydantic-ai** as the
fourth runtime — the first adapter whose sub-tool denials are natively
enforced, in-process.

## v1.7 — the name (2026-07-27, ADR-005)

`agent-project-bootstrap` was accurate for a scaffolding skill and wrong for
what the repo had become: a spec + adapters + an enforcing CLI + an audit
rubric. [ADR-005](adr/ADR-005-naming.md) renamed the product **Barony**
(git-native governance for teams of AI coding agents), kept the CLI **baron**
(ADR-003's metaphor: the baron keeps the estate's books without owning the work
done on the land), and reserved **signet** for SHA-sealed verdicts. The rule:
install `barony`, run `baron`, import `baron`. History was not rewritten — old
names stand where they describe the past.

## v1.8 — the stranger release (2026-07-27, ADR-006)

Until v1.8 a stranger with only `pip install barony` had no path at all — the
templates lived in the skill, and a pip install carries no skill.
[ADR-006](adr/ADR-006-baron-init-template-packaging.md) shipped **`baron
init`**: the deterministic scaffold, emitting the canonical layout from
templates vendored byte-identically as package data (drift-guarded in CI) and
self-validating before the first commit. The conversational path keeps the
judgment work; the quickstarts were rewritten from a verified bare-venv run.

## The through-line

Every mechanism traces to a paid-for failure: collisions got a retry loop
instead of a rule; stranding got a red exit code instead of a manual estate
assessment; handoff rot got an SLA and an index; lock races got the forge's PR
state; enforcement theater got a hook, an in-process interceptor, and an audit
that measures the gap. The substrate never changed: plain markdown + git,
readable by any agent and any human, on any runtime.
