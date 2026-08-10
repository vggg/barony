# Barony

**Git-native governance for teams of AI coding agents: who may do what, who did
what, what's true now — enforced by mechanism, measured by audit, on any runtime.**

> **New here? Read [`docs/user-guide.md`](docs/user-guide.md).** It takes a
> first-time user from install to a scaffolded project with the guard wired,
> proved by `baron doctor`, and a real capability denial on screen — about
> fifteen minutes of reading. Every command in it was run; every output is real.

## What this is, in 30 seconds

Running several AI coding agents on one long-lived project needs three separate
things, which are routinely confused:

| Layer | Answers | What you'd use |
|---|---|---|
| **Coordination** | Who may do what · who did what · what is true now | **Barony** |
| **Per-agent runtime** | How one agent thinks and calls tools | Claude Code, code-puppy, a pydantic-ai harness |
| **Control plane** | Where agents run; routing, deploy, scheduling, secrets | something else |

Barony is the first row only. It is a spec, a CLI (`baron`), and per-runtime
adapters. Each persona is declared once in a runtime-neutral `persona.yaml` and
hydrated onto whatever runtime you have, at the highest enforcement fidelity
that runtime supports. The default substrate is plain markdown + git, and it is
the only one `baron` itself uses: no server, no database, nothing you or your
agents can't read with `cat`.

**It is not** a runtime, a control plane, or an agent framework. There is no
scheduler, message bus, or agent-to-agent RPC — coordination happens at git
tempo, which is the point: every coordination event leaves a reviewable record.
It is also **not an adversarial sandbox**; it stops a cooperating agent from
doing the wrong thing, not a hostile one with shell access.

**What it costs you:** a second repo (the collab repo) alongside your code repo,
a `persona.yaml` per agent, and the discipline of routing material work through
handoffs and ledgers. Plus one hook wired into each working copy, which
`baron doctor` will nag you about until you do it.

**Skip it if** you run one agent on one-shot tasks with no state that has to
outlive the session. A plain session is simpler and this is real overhead.

## The four walls it exists for

Run several agent sessions on one project for a few weeks and these show up.
Each receipt is first-party — from Barony's own pilot projects and audits,
recorded in the ADRs:

- **State chaos.** On 2026-07-22 an estate-wide assessment of a pilot found its
  two most recent results stranded three different ways at once — commits never
  pushed, a pushed branch never merged, and the canonical clone never pulled —
  leaving the status board stale for a week ([ADR-003](docs/adr/ADR-003-baron-cli.md) §1).
  `baron status` turns each stranding class into a red exit code you can put in CI.
- **Enforcement theater.** Rules that live in prose decay: a first-party audit of
  a real multi-agent project measured **operational fidelity 0.53** — roughly half
  the documented coordination protocol was actually being followed (ADR-003 §1).
  Barony labels every capability denial honestly as *enforced* or merely
  *instructed*, and `baron guard` blocks denied actions before the tool runs
  where the runtime allows it.
- **Knowledge rot.** On the same pilot, 18 of 40 handoffs sat `status: open` for
  weeks, and finding numbers collided three separate times because allocation was
  a rule, not a mechanism ([ADR-002](docs/adr/ADR-002-ways-of-working-2026-07.md) §2).
  Barony gives ledgers race-safe numbering (git push atomicity is the lock) and
  handoffs an SLA plus an archive-not-delete lifecycle.
- **Accountability vacuum.** All personas commit under one human GitHub account,
  so the platform is structurally blind to who did what, and self-approval is
  refused outright (verified live; ADR-002 §1/§4). Barony moves accountability
  into the substrate: persona commit prefixes, SHA-sealed review verdicts
  (signets), and a read-only audit that measures the intervention tax.

## Enforced vs instructed

The distinction the whole thing turns on, and the one `baron` prints at you:

> **enforced** — baron mechanises it. Something inspects the pending call and
> refuses it before the tool runs.
>
> **instructed** — it is declared in a file the persona reads, and **nothing
> checks**.

Both are legitimate; only one is a control. Calling an instruction "enforcement"
is the failure this product exists to catch, so `baron` refuses to round up and
CI fails an adapter that claims enforcement it cannot deliver. Six of the ten
capability verbs label `enforced`; the other four are instructions —
`open_pr` and `run_tests` because guard does not parse for them, `read_code` and
`read_collab` because **baron emits no mechanism** that would omit the read
tools, measured once per shipped adapter. `baron rules list` prints the table
with the measurements attached.

## Quickstart

Requires Python ≥ 3.10 and git. Verified end to end from a clean virtualenv —
2.4 seconds of machine time, install included.

```bash
uv tool install barony                 # or: pip install barony  (live on PyPI)

# The code repo you want to govern (skip if you already have one):
mkdir gardenkit && git -C gardenkit init -b main -q && \
  git -C gardenkit commit --allow-empty -m "init" -q

# Scaffold a collab repo next to it — two devs + a librarian:
baron init gardenkit --dir gardenkit-collab --code-repo ./gardenkit \
  --personas dev:fern,dev:moss,librarian:iris
cd gardenkit-collab

baron validate .                       # canonical specs — expect 0 errors
baron status                           # divergence/staleness — green when fresh
baron rules list                       # what the guard enforces, honestly labelled

# First coordination moves:
baron finding new --title "First finding" --author fern --no-push
HANDOFF=$(baron handoff create --for moss --from fern --title "Review the seam")
baron handoff close "$HANDOFF" --note "Done, see F1."
baron index                            # regenerates _handoff/README.md — commit it

# Per-persona working copies (worktrees of the code repo above):
baron worktree add fern                # ../gardenkit-worktrees/fern, branch persona/fern

# Install fern's runtime kit where the runtime reads it, then PROVE it:
cp -R agents/fern/runtime/.claude   ../gardenkit/
cp    agents/fern/runtime/CLAUDE.md ../gardenkit/
baron doctor --dir ../gardenkit        # guard wiring self-test — exit 1 if the hook is missing
```

Drop `--no-push` once the collab repo has an origin remote. **Generating a
runtime kit is not installing it** — skipping the `cp` is how the
badminton-analyzer incident merged 15 PRs under a persona that was denied
`merge_pr`, silently. `baron doctor` exists so that skipping it is loud; it
verifies **wiring, not invocation** (ADR-017), and a green doctor means
"correctly wired", never "enforcement happened".

The [user guide](docs/user-guide.md) walks all of that with real output,
including a live guard denial and the failure modes. Full command reference:
[`cli/README.md`](cli/README.md). The conversational setup path (an agent
interviews you, then scaffolds) routes through
`skills/barony/assets/collab-repo/START.md` — see
[docs/concepts.md](docs/concepts.md).

