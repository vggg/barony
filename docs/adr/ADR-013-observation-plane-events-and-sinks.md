---
created: 2026-08-09
type: decision
status: accepted
decided_by: Vikram
adr: 013
project: barony
related:
  - "[[docs/adr/ADR-003-baron-cli]]"
  - "[[docs/adr/ADR-004-baron-guard-enforcement]]"
  - "[[docs/adr/ADR-007-session-boundary]]"
  - "[[docs/adr/ADR-008-ways-of-working-2026-07-31]]"
---

# ADR-013 (ACCEPTED): Observation plane — events, sinks, and the enforcement/evidence asymmetry

| Field | Value |
|---|---|
| **Status** | **Accepted** — shipped with `baron.events` + `baron.sinks` |
| **Date** | 2026-08-09 |
| **Authors** | Claude (Workstream: event stream + pluggable datastore) |
| **Decision owner** | Vikram |
| **Depends on** | [ADR-003](ADR-003-baron-cli.md) (dependency policy), [ADR-004](ADR-004-baron-guard-enforcement.md) §2.3 (fail-closed) |
| **Numbering note** | ADR-010 and ADR-011 are held by open PRs #29 / #32 and are not reused here. |

## 1. Context and the problem

Baron has no event stream. What it has is a set of per-command, one-off emissions
that never meet each other:

- `guard.log_override()` appends a tab-separated line to the **tracked**
  `.baron/guard-override.log` — and only for overrides. Ordinary allow/deny verdicts
  are printed to stderr and discarded.
- `ledger.add_entry()` returns an int; the fact that "F42 was created by Dara" survives
  only as a git commit message.
- `session.SessionBrief.to_dict()` / `EndReport.to_dict()` already serialise cleanly,
  are printed under `--json`, and are then thrown away.
- `decision.reconcile()` produces `Finding` / `Park` dataclasses on the same pattern.

Every downstream consumer the roadmap names — fleet-health (AGENT-TASKS 3.2), the
pluggable knowledge substrate (3.4), the "Logfire or Phoenix wired" line in
`roadmap.md` — needs the same thing first: **one shape for "something happened", and
one configurable place to put it.** Building any of them without that means three
incompatible telemetry formats and a migration.

This ADR fixes the contract. It is deliberately small, because it is the piece other
workstreams code against and it cannot be changed cheaply once they do.

## 2. Decision — the wire shape

One frozen `Event` dataclass in `cli/src/baron/events.py`, serialised by `to_row()` to
exactly one flat JSON object per line:

```json
{
  "span_name": "guard.decision",
  "trace_id": "00000000000000000000000000000000",
  "span_id": "1111111111111111",
  "start_timestamp": "2026-07-22T12:00:00+00:00",
  "end_timestamp": "2026-07-22T12:00:00+00:00",
  "attributes": {
    "events.version": 1,
    "baron.actor": "dara",
    "baron.subject": "git push origin main",
    "baron.outcome": "deny",
    "agent.name": "dara",
    "tool.name": "Bash",
    "session.id": "",
    "baron.capability.verb": "push_main",
    "baron.enforcement": "enforced",
    "baron.reason": "push to the default branch"
  }
}
```

