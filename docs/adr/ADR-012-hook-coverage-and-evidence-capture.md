---
created: 2026-08-09
accepted: 2026-08-09
type: decision
status: accepted
decided_by: Vikram
adr: 012
project: barony
related:
  - "[[docs/adr/ADR-004-baron-guard-enforcement]]"
  - "[[docs/adr/ADR-007-session-boundary]]"
  - "[[docs/adr/ADR-003-baron-cli]]"
---

# ADR-012: Claude Code hook coverage — one enforcing hook, four observing ones

| Field | Value |
|---|---|
| **Status** | Accepted (2026-08-09) |
| **Date** | 2026-08-09 |
| **Authors** | Vikram + Claude |
| **Extends** | ADR-004 (`baron guard`), ADR-007 (session boundary) |
| **Evidence base** | Claude Code 2.1.226's own hook-event enum, read out of the installed binary |
| **Decision owner** | Vikram |

## 1. Context

ADR-004 shipped `baron guard` against exactly one Claude Code hook event:
`PreToolUse`. That was the right first cut — it is the only event where blocking
is meaningful — but it left `guard.process()` shaped like a function that can
only ever see one kind of payload. It reads `tool_name` and `tool_input` and
nothing else; a `SessionStart` payload fed to it returns 0 not because guard
decided anything but because `"SessionStart"` is not `"Bash"`. That is an
accident that looks like a policy.

It also left Barony with **no event stream at all**. Guard decisions — allows and
denies alike — evaporate; the only durable record is `.baron/guard-override.log`,
which by construction records the rare deliberate crossing and nothing else. The
project's own multi-agent audit measured operational fidelity at 0.53 by
reconstructing sessions from OTel exports; the framework that produced that
number cannot currently produce the data for it.

### 1.1 What the hook surface actually is

The task that prompted this work listed nine hook events; a prior survey
corrected that to fourteen. Both were read off documentation. Reading the
installed binary's own event enum (Claude Code 2.1.226, 2026-08-09) gives
**thirty-one**:

```
PreToolUse, PostToolUse, PostToolUseFailure, PostToolBatch, Notification,
UserPromptSubmit, UserPromptExpansion, SessionStart, SessionEnd, Stop,
StopFailure, SubagentStart, SubagentStop, PreCompact, PostCompact,
PermissionRequest, PermissionDenied, Setup, TeammateIdle, TaskCreated,
TaskCompleted, Elicitation, ElicitationResult, ConfigChange, WorktreeCreate,
WorktreeRemove, InstructionsLoaded, CwdChanged, FileChanged, DirectoryAdded,
MessageDisplay
```

Every payload carries `session_id`, `transcript_path`, `cwd`, `permission_mode`,
`agent_id`, `agent_type`. `PostToolUse` adds `tool_response` and `duration_ms`;
`PostToolUseFailure` adds `error` and `is_interrupt`; `SessionEnd` adds `reason`;
`SessionStart` adds `source` and `model`. Recorded here because the number moved
twice in one week: **the surface grows, so the design must treat an unknown event
name as normal, not exceptional.**

## 2. Decision — dispatch on `hook_event_name`, default to inert

`guard.process()` reads `payload["hook_event_name"]` and routes:

| Value | Path | Can exit 2? |
|---|---|---|
| absent, or `PreToolUse` | ADR-004 enforcement, **unchanged** | **yes** |
| `SessionStart`, `SessionEnd`, `Stop`, `PostToolUse`, `PostToolUseFailure` | evidence handler, then exit 0 | no |
| anything else — known-but-unhandled or never heard of | exit 0 immediately | no |

**Absent means `PreToolUse`.** Guard shipped before it read the field; payloads
that predate this change, and hand-rolled callers, must keep being enforced
rather than silently skipped.

The default arm is the load-bearing one. `KNOWN_HOOK_EVENTS` exists in the source
so a reader can see what was considered, but it is **behaviourally inert**: a name
in it without a handler is treated exactly like a name invented tomorrow. Barony
will be run against Claude Code versions that postdate this ADR, and an event
baron has never heard of must be a no-op, not a fault.

Guard also now consumes `session_id`: `trace_id = sha256(session_id)[:32]`, a
deterministic 32-hex OTel-shaped id derived with no producer state. Every event
of one session — including guard denials — lands in one trace, which is what
makes "this persona was denied `push_main` eleven minutes into session X"
answerable at all. No `session_id`, no trace id: an unattributed row beats a
pile of unrelated rows sharing a fabricated trace.

## 3. Decision — enforcement fails CLOSED, evidence fails OPEN

This asymmetry is the substance of this ADR. It looks like an implementation
detail and is not.

- **Enforcement (`PreToolUse`) fails CLOSED.** Unchanged from ADR-004 §2.3:
  malformed stdin, empty stdin, an unreadable persona file, an internal bug — all
  deny with actionable stderr. A broken guard must not silently become no guard.
  Empty and malformed stdin were previously *observed* to both exit 2 (they share
  the `JSONDecodeError` path) but nothing named it; both are now pinned by test.
