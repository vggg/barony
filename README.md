# Barony

**Git-native governance for teams of AI coding agents: who may do what, who did
what, what's true now — enforced by mechanism, measured by audit, on any runtime.**

Barony is a spec, a CLI (`baron`), and a set of runtime adapters for running
several AI coding agents on one long-lived project without the usual decay. Each
persona is declared once in a runtime-neutral `persona.yaml` and hydrated onto
whatever runtime you have — Claude Code, code-puppy, pydantic-ai, or anything
that can read a prompt — at the highest enforcement fidelity that runtime
supports. The coordination substrate is plain markdown + git: no server, no
database, nothing you or your agents can't read with `cat`.

> Formerly `agent-project-bootstrap`; renamed at v1.7.0
> ([ADR-005](docs/adr/ADR-005-naming.md)). Old GitHub URLs redirect.

## The 60-second pitch

Run several agent sessions on one project for a few weeks and four walls show
up. Each of these receipts is first-party — from Barony's own pilot projects and
audits, recorded in the ADRs:

- **State chaos.** Parallel working copies drift silently. On 2026-07-22 an
  estate-wide assessment of a pilot project found its two most recent results
  stranded three different ways at once — commits never pushed, a pushed branch
  never merged, and the canonical clone never pulled — leaving the status board
  stale for a week ([ADR-003](docs/adr/ADR-003-baron-cli.md) §1). `baron status`
  turns each stranding class into a red exit code you can put in CI.
- **Enforcement theater.** Rules that live in prose decay: a first-party audit
  of a real multi-agent project measured **operational fidelity 0.53** — roughly
  half the documented coordination protocol was actually being followed
  (ADR-003 §1). Barony labels every capability denial honestly as *enforced* or
  merely *instructed*, and `baron guard` blocks denied actions before the tool
  runs where the runtime allows it.
- **Knowledge rot.** On the same pilot, 18 of 40 handoffs sat `status: open` —
  weeks old, with nothing distinguishing "being worked" from "forgotten" — and
  finding numbers collided three separate times (F38/F39, F40/F41, F44/F45)
  because allocation was a rule, not a mechanism
  ([ADR-002](docs/adr/ADR-002-ways-of-working-2026-07.md) §2, ADR-003 §1).
  Barony gives ledgers race-safe numbering (git push atomicity is the lock) and
  handoffs an SLA plus an archive-not-delete lifecycle.