That block is not illustrative prose. `tests/test_events.py::test_adr_013_documents_the_same_row`
parses this file, reads the first ```json fence, and asserts it equals `Event(...).to_row()`.
Drift between this document and the code is a test failure.

Field notes:

- **`start_timestamp` / `end_timestamp` come from `clock.now()`, never `datetime.now()`.**
  `clock.py` is the mandated single source of "now" and carries the `BARON_NOW` backfill
  hatch; an event that bypassed it could not be seeded, backfilled, or tested
  deterministically. A test pins this by injecting a clock.
- Baron's events are points in time, so the two stamps are equal. The pair exists because
  the ingester expects a span shape; a future duration-bearing emitter can widen it without
  a version bump.
- `trace_id` (32 hex) and `span_id` (16 hex) are generated per event when not supplied.
  Correlation across events within one session is a follow-up, not v1: nothing today has a
  parent span to hang off.
- `events.version` is `1` and is bumped only on an incompatible change to this shape.

### 2.1 `kind` is an open dotted string, not a closed enum

Emitted as `span_name`. Baron itself emits `guard.decision`, `guard.override`,
`session.start`, `session.end`, `tool.post`, `tool.failure`; the registry table lives in
the `baron.events` module docstring and grows in the same change as its emitter.

This is the opposite call from the capability vocabulary, which is FROZEN — and the
difference is the whole point of this ADR. The vocabulary is an **enforcement** contract:
an unrecognised verb there means mis-enforcement, so ambiguity is intolerable. This stream
is **observation**: an unrecognised kind costs an analyst one `grep`. Third parties must be
able to emit their own kinds without a baron release.

There is deliberately **no runtime warning** on an unknown kind. It would fire on every
third-party event, and warnings that always fire train people to ignore the channel — which
in guard's case is the channel carrying the actual denial message.

What is frozen instead is the **`baron.` attribute-key namespace**, because that is what
consumers actually parse. Reserved for v1: `baron.actor`, `baron.subject`, `baron.outcome`,
`baron.capability.verb`, `baron.enforcement`, `baron.reason`. Additions are additive;
redefinitions are a version bump.

## 3. Decision — the Sink Protocol, final at three members

`cli/src/baron/sinks/base.py` defines a `@runtime_checkable` `Protocol` with exactly
`name`, `emit(event)`, `close()`, plus `SinkError` / `SinkUnavailable`. Resolution is
`get_sink(name)` in `sinks/__init__.py`, structurally identical to `forge/__init__.py`'s
`get_forge`: built-ins (`null`, `disk`) first, then `entry_points(group="baron.sinks")`
matched by `ep.name`, else a `SinkError` naming the built-ins.

**Three members, final.** `@runtime_checkable` makes `isinstance` test method *presence*,
so adding a fourth member later retroactively invalidates every third-party sink that was
correct the day it was written. The project already paid this: `Forge` grew `get_issue` and
an existing fake stopped satisfying `isinstance`. `forge/base.py` carries the warning;
`sinks/base.py` carries it again, and `test_sink_protocol_surface_is_exactly_three_members`
makes it mechanical rather than aspirational.

Optional capabilities therefore live **outside** the Protocol, discovered with `hasattr`:

- `flush()` — a batching sink may offer it; nothing requires it.
- `bind(cwd)` — a repo-writing sink may offer it, and `events.emit(event, cwd)` calls it
  when present. This exists because `baron guard` learns its cwd from the *hook payload*,
  which need not be the process cwd. Threading that through the Protocol would have cost a
  fourth member for one sink's benefit.

We considered an ABC instead, which would permit safe additions. Rejected: consistency with
the established `baron.forges` plugin pattern is worth more than that flexibility, and two
different plugin idioms in one small CLI is its own tax.

## 4. Decision — the asymmetry: enforcement fails CLOSED, evidence fails OPEN

**This is the load-bearing decision in this document.**

ADR-004 §2.3 is unchanged: guard is fail-closed. A malformed payload, a broken rules
artifact, an internal bug — all become a deny with actionable stderr, because a guard that
fails open is not a guard.

`events.emit()` is the deliberate mirror image. It catches **every** exception and returns
`None`. Rationale, stated as the scenario it prevents: a full disk, a read-only checkout, a
third-party sink whose HTTP client hangs, or a plugin with a typo in `__init__` would
otherwise turn a working session into one where *every tool call* raises inside a
PreToolUse hook. Guard's fail-closed policy would then convert that into *deny everything* —
an unrecoverable brick, caused not by a policy violation but by a logging destination. A
telemetry pipeline must never be able to do that.

The diagnostic is opt-in: `BARON_EVENTS_DEBUG=1` prints the swallowed error to stderr.
It is off by default because guard's stderr **is fed to the model on exit 2** — noise there
degrades the denial message that the deny path exists to deliver.

`test_sink_failure_does_not_change_guard_exit_code` locks this: with `events.emit`
monkeypatched to raise, the deny path still returns exit 2 and the allow path still returns
`(0, "")`.

### 4.1 Honesty rule: events are OBSERVATION, never enforcement

Nothing in `baron.events` or `baron.sinks` can allow, deny, or alter the outcome of any
command. Emission is one-way and consequence-free by construction — §4 guarantees it, since
a component whose failure is ignored cannot be load-bearing.

The one place this could be misread is the `baron.enforcement` attribute. It is a label
describing **the capability verb** the call mapped to, and it is DERIVED at emit time from
the rules artifact's `detection` field: `command` or `file-op` → `"enforced"`,
`none` → `"instructed"`. It is never hardcoded, because `capability-rules.v1.yaml` sets
`detection: none` for `open_pr` and `run_tests`, and stamping those `"enforced"` is exactly
the overclaiming ADR-002 / ADR-008 forbid. The attribute says something about the verb.
It says nothing about the emission, which is observation either way.

## 5. Decision — the event stream is gitignored; the override log stays TRACKED

The disk sink writes `<repo root>/.baron/events/<YYYY-MM-DD>.jsonl` and, on first write,
creates `.baron/events/.gitignore` containing `*`.

The `.gitignore` is scoped **inside** `.baron/events/`, deliberately not at `.baron/` level.
An ignore at `.baron/` would silently un-track `.baron/guard-override.log` in every
downstream repo, quietly removing a governance property that already exists. A test asserts
the override log stays tracked after the sink has written.

The distinction is substantive, not cosmetic:

| | `.baron/guard-override.log` | `.baron/events/*.jsonl` |
|---|---|---|
| What it records | deliberate human acts crossing a capability boundary | machine observation of ordinary operation |
| Volume | a handful, each expected to become a `_handoff/` | one row per tool call |
| Kind | **evidence** — belongs in the diff, in review | **telemetry** — belongs on local disk |
| Git | tracked | ignored |

Committing the event stream would bury real diffs under thousands of machine rows, and
would leak local command strings into shared history. Retention is `find .baron/events
-mtime +N -delete`, not something baron guesses: rotation is by UTC date, there is no size
cap, and nothing prunes. A governance tool that silently deletes its own records is worse
than one that grows.

### 5.1 The `.baron/` convention

`.baron/` is **machine-written state**: the override log, now the event stream. Root
dotfiles are **human-authored config**: `.baron-waivers.yaml`. This ADR states the
convention because the split was previously implicit and the next writer would have had to
guess. A project-level rules file would be human-authored and therefore does **not** belong
under `.baron/`; that collision is settled in whichever ADR ships it, not here.

## 6. Decision — no OpenTelemetry dependency in core, ever

ADR-003's policy (typer + pyyaml only) holds. The disk sink uses stdlib `json`; orjson is
out for the same reason.

OTel *compatibility* is achieved by choosing a wire shape the project's existing file-based
ingester already parses. Verified against
`skills/multi-agent-audit/scripts/ingest_otel.py`: `span_name`, `trace_id`, `span_id`,
`start_timestamp`, `end_timestamp` are each the **first** entry of that script's
`FLAT_NAME_KEYS` / `FLAT_TRACE_KEYS` / `FLAT_SPANID_KEYS` / `FLAT_START_KEYS` /
`FLAT_END_KEYS`, and `agent.name` / `tool.name` / `session.id` are already in its
`AGENT_KEYS` / `TOOL_NAME_KEYS` / `SESSION_ATTR_KEYS`. So `record_from_flat` reads baron's
own stream with zero new code. `test_row_keys_are_the_ingesters_first_choice_keys` re-derives
those first entries from the script and fails if either side drifts.

This also upholds the stated position that telemetry ingestion is **files, never
endpoints** (`skills/multi-agent-audit/SKILL.md` — declining live Logfire/Phoenix queries is
explicit policy). A team that wants a live exporter installs a distribution registering
`baron.sinks`; the dependency lives there, not here.

## 7. Configuration: `BARON_EVENTS_SINK` now, `events:` in the manifest reserved

Sink selection is the `BARON_EVENTS_SINK` environment variable, default `"null"`. Baron
writes nothing unless an operator opts in.

An optional `events:` node (`sink`, plus an opaque `options` map) is added to
`MANIFEST_SPEC`. **Honest bound: no baron command reads it in v1.** It is declared for two
reasons — so a manifest carrying it does not trip `baron validate`'s unknown-field warning
(only `adapters:` and `runtime.adapters` are opaque today), and so the config key is
reserved before another workstream invents a different one.

Wiring it is deferred rather than forgotten. The blocker is measurement, not design: guard
runs as a PreToolUse hook on *every* tool call, and adding a manifest discovery + YAML parse
to that path is a latency regression nobody has quantified. The likely resolution is that
adapters render `events.sink` into the hook environment at `baron init` time, so the hot
path still reads only an env var. That belongs in the ADR that measures it.

## 8. What shipped

- `cli/src/baron/events.py` — `EVENTS_VERSION`, frozen `Event`, `to_row()`, `sink_name()`,
  fail-open `emit()`, and the kind registry in the module docstring.
- `cli/src/baron/sinks/` — `base.py` (Protocol + errors), `__init__.py` (`get_sink`),
  `disk.py`, `null.py`.
- `cli/pyproject.toml` — the `baron.sinks` entry-point group, both built-ins declared.
- `cli/src/baron/schemas.py` — the reserved, currently-unread `events:` manifest node.
- `cli/src/baron/guard.py` — the one wired call site (see §9).
- `cli/tests/test_events.py`, `cli/tests/test_sinks.py`, and three additions to
  `cli/tests/test_guard.py`.

## 9. Scope: exactly one wired call site

Only guard's verdict path emits. That is the one command that already persists events, so it
proves the interface end to end against a real caller rather than a demo. `ledger`,
`session`, `decision` and the runtime adapters are left untouched; they now have an
importable, tested contract to adopt on their own schedule.

The tab-separated `.baron/guard-override.log` is byte-for-byte unchanged. It is cited in
`guard._remedy()`'s user-facing text and in the docs; events are strictly additive.

## 9.1 MEASURED DEFECT in `baron.enforcement` (ops-plane merge, 2026-08-09)

Recorded here rather than fixed, because fixing it decides a question the owner has not
answered yet (see `docs/DECISIONS-FOR-REVIEW.md`, decision **D1**). **Do not read
`baron.enforcement` as trustworthy until D1 is resolved.**

`_enforcement()` derives the label from the rules artifact's `detection` field for the
verbs attached to a `Decision`. That describes **the verb**, not **this evaluation** — and
the two come apart in both directions. Measured against the merged code, not argued:

| call | `Decision.verbs` | emitted `baron.enforcement` | what actually happened |
|---|---|---|---|
| `Write ../../../outside.md` | `('write_path',)` | **`enforced`** | Structural refusal. Guard blocked it because the path escapes the repo root; **no capability adjudicated it** and every persona is denied identically. Over-counts. |
| `Write src/x.py`, persona holds `write_code` | `()` | **`not-applicable`** | A genuine, persona-dependent adjudication — a persona without `write_code` is denied here. Under-counts. |
| `Write _handoff/x.md` | `()` | `not-applicable` | Correct: universal zone, persona-independent. |

So a consumer aggregating on `baron.enforcement` books structural refusals as capability
enforcement and misses real capability allows. `harden/otel` (ADR-014, NOT merged) diagnosed
exactly this and fixed it with a `Decision.adjudicated` flag set at each return site — "a
rule matched AND the outcome turned on the acting persona" — which is the correct basis.

One criticism ADR-014 makes does **not** currently bite: it argues `instructed` asserts a
control guard never measured. True in principle, unreachable in practice — every verb guard
can attach to a `Decision` (`write_code`, `write_path`, `edit_other_personas`, `push_main`,
`force_push`, `merge_pr`) has `detection: command|file-op`, so `instructed` is not emitted on
any real row. Verified by walking the artifact. It would become reachable the moment guard
learns to parse for `open_pr` or `run_tests`.

## 10. Consequences

**Good.** One shape for six categories of thing that happens. The audit skill can read
baron's own stream today. Third-party sinks need no baron change. The default is silent, so
nothing starts writing files an operator did not ask for.

**Costs and accepted risks.**

- The Protocol is genuinely hard to extend. That is the intended trade, and §3 explains the
  escape route (duck-typed extensions).
- `bind()` is an asymmetry: a documented optional method that one built-in implements. It
  earns its keep by keeping the Protocol at three, but it is a wart.
- No correlation IDs across events in v1. Sessions do not yet carry a trace to inherit.
- No pruning. Long-lived repos will accumulate JSONL until an operator runs `find`.
- The manifest `events:` node exists and does nothing. Declared as such here and in the
  code comment, so it cannot be mistaken for a working feature.
- Guard emits one event per tool call through a `git rev-parse` that is cached per process —
  but the *first* emission in each hook process pays it. Measured cost is not established;
  the default sink is `null`, which never touches disk, so the ordinary install pays nothing.