- **Evidence (everything else) fails OPEN, and silently.** A handler that raises
  is swallowed. A missing `baron.events` module is a no-op. An unwritable sink is
  a no-op.

The reason is concrete. Extending fail-closed to evidence hooks would mean a full
disk, a read-only `.baron/`, or a sink misconfiguration blocks `SessionStart` —
**and a blocked `SessionStart` cannot be un-blocked from inside the session.** The
agent is dead before it can be told why. Telemetry is not worth that trade; the
governance property Barony sells is that the guard holds, not that the log is
complete.

Silence rather than a stderr warning, likewise for a concrete reason: guard's
stderr is fed **to the model** on exit 2. Chattering about event-sink health there
degrades the denial message the model is supposed to act on, and trains readers to
skim guard output. `BARON_EVENTS_DEBUG=1` opts in to the diagnostic.

**Corollary, and the invariant everything else is tested against: no hook handler
other than `PreToolUse` may return exit code 2.** `Stop` and `SubagentStop`
blocking is a real Claude Code capability, and it is precisely the trap described
above. `test_only_pretooluse_can_block` iterates all thirty non-`PreToolUse`
events with a payload containing a force-push to main, a write to `/etc/passwd`
and a `..` path escape simultaneously, and asserts exit 0 for every one. Session
preconditions belong in `baron doctor`, not in a session-start hook.

### 3.1 What the evidence handlers deliberately do not do

They do not wrap `baron session start` / `baron session end`. ADR-007 ruled that
Barony does not own the execution loop; a hook that mutates the collab repo on
every session open is a side effect nobody asked for. Wrappers get built on
demand. This is observation.

They do not record `tool_response` content — only its presence. Tool responses
carry file bodies and command output; an evidence stream that quietly accumulates
them is an exfiltration surface, not telemetry.

## 4. Decision — the producer contract

> **SUPERSEDED IN PART BY ADR-013 §2, at the ops-plane merge (2026-08-09).** The
> signature below was *provisional*: it was written while `baron.events` was an
> unlanded parallel workstream, and this section always said the row format
> belongs to that module. The plane shipped with an `Event` value object and
> `emit(event, cwd=None)` instead. **ADR-013's shape is authoritative**; guard's
> `emit_event()` is now a thin adapter onto it. The three decisions this section
> actually owns — open `kind`s, a frozen `baron.` namespace, emit-on-allow — all
> stand. Two specifics were corrected and are marked inline below.

`baron.events` (the sink protocol, `BARON_EVENTS_SINK`, the on-disk row format) is
a **separate workstream**. Guard is a producer only and reaches it through exactly
one late-bound call, so a baron build without the event plane degrades to a
no-op rather than an `ImportError` at hook time:

```python
# PROVISIONAL, as specified here. NOT what shipped — see the note above.
baron.events.emit(kind: str,
                  attributes: dict[str, object],
                  *, trace_id: str | None = None) -> None

# ACTUAL, per ADR-013 §2. guard.emit_event() adapts onto this.
baron.events.emit(event: baron.events.Event, cwd: pathlib.Path | None = None) -> None
```

**Event `kind` is an open dotted string, not a closed enum.** The capability
vocabulary is frozen because it is an *enforcement* contract, where ambiguity
means mis-enforcement. The event stream is *observation*, where an unrecognised
kind costs nothing and a closed enum would make every plugin event a bug report.
`guard.EVENT_KINDS` is a documented registry pinned by test, not a runtime gate,
and there is no runtime warning for unregistered kinds — it would fire constantly
and teach people to ignore guard output.

`guard.EVENT_KINDS` is now required by test to **equal** `baron.events.KNOWN_KINDS`
— one registry, not two. That collapses the provisional `guard.allow` / `guard.deny`
kinds into ADR-013's single `guard.decision` carrying `baron.outcome`; the
information is identical and the consumer joins on one span name.

What **is** frozen is the **`baron.` attribute-key namespace**, because that is
much of what `skills/multi-agent-audit/scripts/ingest_otel.py` parses. **CORRECTION
(merge, 2026-08-09):** the original text said *every* key guard writes is
`baron.`-prefixed, and a test asserted it. That was wrong in the opposite
direction — the ingester joins on the **bare** keys `agent.name`, `tool.name` and
`session.id` (its `AGENT_KEYS` / `TOOL_NAME_KEYS` / `SESSION_ATTR_KEYS`), which
ADR-013 makes fixed slots on every row. Prefixing them would have broken the join
the stream exists to serve. The frozen set is therefore the `baron.` namespace
**plus** `events.version` and ADR-013's `FIXED_ATTR_KEYS`. Keys guard
writes: `baron.events_version`, `baron.hook_event`, `baron.session_id`,
`baron.cwd`, `baron.agent_id`, `baron.agent_type`, `baron.permission_mode`,
`baron.tool_name`, `baron.target`, `baron.persona`, `baron.verbs`, `baron.reason`,
`baron.has_tool_response`, `baron.duration_ms`, `baron.is_interrupt`,
`baron.error`, `baron.session_source`, `baron.model`, `baron.end_reason`.
`baron.events_version` (currently `1`) is stamped on every row and bumped when a
key changes meaning or disappears; adding a key is not a bump.