- **Accountability vacuum.** All personas commit under one human GitHub account,
  so the platform is structurally blind to who did what — every PR shows the
  same merger, and self-approval is refused outright ("Can not approve your own
  pull request", verified live; ADR-002 §1/§4). Barony moves accountability into
  the substrate: persona commit prefixes, SHA-sealed review verdicts (signets),
  and a read-only audit that measures the intervention tax.

If none of those walls are in your future — one-shot tasks, a single agent, no
persistent memory needed — Barony is overkill, and a plain session is simpler.

## Quickstart — a working project from a bare laptop

Requires Python ≥ 3.10 and git. Every command below is verified as written.

```bash
uv tool install barony                 # or: pip install barony  (live on PyPI)

# The code repo you want to govern (skip these two lines if you already have one):
mkdir gardenkit && git -C gardenkit init -b main -q && \
  git -C gardenkit commit --allow-empty -m "init" -q

# Scaffold a collab repo next to it — two devs + a librarian:
baron init gardenkit --dir gardenkit-collab --code-repo ./gardenkit \
  --personas dev:fern,dev:moss,librarian:iris
cd gardenkit-collab

baron validate .                       # canonical specs — expect 0 errors
baron status                           # divergence/staleness — green when fresh
baron rules list                       # what the guard actually enforces, honestly labelled

# First coordination moves:
baron finding new --title "First finding" --author fern --no-push
HANDOFF=$(baron handoff create --for moss --from fern --title "Review the seam")
baron handoff close "$HANDOFF" --note "Done, see F1."
baron index                            # regenerates _handoff/README.md — commit it

# Per-persona working copies (worktrees of the code repo above):
baron worktree add fern                # ../gardenkit-worktrees/fern, branch persona/fern
```

Drop `--no-push` once the collab repo has an origin remote. The `worktree` step
needs the `--code-repo` you passed to `init` (that's what created the code repo
above). `baron init` also emits each persona's runtime kit under
`agents/<slug>/runtime/` (`--runtime claude|generic|pydantic-ai|code-puppy`).
Full command reference: [`cli/README.md`](cli/README.md). The conversational
setup path (an agent interviews you, then scaffolds) routes through
`skills/barony/assets/collab-repo/START.md` — see
[docs/concepts.md](docs/concepts.md).

**See a real one:** [`vggg/barony-demo`](https://github.com/vggg/barony-demo)
is a seeded example — a week of a fictional project's findings, decisions,
handoffs (closed and open), a waiver, and a captured live guard refusal. The
project is fictional; every artifact was produced by the real tools.

## Core concepts

Longer-form explanations, the emitted repo layout, and the adapter mechanics
live in [docs/concepts.md](docs/concepts.md). The short version:

- **Personas & the 10-verb capability vocabulary.** A persona is one
  `persona.yaml`: identity, scope, session ritual, and capabilities drawn from a
  frozen vocabulary of ten intent-level verbs (`read_code`, `write_path`,
  `merge_pr`, `push_main`, …). The canon says *what* a persona may do; each
  runtime's adapter decides *how* that maps to real tools. Every verb exists
  because a real persona on a real task needed it — no speculative vocabulary.
- **The enforced-vs-instructed honesty ladder.** Every denial is classed
  honestly: *enforced* (the runtime makes the action impossible) or *instructed*
  (the persona is told not to). Whole-tool denials are enforceable by omitting
  the tool; sub-tool denials (e.g. "may push, but never to main") need a
  mechanism like `baron guard` or in-process interception. Adapters are
  forbidden to oversell — the claim is machine-checked in CI.
- **Ledgers (findings / decisions).** Investigation outputs and decisions are
  numbered entries in plain markdown indexes, allocated race-safely: append,
  commit, push; on push rejection, rebase, renumber, retry. Duplicates are
  errors; historical gaps are reported but never rewritten.
- **Handoffs.** Every material finding, decision, and correction crosses
  personas as a `_handoff/` file with `status: open|done` frontmatter — a PR
  description is not a substitute. Closing a handoff archives it
  (`_handoff/archive/YYYY/`), never deletes it. `baron index` keeps a generated
  summary table without eating prose.
- **A citable export, not a memory service.** `baron export --json` walks the
  ADRs, decisions, findings and handoffs into flat records that each name the
  commit whose bytes were parsed — so `git show <commit_sha>:<path>` reproduces
  any record exactly, and a source that cannot honour that is skipped by name
  rather than cited wrongly. It is grep/jq-usable on its own; there is no
  knowledge backend, no plugin group and no vendor dependency behind it, and
  [ADR-015](docs/adr/ADR-015-baron-export.md) explains why the semantic-memory
  adapter is withheld until the evaluation harness exists.
- **The divergence radar.** `baron status` reports every working copy's
  ahead/behind/dirty state, unmerged branches with age, overdue handoffs, and
  ledger/wiki staleness — exit 1 on any red. Deliberately-parked reds get
  waivers with a mandatory reason and expiry; an expired waiver resurfaces the
  red on its own.
- **PR-locks.** A hot-file lock is an open draft PR labeled `lock:<path>` — the
  forge's PR state is the only lock state, and a CI guard fails any other PR
  touching a locked path. No lock files, no lock service, no grep races.
- **Worktree topology.** Each persona works on branch `persona/<slug>` in its
  own git worktree over one shared object store — parallel working copies
  without per-clone drift. `baron worktree add|list|remove` manages it;
  `remove` never deletes the branch.
- **Audit, intervention tax, and signets.** The sister skill
  [`multi-agent-audit`](skills/multi-agent-audit/) grades any multi-agent
  project (not just Barony) read-only, with evidence: the headline metric is the
  **intervention tax** — human touches per autonomous task. Review verdicts are
  **signets**: a reviewer's PASS/FAIL comment sealed to the exact head SHA it
  judged, so a new push makes the verdict visibly stale.

## Runtime matrix

One `persona.yaml`, four adapters. Enforcement per adapter, as claimed by each
adapter's machine-readable capability map (checked in CI by
`tests/bi_runtime_accept.py`):

| Runtime | Tier | Whole-tool denials | Guard-covered sub-tool denials¹ | `open_pr` / `run_tests` denials |
|---|---|---|---|---|
| Claude Code | 3 (native subagents) or 2 (`CLAUDE.md`) | enforced at Tier 3 (tool allow-list); instructed at Tier 2 | enforced-with-baron (instructed otherwise) | instructed |
| pydantic-ai | 3 (in-process hydration) | enforced (capability omission) | enforced (in-process interception — the hook cannot be absent) | instructed |
| code-puppy | 2.75 (native JSON agents)² | enforced (tool allow-list) | instructed | instructed |
| generic (any runtime) | 1 (in-prompt + `AGENTS.md`) | instructed | instructed | instructed |

¹ The five sub-tool denials the shared rules artifact
(`capability-rules.v1.yaml`) covers: `push_main`, `force_push`, `merge_pr`,
`write_path` scoping, `edit_other_personas`. Every enforcing consumer loads the
same artifact, so decisions are identical across runtimes. A persona always runs
at the highest tier its runtime supports and degrades gracefully — with the
honesty label degrading alongside it. `baron rules list` prints that table with
its labels; `baron rules explain '<command>' --persona-file <p>` dry-runs one
guard decision (ADR-016).

² code-puppy enforces whole-tool denials natively (JSON agent allow-list) but
its sub-tool denials stay instruction-only — a partial Tier 3, which its own
adapter labels "2.75" rather than round up.

## What Barony is NOT

- **Not an adversarial sandbox.** The guard stops a cooperating persona from
  doing the wrong thing before the tool runs; it does not contain a hostile
  agent that has shell access. Overrides exist and are allowed-but-logged to a
  tracked file — visible in diffs, not silently possible.
- **Not a machine-tempo orchestrator.** There is no scheduler, message bus, or
  agent-to-agent RPC. Coordination happens at git tempo — commits, handoffs,
  PRs — which is the point: every coordination event leaves a reviewable record.
- **Not a server.** Nothing runs. The markdown/git substrate is the only
  database; `baron` is a disciplined reader/writer over files you can edit by
  hand, and structured output (`--json`) is a view, never a second store.

These are design choices, not roadmap gaps — see
[ADR-003](docs/adr/ADR-003-baron-cli.md) §2.2.

## Status, versioning, links

Current release: **v1.8.0** (semver; version lives in
`.claude-plugin/plugin.json` + the skill frontmatter, sync enforced by lint).
Active development — see [`STATUS.md`](STATUS.md) for progress and
[`CHANGELOG.md`](CHANGELOG.md) for release history.

- [docs/concepts.md](docs/concepts.md) — the concepts, longer-form: front door,
  emitted layout, capability ladder, adapters, the `baron` CLI surface.
- [docs/history.md](docs/history.md) — how a Claude-Code-only scaffolding skill
  became runtime-agnostic governance (v0.3 → v1.8).
- [docs/adr/](docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md) —
  ADR-001 (runtime-agnostic architecture) through
  [ADR-006](docs/adr/ADR-006-baron-init-template-packaging.md) (`baron init`).
- [`cli/README.md`](cli/README.md) — full `baron` command reference.
- [`skills/multi-agent-audit/`](skills/multi-agent-audit/) — the read-only audit
  sister skill.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — PR conventions, including the
  docs-land-with-code rule.
- Installing as a Claude Code plugin:
  `/plugin install https://github.com/vggg/barony` (or a local clone path). On
  code-puppy, invoke the neutral files by path — see
  [`USING-WITH-CODE-PUPPY.md`](USING-WITH-CODE-PUPPY.md).

---

MIT License · [vggg](https://github.com/vggg)
