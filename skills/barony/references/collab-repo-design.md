# Design Decisions: collab-repo-project mode

Rationale for the choices baked into the `collab-repo-project` and `join-collab-project` modes (added in v0.3.0). Read before customising.

## Why a separate "collab repo" rather than reusing the code repo

For multi-collaborator projects with remote contributors who don't all share access to the same personal vault, a dedicated collab repo provides clean trust isolation. Designer / analyst / autonomous personas don't need to clone the codebase to read project rules or write findings. The collab repo is a self-contained substrate that any team member can clone, regardless of their access to the code repo.

The alternative (putting collab content inside the code repo under `collab/`) forces every collaborator to pull the codebase even when they only need conventions, decisions, or persona manuals. It also fuses two ACL surfaces (code-access and collab-access) that ideally stay separable.

## Why three persona archetypes (dev / autonomous-event / autonomous-cron) and not one generic template

A single template with all possible fields forces every persona to declare runtime, schedule, decision authority, even when those don't apply. The three archetypes carry only what's relevant:

- **Dev** — has a workspace path, human operator, session-start ritual
- **Autonomous-event** — has a webhook trigger, decision authority on the surface it acts on, cost ceiling, no workspace
- **Autonomous-cron** — has a cadence, a default runner, a failover protocol, scope on what it reads and writes

The Librarian is a special case of autonomous-cron with an additional FAILOVER.md document. Every project gets exactly one Librarian by default; other archetype instances are added per project need.

## Why the Librarian is centralized-with-failover, not a fully distributed mesh

A fully distributed Librarian (one per collaborator, all writing to a shared `wiki/`) creates merge conflicts on `wiki/log.md` every run cycle. Multiple instances doing the same synthesis work is also wasteful compute. Centralized-with-failover gets the failure-resilience property (any team member can take over) without the merge-hell property (only one instance runs at a time).

The runtime is a social contract documented in `FAILOVER.md`, not a technical leader-election protocol. For pilot-scale projects, the runbook is sufficient. If a project grows past the point where social failover is adequate, leader-election or domain-partitioned mesh become reasonable next steps — but not by default.

## Why trust-gating is optional and lifecycle-agnostic

Different projects have different trust profiles: employer-paid contractors, trusted friends, pre-launch sensitive code, mature production code, education-platform contributors. A blanket "first 2 weeks PR-only by default" rule fits some and grates against others. The skill emits a `BOOTSTRAP-ADMIN.md` documenting *how* to enable trust-gating via GitHub branch protection if/when desired. The owner decides whether and when to apply it.

## Why the `BOOTSTRAP.md` structure is sectioned the way it is

Empirically derived from a real onboarding (the first remote collaborator who joined an Option A pattern). The order — project intro → team → identity → workspaces → orientation reading → first PR — matches the natural flow of someone joining cold. Earlier sections give them just enough context to read later sections without re-reading. The "first PR" step at the end is a deliberate forcing function — the round trip validation catches setup issues while the collaborator is still in onboarding mode.

## Why `_handoff/` is included in the collab repo (and not just the code repo)

`_handoff/` is a project-level coordination surface. Code-level handoffs (PR comments, issue threads) belong in GitHub; coordination handoffs (decisions, rule-drift flags, librarian-ingest requests) belong in the collab repo. Putting `_handoff/` here keeps the work-state (code) cleanly separable from the coordination-state (collab).

## Why one personal `_inbox/` and not per-project inboxes

Raw thoughts often aren't categorizable at capture time. Forcing a per-project decision when the thought is half-formed kills the "raw" property. The project owner's personal vault holds the one inbox; the Librarian (running with the cross-project bridge) routes raw captures outward to project collab repos as handoffs when they're project-actionable. Co-workers' raw thoughts are their own problem, outside the skill's scope.

## Why the Librarian doesn't write to the project owner's personal vault

One-way visibility preserves the trust gradient. The project's `wiki/` is visible to all collaborators; the personal vault is not. Cross-project synthesis (where one project's pattern informs another) flows owner → personal vault, not project → personal vault. The Librarian-on-owner's-machine can *read* the owner's personal vault (because the runtime has that access), but it doesn't *write* there — that's Iris's job, and Iris runs separately.

## Why `agents/<persona>/AGENT.md` and not a single `agents.md` registry

Per-persona files mean each persona's operating manual can be edited independently. Granular file ownership maps to the "owner" pattern in hot-file serialization: each persona owns its `AGENT.md`. A central registry would require all-personas-or-none changes and reintroduce coordination problems we've already eliminated.

The `CONVENTIONS.md § Identity, labels, and routing` table is a *thin* registry — just enough cross-persona reference for routing decisions, not the canonical content of each persona's manual.

## Why placeholder `{{COLLAB_REPO_SSH_URL}}` and not just `{{COLLAB_REPO}}`

The skill needs the SSH clone URL for the clone step, separate from the `org/repo` slug used in GitHub API calls. Using two placeholders keeps the substitution explicit and prevents copy-paste errors at clone time.

## Why no scripts/ folder in this mode either

Same reason as v0.2.0 vault-project mode: step-by-step instructions in SKILL.md are more durable than scripts. The collab-repo bootstrap steps are short enough that automation doesn't pay off. If a particular project bootstraps frequently enough to need automation, it should script that in its own infrastructure — not in this skill.
