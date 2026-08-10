# Barony — user guide

For a first-time user. It goes: what this is (and is not) → the one idea you
need before you install → install → a real project → wiring enforcement and
proving it → the core loop → the limits.

**Every command below was run.** Every block of output is what came back. The
walk-through was replayed from a clean virtualenv end to end and the machine
time was **2.4 seconds**, install included — so the fifteen minutes this guide
budgets is reading time, not waiting time. Paths in the captured output are
shortened to `…/trial/` for width; nothing else is edited.

Contents:

1. [What Barony is, and what it is not](#1-what-barony-is-and-what-it-is-not)
2. [Enforced vs instructed — read this before you install](#2-enforced-vs-instructed--read-this-before-you-install)
3. [Install](#3-install)
4. [Your first project](#4-your-first-project)
5. [Wire enforcement, then prove it](#5-wire-enforcement-then-prove-it)
6. [Trigger a real denial](#6-trigger-a-real-denial)
7. [The core loop](#7-the-core-loop)
8. [Observation, which is off by default](#8-observation-which-is-off-by-default)
9. [Honest limits](#9-honest-limits)
10. [Where to go next](#10-where-to-go-next)

---

## 1. What Barony is, and what it is not

Running several AI coding agents on one long-lived project needs three
different things. They are usually confused with each other, so name them:

| Layer | What it answers | What you'd use |
|---|---|---|
| **Coordination** | Who may do what · who did what · what is true now | **Barony** |
| **Per-agent runtime** | How one agent thinks, calls tools, and edits files | Claude Code, code-puppy, a pydantic-ai harness |
| **Control plane** | Where agents run, how work is routed, deployed, scheduled, credentialed | something else — Barony has no opinion |

Barony is only the first row. It is a **coordination layer**: a spec, a CLI
(`baron`), and per-runtime adapters. The substrate is plain markdown and git —
files you can read with `cat` and diff in a PR.

**So, concretely, Barony is not:**

- **Not a runtime.** It never calls a model. It does not run an agent loop.
  `baron` is a CLI you or your agent runs between turns, plus one hook that the
  runtime calls.
- **Not a control plane.** No scheduler, no deploy, no routing, no secrets, no
  service to operate. Nothing is listening on a port.
- **Not an agent framework.** There is no message bus and no agent-to-agent
  RPC. Coordination happens at git tempo — a commit, a handoff file, a PR —
  which is deliberate: every coordination event leaves a record you can review.
- **Not an adversarial sandbox.** The guard stops a *cooperating* agent from
  doing the wrong thing. It does not contain a hostile one with shell access.
  Where the boundary must actually hold, use OS-level isolation.
- **Not a server or a database.** git + markdown is the default substrate, and
  it is the only one `baron` itself uses. `--json` output is a view, never a
  second store.

**You probably don't need it if:** you run one agent, on one-shot tasks, with
no state that has to survive the session. A plain session is simpler, and this
is real overhead.

**You probably do want it if:** several agent personas work the same repo over
weeks, you have been surprised by which one did something, and "we wrote the
rule down" has not been enough.

---

## 2. Enforced vs instructed — read this before you install

This is the distinction the whole product turns on, and `baron` prints these
two words at you constantly. Get them backwards and you will misread every
label.

> **enforced** — baron mechanises it. Something inspects the pending call and
> refuses it before the tool runs.
>
> **instructed** — it is written in a file the persona is expected to read, and
> **nothing checks**.

Both are legitimate. Only one of them is a control. Barony's position is that
labelling an instruction as enforcement is the actual failure mode — the reason
a documented protocol decays into theatre — so `baron` refuses to round up, and
CI fails an adapter that claims enforcement it cannot deliver.

Here is the table, printed by the tool itself:

```console
$ baron rules list
capability-rules v1 (capability-vocab.v1, ambiguity: conservative-deny)
VERB                 CLASS       DETECTION  ENFORCEMENT        LABEL
read_code            whole-tool  none       adapter-dependent  instructed
read_collab          whole-tool  none       adapter-dependent  instructed
write_code           whole-tool  file-op    guard              enforced
write_path           sub-tool    file-op    guard              enforced
open_pr              sub-tool    none       instructed         instructed
run_tests            sub-tool    none       instructed         instructed
merge_pr             sub-tool    command    guard              enforced
                     rules: gh.pr_merge
push_main            sub-tool    command    guard              enforced
                     rules: git.push.all_branches, git.push.default_branch_target, git.merge.on_default_branch
force_push           sub-tool    command    guard              enforced
                     rules: git.push.force_flags, git.push.plus_refspec
edit_other_personas  sub-tool    file-op    guard              enforced
                     rules: file_ops.spec_dir
```

Read that as: **six of the ten verbs label `enforced` — baron mechanises them.
The other four are instructions.** `open_pr` and `run_tests` are instructions
because guard does not parse for them. `read_code` and `read_collab` are
instructions because **baron emits no mechanism** that would omit the read
tools — not because a runtime couldn't, if you hand-wrote one.

(Five of those six — `push_main`, `force_push`, `merge_pr`, `write_path`
scoping, `edit_other_personas` — are the **sub-tool** denials, the set the
adapters and the runtime matrix call "the five guard-covered denials".
`write_code` is the sixth and is whole-tool.)

`baron rules list` prints a long footnote naming, per adapter, the test that
measured that claim. It is worth reading once. The short version: the
`adapter-dependent` label is an honest downgrade, made after measuring all four
shipped adapters and finding nothing.

---

## 3. Install

Requirements: **Python ≥ 3.10** and **git**. `gh` is needed only for
`baron lock`; nothing else in this guide uses it.

The distribution is `barony`; the console script is `baron`.

```bash
uv tool install barony      # or: pip install barony
baron --version
```

From a clone, which is what this guide was verified against:

```console
$ uv venv .venv
$ uv pip install --python .venv/bin/python /path/to/barony/cli
$ .venv/bin/baron --version
barony 0.7.0
```

**Two version numbers, on purpose.** `baron --version` reports the **CLI
package** version (`0.7.0` here). The **plugin/skill** version in
`.claude-plugin/plugin.json` is a separate line (`1.10.0`) and moves for
template and spec changes. If you are pinning something, be clear which one.

---

## 4. Your first project

Barony scaffolds a **collab repo** — the coordination substrate — as a separate
repo from the code you're actually shipping. That separation is the first thing
people ask about, so: the collab repo is the governance record. Keeping it out
of the code repo means agents' coordination churn (handoffs opening and
closing, ledgers growing) never touches your product history, and the code repo
can be cloned by someone who doesn't care about any of this.

Make a code repo to govern (skip if you have one):

```console
$ mkdir gardenkit
$ git -C gardenkit init -b main
Initialized empty Git repository in …/trial/gardenkit/.git/
$ git -C gardenkit commit --allow-empty -m "init"
[main (root-commit) e2c6929] init
```

Scaffold the collab repo beside it — two devs and a librarian:

```console
$ baron init gardenkit --dir gardenkit-collab --code-repo ./gardenkit \
    --personas dev:fern,dev:moss,librarian:iris
scaffolded gardenkit at …/trial/gardenkit-collab (39 files)
personas: fern (dev), moss (dev), iris (librarian) · runtime kit: claude
git: initialized on branch main, first commit made

next steps:
  1. cd gardenkit-collab
  2. baron validate .        # canonical specs — expect 0 errors
  3. baron status            # divergence/staleness report (green when fresh)
  4. INSTALL each persona's runtime kit where its runtime starts —
     copy agents/<slug>/runtime/ into that working copy (see its README).
     Generating the kit is not installing it: the badminton-analyzer
     incident merged 15 PRs under a persona denied merge_pr because the
     guard hook was generated and never copied.
  5. baron doctor --dir <that working copy>   # proves the wiring; exit 1
     if the hook, executable, persona, or rules are missing (ADR-017)
  6. open your runtime there — canon/START.md routes you
  7. every session: sync repos, read CONVENTIONS.md + COORDINATION.md,
     check _handoff/ (COORDINATION.md § Session-start checklist)

edit next: agents/<slug>/persona.yaml scope blocks (init fills a generic
placeholder scope), manifest.yaml description, and backlog.md.
```

`init` refuses a non-empty target directory, validates what it wrote before
reporting success, and commits exactly the files it wrote — never `git add -A`.

### What appeared, and why it looks like this

```
manifest.yaml             # the project spec: repos, backlog, roster, adapters
CONVENTIONS.md            # repo-wide rules
COORDINATION.md           # the multi-persona protocol
backlog.md                # where work comes from

canon/                    # the runtime-neutral spec, COPIED IN
  START.md ORCHESTRATE.md PARTICIPATE.md
  capability-vocab.v1.md capability-rules.md
  persona.schema.md manifest.schema.md
adapters/                 # one HYDRATE.md per runtime
  claude/ code-puppy/ pydantic-ai/ generic/

agents/
  fern/persona.yaml       # CANONICAL machine truth for this persona
  fern/runtime/           # the per-runtime kit — generated, NOT installed
    CLAUDE.md .claude/settings.json README.md
  moss/… iris/…

_handoff/                 # cross-persona messages; archive/ on close
  2026-08-10-bootstrap-to-iris-genesis.md
  README.md               # generated index block
findings/index.md         # numbered ledger F1, F2, …
decisions/index.md        # numbered ledger D1, D2, …
wiki/                     # synthesised by the librarian

.github/workflows/lock-guard.yml
.github/workflows/strip-stale-verdict.yml
```

Four of those choices are load-bearing and worth understanding now:

- **`canon/` is copied, not referenced.** A joiner clones the collab repo and
  has the whole spec — no dependency on this project, no version skew between
  what the personas were told and what you read.
- **`persona.yaml` is the machine truth; everything else about a persona is
  derived from it.** The runtime kit, `baron guard`'s decisions and
  `baron validate` all read that one file. Edit the yaml and regenerate; never
  hand-edit the derived kit. (`init` does not write the human-readable
  `AGENT.md` manual — that is conversational-path work, like the scope prose.)
- **`agents/<slug>/runtime/` is generated but not installed.** It sits in the
  collab repo. Nothing has been wired anywhere yet. §5 is about that gap, and
  the gap is the single most common way this fails.
- **Ledgers and handoffs are markdown with numbers in it.** There is no
  database. `baron` allocates numbers race-safely using git push atomicity as
  the lock.

The scaffolded persona, in full — this is what "who may do what" looks like:

```yaml
persona: Fern
slug: fern
archetype: dev
identity:
  git_name: Fern
  git_email: fern@gardenkit.local
  commit_prefix: "fern:"
  routing_label: agent-fern
capabilities:
  allow:
    - read_code
    - read_collab
    - write_code
    - write_path: [findings, _handoff]
    - open_pr
    - run_tests
  deny:
    - write_path: [wiki]
    - merge_pr
    - push_main
    - force_push
    - edit_other_personas
```

Verbs come from a **frozen vocabulary of ten** (`canon/capability-vocab.v1.md`).
They are intent-level — `open_pr`, never `gh_pr_create` — so one persona spec
maps onto every runtime.

Check the specs and the estate:

```console
$ baron validate .
4 file(s) checked: 0 error(s), 0 warning(s)

$ baron status
all green — no divergence, no overdue handoffs, ledgers current
```

You cannot invent a verb. Add `deploy_prod` to a persona's `allow:` list and:

```console
$ baron validate .
ERROR   agents/moss/persona.yaml: [verb] capabilities.allow[6]: 'deploy_prod' is not a v1 capability verb
4 file(s) checked: 1 error(s), 0 warning(s)
$ echo $?
1
```

The vocabulary is frozen because it is an *enforcement* contract, and ambiguity
there means mis-enforcement. Every v1 verb was coined during real adapter work
and exercised in a dogfood project before freezing; there is no speculative
vocabulary.

**Now edit two things before you go further**, because `init` deliberately does
not guess them: each persona's `scope:` block (it writes a placeholder and says
so) and `project.description` in `manifest.yaml`. Scope prose and roster design
are judgment work; `init` does the mechanical part and prints pointers rather
than pretending.

---

## 5. Wire enforcement, then prove it

**Generating the kit is not installing it.** In the incident this whole command
exists for, a project merged 15 PRs under a persona that was denied `merge_pr`.
Nothing failed. The hook had never been copied into `.claude/settings.json`, so
the denial degraded to persona text, exactly as designed, and silently. An
absent guard and a guard that never had to fire leave identical evidence.

So run `baron doctor` **first**, before copying anything, and watch it say so:

```console
$ baron doctor --dir ../gardenkit
baron doctor — guard WIRING self-test
project dir: …/trial/gardenkit
guard probe:  subprocess — /Users/…/.local/bin/baron guard

PASS    cli-on-path       baron -> /Users/…/.local/bin/baron — barony 0.7.0 (the default `baron` on PATH — no hook command names one) [bound: a bare executable name is resolved against DOCTOR's PATH, not the runtime's; an absolute path in the hook command removes the ambiguity]
FAIL    hook-configured   no `baron guard` PreToolUse hook in this project (no project settings file). Capability denials here are INSTRUCTED, not enforced.
                          -> Add a PreToolUse hook to .claude/settings.json whose command is `baron guard --persona-file "${CLAUDE_PROJECT_DIR}/agents/<slug>/persona.yaml"` with matcher "Bash|Edit|Write|NotebookEdit" (see adapters/claude/HYDRATE.md). …
UNKNOWN hook-matcher      no guard hook found — nothing to check the matcher of
UNKNOWN persona-file      no persona file is named by the hook command, --persona-file, or $BARON_PERSONA_FILE
PASS    rules-artifact    capability-rules v1 loaded (supported: 1), 10 verbs, ambiguity policy 'conservative-deny'
PASS    enforcement-path  a synthetic denied Write returned exit 2 with a capability reason from `/Users/…/.local/bin/baron guard`
PASS    fail-closed       malformed hook stdin returns exit 2 …
PASS    override-env      BARON_GUARD_OVERRIDE is not set — denials are not being waved through
INFO    override-log      …/gardenkit/.baron/guard-override.log — not created yet, directory writable
-- 5 pass, 1 fail, 2 unknown, 1 info
$ echo $?
1
```

Note the phrasing on the FAIL: *"Capability denials here are INSTRUCTED, not
enforced."* That is the honest reading of an unwired project, and it exits 1 so
CI can hold the line.

Now install fern's kit into fern's working copy:

```bash
cp -R agents/fern/runtime/.claude   ../gardenkit/
cp    agents/fern/runtime/CLAUDE.md ../gardenkit/
```

> **Copy those two entries, not the directory.** `agents/fern/runtime/` also
> contains a `README.md` describing the kit. `cp -R agents/fern/runtime/. ../gardenkit/`
> would drop it at the root of your code repo, on top of your own README.

Then prove it:

```console
$ baron doctor --dir ../gardenkit
guard probe:  subprocess — …/trial/.venv/bin/baron guard

PASS    cli-on-path       baron -> …/.venv/bin/baron — barony 0.7.0 (named by the hook command)
PASS    hook-configured   .claude/settings.json wires a PreToolUse hook: `baron guard --persona-file "${CLAUDE_PROJECT_DIR}/../gardenkit-collab/agents/fern/persona.yaml"`
PASS    hook-matcher      matcher "Bash|Edit|Write|NotebookEdit" covers all governed tools (Bash, Edit, Write, NotebookEdit)
PASS    persona-file      …/gardenkit-collab/agents/fern/persona.yaml (the hook command) parses — slug 'fern', 6 allow / 5 deny verb(s)
PASS    rules-artifact    capability-rules v1 loaded (supported: 1), 10 verbs, ambiguity policy 'conservative-deny'
PASS    enforcement-path  a synthetic denied Write returned exit 2 with a capability reason from `…/.venv/bin/baron guard` (named by the hook command) — the command Claude Code would start does block
PASS    fail-closed       malformed hook stdin returns exit 2 from `…/.venv/bin/baron guard` (named by the hook command)
PASS    override-env      BARON_GUARD_OVERRIDE is not set — denials are not being waved through
INFO    override-log      …/gardenkit/.baron/guard-override.log — not created yet, directory writable
-- 8 pass, 0 fail, 0 unknown, 1 info
$ echo $?
0
```

### What a green doctor does and does not mean

Doctor prints its own bound on every run, green included, and you should take
it literally:

> doctor verifies **WIRING, not invocation**. It proves this install *can*
> enforce […]. It **cannot** observe whether Claude Code actually ran the hook
> on a real tool call; nothing outside the runtime can.

Read a green doctor as *"correctly wired"*. Never as *"enforcement happened"*.

Two further bounds it also prints, both of which will bite someone:

- Checks 6–7 spawn **the executable the hook names**, not the imported `baron`
  package — because a project wired to a stale or hand-rolled `baron` is the
  same failure as no hook at all. Where the hook names nothing resolvable,
  doctor falls back in-process and says so; that PASS is about the library.
- A **bare** `baron` in the hook command is resolved against *doctor's* `PATH`,
  not the runtime's. In the first run above, that resolved to a different
  install than the one under test — visible in the `guard probe:` line, which
  is why doctor prints it. An absolute path in the hook command removes the
  ambiguity.

And one bound it does not print: **doctor reads project-level settings only.**
A hook wired in `~/.claude/settings.json` is invisible to it and reads as a
FAIL.

---

## 6. Trigger a real denial

`baron guard` is a Claude Code **PreToolUse hook**: hook JSON on stdin, exit 0
to stay out of the way, exit 2 with a reason on stderr to block. You can drive
it by hand, which is the fastest way to see what your persona actually permits.

`fern` denies `push_main`. Save a hook payload as `pretooluse.json` — `cwd` is
the working copy the call would run in, and is where the override log below
lands, so make it absolute:

```json
{"hook_event_name":"PreToolUse","session_id":"s1","tool_name":"Bash",
 "tool_input":{"command":"git push origin main"},
 "cwd":"/abs/path/to/trial/gardenkit"}
```

```console
$ baron guard --persona-file agents/fern/persona.yaml < pretooluse.json
baron guard: DENY Bash for persona 'fern' (agents/fern/persona.yaml)
  target: git push origin main
  inferred capability `push_main` — not granted to this persona (no origin remote is configured yet, so the default branch can't be confirmed — treating `main` as the default branch to stay on the safe side)
If this operation is deliberate: re-run with BARON_GUARD_OVERRIDE="<reason>" set — the call will be allowed and the override appended to .baron/guard-override.log (a TRACKED file; turn the override into a _handoff/ explaining it). Otherwise route the work through a persona that holds the capability.
$ echo $?
2
```

Three things in that one output. The verb is **named**, so the agent is told
what it lacked rather than just refused. The **inference is named** — parsing is
conservative, and when guard cannot confirm the default branch it says which
way it erred. And the **escape hatch is offered**, because a guard that can
brick a session is worse than no guard.

### The dry run, without hand-writing JSON

```console
$ baron rules explain 'git push origin main' --persona-file agents/fern/persona.yaml
target : git push origin main
persona: fern (agents/fern/persona.yaml)
verdict: DENY
verbs  :
  push_main            enforced   (guard; candidate rules: git.push.all_branches, git.push.default_branch_target, git.merge.on_default_branch)
reason :
  inferred capability `push_main` — not granted to this persona (…)
$ echo $?
1

$ baron rules explain 'git push origin main' --persona-file agents/iris/persona.yaml
target : git push origin main
persona: iris (agents/iris/persona.yaml)
verdict: ALLOW
verbs  :
  push_main            enforced   (guard; candidate rules: git.push.all_branches, git.push.default_branch_target, git.merge.on_default_branch)
$ echo $?
0
```

Same command, two personas, opposite verdicts — which is what
persona-dependent enforcement means, and it is exactly the difference between
this and a lint rule. `explain` calls the real evaluator, not a
reimplementation, and a test pins the two together so they cannot drift.

**Why the librarian may push to main, and what that costs.** Look at the
scaffolded `agents/iris/persona.yaml`:

```yaml
    - push_main          # scoped by instruction to wiki/ + _handoff/ only (CONVENTIONS push policy)
```

That comment is the whole lesson in one line. The **verb** is enforced — guard
allows or denies `push_main` per persona, mechanically. The **narrowing** —
"only for wiki and handoffs" — is an *instruction* in `CONVENTIONS.md`, and
nothing checks it. Guard has no verb for "may push main, but only these paths":
it maps the command to `push_main`, sees iris holds it, and allows. Iris
direct-pushing a `findings/` or `decisions/` change to main is outside the
stated policy and guard will not stop her.

If that gap matters to you, do not grant `push_main` — grant it to a merger
persona and route everything through PRs. Reading the label correctly is what
tells you which of the two you are relying on.

### The override, and why it is loud

```console
$ BARON_GUARD_OVERRIDE="release cut, approved in _handoff/2026-08-10-cut.md" \
    baron guard --persona-file agents/fern/persona.yaml < pretooluse.json
$ echo $?
0
$ cat ../gardenkit/.baron/guard-override.log
2026-08-10T17:14:55.315560+00:00	Bash	git push origin main	release cut, approved in _handoff/2026-08-10-cut.md
2026-08-10T17:26:11.302423+00:00	Bash	git push origin main	second cut, same handoff
```

That log is **tracked**, deliberately not gitignored. An override is a
deliberate human act and belongs in the diff. `baron doctor` also fails you if
`BARON_GUARD_OVERRIDE` is sitting exported in your shell, because at that point
every denial is being waved through.

### The bypass you should know about now

Take the same payload as above and wrap the command in `bash -c`:

```json
{"hook_event_name":"PreToolUse","session_id":"s1","tool_name":"Bash",
 "tool_input":{"command":"bash -c 'git push origin main'"},
 "cwd":"/abs/path/to/trial/gardenkit"}
```

```console
$ baron guard --persona-file agents/fern/persona.yaml < bypass.json
$ echo $?
0
```

Silence, exit 0. The identical push was denied a moment ago.

`bash -c '…'`, `sh -c "…"` and `python3 -c '…'` run their payload uninspected.
The parser inspects each top-level subcommand's tokens; it does not recurse
into an interpreter invoked with an inline program string. This is **not
fixed**, it is documented on purpose, and it is stated again in §9. It is an
accepted limit of static enforcement against the honest-mistake class — which
is the class it targets. `bash -c` is common enough to hit by accident. Where
the boundary must hold against a wrapper, you need OS-level isolation.

---

## 7. The core loop

### Ledgers and handoffs

Findings (investigation outputs) and decisions are numbered entries in
markdown. Handoffs are how anything material crosses between personas — a PR
description is not a substitute.

```console
$ baron finding new --title "Guard blocks push_main for fern" --author fern --no-push
F1 — Guard blocks push_main for fern (committed (not pushed))

$ baron handoff create --for moss --from fern --title "Review the guard seam"
…/gardenkit-collab/_handoff/2026-08-10-review-the-guard-seam.md

$ baron handoff close _handoff/2026-08-10-review-the-guard-seam.md \
    --note "Done, see F1." --as moss
…/gardenkit-collab/_handoff/archive/2026/2026-08-10-review-the-guard-seam.md

$ baron index
wrote …/gardenkit-collab/_handoff/README.md
ok      findings: numbering duplicate-free and monotonic
ok      decisions: numbering duplicate-free and monotonic
```

Closing a handoff `git mv`s it to `_handoff/archive/YYYY/` — **archive, never
delete**. Number allocation is race-safe: append, commit, push; on push
rejection, rebase, renumber, retry. git's push atomicity is the lock. Duplicate
numbers are an error; historical gaps are reported and never rewritten, because
tidying history would forge the record. Drop `--no-push` once the collab repo
has a remote.

### `baron status` — the divergence radar

```console
$ baron status
SEV   AREA  SUBJECT                              CHECK  DETAIL
warn  repo  repo:code …/trial/gardenkit           dirty  2 uncommitted path(s)
warn  repo  repo:collab …/trial/gardenkit-collab  dirty  1 uncommitted path(s)
-- 0 red, 2 warn
$ echo $?
0
```

Reds are: commits never pushed, origin commits never pulled, an unmerged branch
(with age), and a handoff open past the SLA. Warns are dirt and ledger/wiki
staleness. **Exit 1 on any red**, so this goes in CI. Add `--fetch` or the
`behind` class is invisible.

Parking a red deliberately is `baron waiver add`, and a waiver needs a reason,
a linked handoff, and a **mandatory expiry** — an expired waiver stops matching
and the red comes back on its own.

### `baron export` — citable records, not a memory service

```console
$ baron export
finding  F1             -            ac5d3516  Guard blocks push_main for fern
handoff  2026-08-10-bootstrap-to-iris-genesis open  f7c28bb8  Iris — genesis acknowledgment
handoff  2026-08-10-review-the-guard-seam     done  8dd892a7  Review the guard seam

3 record(s) at 8dd892a7 (finding=1, handoff=2)
```

Every record names the commit whose bytes were parsed, so the citation is
reproducible:

```console
$ baron export --json | jq '.records[0] | {id, path, commit_sha}'
{
  "id": "F1",
  "path": "findings/index.md",
  "commit_sha": "ac5d35169ffa0dc31c1ee59adfacb472c9f8da75"
}

$ git show ac5d35169ffa0dc31c1ee59adfacb472c9f8da75:findings/index.md
…
### F1 — Guard blocks push_main for fern (2026-08-10, fern)
```

A source that is untracked or has uncommitted edits is **skipped and named**,
never emitted with a SHA that resolves to different text. There is no knowledge
backend behind this, no vendor dependency, and no plugin group — `--json` plus
`jq` is the whole interface.

### Worktrees, and the one path gotcha

Each persona gets a git worktree on branch `persona/<slug>` over one shared
object store, instead of a clone each (clones drift).

```console
$ baron worktree add fern
…/trial/gardenkit-worktrees/fern
$ baron worktree list
PATH                                    BRANCH        AHEAD  BEHIND
…/trial/gardenkit                       main          0      0    (main working copy)
…/trial/gardenkit-worktrees/fern        persona/fern  0      0
```

The generated kit's hook path assumes the working copy is a **sibling** of the
collab repo. A worktree under `workspace.worktrees_root` is one level deeper,
so copying the kit in unchanged breaks the path — and doctor is what tells you,
by name:

```console
$ baron doctor --dir ../gardenkit-worktrees/fern
FAIL    persona-file      persona named by the hook command does not load: persona file not found: …/gardenkit-worktrees/fern/../gardenkit-collab/agents/fern/persona.yaml
-- 7 pass, 1 fail, 0 unknown, 1 info
```

Fix the depth in that copy's `.claude/settings.json` (`/../` → `/../../`) and
it goes green at 8 pass. The kit's own README warns about this; doctor is what
makes forgetting loud.

### Catching a persona that was never hydrated

`baron validate` also compares the declared roster against the runtime's agent
registry — but only for runtimes the manifest **explicitly declares** under
`adapters:`. The signal it looks for is **partial** registration, because zero
registered agents is legitimate in several cases and would be a false alarm.

Captured from a second scaffold (`--runtime code-puppy`, personas `scout` and
`librarian`) with `adapters: {code-puppy: {}}` added to the manifest and only
`scout` hydrated:

```console
$ baron validate .
ERROR   manifest.yaml: [runtime-drift] code-puppy: persona 'librarian' is declared in
manifest.personas but has no agent registered, while 1/2 sibling personas are registered
in this project's own repo (scout) — so this project DOES hydrate agents here and
'librarian' was missed. Work routed to it will silently run as some other agent: wrong
identity, wrong commit prefix, wrong capabilities. …
3 file(s) checked: 1 error(s), 0 warning(s)
$ echo $?
1
```

That is a real incident shape: a cron ran under the wrong persona because one
agent file was never written. Note the precondition — with `--runtime claude`,
`baron init` writes an `adapters.claude` block for you; with `--runtime
code-puppy` it writes **no `adapters:` block at all**, so this check stays
silent until you add one by hand.

### Other runtimes

One `persona.yaml`, four adapters, and a persona runs at the highest tier its
runtime supports with the honesty label degrading alongside:

| Runtime | Kit `baron init --runtime …` emits | Whole-tool denials | The five guard-covered sub-tool denials |
|---|---|---|---|
| Claude Code | Tier-2 `CLAUDE.md` + `.claude/settings.json` hook | instructed at Tier 2; enforced at Tier 3 | **enforced** once the hook is wired |
| pydantic-ai | `agent_setup.py`, which *is* the Tier-3 hydration | enforced (capability omission) | **enforced** in-process — the hook cannot be absent |
| code-puppy | Tier-1 `AGENTS.md` | enforced at Tier 3, which is hand-hydrated | instructed |
| generic | Tier-1 `AGENTS.md` | instructed | instructed |

The five guard-covered sub-tool denials are `push_main`, `force_push`,
`merge_pr`, `write_path` scoping, and `edit_other_personas`. `open_pr` and
`run_tests` are instructed everywhere. Every enforcing consumer loads the same
`capability-rules.v1.yaml`, so `git push origin main` is judged identically on
Claude Code and on pydantic-ai.

Two things to take from the middle column. **Tier 3 is where whole-tool denials
become real**, and on Claude Code and code-puppy `baron init` does not get you
there — it emits Tier 2 and Tier 1 respectively, and Tier 3 needs the in-session
recipe in `adapters/<runtime>/HYDRATE.md`. pydantic-ai is the exception: its
emitted bootstrap builds the guarded agent in-process, so hydration and Tier 3
are the same step. Running code-puppy? See
[`USING-WITH-CODE-PUPPY.md`](../USING-WITH-CODE-PUPPY.md).

*This walk-through exercised the Claude Code path only.* The pydantic-ai path
needs the optional extra (`pip install 'barony[pydantic-ai]'`) and was not run
here; the table above restates the adapters' own machine-checked claims.

---

## 8. Observation, which is off by default

`baron guard` can emit a structured row per decision. **The default sink is
`null` and baron writes nothing** — that is a signed decision, not an
oversight. Enabling telemetry is an operator's act, not a consequence of
installing a governance tool.

```console
$ BARON_EVENTS_SINK=disk baron guard --persona-file agents/fern/persona.yaml < pretooluse.json
$ find ../gardenkit/.baron/events -type f
../gardenkit/.baron/events/2026-08-10.jsonl
../gardenkit/.baron/events/.gitignore

$ jq . ../gardenkit/.baron/events/2026-08-10.jsonl
{
  "span_name": "guard.decision",
  "trace_id": "02cccd8bc6847069157ea145448b2fb7",
  "span_id": "9db18070e9e9626c",
  "start_timestamp": "2026-08-10T17:15:01.195336+00:00",
  "end_timestamp": "2026-08-10T17:15:01.195336+00:00",
  "attributes": {
    "events.version": 1,
    "baron.actor": "fern",
    "baron.subject": "git push origin main",
    "baron.outcome": "deny",
    "agent.name": "fern",
    "tool.name": "Bash",
    "session.id": "trial-1",
    "baron.capability.verb": "push_main",
    "baron.enforcement": "enforced",
    "baron.events_version": 1,
    "baron.reason": "inferred capability `push_main` — not granted to this persona (…)",
    "baron.runtime": "claude-code",
    "baron.trigger": "PreToolUse"
  }
}
```

Flat JSONL, no OpenTelemetry dependency. The `.gitignore` that appeared beside
it holds `*` and lives **inside** `.baron/events/` — deliberately not at
`.baron/` level, because an ignore there would silently un-track
`.baron/guard-override.log`.

Three things to know before you turn it on:

- **`baron.enforcement` on a row is a per-call observation** — did a capability
  adjudicate *this* call — with the vocabulary `enforced | unevaluated |
  unknown`. It is not the static posture label from §2, which is a property of
  (persona, verb, runtime) and lives only on `baron rules list`.
- **The verb is not a proxy for the enforcement field.** An `unevaluated` row
  still carries a `baron.capability.verb`. Any aggregation must filter on
  `enforcement == "enforced"` *before* it groups by verb, or it over-counts.
- **Emission fails open and silent; enforcement fails closed.** A broken sink
  can never turn "log this" into "deny everything". `BARON_EVENTS_DEBUG=1` to
  see swallowed errors. `.baron/events/` is gitignored; retention is yours.

---

## 9. Honest limits

Not a footnote. These are the things a green test suite invites you to assume
and shouldn't.

1. **No test drives a real Claude Code process against a scaffolded repo.**
   Enforcement is proven by **wiring**, not by invocation. `baron doctor` is the
   nearest thing and says so on every run. Whether the runtime actually called
   the hook on a real tool call is not observable from outside the runtime.
2. **The `bash -c '…'` guard bypass stands.** Demonstrated live in §6. Not a
   regression, not fixed, documented on purpose. Static parsing of an inline
   program string is out of scope; use OS-level isolation where the boundary
   must actually hold.
3. **`.baron/rules.yaml` is parsed but never activated.** `baron rules validate
   --file` and `baron rules diff --file` will check a candidate rules document —
   and baron still loads only the **packaged** artifact. There is no
   project-level rules discovery, no merge, no precedence. Do not build a
   workflow on the assumption that a local rules file changes anything.
4. **`baron doctor` reads project-level settings only.** A hook wired in
   `~/.claude/settings.json` is invisible and reads as FAIL, and a bare
   executable name resolves against doctor's `PATH`, not the runtime's. Both
   bounds are printed on every run. Note this bites the *default* wiring, which
   is a bare `baron guard …`.
5. **Runtime neutrality is proved with two producers, not three.** Claude Code
   and pydantic-ai both emit into the same plane in the same wire shape, and
   their rows for one governance fact differ in exactly four attributes. That
   falsifies "the plane is Claude-Code-shaped"; it is not proof the shape fits
   every runtime. code-puppy has **no pre-tool seam**, so it emits nothing and
   is deliberately absent rather than emitting post-hoc rows implying an
   adjudication that never happened.
6. **`instructed` is verified at emission, never at receipt.** It means baron
   put the sentence in the kit. Nothing checks that the runtime loaded the file,
   so a silently-ignored `AGENTS.md` is indistinguishable from a heeded one.
   This is the honest ceiling on the label.
7. **No adapter's read-tool exposure is verified against a live runtime.** All
   four are measured, but only pydantic-ai's measurement runs the emitted kit;
   the other three are static inspections proving *baron emits no mechanism* —
   which is the claim `baron rules list` makes, and nothing more.

The project publishes its own measured operational fidelity of **0.53** — about
half of a documented coordination protocol actually being followed, on a real
first-party project — rather than rounding up. These bounds are in the same
spirit. They are the reason to believe the labels that *are* green.

---

## 10. Where to go next

- **[`../README.md`](../README.md)** — the 30-second version and the four
  problems this exists for.
- **[`concepts.md`](concepts.md)** — every concept here at paragraph length:
  the front door, the emitted layout, the capability and honesty ladders, the
  adapters, PR-locks, signets.
- **[`../cli/README.md`](../cli/README.md)** — the full `baron` command
  reference, including `lock`, `waiver`, `session`, `hydrate` and every flag.
- **[`adr/`](adr/)** — why, argued rather than asserted. Start with
  [ADR-003](adr/ADR-003-baron-cli.md) (the CLI and the field incidents behind
  it), [ADR-004](adr/ADR-004-baron-guard-enforcement.md) (guard),
  [ADR-017](adr/ADR-017-baron-doctor-wiring-selftest.md) (doctor and the
  wiring-vs-invocation bound), and
  [ADR-022](adr/ADR-022-substrate-invariant-amended-default-not-only.md) (what a
  plugin may and may not be authoritative for).
- **[`DECISIONS-FOR-REVIEW.md`](DECISIONS-FOR-REVIEW.md)** — the current
  consolidation's decisions, §E honest bounds and §F deliberate non-goals. §9
  above is drawn from §E.
- **[`../skills/multi-agent-audit/`](../skills/multi-agent-audit/)** — the
  read-only sister skill that *grades* a multi-agent project (any framework, not
  just Barony). Headline metric is the **intervention tax**: human touches per
  autonomous task.
- **[`BACKLOG.md`](BACKLOG.md)** — what is not built, and why.
- **[`history.md`](history.md)** — how a Claude-Code-only scaffolding skill
  became runtime-agnostic governance.
- **[`vggg/barony-demo`](https://github.com/vggg/barony-demo)** — a seeded
  example project: a week of findings, decisions, handoffs, a waiver, and a
  captured live guard refusal. The project is fictional; every artifact was
  produced by the real tools.