Guard emits on **allows as well as denies**. A stream that records only denials
cannot answer "how often did the boundary hold?" — which is the question the 0.53
fidelity measurement needed and could not answer.

### 4.1 Honesty about what is tested

*Original text, kept for the record:* "The event plane had not landed when this
shipped. Everything above is verified against `cli/tests/fake_events.py`, a
contract double implementing the signature. That proves the **producer** side —
kinds, attributes, trace correlation, fail-open — and proves **nothing** about
interoperability with the real plane. `test_real_event_plane_matches_the_producer_contract`
skips today and starts failing the moment `baron.events` exists with an
incompatible `emit`."

**As of the ops-plane merge that bound is narrower, and the canary did its job.**
The plane landed, the canary stopped skipping, and it caught exactly the
divergence it was built for. The double was rewritten onto the real signature and
now re-exports the real `Event`, `KNOWN_KINDS` and `FIXED_ATTR_KEYS`, so it cannot
silently drift again.

What is still NOT proven by the green suite: the producer tests use the double's
own writer, not `baron.sinks.disk`. Real-sink behaviour is covered separately by
`test_sinks.py` and by the ADR-013 section of `test_guard.py`, which drive the
actual disk sink. No test yet drives a real Claude Code process against a
scaffolded repo end to end — `baron doctor` (ADR-017) is the nearest thing, and it
probes enforcement, not evidence.

## 5. Decision — generated wiring, and why it is safe to land

`baron init`'s Claude kit now emits five hook blocks instead of one, all invoking
the same `baron guard --persona-file …`: `PreToolUse` (timeout 15, enforcement),
`PostToolUse` and `PostToolUseFailure` (matcher unchanged, timeout 5), and
`SessionStart` / `SessionEnd` (**no matcher** — those events carry no tool name, so
a matcher would silently never fire; timeout 5, because an evidence hook that
hangs delays a session for no benefit).

`Stop` is handled in code but **not wired by default**: it fires every turn, and
its only distinctive power is blocking, which §3 refuses.

This is the riskiest change in the set, because the generated `.claude/settings.json`
already exists byte-for-byte in every repo `baron init` has ever produced. Two
things make it landable:

1. **The `PreToolUse` block is byte-frozen** — matcher, command, `timeout: 15`,
   key order — and pinned by `test_scaffold.py::pretooluse_block`, so the sibling
   blocks cannot perturb it.
2. **Default-off means default-unchanged.** The event plane's default sink is null,
   so a freshly scaffolded repo with these hooks wired behaves *identically* to one
   without them. Turning telemetry on later becomes one environment variable rather
   than a re-hydration of every persona kit.

Both templated copies of `adapters/claude/HYDRATE.md` gain step **3d** and are
re-synced (`cli/scripts/sync_templates.py`); `test_template_sync.py` is the guard
on that pair.

## 6. Consequences

- Guard has a second job. `baron guard` is no longer "the PreToolUse hook" but
  "the hook", dispatching internally. One binary, one config line per event, no
  second command to keep in sync.
- Existing downstream repos are unaffected until re-hydrated: their single
  `PreToolUse` block still works, because absent-`hook_event_name` and
  `PreToolUse` take the same path.
- The enforcement honesty label is **unchanged**. Evidence hooks enforce nothing;
  `enforced-with-baron (instructed otherwise)` still describes exactly five verbs
  and `tests/bi_runtime_accept.py` still polices that string.
- Five hook invocations per tool call instead of two (PreToolUse + PostToolUse)
  is measurable process-spawn overhead. Not measured here; if it bites, the fix
  is a persistent sink, not fewer events.

## 7. Rejected

- **Let `SessionStart` block on a failed precondition** (no persona file, baron
  not installed, dirty worktree). Tempting and wrong: unrecoverable from inside
  the session. That is `baron doctor`'s job.
- **A closed enum of event kinds.** Right for enforcement contracts, wrong for
  observation. See §4.
- **Vendoring a minimal `baron/events.py` here** so the tests could run against
  something real. It would have collided with the events workstream on merge and
  produced a fake integration claim. A contract double plus a merge canary is the
  honest version.
- **Fail-closed evidence, or a stderr warning on emission failure.** §3.
- **Wiring `UserPromptSubmit`.** It carries the user's raw prompt, and an evidence
  stream that accumulates prompts is a different product with different consent
  requirements. If it is ever wanted, it needs its own decision.
- **Rendering `session.render_brief` from the `SessionStart` hook.** Genuinely
  attractive — Claude Code injects a `SessionStart` hook's stdout into the session
  as context, so the existing brief (open handoffs, conventions pointer, backlog
  location) could arrive automatically. Deferred, for two reasons. `guard.process()`
  returns `(exit_code, stderr)` and has no stdout channel; adding one widens the
  hook contract that ADR-004 §2.1 deliberately kept to exit codes. And rendering the
  brief means reading the collab repo — possibly a `git pull` — inside a hook that is
  otherwise guaranteed cheap and side-effect-free, on the one event where a hang is
  most expensive. Worth doing; worth doing as its own change, with its own timeout
  story, not smuggled in behind "evidence capture".