**See a real one:** [`vggg/barony-demo`](https://github.com/vggg/barony-demo) is
a seeded example — a week of a fictional project's findings, decisions, handoffs
(closed and open), a waiver, and a captured live guard refusal. The project is
fictional; every artifact was produced by the real tools.

## Runtime matrix

One `persona.yaml`, four adapters, as claimed by each adapter's machine-readable
capability map (checked in CI by `tests/bi_runtime_accept.py`):

| Runtime | Tier | Whole-tool denials | Guard-covered sub-tool denials¹ | `open_pr` / `run_tests` |
|---|---|---|---|---|
| Claude Code | 3 (native subagents) or 2 (`CLAUDE.md`) | enforced at Tier 3 (tool allow-list); instructed at Tier 2 | enforced-with-baron (instructed otherwise) | instructed |
| pydantic-ai | 3 (in-process hydration) | enforced (capability omission) | enforced (in-process interception — the hook cannot be absent) | instructed |
| code-puppy | 2.75 (native JSON agents)² | enforced (tool allow-list) | instructed | instructed |
| generic (any runtime) | 1 (in-prompt + `AGENTS.md`) | instructed | instructed | instructed |

¹ The five denials the shared rules artifact (`capability-rules.v1.yaml`)
covers: `push_main`, `force_push`, `merge_pr`, `write_path` scoping,
`edit_other_personas`. Every enforcing consumer loads that same artifact, so
`git push origin main` is judged identically across runtimes. A persona runs at
the highest tier its runtime supports and degrades gracefully, with the honesty
label degrading alongside. **Note `baron init` does not reach Tier 3 on any
runtime** — it emits Tier 2 on Claude and Tier 1 elsewhere; Tier 3 needs the
in-session recipe in `adapters/<runtime>/HYDRATE.md`.

² code-puppy enforces whole-tool denials natively (JSON agent allow-list) but
its sub-tool denials stay instruction-only — a partial Tier 3, which its own
adapter labels "2.75" rather than round up.

## Honest limits

Full list with what each means for you:
[user guide §9](docs/user-guide.md#9-honest-limits), drawn from
[`docs/DECISIONS-FOR-REVIEW.md`](docs/DECISIONS-FOR-REVIEW.md) §E. The headline
four:

- **No test drives a real Claude Code process against a scaffolded repo.**
  Enforcement is proven by wiring, not by invocation.
- **The `bash -c '…'` guard bypass stands** and is documented on purpose. Static
  parsing does not recurse into an inline program string.
- **`.baron/rules.yaml` is parsed but never activated.** `baron rules validate
  --file` checks a candidate; baron still loads only the packaged artifact.
- **`baron doctor` reads project-level settings only.** A hook in
  `~/.claude/settings.json` is invisible to it.

## Status, versioning, links

Active development, not a finished product. Two version numbers, on purpose:
the **plugin/skill** version lives in `.claude-plugin/plugin.json` and the skill
frontmatter (currently **1.10.0**, sync enforced by lint); the **CLI package**
version is separate (`baron --version`). See [`STATUS.md`](STATUS.md) for
progress and [`CHANGELOG.md`](CHANGELOG.md) for release history.

- [docs/user-guide.md](docs/user-guide.md) — **start here.**
- [docs/concepts.md](docs/concepts.md) — every concept at paragraph length:
  emitted layout, capability + honesty ladders, adapters, PR-locks, signets,
  worktree topology, the `baron` surface.
- [docs/adr/](docs/adr/) — why, argued rather than asserted. ADR-001
  (runtime-agnostic architecture) through
  [ADR-022](docs/adr/ADR-022-substrate-invariant-amended-default-not-only.md)
  (what a plugin may and may not be authoritative for).
- [docs/DECISIONS-FOR-REVIEW.md](docs/DECISIONS-FOR-REVIEW.md) — the current
  consolidation: decisions, §E honest bounds, §F deliberate non-goals.
- [`cli/README.md`](cli/README.md) — full `baron` command reference.
- [`skills/multi-agent-audit/`](skills/multi-agent-audit/) — the read-only
  sister skill that *grades* any multi-agent project (not just Barony).
  Headline metric: the **intervention tax**, human touches per autonomous task.
- [docs/history.md](docs/history.md) — how a Claude-Code-only scaffolding skill
  became runtime-agnostic governance.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — PR conventions, including the
  docs-land-with-code rule.
- Installing as a Claude Code plugin:
  `/plugin install https://github.com/vggg/barony` (or a local clone path). On
  code-puppy, invoke the neutral files by path — see
  [`USING-WITH-CODE-PUPPY.md`](USING-WITH-CODE-PUPPY.md).

> Formerly `agent-project-bootstrap`; renamed at v1.7.0
> ([ADR-005](docs/adr/ADR-005-naming.md)). Old GitHub URLs redirect.

---

MIT License · [vggg](https://github.com/vggg)
