# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

> **Reviewers start at [`docs/DECISIONS-FOR-REVIEW.md`](docs/DECISIONS-FOR-REVIEW.md).** This
> release consolidates five parallel hardening workstreams. **D1's semantics half is now
> DECIDED and fixed** — `baron.enforcement` is a per-call observation
> ([ADR-018](docs/adr/ADR-018-adjudicated-enforcement-on-the-event.md)); what remains of D1
> is merge work (retire `telemetry.py`, re-merge `ingest_otel.py`'s
> `partition_guard_records`). One decision is still BLOCKING: whether Cognee is a projection
> or an authoritative source (ADR-015 §4.1).
>
> **ADR-014 is deliberately absent from `docs/adr/`.** A sixth workstream (`harden/otel`)
> built a second, incompatible observation plane; it is NOT merged and its branch is intact
> at `harden/otel`. The number is reserved for it. See DECISIONS-FOR-REVIEW §D.

### Added — `baron guard` taps the wider Claude Code hook surface (ADR-012)

`baron guard` was wired to exactly one hook event (`PreToolUse`, ADR-004), and
`guard.process()` was shaped to match: it read `tool_name`/`tool_input` and nothing else,
so a `SessionStart` payload returned 0 not because guard decided anything but because
`"SessionStart"` is not `"Bash"`. Barony also had **no event stream at all** — guard
decisions evaporated, and the framework that measured its own operational fidelity at 0.53
could not produce the data that measurement needs.

- **`hook_event_name` dispatch** in `guard.process()`. Absent or `PreToolUse` → the ADR-004
  enforcement path, byte-unchanged (absent means PreToolUse for back-compat: guard shipped
  before it read the field). Five events get evidence handlers. **Everything else exits 0
  immediately.** The default arm is load-bearing, not defensive padding — see below.
- **The hook surface is bigger than the docs say.** The list this work started from had 9
  events; a survey corrected it to 14. Reading Claude Code 2.1.226's own event enum out of
  the installed binary gives **31**. Recorded in `guard.KNOWN_HOOK_EVENTS` — which is
  deliberately **inert**: a name in it without a handler behaves exactly like a name
  invented tomorrow. The surface grows, so unknown must be normal, not exceptional.
- **Evidence handlers** — `SessionStart` → `session.start`, `SessionEnd`/`Stop` →
  `session.end`, `PostToolUse` → `tool.post`, `PostToolUseFailure` → `tool.failure`. They
  emit and exit 0, always. They record the *presence* of `tool_response`, never its content:
  responses carry file bodies and stdout, and a stream that accumulates them is an
  exfiltration surface, not telemetry. They do **not** wrap `baron session start/end` —
  ADR-007 already ruled Barony does not own the execution loop.
- **Session correlation.** `trace_id = sha256(session_id)[:32]` — deterministic, no producer
  state — so guard denials land in the same trace as the session events. Nothing consumed
  `session_id` before.
- **Enforcement fails CLOSED; evidence fails OPEN.** The asymmetry is the point. Extending
  fail-closed to evidence would mean a full disk or an unwritable `.baron/` blocks
  `SessionStart` — **and a blocked `SessionStart` cannot be un-blocked from inside the
  session.** Silent rather than warning, because guard's stderr is fed to the *model* on
  exit 2 and noise there degrades the denial message; `BARON_EVENTS_DEBUG=1` opts in.
- **Hard invariant: only `PreToolUse` may exit 2.** `Stop`/`SubagentStop` blocking is a real
  Claude Code capability and is exactly the trap above. `test_only_pretooluse_can_block`
  iterates all 30 non-`PreToolUse` events with one payload carrying a force-push to main, a
  write to `/etc/passwd` and a `..` escape simultaneously, asserting exit 0 for every one.
- **Empty and malformed stdin are both pinned at exit 2.** They already shared the
  `JSONDecodeError` path, but nothing named it; ADR-004 §2.3 makes it policy, so it now has
  a test rather than a coincidence.
- **Generated wiring** (`baron init` Claude kit + step **3d** in both copies of
  `adapters/claude/HYDRATE.md`): four evidence hook blocks alongside the enforcement one,
  all invoking the same command. Session events get **no matcher** — they carry no tool
  name, so a matcher would silently never fire. The `PreToolUse` block is **byte-frozen**
  (matcher, command, `timeout: 15`, key order) and pinned by test, because it already exists
  verbatim in every repo `baron init` has ever generated. `Stop` is handled in code but not
  wired: it fires every turn and its only distinctive power is blocking.
- **Default-off means default-unchanged.** The event plane's default sink is null, so a
  freshly scaffolded repo with these hooks wired behaves identically to one without them.
  That safety property is what makes the generated-settings change landable.

**Honesty boundary.** The event plane (ADR-013, below) landed in this same release, so
guard's producer side is no longer verified against a stand-in alone. At merge the two
workstreams disagreed on the wire shape — ADR-012 §4 had provisionally specified
`emit(kind, attributes, *, trace_id=None)` and `guard.*` kinds while the plane was unlanded,
and ADR-013 shipped an `Event` value object with a single `guard.decision` kind carrying
`baron.outcome`. **ADR-013's shape won**, because ADR-012 §4 had itself delegated the row
format to `baron.events`; guard's `emit_event()` is now an adapter onto it and
`test_real_event_plane_matches_the_producer_contract` is a live assertion rather than a
skipped canary. Two ADR-012 test claims were corrected in the process: emitted kinds are now
required to equal `baron.events.KNOWN_KINDS`, and "every attribute key is `baron.`-prefixed"
was wrong in the other direction — `ingest_otel.py` joins on the BARE keys `agent.name` /
`tool.name` / `session.id`, so those are fixed slots and prefixing them would break the join.
Enforcement labels are unchanged: evidence hooks enforce nothing, and
`enforced-with-baron (instructed otherwise)` still describes exactly five verbs.

### Added — the observation plane: one event shape, pluggable sinks (ADR-013)

Baron had no event stream. It had six unrelated, per-command emissions: guard's override log
(overrides only — ordinary verdicts were printed and discarded), `ledger.add_entry()`
returning an int, `SessionBrief.to_dict()` printed under `--json` and dropped, and so on.
Every consumer the roadmap names — fleet-health (AGENT-TASKS 3.2), the knowledge substrate
(3.4), "Logfire or Phoenix wired" — needs one shape and one configurable destination first.

- **`baron.events`** — `EVENTS_VERSION = 1`, a frozen `Event(kind, actor, subject, outcome,
  attributes, ts, trace_id, span_id)`, and `to_row()` producing one flat JSON object per
  line. Timestamps come from `clock.now()`, never `datetime.now()`, so the `BARON_NOW`
  backfill hatch reaches events; a test pins it by injecting a clock.
- **`baron.sinks`** — a `@runtime_checkable` `Sink` Protocol (`name`, `emit`, `close`),
  `get_sink()` structurally identical to `get_forge()`, plus `disk` (append-only JSONL,
  date-rotated, stdlib `json` only per ADR-003) and `null` (**the default** — baron writes
  nothing unless `BARON_EVENTS_SINK` says so).
- **`baron.sinks` entry-point group** in `cli/pyproject.toml`, mirroring `baron.forges`.
  Both built-ins are declared there and a test loads them through real
  `importlib.metadata` discovery, not a fake.
- **Guard's verdict path emits**, and only guard's. One event per allow / deny / override /
  fail-closed error. The tab-separated **tracked** `.baron/guard-override.log` is
  byte-for-byte unchanged — it is cited in `_remedy()`'s user-facing text; events are
  additive. All 24 pre-existing guard tests pass unmodified.
- **`events:` manifest block** added to `MANIFEST_SPEC` and `manifest.schema.md` (v1.3) so a
  manifest can carry the config without tripping `baron validate`'s unknown-field warning.
  **Reserved, not read**: `BARON_EVENTS_SINK` is the only live selector. Labelled as such in
  the schema comment, the canon, and ADR-013 §7 rather than quietly implied.

Three decisions worth reading ADR-013 for:

- **Enforcement fails CLOSED; evidence fails OPEN.** `events.emit()` swallows every
  exception. Without that, a full disk inside a PreToolUse hook would meet guard's
  fail-closed policy and deny every tool call — a session bricked by a logging destination.
  `BARON_EVENTS_DEBUG=1` surfaces swallowed errors; it is off by default because guard's
  stderr is fed to the model on exit 2 and noise there degrades the denial message.
  `test_sink_failure_does_not_change_guard_exit_code` pins both exit codes.
- **The event stream is gitignored; the override log stays tracked.** The `.gitignore` the
  disk sink writes contains `*` and lives *inside* `.baron/events/`, deliberately not at
  `.baron/` level — an ignore there would silently un-track `guard-override.log` in every
  downstream repo. A test asserts it stays tracked.
- **No OpenTelemetry dependency, ever.** ADR-003 holds. The five top-level row keys are each
  the first entry of `ingest_otel.py`'s flat key lists, so the existing audit skill reads
  baron's stream with zero new code. A test re-derives those keys from the script and fails
  if either side drifts.

`baron.enforcement` on an event was originally DERIVED from the rules artifact's `detection`
field. **That was a defect and it is fixed below** — see *Changed — `baron.enforcement` is a
per-call observation*.

### Changed — `baron.enforcement` on an event is a per-call observation ([ADR-018](docs/adr/ADR-018-adjudicated-enforcement-on-the-event.md))

**BREAKING for consumers of the event stream. Landed now because the default sink is `null`
and nothing is emitting yet — this is the last cheap moment.**

The attribute derived its value from the rules artifact's `detection` field for whatever
verbs a `Decision` carried. That is a static property of a **verb** answering a **per-call**
question, and ADR-013 §9.1 measured it wrong in both directions against merged code:
`Write ../../../outside.md` emitted `enforced` (a structural refusal every persona is denied
identically — nothing adjudicated it), while `Write src/x.py` by a persona holding
`write_code` emitted `not-applicable` (a real, persona-dependent adjudication). The field
simultaneously over-counted structural refusals and missed genuine capability allows — an
enforcement counter that inflates itself by construction, in a project that publishes 0.53
rather than rounding up.

- **`Decision.adjudicated: bool = False`**, set EXPLICITLY at all eleven return sites in
  `evaluate_bash` / `evaluate_write`, plus `ALLOW_ADJUDICATED` alongside the existing
  persona-independent `ALLOW`. `enforced` now requires **both** halves: a capability rule
  matched **and** the outcome turned on the acting persona. Ported from ADR-014 §4.2 on the
  unmerged `harden/otel` branch, which diagnosed this independently; not redesigned.
- **`guard._enforcement(verbs)` is deleted.** A test asserts the symbol stays gone. The flag
  is deliberately not a function of the verb tuple, which is wrong in both directions: a
  `write_code` allow names no verb, and the `..`-escape deny names `write_path`.
- **`_Trace` carries the observation through `guard.process()`**, with `adjudicated`
  defaulting to `False` and raised only by copying a real `Decision`. Every path that returns
  without one — out-of-jurisdiction tool, malformed payload, fail-closed error, fail-closed
  override bypass — is `unevaluated` **by construction** rather than by someone remembering.
  A return site added tomorrow that forgets the flag under-claims, never over-claims.
- **The vocabulary is exactly `enforced` | `unevaluated` | `unknown`** (`ENFORCEMENT_VALUES`,
  pinned by test). `not-applicable` is gone, subsumed by `unevaluated`. **`instructed` is
  gone from the event path entirely** — it is a static posture property of a
  (persona, verb, runtime) triple and asserts a control a PreToolUse hook cannot measure.
  ADR-013 §9.1 had argued this criticism did not bite because the value was unreachable in
  practice; the facts were right and the conclusion was wrong. `instructed` is **unchanged**
  on the posture surface (`baron rules list`, `CapabilityRules.label`), where `open_pr` and
  `run_tests` still carry it.
- **A fail-closed deny is `unevaluated`, not `enforced`** — guard blocked *because it could
  not evaluate*. Otherwise a guard that crashed on every call would report perfect
  enforcement. `unknown` is kept for the one case it means something: an unreadable rules
  artifact, where guard cannot say what was even adjudicable.
- **CONSUMER CAVEAT, stated in `events.py`, ADR-018 §5 and a test:**
  `baron.capability.verb` **can be non-empty on an `unevaluated` row**. Any verb-level
  aggregation must filter on `baron.enforcement == "enforced"` **first**;
  `test_verb_aggregation_must_filter_on_enforcement_first` emits two real rows carrying
  `write_path` — one adjudicated, one structural — and asserts the naive count is 2 while the
  correct count is 1.

Thirteen new tests, two artifact-derived ones removed; suite 386 → 397. Both measured
defects flip under test. ADR-013 §4.1's
label paragraph is struck through in place and §9.1 is rewritten from "MEASURED DEFECT … do
not read as trustworthy" to the resolution, keeping the measurement that forced it.

### Changed — the observation plane is runtime-neutral, and a second producer proves it ([ADR-019](docs/adr/ADR-019-runtime-neutral-event-plane.md))

The plane *looked* neutral — `events.KNOWN_KINDS` names no runtime, Claude Code's 31 hook
names sit behind a dispatch table — but exactly one producer had ever written a row, and one
attribute carried Claude Code's vocabulary onto the shared wire. Nothing distinguished "this
plane is runtime-neutral" from "this plane has one producer and it is Claude Code". That is
the same asserted-not-measured claim ADR-018 had just removed from `baron.enforcement`, one
level up. `docs/BACKLOG.md` had named the gap: *"the pydantic-ai adapter enforces in-process
but emits nothing."*

- **BREAKING — `baron.hook_event` is renamed to `baron.trigger`, with no alias.** The key is
  now neutral; the **value stays the runtime's own seam name** (`PreToolUse`,
  `before_tool_execute`), because normalising the values would put an unverifiable
  translation between the reader and the name the runtime uses in its own docs. Only
  meaningful read together with `baron.runtime`. No consumer exists (default sink is still
  `null`), which is why a clean rename beat an alias — the same "last cheap moment" call
  ADR-018 made three commits earlier.
- **NEW `baron.runtime` on every guard-sourced row** — `claude-code`, `pydantic-ai`, or
  `unknown`; landed set pinned as `guard.KNOWN_RUNTIMES`. Without it a merged stream is
  unpartitionable and a consumer cannot tell *"pydantic-ai never denied anything"* from
  *"pydantic-ai never ran"*. **Defaults to `unknown`, not `claude-code`:** a producer that
  forgets is unattributed, never mis-attributed — ADR-018's under-claim rule applied to a
  second field.
- **`guard.observe_decision(...)` — the public producer seam.** It takes a `Decision`, has
  **no `enforcement=` argument**, and infers nothing from `outcome`/`verbs`/`subject`, so
  ADR-018's "read the label off `Decision.adjudicated` and nothing else" survives exposure as
  public API. Passing `None` yields `unevaluated` even while asserting a deny.
- **pydantic-ai is now a real second producer.** `BaronGuardCapability.before_tool_execute`
  emits `guard.decision` into the same plane. `check()` gained a sibling
  `decide() -> Decision | None` because `str | None` collapsed "allowed" and "no
  jurisdiction", and emission needs them apart. Read tools emit nothing, mirroring
  `Read`/`Grep` under PreToolUse; correlation uses pydantic-ai's `conversation_id` (then
  `run_id`) through the same `_trace_id` hash; a broken sink still cannot stop the veto.
- **The evidence, measured rather than asserted:** driven with the same persona and the same
  command, both producers append to the **same** `.baron/events/` file and the two rows
  differ in **exactly four** attributes — `baron.runtime`, `baron.trigger`, `tool.name`
  (runtimes name their own tools) and `session.id`. Verdict, verb, enforcement label, actor,
  subject and reason are byte-identical, and the difference set is asserted exactly. The
  headline test drives a **real `Agent.run_sync`** and reads what the **real `DiskSink`**
  wrote — ADR-001's standard for an adapter claim.
- **HONEST GAP — code-puppy is deliberately absent from `KNOWN_RUNTIMES`.** It has no
  PreToolUse equivalent (recorded in `docs/BACKLOG.md` since ADR-012) and this change does
  not invent one: emitting from a post-hoc log would imply an adjudication that never
  happened. The proof is **two producers, not three**, and the third is blocked on the
  runtime, not on baron. Pinned by a test so the tuple grows with a landed adapter and never
  with an intention.

Twenty new tests (`cli/tests/test_runtime_neutrality.py`); suite 397 → 417. ADR-012 §4 and
ADR-013 §2 carry supersession notes.

### Added — `baron export`: the governed corpus as citable records ([ADR-015](docs/adr/ADR-015-baron-export.md))

`baron export [--kind …] [--json]` walks the four corpora a collab repo already keeps —
`docs/adr/*.md`, `decisions/index.md`, `findings/index.md`, `_handoff/**.md` — and emits one
flat record per artifact: `{id, kind, title, path, commit_sha, status, body, links}` plus an
open `meta` bag. No new dependency (still typer + pyyaml), no network, no plugin seam.

- **The citation gate is the point.** `AGENT-TASKS.md` 3.4 requires every retrieval result to
  carry `path + commit SHA`. A record is emitted **only** if its source file is tracked and
  unmodified, so `git show <commit_sha>:<path>` reproduces the parsed bytes exactly. Sources
  failing that test are **skipped and named** in `skipped[]` with a reason and a lost-record
  count — never emitted with a SHA that resolves but returns different text, which is the
  failure mode that would poison a downstream index with confidently-wrong citations.
  `--allow-dirty` relaxes the gate for **modified tracked** sources only, stamping
  `meta.dirty` so the caveat travels with the data rather than with the invocation; untracked
  sources are skipped regardless, keeping `commit_sha` non-empty in every record ever emitted.
  The gate reads `git status --porcelain -z`: plain `--porcelain` C-quotes non-ASCII and
  spaced paths, which made the gate fail *open* on those files (fixed, regression-tested with
  a literal non-ASCII filename — see ADR-015 §3.2).
- **Both real ledger entry-forms parse.** Full `### F40 — title (date, author)` blocks *and*
  bare `| F40 | title |` index rows, with the heading form winning for the same ID — the
  shape badminton-analyzer's migrated F1–F39 table actually has. Entries with no trailing
  `(date, author)` (its whole D48+ run) parse too.
- **`status` is null for findings and decisions**, on purpose: the canon gives ledgers no
  lifecycle field, supersession is prose, and a regex that produced `"superseded"` would be
  the enforced-vs-instructed overclaim ADR-002 bans.
- **Byte-stable across runs** — sorted output, ISO-coerced YAML dates, and `age_days`
  deliberately dropped (it is a function of today). Locked by a test; without it nothing
  downstream can sync incrementally.
- Measured on real repos: 284 records (62 decisions / 62 findings / 160 handoffs) out of
  `baddie-analyzer-collab`, all 284 citations verified by **byte-equality** (`git show
  <sha>:<path>` vs the file on disk, 0 mismatches) rather than by mere resolvability.

### Not shipped, deliberately — the knowledge-substrate adapter (`AGENT-TASKS.md` 3.4)

No `baron.knowledge` entry-point group, no sink protocol, **no semantic-memory adapter, and no
vendor named anywhere under `cli/src/baron/`** (asserted by test). 3.4 is gated on **3.3**, the
governed-memory evaluation harness, which does not exist — building the adapter first inverts
the project's own measure-first rule on the exact task where that rule is written down — and an
entry-point group with no consumer is public API that cannot be retracted. Two further tests
pin the boundary: runtime dependencies are still exactly `["typer", "pyyaml"]`, and
`baron.forges` is still the only entry-point group.

**Open owner decision** ([ADR-015](docs/adr/ADR-015-baron-export.md) §4.1, carried from the
2026-08-04 reconciliation): is a semantic-memory backend a *rebuildable projection* over
git+markdown, or a candidate *authoritative* source? The latter contradicts the product
vision's invariant #1 ("the repo is the only source of truth; `cat` always works"). The export
is the input either answer consumes, so it is not wasted under either branch. **Nothing here
claims a working third-party integration — none was built and none was run** (ADR-015 §6).
### Added — externalizable capability rules, step 1: the rule-list representation and `baron rules` (ADR-016)

Teams want project-specific guard rules without forking baron. `docs/BACKLOG.md`
(2026-07-28) called this "mostly a loader + merge + a precedence story, no new detection
code". That was wrong about the blocker. The rule table has been externalized *data* since
v1.6.0, but the parsed form — `rules.CapabilityRules` — was a flat record with one field
per built-in rule (`push_force_flags`, `push_force_verb`, `gh_pr_merge_subcommand`,
`universal_write_components`, …). **A structure with a fixed field per rule cannot hold an
additional rule.** The data was external; the shape was not extensible.

- **`CapabilityRules` is now a rule LIST** — `command_rules: tuple[CommandRule, ...]` and
  `path_rules: tuple[PathRule, ...]`, each rule carrying a stable `id`
  (`git.push.force_flags`, `gh.pr_merge`, `file_ops.spec_dir`, …), a `matcher` from a
  **closed** set, a `verb`, and a `source` provenance tag. Eight built-in rules; the ids are
  the public handle `baron rules explain` prints and `baron rules diff` joins on.
- **The matcher set is closed on purpose, and the document names its matcher.**
  `flag_present`, `refspec_prefix`, `refspec_default_branch`,
  `current_branch_is_default`, `subcommand_present` (command rules); `universal_write`,
  `spec_dir` (path rules). Each command rule in `capability-rules.v1.yaml` now states its
  `matcher`, and the parser refuses one outside the closed set *and* one that is not the
  matcher guard implements for that rule id — a document claiming `force_flags` is matched
  by `subcommand_present` describes a check nobody performs. The field is optional but
  authoritative: absent it defaults to guard's matcher, so a v1 document written before this
  change still parses identically. Rule **ids** come from the document too (a rule's id is
  its position, `commands.git.push.rules.<key>` → `git.push.<key>`). This makes the
  BACKLOG's cheap/expensive split mechanical instead of aspirational: a new modality (file
  size, time window, rate limit, anything semantic) is new detection code in `guard.py`, not
  a config line. *Honest limit:* path-rule matchers are **not** document-supplied —
  `file_ops` is a flat block whose keys name the semantics directly, so the closed-set check
  over `PATH_MATCHERS` is a developer-edit guard and is labelled as one.
- **Unrecognised content is refused, never ignored.** The parser enumerates the keys and
  rules the document actually carries and refuses any it does not implement — at the top
  level, in `verbs.<verb>`, throughout `commands.*`, and in `file_ops` — as well as a
  document that omits a built-in rule or a required rule parameter. Silently dropping an
  unrecognised rule is the worst failure mode an enforcement artifact has: the document says
  a thing is blocked and nothing blocks it.
- **Behaviour preservation is the acceptance criterion, not a claim about it.**
  `cli/src/baron/guard.py` and `cli/src/baron/runtimes/pydantic_ai.py` are **byte-identical**
  across this change. All fifteen pre-existing accessors survive as derived read-only
  properties with the same name and type, pinned by
  `test_legacy_accessors_are_behaviour_preserving` against **hand-transcribed pre-refactor
  literals** — deliberately literals, because re-deriving them from the artifact would test
  the loader against itself and prove nothing.
- **`baron rules list|validate|diff|explain`** — the read-only audit surface. Until now the
  only way to ask baron what it enforces was to read the YAML by hand, which the project's
  own measured 0.53 operational fidelity says is not good enough. All four take `--json`.
- **`list` reports enforcement in three states, but only one of them is `enforced`.**
  `guard` (guard mechanically checks it) / `adapter-dependent` (guard does NOT parse for it;
  a runtime with a tool allow-list *could* enforce it by omitting the tool, but the one
  adapter **measured** does not) / `instructed` (nothing checks it — `open_pr`, `run_tests`,
  by design).
  `label` says `enforced` **only** for `guard`; `adapter-dependent` labels `instructed`. The
  qualifier is carried in the `--json` payload (`label_caveat` at the top level, `caveat`
  per affected verb) as well as the table footer — machine consumers are the ones most
  likely to trust `label` unread. The label is gated by a **measurement**:
  `test_denying_read_code_does_not_omit_read_tools` hydrates a persona denying `read_code`
  through `pydantic_ai.plan()` and asserts the read tools are still present, so the claim
  cannot drift ahead of the adapters.
- **`explain` is a dry run of the real decision.** It calls `guard.evaluate_bash` /
  `guard.evaluate_write`, and `test_rules_explain_matches_guard_evaluate_bash_exactly` pins
  its JSON verdict to the evaluator's `Decision` for the same input, so a second
  implementation cannot creep in. Exit 0 would-pass / 1 would-be-DENIED / 2 could not
  evaluate. Honest limit, stated in `--help`: it lists the rules that *can* imply each verb,
  not the single rule instance that matched — re-deriving that in the CLI would mean a
  second parser that could drift from the first.
- **New fail-closed parse refusals, all reachable from document input**: an unknown
  `vocabulary` (previously the field was not read at all); a rule the parser does not
  implement; an unrecognised key; an unknown matcher; a matcher other than the one guard
  implements for that rule; a missing built-in rule; a missing required rule parameter.
  These join the existing unknown-`rules_version` refusal; guard turns every one into an
  exit-2 DENY. (The duplicate-rule-id check is a `CapabilityRules` invariant reachable only
  via `dataclasses.replace()`, not from a document — it guards the deferred loader and
  developer edits, and is counted as such rather than as document validation.)
- **`rules diff` delegates to `rules.diff_rules()`**, a pure function, so its
  `rules_added` / `rules_removed` branches can be unit-tested against constructed values.
  No document can currently produce either (an extra rule is refused, a missing one is too);
  they exist for the deferred loader.

#### Round-3 corrections

Three defects found in review, all in the same family — a claim wider than the thing that
backed it. Recorded rather than quietly fixed, per ADR-002/ADR-008.

- **Verb-entry VALUES are now validated, not just keys.** Every refusal shipped in rounds
  1–2 targeted a *key* or a *rule slot*; no *value* was checked. Measured, all at exit 0 on
  the shipped `validate`: `detection: banana` passed; `class: banana` passed and silently
  re-routed `enforcement()`; and `read_code` with `detection: command` and no rule behind it
  passed **and made `baron rules list` print `LABEL=enforced` for a verb nothing checks** —
  a false enforcement claim from a one-word document edit, which is the exact failure this
  work exists to prevent. `class` and `detection` are now closed sets and both are
  **required** (defaulting an enforcement decision is a guess). New
  `rules._check_detection_consistency` cross-checks `detection` against the rules that
  actually bind each verb, **symmetrically**: over-claiming (`command`, no rule) and
  under-declaring (a rule binds it, entry says `none`) are both refused. That check
  previously existed only as an assertion in `test_rules.py` against the packaged artifact,
  where no document input could ever reach it.
- **`rules diff` now joins on verb id as well as rule id** (`verbs_changed`). It was blind to
  verb entries: a candidate that rewrote `detection`, `class` or `notes` on an existing verb
  printed `identical to the packaged artifact` and exited 0 — reproduced three ways. Those
  are the fields that decide whether baron prints `enforced`, so the edit most worth
  reviewing was the one the review surface could not see. The renderer names the resulting
  `enforcement/label` transition inline and prints values in full (a first draft truncated to
  a fixed prefix, making two different `notes` blocks look identical — a diff that hides the
  diff). Unlike `rules_added`/`rules_removed` this branch **is** document-reachable and is
  covered by document fixtures.
- **`validate`'s "no unrecognised content" check no longer overstates itself.** It was
  hardcoded `True` behind text claiming "every key and rule in the document is one this
  baron implements", and printed `ok` over a document containing `detection: banana`. Its
  text now names exactly what is covered, and a new **computed** check,
  `detection matches implementation`, re-derives the enforced/backed relationship from the
  parsed table instead of asserting it.
- **`LABEL_CAVEAT` is scoped to what was measured.** It stated "no adapter baron ships does"
  omit read tools as fact for all four adapters, on the strength of one instrumented test.
  Only **pydantic-ai** was measured; the `claude` and `code-puppy` kits are prompt/config
  templates whose tool exposure belongs to the host runtime and is **unmeasured**. The label
  is unchanged (absent a measurement, `instructed` is the honest default) but the reason is
  now "unmeasured", not a claim about untested code. *(Superseded later in this same
  release by ADR-020 — the other three adapters were measured and the "unmeasured" scoping
  is retired. See the ADR-020 entry below.)*
- **The circular label test is replaced.** `test_only_guard_checked_verbs_are_labelled_enforced`
  derived its expectation from `detection` — the field under test — and ran only against
  `load_rules()`, so it restated the document back to itself and green-lit the
  `detection: command` hole above. Replaced by a **literal** `EXPECTED_CLAIMS` table for all
  ten verbs, a test asking whether a rule could actually fire, and the parser change that
  makes the bad state unrepresentable from document input.

> **Blocking owner decision (ADR-016 §8, D-1).** Narrowing `enforced` to guard-checked verbs
> changed what `baron rules list` prints for `read_code`/`read_collab` from `enforced` to
> `instructed` — a user-visible output change, and a claim about the product an implementer
> should not sign off alone. The box is unticked and recorded as blocking for merge.

### Not shipped, deliberately — the project-level rules loader

`baron rules validate --file` / `diff --file` will parse a candidate rules document, but
**validating a file does not activate it**. Every enforcer still loads the PACKAGED
artifact only — no `.baron/rules.yaml` discovery, no merge, no precedence — pinned by
`test_guard_reads_packaged_data_only`. ADR-016 §5 records the one-way doors that need
their own ADR first: add-only/deny-only (project rules may never grant), explicit supported
version ranges on *both* artifacts, refuse-don't-ignore on a malformed project file
(matching guard's fail-closed policy, deliberately unlike `.baron-waivers.yaml`'s
soft-fail), `load_rules()` cache safety once it is path-dependent, and the `.baron/`
(machine state) vs root-level `.baron-waivers.yaml` (human config) convention collision.
**Project-defined verbs are a separate, unmade decision** (ADR-016 §6.1): they would break
the frozen-vocabulary invariant asserted in two test files, and custom rules for *existing*
verbs — the 90% case — need no vocabulary change at all.

Docs: new `docs/adr/ADR-016-externalizable-capability-rules.md`; `cli/README.md` §`baron
rules`; `skills/barony/references/capability-rules.md` (+ the vendored template copy)
gained the inspection surface, the three-state labelling table and the
not-loaded-yet section; `docs/BACKLOG.md` § *User-extensible guard rules* records why "mostly
a loader" was wrong and what is still open. **CLI track: a minor bump** (new command
surface, no behaviour change) — left to the release commit.
### Added — `baron doctor`: the guard wiring self-test ([ADR-017](docs/adr/ADR-017-baron-doctor-wiring-selftest.md))

Closes the first and highest-value checkbox in the roadmap's `baron guard` hardening
list. The badminton-analyzer incident merged 15 PRs under a persona denied `merge_pr`,
and nothing had failed: `baron guard` had never been wired into `.claude/settings.json`,
so the denial degraded to persona text exactly as designed — and **silently**. An absent
guard and a guard that never had to fire produce identical evidence: nothing.

- **`baron doctor [--dir .] [--persona-file F] [--json]`** — nine read-only checks, each
  with a remedy line, **exit 1 on any FAIL**: the hook's executable resolves and runs;
  project `.claude/settings.json` wires a `baron guard` PreToolUse hook; its matcher
  covers every governed tool (`Bash`, `Edit`, `Write`, `NotebookEdit`); the named persona
  parses; `capability-rules.v1.yaml` loads at a supported `rules_version`; **a synthetic
  denial fed to the executable the hook actually names really returns exit 2**; malformed
  stdin also returns exit 2 (ADR-004 §2.3); `BARON_GUARD_OVERRIDE` is not sitting exported;
  and the override log is writable (INFO).
- **Checks 6 and 7 spawn the hook's own command** (`<exe> guard --persona-file <probe>`,
  wrapper prefixes such as `uv run` included), not the `baron` package that happens to be
  importable in doctor's interpreter. A project wired to a stale, shadowed or hand-rolled
  `baron` *is* the badminton shape, and an in-process probe is structurally blind to it —
  it exercises the very module the bug assumes is fine. Where the hook names no resolvable
  executable, doctor falls back in-process and the check detail says so in those words: a
  PASS there is about the library, not about the command the hook would run.
- **The caveat ships with the command, not just the docs.** Doctor verifies WIRING, not
  invocation — it proves the install *can* enforce and cannot observe whether Claude Code
  actually ran the hook, because nothing outside the runtime can. That sentence prints on
  every run including green ones, is a field in `--json`, and is grep-asserted by a test.
  A command that implied otherwise would manufacture the same false confidence that
  produced the badminton merges.
- **Check 6 uses a synthetic persona, not the project's** — otherwise it would measure the
  project's capability grants rather than the mechanism (a permissive project would PASS
  vacuously; a merger persona holding `merge_pr` would FAIL falsely). It also rejects an
  exit 2 that arrived via the internal-error path: a guard that denies everything by
  crashing is an outage that happens to look safe, not enforcement.
- **Probes neutralise `BARON_GUARD_OVERRIDE` and restore it** — left set, it would measure
  the escape hatch instead of the mechanism. Its being exported is its own FAIL: for a
  session, it is indistinguishable from having no guard.
- **Evidence checks are INFO, never FAIL.** Enforcement is fail-closed; evidence is
  fail-open. A broken audit sink must not be reported as broken enforcement, or people
  learn to ignore the exit code. A gitignored `guard-override.log` is called out loudly in
  the detail and still exits 0 on its own.
- **Un-copied runtime kits get a named remedy** — when there is no hook but
  `agents/<slug>/runtime/.claude/settings.json` exists, the remedy names the kit path, the
  incident, and the `cp -R`. That gap *is* the badminton shape.
- **Wrapper hook commands are understood.** `uv run baron guard …` / `poetry run baron
  guard …` resolve the *launcher*, not the bare `baron` token, which may exist only inside
  the environment the launcher materialises; resolving it directly produced a false FAIL on
  a correctly-wired project. A resolvable launcher that will not answer `--version` here is
  reported UNKNOWN, not FAIL — doctor's value depends on people believing it when it shouts.
- **Two bounds are stated in the output, not just the docs**: which binary was measured
  (above), and that a bare executable name is resolved with `shutil.which` against
  **doctor's** PATH rather than the runtime's — the same non-reproducibility that keeps
  `~/.claude/settings.json` out of scope.
- `baron init`'s next-steps now has an explicit INSTALL-the-kit step followed by
  `baron doctor`, and both READMEs' quickstarts do the same (verified as written).
- Tests: `cli/tests/test_doctor.py` — mostly mutation tests, each asserting doctor names the
  break at nonzero exit. Delete the settings file; corrupt the persona; narrow the matcher;
  break the executable path; and — the one no monkeypatch can express — point the hook at a
  shell-script `baron` that answers `--version` but exits 0 on `guard`, or exits 2 with no
  `baron guard:` reason, or crash-denies.

### Documented — two evaluation gaps that were already decided

From the 2026-08-08 Barony/Nasiko evaluation. Recording the existing decision honestly *is*
the deliverable here; re-deriving a settled decision as a fresh proposal is the documented
failure mode of that note (its own CORRECTIONS block, ¶2).

- **Fail-open vs fail-closed on hook failure — settled since ADR-004 §2.3, now also
  measured and pinned.** No new ADR: the policy was decided, implemented
  (`guard.process()`'s two DENY paths), and documented on day one. The 2026-08-08 hands-on
  run measured it empirically; `test_doctor.py::test_fail_closed_policy_is_pinned_adr_004_s2_3`
  and doctor's own `fail-closed` check now assert it per-install.
- **`open_pr` / `run_tests` denial parsing stays DEFERRED** (`docs/BACKLOG.md` § Guard
  coverage growth), with the date and the reason: no observed-need evidence exists anywhere
  in the repo or the evaluation, and the vocabulary's design rule 4 / ADR-004 §2.2 make
  observed need the trigger. `capability-rules.v1.yaml` is unchanged and `rules_version`
  stays 1.

### Changed — the read-verb posture label now rests on FOUR measured adapters ([ADR-020](docs/adr/ADR-020-read-verb-posture-measured-on-four-adapters.md))

The owner's **D3 decision**, executed. `baron rules list` printed `instructed` for
`read_code` / `read_collab` on the strength of one measurement (`pydantic-ai`) while
speaking for four adapters; ADR-016 §4.1's round-3 wording admitted this by calling the
other three **unmeasured**. Honest, and a stopping point rather than a resting place —
prose saying "the others are unmeasured" fails no test when a fifth adapter lands.

**The printed label does not change.** What changes is that the evidence is now the same
size as the claim.

- **Three new static emission measurements.** `claude`, `code-puppy` and `generic` each get
  one: baron is handed two persona specs identical but for the two read verbs, generates a
  runtime kit from each, and the kits are inspected for any construct a runtime reads as a
  tool allow/deny list. `claude` emits exactly one machine-readable artifact
  (`.claude/settings.json`) and every key at every depth is hook wiring — no `permissions`,
  no `allowedTools`/`disallowedTools`, no `.claude/agents/<slug>.md` subagent, and no
  repo-level `.claude/` either. `code-puppy` and `generic` emit no machine-readable
  artifact at all. In every case the machine-readable surface is **byte-identical across
  the A/B pair** while the prose carries the denial: nothing baron emits is even a function
  of the denial, which is what `instructed` means.
- **Why this was cheap, when ADR-016 §8 costed it as "a larger piece of work".** The
  needed direction is negative, and negatives here are static: proving baron emits no
  enforcement mechanism is an inspection of what `baron init` generates. Only proving one
  *exists* would have needed a live runtime.
- **`pydantic-ai` keeps its live gate, untouched.** Its kit is executable Python, so the
  harness refuses to clear it statically and names
  `test_denying_read_code_does_not_omit_read_tools` instead. A harness that quietly cleared
  it would be manufacturing the fourth measurement rather than making it.
- **`rules.READ_VERB_MEASUREMENTS`** — one entry per shipped adapter, naming the evidence
  and the test behind it. `LABEL_CAVEAT` is built **from** it, so the published caveat
  cannot drift from the measurements, and a test asserts the keys equal
  `scaffold.ADAPTERS`: **a fifth adapter breaks the label's basis until it is measured.**
  That is the anti-drift lock the round-3 wording structurally could not provide.
- **The honest bound is published with the label**: the measured claim is *baron emits no
  mechanism capable of omitting the read tools*, **not** *the runtime cannot enforce them*.
  A hand-written `permissions.deny`, or the Tier-3 subagent the `claude` and `code-puppy`
  HYDRATE.md recipes describe, does enforce them — and is outside what `baron rules list`
  speaks for. Those HYDRATE tables still print `enforced` for the read verbs and are **not
  wrong**: they describe an artifact a human hand-authors, which baron never generates.
  Recorded as a known divergence (ADR-020 §7), not resolved by editing one table to match
  the other.
- **Caveat rendering.** `--json` still publishes the full `LABEL_CAVEAT` (claim + all four
  measurements) top-level and per row. The human table prints the new
  `LABEL_CAVEAT_SUMMARY` — same claim, same bound, no evidence — then one
  `measured — <adapter>: …` line each; a test asserts the summary is a literal prefix of
  the full string so the short form can never soften into a paraphrase. Four measurements
  inlined into one paragraph is a wall of text, and an unread caveat is the failure mode
  the field exists to prevent.
- **New reusable harness** `cli/tests/omission.py` — *does adapter X emit a mechanism
  capable of omitting the tools that verb Y grants?* Keyed `(adapter, verb)` because the
  per-runtime capability matrix is the planned follow-up and this is slice one. It applies
  `rules.py`'s refuse-don't-ignore rule to emission: `KIT_ARTIFACTS` is a closed
  classification of everything baron writes into a kit, and an unrecognised artifact fails
  the assertion *before* any mechanism check. **Verified to fail** —
  `test_the_harness_detects_a_mechanism_when_one_is_present` plants a `permissions.deny`
  block, a Tier-3 subagent file and a code-puppy agent JSON into real generated kits and
  asserts the probe fires on each.
- **ADR-016 §8 D-1 is ticked APPROVED**, with the basis recorded as four measured adapters.
  §4.1's round-3 scoping is superseded, and `DECISIONS-FOR-REVIEW.md` §D3 and §E.3 are
  updated: §E.3 no longer says "three of four adapters are unmeasured" but states the
  narrower bound that is actually true — no adapter's read-tool exposure is verified
  against a *live* runtime, and three of the four measurements speak only for what baron
  emits.
- Suite: 386 → **393**.

## [1.10.0] — 2026-08-04

### Added — ritual-token coverage is now gated in the adapters

Closes the gap `docs/BACKLOG.md` recorded during the 1.9.0 cycle. `check_review_feedback`
(ADR-008 §2) shipped to three of four runtimes on its first cut, because each renderer
keeps its own surface and nothing cross-checked them — and **both renderer styles fail
silently**: the code renderers echo the raw token, the prose surfaces simply omit the step.
1.9.0 guarded the two code renderers; the three prose surfaces stayed ungated.

- **`ritual-map:v1` marker** in `adapters/{claude,code-puppy,generic}/HYDRATE.md` — the same
  convention `capability-map:v1` already established. Adapter authors now maintain a parsed
  contract, which is why this is a minor bump rather than a patch.
- **`tests/bi_runtime_accept.py` check (d)** asserts every ritual token is declared in every
  prose surface, and flags unknown tokens. Token list comes from the **canon**
  (`persona.schema.md`'s session-ritual table), not from `baron.schemas` — the harness is
  stdlib-only and runs without baron installed (ADR-006 §2).
- **`test_ritual_tokens_match_the_canon`** — the JOIN, and the reason the rest is worth
  anything. Review of the first cut proved that adding a token to `RITUAL_TOKENS` plus both
  code renderers, without touching the canon, left all three prose adapters uncovered with
  every suite green: the guard was wired to one end of a contract whose other end nothing
  checked. The chain now runs **code renderers ← `RITUAL_TOKENS` ← canon → adapters**.
- **A closed fence, not a scan-to-next-heading.** Entries are read only between
  `ritual-map:v1` and its closing marker, because a prose bullet mentioning a token *after*
  the surface was otherwise miscounted as a declaration — a deleted entry could be masked by
  a passing mention. Both failure modes have mutation tests.
- **Shape-tolerant parser** — claude and code-puppy use pipe tables, generic a bullet list;
  normalising them would be churn for its own sake. An entry must *start* its line with `|`
  or `-` plus the backticked token, so a token merely mentioned in prose is not miscounted.
- Verified by mutation: deleting one token from one adapter fails the harness with that
  adapter and token named. (An earlier cut of the parser stopped at generic's wrapped
  continuation lines and reported 4 of 5 tokens missing from a surface declaring all 5 —
  caught by the guard itself before commit.)

_Nothing yet._

## [1.9.0] — 2026-08-02

The governance-hardening release: the 2026-07-31 pilot ways-of-working folded
into the canonical templates (ADR-008), and spec↔runtime drift detection
(P2.3). Bundles everything accumulated since **1.8.0** — the plugin/skill was
unreleased across 1.8.1 and 1.8.2, and the pending bundle was relabelled to
**1.9.0** when the P1 fold-in added a schema token and a new emitted workflow;
a patch label would have been wrong.

**CLI track (`barony` on PyPI, versioned independently — `cli/pyproject.toml`):**
0.5.1, 0.5.2, 0.5.3, 0.5.5 and 0.5.6 are live. **0.5.4 was never published** (its
content ships inside 0.5.5), and **0.6.0 is likewise not published separately** —
its content ships inside **0.7.0**, which is the version released here. Skipping
an intermediate version rather than back-publishing it follows the 0.5.4
precedent: the CHANGELOG keeps the full per-version history either way.

### Added — `barony` 0.7.0: spec↔runtime drift detection (AGENT-TASKS P2.3)

`baron validate` now compares the personas a project **declares** against the
agents its runtime has actually **registered**. Owner picked this over P2.1
(2026-08-02) as the smaller, schema-change-free build.

**The failure it closes** (badminton-analyzer pilot, 2026-07): the collab repo
declared eight personas; the Claude subagent registry held six. `terrence` and
`carson` existed only as `persona.yaml`. Routing work to them did not fail
loudly — it fell through to whatever agent the runtime *did* have, so a cron ran
under the **wrong persona**: wrong identity, wrong commit prefix, wrong
capability set. Verified against the real pilot repo: the check reports exactly
those two.

- **The signal is PARTIAL registration, not absence.** Some personas registered
  and others not is positive evidence that the project hydrates agents on this
  runtime, which makes the gaps genuine drift (**error**). **That evidence must be
  repo-scoped** — a user-level `~/.claude/agents` entry matching a persona name
  proves nothing about this project (the directory is machine-wide and `dev` /
  `librarian` are the scaffold defaults); it can satisfy a persona but never
  establish that the project hydrates agents. All-or-nothing is
  **silent**, because zero registered is *correct* for a Tier-2 Claude project
  (`HYDRATE.md`: at Tier 2 "do NOT emit a dead subagent file"), a freshly
  scaffolded project (Tier-3 hydration is conversational, ADR-006 §3), and any
  Tier-1 runtime. **`tier: auto` is treated as Tier 3 — a judgement call, not a
  sidestep:** under `auto` HYDRATE.md permits per-persona degradation to Tier 2,
  which baron cannot distinguish statically from drift. It errors, and names the
  escape hatch in the message — declare `runtime.adapters.<runtime>.tier: 2` on
  that persona and the check honours it. **That escape hatch has a real cost, and
  the message says so:** the override is permanent and locks the persona out of
  Tier 3, so its whole-tool denials drop from enforced to instruction-only —
  whereas the ambiguity it resolves (`auto` degradation) is per-session. Explicit `tier: 2` at **either** the
  manifest or the per-persona level (`persona.schema.md` v1.1) is skipped.
- **Registries** — `claude` (`.claude/agents/<slug>.md`) and `code-puppy`
  (`.code_puppy/agents/<slug>.json`), searched collab-root → `paths.root` → each
  `repos[].path` → `~/`. Registration matches the adapter's filename **or** a
  `name:` frontmatter match, since that is what Claude keys a subagent on.
  `pydantic-ai` and `generic` have no inspectable registry (in-process hydration
  / Tier-1 prose) and are excluded in code with a comment.
- **Only declared runtimes are checked**, so a stray registry cannot fail a
  project that does not hydrate agents. User-level-only resolution **warns**:
  `~/.claude/agents` is shared across every project on the machine.
- **Honest limits, stated in the module**: a one-persona project cannot produce a
  partial state, and a fleet that drifted *entirely* reads as "not hydrated".
- **On CI:** the Claude registry is repo-scoped and travels with the clone
  (`HYDRATE.md` step 3a), so a committed `.claude/agents/` **is** present in CI by
  design, and a partially-registered project fails there deliberately.
  `--no-runtime-drift` opts out. `baron init` passes it for its own self-check —
  init validates the spec it wrote, not the environment around it.
- **Tests:** `cli/tests/test_drift.py` (13 cases: the pilot shape, the
  fresh-scaffold regression, explicit tier 2 vs 3, `paths.root` resolution,
  frontmatter matching, and an anti-vacuity guard that fails if `check` is
  gutted). Two `test_scaffold.py` assertions were reading the *developer's* real
  `~/.claude/agents`; both now scope to schema conformance.

### Proposed (no code) — [ADR-009](docs/adr/ADR-009-baron-decision-reconciliation.md): `baron decision`

Design proposal for the FM6/D57 mechanism ADR-008 §4 named but shipped as prose:
a ratified decision must reach the surfaces personas pull *work* from, not just
`decisions/`. **Awaiting owner review — nothing implemented.**

Load-bearing boundary: **baron never determines what a decision contradicts** —
inferring it needs a model call (crossing ADR-007's line) and its worst failure
is parking live work. Surfaces are declared input; baron performs the mechanical
steps and **verifies discharge**, reporting three states (discharged /
outstanding / **unverifiable**) so an unreachable forge is never scored as
either. Obligations live in a marker-delimited region inside the
`decisions/index.md` entry (ADR-003 §2.2 — no second store).

**Rev. 2 after adversarial design review**, which found four blocking defects in
rev. 1. The material one: `park` discharged on "closed OR label+comment", but
D57's own table records the FM6 epic as parked exactly that way and left OPEN —
the check would have gone green on the state that caused the failure it cites.
Park now discharges only when an agent's backlog query stops returning the item
(closed, or filtered via a declared `manifest.backlog.park_label` — a real
schema change, which is the honest cost). Also corrected: the `enforced` tier
claim (nothing here vetoes a call — instructed + visibility, per ADR-004);
`direction_doc` discharging on a closed ticket (an index substituted for the
record — the exact ADR-008 §1 failure); and the "detection was never the
problem" justification, which generalized from a post-hoc RCA.
§10 lists five questions blocking implementation.

### Added — plugin 1.9.0 + `barony` 0.6.0 (ways of working 2026-07-31 — ADR-008)

Promotes the 2026-07-30/31 badminton-analyzer pilot hardening into the canonical
templates, so the next `baron init` scaffold ships with it instead of every
adopter re-discovering it. Same promotion mechanism ADR-002 used for the July
learnings; recorded in
[ADR-008](docs/adr/ADR-008-ways-of-working-2026-07-31.md). (AGENT-TASKS P1.1–P1.5.)

Both new review-loop rules trace to one structural gap: **ADR-002 gave verdicts a
SHA but never said what a label is**, so personas filled the answer in themselves,
in opposite directions, and both answers were wrong.

- **`CONVENTIONS.md` — "A label is not evidence, in either direction"** (ADR-008
  §1). Labels are an index; the record is the verdict comment bound to a head SHA
  (`REVIEW:PASS/FAIL <sha>`). Check the SHA against the current head **before
  acting on an approval label** *and* **before concluding a block is stale** — the
  second direction is new; the first existed only as a Merger precondition and is
  now general. Corollary: green CI does not clear a block. Forbids adjudicating a
  label-vs-verdict disagreement by adding another persona — check the SHA.
- **`CONVENTIONS.md` — "Decision & ADR intake: the Librarian RECORDS and
  RECONCILES"** (ADR-008 §4). Five-step intake: record with supersession →
  park/close contradicting epics and backlog items → reconcile the direction doc
  (route a ticket if it's in a repo the Librarian can't write) → broadcast →
  hydrate directional decisions at session start before ticket selection.
  Personas re-derive "what next" from the direction doc and open epics, never from
  `decisions/`, so a recorded-but-unreconciled decision is invisible to exactly
  the surfaces that drive work. Honest label: discipline-in-a-doc; the mechanical
  version is the proposed `baron decision` (AGENT-TASKS P2.1).
- **New session-ritual token `check_review_feedback`** (ADR-008 §2; persona
  schema **v1.2**) — *act on review verdicts that are LIVE at your current head,
  before claiming new work.* Ships in the `__DEV__` ritual ordered **before**
  `check_backlog` (the ordering is the substance: feedback on work you have
  outranks a new ticket). Mapped in the claude / code-puppy / generic
  `HYDRATE.md` prose ritual-token surfaces **and** in the pydantic-ai hydrator
  (which renders in code, not in prose), rendered as SHA-test prose by `baron
  init`'s runtime kits, and added to baron's `RITUAL_TOKENS`. Additive — a
  ritual omitting it behaves exactly as before, and unknown tokens were already
  a warning, not an error.
- **New cross-runtime drift guard** for the ritual vocabulary
  (`test_every_ritual_token_renders_on_every_runtime`). Both **code** renderers
  fall back to echoing the raw token, so a missing entry does not crash — the
  rule silently vanishes from that runtime's persona body.
  `bi_runtime_accept.py` never gated this (it parses capability maps, not ritual
  tokens). Every `RITUAL_TOKENS` entry must now render real prose on both code
  renderers (`scaffold._ritual_lines` and `runtimes.pydantic_ai._RITUAL_LINES`).
  The other three adapters' `HYDRATE.md` prose surfaces remained **ungated** at
  this version — a known, recorded gap, **closed in 1.10.0** (above).
- **`.github/workflows/strip-stale-verdict.yml`** (ADR-008 §3) — emitted by
  `baron init` alongside `lock-guard.yml`: on every `synchronize`, removes the
  project's reviewer verdict labels and comments that the head moved, so that —
  where it is installed and covers the label — "a review-state label is present"
  means "a verdict exists at *this* head". Owner gates (`needs-human`, `hold`,
  `contract-change`) are explicitly excluded — only the owner lifts those.
  Dependency-free (bash + `gh`, built-in `GITHUB_TOKEN`), no-ops on fork PRs.
  Carries the `lock-guard.yml`-style honest limitation: it removes a misleading
  label, it cannot stop a persona that never reads verdicts — the merge gate
  still lives in the Merger's preconditions. Written into the collab repo (the
  repo init scaffolds); the header instructs copying it to the code repo, where
  most reviewed PRs live.
- **Reviewer / Merger templates hardened** (ADR-008 §1). Reviewer: verdict format
  is a parsed contract (full head SHA, never a branch/`HEAD`/abbreviation, fetched
  via `gh pr view --json headRefOid`); re-review publishes a NEW verdict, never
  edits the old one; labels follow the verdict and never lead it. Merger: **a
  label is never an input to the merge decision** — read the verdict, compare the
  SHA yourself, and if label and verdict disagree strip the label and refuse.
- **`COORDINATION.md § Review and merge`** gains the dev-side feedback-sweep step
  and states that review-state labels are an index for every persona in the loop.

Vendored template copy re-synced (`cli/scripts/sync_templates.py`); drift guard
green; 133 CLI tests (2 new) + both stdlib suites pass.

### Added — `barony` 0.5.6 + plugin 1.8.2 (session boundary — ADR-007 + thin session primitives)

The 2026-07-28 pydantic-ai interop eval found the split: enforcement is solid
(the in-process guard vetoes denied tool calls, proven live) but the session
RITUAL — sync repos, read conventions/handoffs, check the backlog, record
findings/handoffs, commit with the right prefix, regenerate the index — was
instructed prose only; a human/script had to drive it.
[ADR-007](docs/adr/ADR-007-session-boundary.md) records two decisions.

- **Barony does NOT own the agent execution loop.** No `baron run` driver;
  orchestration/execution belongs to the runtime layer (ADR-001's three-layer
  positioning: Barony = coordination policy + governance + audit; runtime =
  execution). A driver would duplicate — and lose to — pydantic-ai / Temporal /
  Claude Code, and cross the boundary the design defends.
- **Barony DOES ship thin, optional session-ritual primitives.**
  `baron session start [--persona] [--sync] [--json]` (session-open: optional
  `git pull --ff-only`, then the persona's open handoffs + a
  CONVENTIONS/COORDINATION pointer + the manifest backlog location) and
  `baron session end [--persona] [--json]` (session-close: regenerate the handoff
  index, commit dirty `_handoff/ findings/ decisions/ wiki/` by path — never
  `git add -A` — with the persona's `commit_prefix` else `baron:`, then a
  `baron status` divergence check; exit 1 on red). They mechanize ONLY the
  git/markdown bookkeeping — no agent loop, no model calls, no runtime coupling;
  opt-in (nothing in baron requires them); NOT new capability verbs (the frozen
  10 stay frozen). They compose existing baron functions (`status`, `handoff`,
  `indexer`, `gitutil`) — nothing reinvented. Honesty in both `--help`: "they do
  NOT run an agent — orchestration is the runtime's job (ADR-007)."
- **Docs:** `cli/README.md` "session ritual primitives (optional)" (the boundary
  + the three composition points: a human between turns, a driver/CI wrapper, a
  runtime adapter capability/hook); `docs/concepts.md` short paragraph; the
  pydantic-ai adapter HYDRATE.md gains a "composing the session ritual (optional)"
  note (plugin/skill **1.8.1 → 1.8.2**; vendored template copy re-synced
  byte-identical). `docs/BACKLOG.md`'s "reverse-direction / `baron run` driver —
  decision pending" note is replaced with the ADR-007 resolution.
- **Tests:** `cli/tests/test_session.py` — start surfaces a persona's open
  handoff + brief, `--json` shape, `--sync` fast-forward pulls (bare-origin
  fixture), end regenerates the index + commits dirty coordination files with the
  persona prefix + reports status, end exits 1 on red, both no-op-clean.

### Added — `barony` 0.5.5 (worktree repair commands — rest of baron M6)

Closes the `docs/BACKLOG.md` "Worktree topology — repair commands" item: the
migration runbook surfaced two repair needs when a worktree dir is moved or
deleted *outside* baron (git leaves a stale registration in `.git/worktrees/`).

- **`baron worktree prune [--dry-run]`** — wraps `git worktree prune` to clear
  stale administrative registrations for worktree dirs that no longer exist.
  `--dry-run` uses `git worktree prune -n` to report what would go without
  changing anything; the report (git writes it to stderr) is surfaced in plain
  text, and a clean "nothing to prune" when there is none.
- **`baron worktree repair [PATH…]`** — wraps `git worktree repair` to fix a
  worktree's admin links (gitdir pointer + `.git` gitlink) after a worktree or
  the main repo was moved on disk. With paths, repairs those; otherwise all.
  Requires git >= 2.30 (a capability check via `git worktree -h` gives a clean
  error on an older git).
- Both are **non-destructive to committed work** — they touch only
  `.git/worktrees/` admin state, never a branch or its history (stated in
  `--help`), consistent with `remove`'s safety ethos. `--repo` resolves from the
  manifest (`repos[role=code]`) exactly like the other worktree commands.
- Docs: `docs/worktree-migration.md`'s gotcha section now points at
  `baron worktree prune`/`repair` instead of raw git; `cli/README.md` documents
  the subcommands.

### Security / hardening — `barony` 0.5.4 (interop hardening + backlog burndown)

Driven by a hands-on dogfood of the pydantic-ai adapter (2026-07-28).

- **Least-privilege Shell in the pydantic-ai adapter (real containment gap).**
  `build_agent`/`plan` previously gave any shell-granting persona a *full* shell
  (`Shell(cwd, denied_commands=[])`) — a reviewer whose only shell-implying grant
  was `run_tests` could `curl`/`rm`/`git push feature/x` (the guard only vetoes
  three git sub-verbs). Now: a persona whose only shell need is `run_tests` (and
  no broad `write_code`/dev verbs) gets an **allowlisted** shell restricted to
  test runners (`pytest`/`py.test`/`tox`/`nox`/`unittest`/`coverage`,
  `denied_commands=[]` since the harness makes allow/deny mutually exclusive); a
  broader dev shell stays general but now sets `denied_operators=['>', '>>', '|']`
  so a redirect can't write out of root behind the guard. `python -m pytest` /
  `make test` are intentionally excluded (the harness matches the executable
  name; allowing `python`/`make` would re-open a general runner).
- **Guard denies out-of-root writes itself (defense-in-depth).**
  `guard.evaluate_write` now normalizes the target and DENIES any path that
  escapes the collab/persona root (a `../outside.md` resolving above root),
  rather than leaving it to the harness FS jail (which a Shell `>` redirect
  escapes anyway).
- **Guard-bypass honesty is now prominent.** `bash -c '...'` / `sh -c "..."` /
  `python3 -c '...'` wrappers run their payload uninspected by the static parser
  — documented plainly in `guard.py`, the pydantic-ai `HYDRATE.md`, and
  `docs/concepts.md`. (No blocking heuristic added — it would false-positive on
  every read-only persona's legitimate `bash -c`.)
- **Calmer remote-less guard wording.** The first-run "origin default branch
  undeterminable; `main` conservatively treated…" stderr is reworded to a calmer,
  still-honest phrasing.
- **`RepoContext` wired (additive).** `build_agent` now adds
  `RepoContext(workspace_dir=<collab_root>)` when a `collab_root` is passed
  (auto-loads `CLAUDE.md`/`AGENTS.md`), with a clean fallback if the installed
  harness lacks it.
- **`baron handoff create --body-file F`** — parity with `finding`/`decision`;
  the file's content becomes the handoff body under the frontmatter.
- **`baron handoff close --as <slug>`** — attributes the close commit as
  `<slug>:` instead of the default `baron:`.
- **`BARON_NOW` clock override** — the default clock honors an ISO
  date/datetime `BARON_NOW` env var for demos/backfills (a testing seam, not for
  normal use; malformed values raise).
- **Docs — `--author` vs git author.** `cli/README.md` + command help now
  document that `--author` sets ledger attribution while the git author identity
  is separate (allocator-vs-proposer).
- **Version-string honesty.** The "pydantic-ai-slim 2.16.0" string in
  `cli/pyproject.toml`, `pydantic_ai.py`, and the adapter `HYDRATE.md` is
  corrected to the tested range (harness 0.10.0 / slim 2.14.1–2.19.x).

### Changed — plugin/skill **1.8.1** (paired with 0.5.4)

- The pydantic-ai adapter `HYDRATE.md` (skill asset + vendored template, kept
  byte-identical) documents the least-privilege Shell, `RepoContext` wiring, the
  prominent `bash -c`/`sh -c` bypass note, and the corrected version range.
  `plugin.json` + `SKILL.md` bumped together (lint-enforced).

### Fixed — `barony` 0.5.3 (install-UX shakeout)

- **`barony` now works as a command too**, aliased to `baron`. A fresh
  `pip install barony` followed by the natural `barony --version` was dead-ending
  in `command not found` (the package is `barony`, the command was only `baron`).
  Both now resolve to the same CLI; `baron` stays the primary/documented name.

### Fixed — `barony` 0.5.2 (first-publish shakeout)

- **`baron --version` / `-V`** now exists — it errored ("No such option") the
  minute 0.5.1 hit PyPI and someone ran the obvious first command.
- **`__version__` no longer drifts** — it derives from installed package
  metadata (it had silently sat at `0.4.0` while the package shipped `0.5.1`).
  New `test_version_flag_matches_pyproject` guards `--version` ≡ pyproject.
- README + `cli/README.md` install sections flipped to the live PyPI path
  (`uv tool install barony`) now that the package is published.

### Packaging — `barony` 0.5.1 (pre-publish polish)

- **`[project.urls]`** added to `cli/pyproject.toml` (Homepage/Repository/
  Documentation/Changelog/Issues → `github.com/vggg/barony`) so the PyPI page
  links home instead of rendering as an orphan. `description` sharpened to the
  product one-liner. `cli/README.md` opens as a proper package landing page.
- `.gitignore` covers build artifacts (`dist/`, `build/`, `*.egg-info/`).
- Homepage points at the repo until `barony.dev` is registered.

### Changed — docs only (no version bump)

- **README.md rewritten as the outsider's front door** (inverted pyramid): the
  one-liner + three-sentence identity, the four-walls 60-second pitch with one
  first-party receipt each (stranding incident, operational fidelity 0.53,
  handoff/ledger rot, single-account accountability), the verified v1.8.0
  quickstart (commands unchanged), ~3-sentence core concepts, the per-adapter
  runtime/enforcement matrix sourced from the HYDRATE capability maps, an
  explicit "what Barony is NOT" section, and status/links.
- **Deep material moved out of the README**: new `docs/concepts.md` (longer-form
  concept explanations, emitted layout, capability ladder, guard/lock/worktree/
  audit detail) and `docs/history.md` (the v0.3 → v1.8 evolution narrative,
  linking ADR-001/002/005/006). `CLAUDE.md` gains a one-line pointer to the
  README as the public story and lists the two new docs files.

## [1.8.0] — 2026-07-27

**The stranger release** — a stranger with a laptop gets a working project in
minutes: `pip install barony`, `baron init`, done. The deterministic scaffold path
lands as a CLI command ([ADR-006](docs/adr/ADR-006-baron-init-template-packaging.md));
the conversational path (`START.md` → `ORCHESTRATE.md`) keeps the judgment work.
CLI version `0.4.0 → 0.5.0`.

### Added

- **`baron init <name> [--dir] [--code-repo] [--personas archetype:slug,...]
  [--runtime claude|generic|pydantic-ai|code-puppy] [--no-git]`**
  (`cli/src/baron/scaffold.py`) — emits the canonical collab-repo layout:
  `CONVENTIONS.md`/`COORDINATION.md` filled, a schema-conformant `manifest.yaml`
  (relative paths, `backlog: file`, `workspace.worktrees_root` when a code repo is
  named), `canon/` + `adapters/` copied verbatim (ORCHESTRATE.md §2a), hydrated
  `agents/<slug>/persona.yaml` per persona (identity `<slug>@<project>.local`;
  librarian renameable, e.g. `librarian:iris`; generic edit-me scope — never fake
  specificity), a genesis handoff, `findings/`+`decisions/` index headers the real
  ledger allocator appends to, the wiki stub, and the lock-guard CI template.
  Self-validates with the real schemas (zero errors) before `git init -b main` +
  a first commit of exactly the files written. Refuses a non-empty directory.
- **Per-persona runtime kits** (`agents/<slug>/runtime/`) — the deterministic
  floor of each adapter: claude = Tier-2 persona `CLAUDE.md` + `.claude/settings.json`
  wiring the `baron guard` PreToolUse hook (HYDRATE.md steps 3b/3c); generic and
  code-puppy = Tier-1 `AGENTS.md`; pydantic-ai = the `agent_setup.py` bootstrap.
  Tier-3 hydration and scope prose stay conversational — the kits' READMEs say so.
- **Template packaging (ADR-006)** — the skill tree stays the single canonical
  source; `baron init` reads a byte-identical vendored copy shipped as package
  data (`cli/src/baron/data/templates/`, synced by `cli/scripts/sync_templates.py`).
  Drift guard: `cli/tests/test_template_sync.py` fails CI on any divergence.
- **Tests** — `cli/tests/test_scaffold.py` (layout, self-validation, hydration,
  runtime kits, git init, re-init refusal, ledger-on-scaffold) + the sync guard;
  cli suite 92 → 103 tests. *(Corrected post-release: this entry originally
  claimed 114.)*

### Changed

- **README.md / cli/README.md** — new Quickstart sections with the exact
  command sequence verified end-to-end from a fresh install against an existing
  git code repo: init → validate → status → finding → handoff create/close →
  index → worktree add, plus a `baron guard` deny/allow smoke. (The `status` and
  `worktree` steps require the code repo the quickstart creates first.)
- **`baron validate`** — the template-skip rule also covers baron's own vendored
  templates (`baron/data/templates/`), mirroring the repo lint.
- **ORCHESTRATE.md** — notes the `baron init` shortcut for its mechanical steps
  (1–2a) and where the conversational recipe resumes.

## [1.7.0] — 2026-07-27

**The Barony release** — the project is renamed from `agent-project-bootstrap` to
**Barony**: git-native governance for teams of AI coding agents. The rename is recorded
in [ADR-005](docs/adr/ADR-005-naming.md); the naming system is **Barony** = the
product/framework (spec + adapters + baron CLI + audit), **baron** = the CLI
(install `barony`, run `baron`, import `baron`).

### Changed

- **Repo** — `vggg/agent-project-bootstrap` → `vggg/barony` (GitHub redirects the old
  URLs). All live GitHub links updated.
- **Skill directory** — `skills/agent-project-bootstrap/` → `skills/barony/` (git mv);
  skill frontmatter `name: barony`; plugin manifest `name: barony`. The sister skill
  keeps its name (`multi-agent-audit`). All path references (docs, tests, templates,
  legacy pointers) updated.
- **CLI distribution** — `baron-cli` → **`barony`**, version `0.3.0 → 0.4.0`. Console
  script and import package stay `baron`; the optional extra is now
  `barony[pydantic-ai]`.
- **Positioning copy** — README/CLAUDE/STATUS identity statements rewritten around the
  current positioning ("git-native governance for teams of AI coding agents"); stale
  v0.3-era scaffolding/vault copy removed from CONTRIBUTING. The "signet" name is
  introduced for SHA-sealed review verdicts (reserved sub-brand, ADR-005 §2).
- **Leak scrub** — absolute local paths and non-fiction personal identities removed
  from audit-skill examples (`references/timeline.md`, `references/actor-resolution.md`,
  `assets/actors.example.yaml`, `references/confidence-and-trends.md`); replaced with
  generic placeholders.

### Added

- **`docs/adr/ADR-005-naming.md`** — the naming decision, research summary (PyPI/npm
  availability, rejected alternatives), and rename mechanics.

Historical entries below this line keep the old name where they describe the past —
history is not rewritten.

## [1.6.0] — 2026-07-23

The fourth-runtime release: the guard's rule table becomes a versioned, machine-readable
artifact every enforcer shares; the generic adapter emits `AGENTS.md` (the cross-runtime
context convention); and pydantic-ai lands as a full runtime adapter with a working
in-process hydrator — the first adapter whose sub-tool denials are natively `enforced`.

Also in this release — `multi-agent-audit` v1.4 telemetry mode: `scripts/ingest_otel.py`
(OTLP-JSON/JSONL trace-export ingestion — Claude Code, Logfire, Phoenix; stdlib-only,
files-only, never live endpoints) + `scripts/merge_telemetry.py` (additive, source-tagged
snapshot merge; git-derived metrics never overwritten). Upgrades intervention-tax inputs
from `inferred` to `measured` when an OTel export exists; `not measurable` is reported
honestly, never estimated. New `tests/test_ingest_otel.py` (66 checks) + fixtures.

### Added — the capability-rules artifact (single source for enforcement rules)

- **`cli/src/baron/data/capability-rules.v1.yaml`** (new, `rules_version: 1`) — the
  runtime-agnostic verb→enforcement rule table `baron guard` previously hardcoded, now
  shipped as baron package data (`importlib.resources`, loaded by the new
  `cli/src/baron/rules.py`): git command patterns (push to default branch / `--all` →
  `push_main`; force flags + `+refspec` → `force_push`; `gh pr merge` → `merge_pr`;
  `git merge` on the default branch → `push_main`), the value-taking options each parser
  must skip, fallback default-branch names, file-op scoping semantics
  (`_handoff/` universal-write, own-vs-other `agents/<slug>/` spec dirs, denied-scopes-
  always-block precedence), the `conservative-deny` ambiguity policy, and per-rule notes
  (including which verbs are deliberately NOT parsed: `open_pr`/`run_tests`). Placement
  rationale recorded in the ADR-004 addendum §4.1.
- **`guard.py` refactored to consume the artifact** — mechanics (shell splitting, refspec
  resolution, branch lookups, hook I/O) stay code; every pattern is loaded from the rules.
  Behavior identical: the 19 guard tests pass unchanged. A broken/unsupported artifact
  fails CLOSED (deny with the reason), never open. New `cli/tests/test_rules.py` asserts
  the artifact is packaged + versioned, its verb set exactly matches the frozen 10-verb
  vocabulary, guard decisions actually follow the loaded data (mutation test), and
  `rules_version` mismatches are refused.
- **`references/capability-rules.md`** (new skill reference) — the prose contract: the
  artifact is THE single source for enforcement rules; consumers (baron guard, runtime
  adapters) load it and never restate patterns. `capability-vocab.v1.md` gains a pointer
  note (the vocabulary itself is untouched — still frozen at 10 verbs).

### Added — AGENTS.md emission (generic adapter, Tier 1)

- **`adapters/generic/HYDRATE.md` step 3 (new)** — Tier-1 hydration now emits ONE
  artifact: an `AGENTS.md` in the persona's working-copy root, derived entirely from
  `persona.yaml` (marked generated-do-not-hand-edit), with identity, scope, session
  ritual, capability grants AND denials in plain imperative language, and collab-repo
  pointers. AGENTS.md-aware runtimes (pydantic-ai-harness `RepoContext()`, etc.)
  auto-load it; for everything else it is the core loop's re-read target. **Honest tier
  note carried in the template itself:** everything in it is instruction-only — emitting
  a file does not upgrade the tier.
- **Claude adapter note** — `CLAUDE.md` remains that adapter's native context file;
  emitting `AGENTS.md` alongside is optional/additive (useful when the same working copy
  is visited by AGENTS.md-aware runtimes), both derived from `persona.yaml`.

### Added — pydantic-ai runtime adapter (the fourth runtime)

- **`adapters/pydantic-ai/HYDRATE.md`** (new) — full adapter in the standard format with
  the machine-readable `capability-map:v1` table covering all 10 verbs. The adapter's
  distinction, stated honestly: hydration is **in-process**, so the five guard-covered
  sub-tool denials (`write_path` scoping, `merge_pr`, `push_main`, `force_push`,
  `edit_other_personas`) are natively class **`enforced`** — the interception hook cannot
  be absent from an agent built via `build_agent` (unlike the Claude hook, which degrades
  without baron). Whole-tool denials via capability omission (no shell verbs → no `Shell`
  capability at all; no write verbs → natively read-only `FileSystem`).
  `open_pr`/`run_tests` denials stay `instructed` (the rules artifact defines no
  detection for them). Verified against **pydantic-ai-harness 0.10.0** +
  **pydantic-ai-slim 2.16.0** (2026-07-23; APIs: `Agent(capabilities=[...])`,
  `AbstractCapability.before_tool_execute` + `ModelRetry` veto, harness
  `FileSystem`/`Shell`/`RepoContext`).
- **`cli/src/baron/runtimes/pydantic_ai.py`** (new) — the working hydrator:
  `build_agent(persona_file, collab_root=None, model=...) -> Agent`. Instructions
  composed from persona identity/scope/ritual/capabilities; `FileSystem` scoped per
  write verbs (`protected_patterns=['*', '**/*']` = natively read-only when no write
  verb); `Shell` only when a shell-granting verb is allowed, with `denied_commands`
  seeded with common test runners when `run_tests` is denied; a guard capability whose
  `before_tool_execute` evaluates `run_command` commands and file-write paths through
  `baron.guard`'s evaluators — i.e. the SAME `capability-rules.v1.yaml` the Claude hook
  uses — and vetoes denials with `ModelRetry` (reason fed to the model, mirroring
  exit-2 + stderr). `runtime.model_hint` honored as the default model; the offline
  `"test"` model is the fallback placeholder.
- **Optional extra `baron-cli[pydantic-ai]`** — pinned `pydantic-ai-harness>=0.10,<0.11`
  + `pydantic-ai-slim>=2.14.1,<3` (harness is 0.x; minor releases may break). Without
  the extra the module import-errors cleanly with install instructions. The dev
  dependency group repeats the pins so the test suite exercises the real APIs.
- **`baron hydrate pydantic-ai --persona-file F [--out agent_setup.py]`** (new command,
  new `hydrate` sub-app) — emits a ready-to-edit bootstrap script (imports
  `build_agent`, offline-model placeholder). Emission needs only baron; running the
  script needs the extra.
- **`cli/tests/test_pydantic_ai.py`** (new, offline only — TestModel/FunctionModel, no
  API keys): dev fixture gets Shell, reviewer fixture gets NO Shell capability;
  write scoping follows the verbs (scopes allowed, `src/` blocked, own vs other
  `agents/<slug>/` dirs); a scripted `git push origin main` attempt through a REAL agent
  run is vetoed before execution with the guard's reason (FunctionModel scripts the tool
  call — TestModel cannot script specific args); interceptor unit tests; clean
  import-error path (subprocess with the dependency blocked); CLI emission tests.
- **`tests/bi_runtime_accept.py`** — the sweep now covers **4 adapters**; the pydantic-ai
  map must cover all 10 verbs and the tess/rex fixtures must hydrate to the equivalent
  contract. Enforcement-tier consistency extended and TIGHTENED: both per-adapter
  allowances (claude's `enforced-with-baron (instructed otherwise)`, pydantic-ai's plain
  `enforced` on sub-tool rows) are now accepted ONLY on the five guard-covered verbs —
  a guard claim on an `open_pr`/`run_tests` row fails for every adapter.

### Changed — meta

- `plugin.json` + `SKILL.md` frontmatter `1.5.0 → 1.6.0`; `baron-cli` package
  `0.2.0 → 0.3.0` (and `baron.__version__` re-synced — it had lagged at 0.1.0).
- ADR-004 gains a **§4 addendum**: §4.1 rules-artifact externalization + placement
  rationale; §4.2 the pydantic-ai adapter's native-`enforced` sub-tool claim and why it
  needs no qualifier.
- ADR-001 §4.5/§4.6 current-adapter enumerations, `README.md` (runtime count 3 → 4,
  support table row, adapters listing, baron section), `CLAUDE.md`, `CONTRIBUTING.md`,
  `cli/README.md` (rules artifact, `baron hydrate pydantic-ai`, the extra),
  `STATUS.md`, `docs/BACKLOG.md` (guard-coverage entry re-scoped: pydantic-ai now has an
  in-process seam; pilot validation of the new adapter tracked), emitted
  `START.md`/`ORCHESTRATE.md` (runtime-key table + canon/adapters copy lists now include
  pydantic-ai and `capability-rules.md`).
- `tests/lint_repo.py` skips `.venv`/`.pytest_cache` (the newly installed harness ships
  READMEs whose relative links are not this repo's content).
- CLI test suite 75 → 91 tests.

## [1.5.0] — 2026-07-23

The mechanisms release: baron grows enforcement (guard), locking (PR-as-lock), the
worktree topology tooling, and status waivers — and the M1–M3 work ships properly.

> **Honest release note:** the "baron CLI M1–M3" block below was developed and pushed
> under `[Unreleased]` (2026-07-22) without a version cut — it reached `main` unreleased.
> It is folded into this 1.5.0 entry verbatim rather than back-dated as a phantom
> release; 1.5.0 is its first released version.

### Added — `baron guard` M4: deterministic capability enforcement (ADR-004)

- **`docs/adr/ADR-004-baron-guard-enforcement.md`** (accepted 2026-07-23) — why
  hook-based sub-tool enforcement is a contract change deserving its own record: it
  amends the enforceability-class honesty boundary (`capability-vocab.v1.md`) that every
  adapter's "do not oversell" rule is built on.
- **`baron guard --persona-file <persona.yaml>`** (`cli/src/baron/guard.py`) — a Claude
  Code **PreToolUse hook** implementing the documented contract
  (https://code.claude.com/docs/en/hooks): hook JSON on stdin (`tool_name`,
  `tool_input`, `cwd`); exit 0 + silence = defer to the normal permission flow; exit 2 =
  block with stderr fed to the model. Decision logic maps tool calls to the frozen v1
  verbs: `git push` to the default branch → `push_main` (conservative on ambiguity —
  an unresolvable target is inferred as the enforcement-relevant verb and denied for
  personas lacking it, stderr naming the inference); force flags / `+refspec` →
  `force_push`; `gh pr merge` → `merge_pr`; `git merge` while on the default branch →
  `push_main`; Edit/Write/NotebookEdit paths → `write_path` scopes /
  `edit_other_personas` / `write_code`, with `_handoff/` universally writable and a
  persona's own `agents/<slug>/` dir its own surface. Non-git/gh commands and unknown
  tools pass — a capability gate, not an allowlist. **Fail-closed but not brick**:
  malformed stdin / unreadable persona → deny with actionable stderr;
  `BARON_GUARD_OVERRIDE=<reason>` allows AND appends to the **tracked**
  `.baron/guard-override.log` (overrides are visible in diffs; each is expected to
  become a handoff). Env `BARON_PERSONA_FILE` honored.
- **Claude adapter HYDRATE.md step 3c** — Tier 2/3 hydration also emits a
  `.claude/settings.json` hooks block (PreToolUse, matcher
  `Bash|Edit|Write|NotebookEdit` → `baron guard`), with the honest note: five sub-tool
  denials (`push_main`, `force_push`, `merge_pr`, `write_path` scoping,
  `edit_other_personas`) upgrade from instructed to ENFORCED **when baron is
  installed**; without it the hook fails non-blocking and they degrade to instructed.
  The capability map's sub-tool rows now claim the exact qualified form
  `enforced-with-baron (instructed otherwise)` (`open_pr`/`run_tests` stay
  `instructed` — guard does not parse for them), and
  **`tests/bi_runtime_accept.py`**'s tier-consistency assertion accepts exactly that
  form, only on sub-tool rows, only for the claude adapter.

### Added — `baron lock` M5: PR-as-lock (mechanizes ADR-002 §3)

- **`baron lock claim <path> [--reason]` / `release <path>` / `list`**
  (`cli/src/baron/lock.py`) — the open PR is the lock: claim = `lock/<slug>` branch with
  one empty commit (`git commit-tree`; the local checkout is never touched) + a draft PR
  labeled `lock:<path>` with the reason in the body; claim refuses when an open lock PR
  for the path exists, showing the holder; release closes the PR + deletes the branch;
  list prints path/holder/age/PR#. Replaces the markdown LOCK-commit protocol.
- **Forge Protocol extended** (additive): `create_branch`, `close_pr`, label-aware
  `open_pr` (`head`, `labels` — labels created idempotently) and richer
  `list_open_prs` (labels/author/createdAt/url). All `gh` calls stay behind the Forge
  interface; `ForgeUnavailable` raised cleanly without `gh`; lock tests run against a
  recorded fake forge — no live `gh`.
- **`assets/collab-repo/.github/workflows/lock-guard.yml`** (new template) —
  dependency-free CI guard (bash + the `gh` Actions provides): fails a PR that touches a
  locked path unless it IS the lock PR; carries the ADR-002 §3 honest limitation
  (without branch protection a red check is an alarm, not a wall). The emitted
  `COORDINATION.md` lock mechanics now name the concrete commands and file.

### Added — baron M6 tooling: worktree topology

- **`baron worktree add <persona> [--root DIR]` / `list` / `remove [--force]`**
  (`cli/src/baron/worktree.py`) — one shared object store, branch `persona/<slug>`,
  worktrees under the manifest's `workspace.worktrees_root` (v1.2 seam, consumed
  unchanged). `remove` refuses on dirt or unmerged commits unless `--force` and never
  deletes the persona branch. `baron status` sweeps worktrees like clones (each
  worktree reports its checked-out HEAD; the repo-wide branch sweep runs once).
- **`docs/worktree-migration.md`** (new) — clone-per-persona → worktrees runbook
  (drain clones, verify with `baron status --fetch`, create worktrees, repoint
  manifest + session CLAUDE.md paths, retire clones) with an honest rollback section.
  The live migration of the pilot workspace is deliberately NOT in this release.

### Added — status waivers (from the pilot-triage backlog entry)

- **`.baron-waivers.yaml` + `baron waiver add|list`** (`cli/src/baron/waivers.py`) —
  `{subject (fnmatch on the status SUBJECT column), reason, handoff, expires}`.
  `baron status` downgrades matching reds to warn with `(waived: <reason>)` appended;
  EXPIRED waivers stop matching (the red resurfaces) and are reported as their own
  `expired-waiver` warn; malformed entries are reported, never silently dropped.
  `waiver add` refuses past expiry dates and duplicate patterns.

### Changed — meta

- `plugin.json` + `SKILL.md` frontmatter `1.4.0 → 1.5.0`; `baron-cli` package
  `0.1.0 → 0.2.0`; `STATUS.md`, `README.md`, `cli/README.md`, `docs/BACKLOG.md`
  (waivers entry removed as shipped; remaining M6/merger-preconditions/guard-coverage
  items re-scoped), ADR-003 gains a §5 addendum for the lock/worktree/waiver decisions.
- CLI test suite 36 → 74 tests (guard subprocess tests, fake-forge lock tests, worktree
  fixture, waiver cases).

### Added — baron CLI M1–M3 (Phase 2: conventions → mechanisms, ADR-003)

- **`docs/adr/ADR-003-baron-cli.md`** (accepted 2026-07-22) — the `baron` CLI decisions:
  markdown/git substrate as the only database; typer+pyyaml-only dependency policy (git/gh
  via subprocess); forge Protocol with GitLab-as-plugin backlog (`baron.forges` entry-point
  group); ledger ID allocation via push-retry; archive-not-delete handoff lifecycle.
  Motivations traced to field evidence: three F-number collisions, the 2026-07-22
  triple-stranding incident, markdown LOCK-commit races, 18/40 open handoffs
  (badminton-analyzer), and enforcement theater (GardenTwin audit, operational fidelity 0.53).
- **`cli/`** — the `baron-cli` package (src layout, Python ≥ 3.10, console script `baron`):
  - **M1 `baron validate [PATH]`** — persona.yaml/manifest.yaml validation against
    declarative schemas (`cli/src/baron/schemas.py`) formalized from the prose specs;
    embeds the FROZEN 10-verb capability vocabulary with a drift-guard test that re-parses
    `references/capability-vocab.v1.md`. Checks parse/fields/types/verbs/allow-deny
    overlap/unfilled placeholders; template dirs (`assets/collab-repo/`, `legacy/`) skipped
    on discovery. `--json`; exit 0 clean / 1 errors.
  - **M2 `baron status [--fetch] [--sla N] [--json]`** — divergence & staleness report:
    ahead/behind origin default branch, dirt, unmerged local branches with age, open
    handoffs past SLA, ledger staleness vs code-repo activity (labeled heuristic), stale
    `wiki/status.md`. Acceptance test builds a synthetic topology reproducing the three
    2026-07-22 stranding classes. Exit 0 green / 1 any red.
  - **M3 ledgers & handoffs** — `baron finding new` / `baron decision new` (max-ID parse of
    both heading and table-row forms, push-retry renumbering on rejection, injectable
    clock, `--no-push`); `baron handoff create/close/list` (standard frontmatter; close =
    status flip + `closed:` date + optional note + `git mv` to `_handoff/archive/YYYY/`);
    `baron index` (marker-delimited summary block in `_handoff/README.md` + report-only
    numbering verification). Race acceptance test: two clones allocate the same F-number;
    the rejected writer renumbers and both land.
- **`references/manifest.schema.md` v1.2** — optional `workspace.clones` /
  `workspace.worktrees_root` fields (local persona working copies for `baron status`
  sweeps); commented example block in `manifest.example.yaml`.
- **`docs/BACKLOG.md`** — GitLab forge plugin design sketch (entry-point discovery, same
  Protocol, `forge: gitlab` manifest key) plus consciously deferred M1–M3 items; worktree
  topology tracked as baron M6.
- **CI** — new `baron-cli` job (`uv run --project cli pytest cli/tests`); the stdlib-only
  jobs are untouched.

## [1.4.0] — 2026-07-22

The credibility-debt release: one front door, honest artifacts, real tests, and the
field-proven July-2026 ways-of-working (ADR-002).

### Changed — one front door (legacy path quarantined)

- **`SKILL.md` rewritten as a thin front door** (frontmatter bumped `1.1.0 → 1.4.0`, gains a
  `description:` for skill discovery). All new-project creation and joining routes through
  `assets/collab-repo/START.md` → `ORCHESTRATE.md` / `PARTICIPATE.md`; the legacy modes are a
  one-line pointer.
- **Legacy v0.3 path moved to `legacy/`** at the repo root: `legacy/vault/`,
  `legacy/workspaces/` (the template trees only the legacy modes consume) and
  `legacy/SKILL-v0.3.md` (the three-mode emit instructions, verbatim). `legacy/README.md`
  marks it deprecated/unmaintained, kept for existing v0.x projects.
- **`.claude-plugin/plugin.json`** `1.3.0 → 1.4.0`; description reflects the one-front-door +
  legacy-quarantine reality. Version sync with `SKILL.md` is now lint-enforced.
- **Doc dedup:** the v0→v1 migration story now lives ONLY in ADR-001 + this changelog;
  `README.md`, `SKILL.md`, `CLAUDE.md`, `STATUS.md`, and `docs/LEARNINGS.md` trimmed to
  one-line pointers. `CLAUDE.md`/`STATUS.md` no longer claim "v1.0 shipped / v1.1 candidates"
  as the current state.

### Added — missing/broken artifacts fixed

- **`assets/collab-repo/manifest.example.yaml`** — realistic worked example of the
  `manifest.schema.md` contract (two interactive dev personas + librarian, two-repo pattern).
- **`agents/__DEV__/persona.yaml` is a real template** — was a verbatim copy of the
  `tests/examples/tess` fixture (hardcoded `persona: Tess`); now uses the same
  `{{PLACEHOLDER}}` tokens as its sibling `AGENT.md`.
- **Archetype parity (closes an ADR-001 §10.8 deferred item):** `persona.yaml` templates for
  `librarian`, `__AUTONOMOUS_EVENT__`, and `__AUTONOMOUS_CRON__` alongside their `AGENT.md`s,
  capability sets drawn from the frozen v1 vocabulary. `persona.schema.md`'s "these archetypes
  only exist as legacy AGENT.md templates" caveat replaced with the supported-archetype table.
- **`docs/notes/CORRECTION-wibey-vs-codepuppy.md`** and **`docs/notes/code-puppy-capability-map.md`**
  — reconstructed stubs (originals were cited by `capability-vocab.v1.md` and the code-puppy
  adapter since v1.0 but never committed; marked as reconstructed).

### Added — July-2026 ways-of-working (ADR-002; field-proven on badminton-analyzer)

- **`docs/adr/ADR-002-ways-of-working-2026-07.md`** (accepted 2026-07-22) — decisions + evidence.
- **Emitted `CONVENTIONS.md`:** single-GitHub-account constraint as a stated first principle
  (every gate enforced by persona capability, never GitHub perms); "everything material gets
  a handoff" (findings, decisions, corrections; numbers are proposed to the Librarian, never
  self-assigned); machine-local persona-state convention (`~/.claude/agent-state/` analog +
  snapshot-restore).
- **Emitted `COORDINATION.md`:** Lock pattern is now lock-via-open-PR + `lock:*` labels + a CI
  guard (CODEOWNERS explicitly rejected — no enforcement without branch protection); Owner
  pattern is an evidence gate; new "Review and merge" section (SHA-bound Reviewer verdicts,
  Merger preconditions); persona.yaml CI validation documented.
- **Reviewer + Merger persona archetype templates** (`agents/__REVIEWER__/`,
  `agents/__MERGER__/`, each `persona.yaml` + `AGENT.md`): adversarial fresh-context reviewer
  publishing SHA-bound verdict comments; merger holding the project's only `merge_pr` as a
  precondition gate.
- **Librarian template corrections** (ADR-002 §6): `open_pr` allowed; event-triggered
  reconcile preferred with cron as backstop.

### Changed — real tests + CI

- **Adapters carry a normalized machine-readable capability map** (`capability-map:v1` marker
  in each `adapters/*/HYDRATE.md`): one row per frozen v1 verb — class, runtime-neutral
  grants category, runtime tools, deny-enforcement claim. The claude/code-puppy maps also gain
  rows for `merge_pr`/`push_main`/`force_push`/`edit_other_personas` (needed now that merger
  and librarian archetypes can ALLOW them).
- **`tests/bi_runtime_accept.py` rewritten** — it previously re-implemented the
  capability→tool mapping in Python and tested itself (tautological). It now PARSES the
  actual HYDRATE.md tables + `capability-vocab.v1.md` and asserts: every v1 verb mapped in
  every adapter; tess/rex fixtures hydrate to an equivalent contract across adapters
  (identity, grants, denies, whole-tool denial honoring); enforcement-tier claims consistent
  (generic all-instructed; Tier-3 adapters enforced exactly for whole-tool verbs). Now
  stdlib-only (no PyYAML).
- **`tests/lint_repo.py` (new, stdlib):** unfilled `{{placeholder}}` tokens outside template
  dirs; dead relative markdown links repo-wide; fixture-name leaks ("Tess"/"Rex") in shipped
  templates; plugin.json ↔ SKILL.md version sync.
- **`.github/workflows/ci.yml` (new):** runs both tests with plain python on push + PR.
- **code-puppy adapter worked example** re-anchored to the `tests/examples/tess` fixture and
  de-named (fixture display names no longer appear in shipped templates); its stale v0 verb
  list (`write_findings`/`write_handoff`) corrected to the v1 `write_path` form.
- **`CLAUDE.md` / `CONTRIBUTING.md`** test instructions updated (`uv run --with pyyaml` no
  longer needed).

## [1.3.0] — 2026-06-12

The first-real-audit-feedback release. v1.2.0 shipped the `multi-agent-audit` skill and Iris ran it against GardenTwin within hours; the audit's own write-up identified 13 substantive failures + a missing timeline feature. v1.3 closes all 13 and adds the timeline. Self-validating loop completed in <24h.

### Added — `multi-agent-audit` skill v1.3 (closes all 13 v1.2.0 findings + timeline feature)

#### Multi-substrate Agents lens (Finding #1)

The biggest v1.2 framing flaw was overweighting the `git log` lens for the Agents drift dimension. v1.3 codifies the multi-substrate rule in `references/drift-analysis.md` and `references/bootstrap-adapter.md`:

- **Agents identity** is mined from **five substrates** (GitHub `agent-*` labels, vault `_handoff/` `from:`/`for:` fields, dev-log/EOD/session-log frontmatter, optional persona-prefix commits, and `git log` as a last-resort fallback). Git-log identity collision is the *rule* for single-human multi-agent projects, NOT pathological drift.
- `bootstrap-adapter.md` now ships a per-substrate presence vector + operationally-present threshold.

#### Conv-commits filter (Finding #8)

`scripts/collect_git_metrics.sh` now defaults `CONV_COMMITS_FILTER=1` — Conventional Commits keywords (`feat`/`fix`/`docs`/`chore`/`refactor`/`test`/`ci`/`style`/`perf`/`build`/`revert`) bucket into a new `commits_by_conv_commit_type` field rather than polluting `commits_by_persona_prefix`. New `PERSONA_PREFIXES` env supports an explicit allowlist; everything else goes to `commits_by_other_prefix`. Smoke-tested.

#### Snapshot schema v1.0 → v1.1 — `addenda:` + `auditor_independence:` (Findings #3, #6)

`references/confidence-and-trends.md` defines schema v1.1 (additive — old snapshots still readable):

- **`addenda:` array** on the snapshot is the ONE allowed edit to a shipped point-in-time record. `addenda[*].revised_values` overrides any body field via dot-path; `trend_reader.py` applies them automatically before computing deltas.
- **`audit_run.auditor_independence`** flag captures whether the auditor is itself a participant in the audited project. Renderer surfaces this as a callout banner. Required starting v1.3; surfaces conflict-of-interest in §11 Methodology.

#### Weighted operational-fidelity formula (Finding #12)

`references/metric-taxonomy.md` adds the optional weighted formula. Default per-dimension weights: Guardrails 2.0, Reviewers 1.5, Agents/Autonomy/Routing/Backlog 1.0 each, Rituals 0.5. Equal-weight remains the default; weighted is opt-in.

#### Timeline feature (new — user request)

A new §9.5 Timeline section in the markdown report + horizontal SVG block in the HTML dashboard, surfacing the **important events** in the audit window (releases, ADR creations, roster changes, CONVENTIONS/COORDINATION changes, incidents, audit snapshots, large features).

- **`references/timeline.md`** (new) — event taxonomy, detection rules per type, importance heuristic 1–10, output formats.
- **`scripts/extract_timeline.py`** — detector for 8 event types from a code repo + optional coordination/vault path. Importance scoring with adjacency-aware label staggering. Emits markdown or JSON.
- HTML SVG in `assets/report-template.html`: markers colored by type and sized by importance; week-tick axis; legend; labels for importance ≥7.

#### Five Python helpers — stdlib-only (Findings #4 #5 #9 #10 #11)

- **`scripts/trend_reader.py`** — walks `snapshots/`, applies `addenda[*].revised_values`, computes deltas on the canonical trend metrics, emits §10 Trend markdown OR JSON. Handles single-snapshot, schema mismatch, window-size mismatch gracefully.
- **`scripts/compute_centrality.py`** — Brandes' betweenness centrality on the coordination network (handoffs + optional reviews/merges). SPOF flag at 2.5× mean ratio. **Smoke-test against the vault's handoff graph produced Iris ratio 4.7× — sharper than the v1.2.0 hand-waved 2.1× estimate**, demonstrating the script generates findings the human-driven audit missed.
- **`scripts/parse_coverage.py`** — auto-detects Istanbul / LCOV / Cobertura formats; optional `--baseline` for delta computation; normalized output schema.
- **`scripts/persona_attribution.py`** — joins `agent-*` claim labels → PRs closing those issues → files touched per persona. The v1.3 fix for the v1.2.0 identity-collision finding using the multi-substrate lens.
- **`scripts/extract_timeline.py`** — see Timeline feature above.

#### HTML dashboard renderer (Finding #2 — "HTML dashboard wasn't produced")

- **`scripts/render_report.py`** (new, ~350 lines, stdlib) — fills the template's 18 simple `{{X}}` placeholders + 10 `<!-- INSERT:X -->` block markers; auto-detects template location relative to the script; injects a single JSON `data` object for the Chart.js script block (no inline mustache).
- **`assets/report-template.html` rewritten** — mustache-style loops replaced with INSERT markers (renderer-fillable, no template engine dep). Adds: per-persona scorecards grid, timeline SVG section, auditor-independence callout, false-win callout, addenda card.

#### Short-form executive-summary mode (Finding #13)

- **`references/short-form-mode.md`** — spec + markdown/HTML templates.
- **`scripts/render_short.py`** — stdlib renderer. Markdown: ~1 KB. HTML: ~4 KB (no Chart.js dependency). Applies addenda like the full renderer.

#### Subagent isolation smoke test (Finding #10 — "subagent-isolation test didn't happen")

- **`tests/subagent_isolation_smoke.md`** — runbook for verifying the `project-auditor` subagent's read-only contract. Static checks + manual runtime tests (Edit-injection refusal, destructive-shell refusal, audited-repo-unchanged verification). Honest about tool-enforced vs instruction-enforced layers.
- **`tests/verify_readonly_contract.sh`** — automated static portion: 6 checks (subagent file exists, tools list correct, Edit absent, no destructive `gh api -X` in scripts, no destructive `git`/`gh` in `.sh` code or `.py` subprocess calls, SKILL.md retains read-only language). All 6 pass on the v1.3 skill.

#### Coverage-parser documentation (Batch 2 companion)

- **`references/coverage-parsers.md`** — documents `parse_coverage.py` usage, supported formats, project-type-specific discovery rules, baseline-vs-current workflow, recommended remediation when reports are absent.

### Changed — meta-docs for v1.3

- **`SKILL.md`** — inputs-to-confirm checklist gains independence flag, weighting choice, timeline-yes/no. File inventory updated for the v1.3 layout (scripts/, tests/).
- **`STATUS.md`** — v1.3 marked shipped; v1.4+ candidates updated.
- **`README.md`** — sister-skill section mentions v1.3 enhancements.
- **`.claude-plugin/plugin.json`** — version 1.2.0 → 1.3.0; description mentions short-form mode + timeline feature.
- **`skills/multi-agent-audit/.gitignore` (new)** — prevents accidental `__pycache__/` tracking.

### Validation

The v1.3 skill running on its own coordination substrate (vault handoffs) already produced findings sharper than the v1.2 human-driven audit. Re-audit of GardenTwin with v1.3 is the formal validation step; first opportunity for trend-mode-with-overrides to fire on a real project.

## [1.2.0] — 2026-06-12

### Added — `multi-agent-audit` skill + `project-auditor` subagent (sister skill to `agent-project-bootstrap`)

New skill at `skills/multi-agent-audit/` for grading multi-agent software projects against an evidence-based rubric. Sister to `agent-project-bootstrap`: bootstrap **builds** multi-agent projects; multi-agent-audit **grades** them. **Read-only by construction.** Headline metric: **INTERVENTION TAX** = human touches per autonomous task. Framework-neutral (works on `agent-project-bootstrap`, CrewAI, LangGraph, AutoGen, Copilot agents, custom loops); two-layer (universal WHAT-to-measure + per-layout WHERE-it-lives discovery).

- **`skills/multi-agent-audit/SKILL.md`** (326 lines) — orchestrator: read-only principle, two-layer framework-neutral design, Steps 0/0.5/1/3/4 workflow, inputs-to-confirm checklist, output-location convention (collab-repo `audit/` if exists, else `~/Workspace/audit-reports/`), invocation paths for Claude Code (subagent + direct) and code-puppy (read SKILL.md by path).
- **`agents/project-auditor.md`** — Claude Code subagent. Tool allow-list `Read, Grep, Glob, Bash, Write` (no `Edit`); `Write` only for the report file outside the audited repos. Refuse-to-fix policy explicit ("while you're in there, can you also..." → no).
- **`references/discovery.md`** — Step 0 procedure: declared roster sources (in priority order: `actors.yaml` → `manifest.yaml` → `agents/<name>/persona.yaml` → `AGENT.md` → CONVENTIONS.md), backlog source detection, coordination substrate, autonomy triggers, declared guardrails; layout-family heuristics (bootstrap v1.x / v0.x / vault-project / CrewAI / LangGraph / AutoGen / Copilot / custom); default 90-day window.
- **`references/actor-resolution.md`** — Step 0.5 inventory: enumerate from ALL sources (git committers + PR authors + PR REVIEWERS + mergers + CI bots/Apps + declared roster + coordination substrate); classify `human | autonomous | hybrid`; resolve N identities → 1 canonical actor (persona-prefix wins over email); non-committing-agents special case.
- **`references/drift-analysis.md`** — DUAL-LENS rule (INTENDED | ACTUAL | GAP + confidence) across 7 dimensions (agents / autonomy / reviewers / guardrails / routing / backlog / rituals); the load-bearing **enforced-vs-instructed** distinction; **operational fidelity** formula 0.00–1.00 with four interpretation bands; three drift archetypes (declared-not-operationalized, observed-undeclared, instructed-only-vs-enforced).
- **`references/metric-taxonomy.md`** — 7-category universal metric definitions (Throughput / PR review / Autonomy split + INTERVENTION TAX / Coordination + Network / DORA + flow / Quality + rework / Guardrail + ritual efficacy); per-axis 1–5 scoring rubric; **score-rollup-without-collapse** rule (do NOT compress 7 axes into a single number; name the failure-mode pattern instead).
- **`references/platform-integrations.md`** — read-only gh/git queries for every metric; explicit `gh api` GET-only enumeration; HTTPS-clone rule; pagination/sampling guidance; explicit don'ts (no `-X POST/PUT/PATCH/DELETE`, no `git commit/push/tag/rebase/merge/reset`).
- **`references/advanced-metrics.md`** — DORA four + extensions (merge-gate wait, WIP); network analysis with betweenness centrality + single-point-of-failure heuristic (top centrality > 2.5× mean); review/handoff/merge edge taxonomy.
- **`references/confidence-and-trends.md`** — confidence labels (`measured | inferred | not measurable`); full snapshot JSON v1.0 schema with worked example; trend-mode delta computation; window normalization rules (rate vs count metrics).
- **`references/bootstrap-adapter.md`** — agent-project-bootstrap v1.x layout adapter: exact mining commands for `manifest.yaml`, `agents/<slug>/persona.yaml`, `_handoff/`, `decisions/`, `findings/`, `wiki/`; commit-prefix attribution; enforced-vs-instructed cross-reference table; non-committing-agent reminder (Iris librarian, gh-actions PR review bots).
- **`references/report-template.md`** — markdown audit-report skeleton with 12 sections; placeholders only — every audit fills the same shape.
- **`assets/actors.example.yaml`** — declared-roster template; supports human/hybrid/autonomous classes, identity-resolution rules, declared guardrails, declared rituals, and an explicit `committing: false` marker for non-committing agents.
- **`assets/report-template.html`** — self-contained flat HTML + Chart.js dashboard template (stone/emerald palette matching TrellisIQ brand): verdict card, drift table, headline cards (intervention tax / autonomy donut / DORA / fidelity), per-persona bars, throughput trend, score radar, agent inventory table, ranked-opportunities list, trend section (renders only when ≥2 snapshots exist), methodology + caveats.
- **`scripts/collect_git_metrics.sh`** — read-only bash script that produces machine-readable JSON: commits-by-canonical-actor (persona-prefix honored), reverts/hotfixes/fixups, lines-by-author, cadence (active days), large-commit proxy (≥20 files = `git add -A` heuristic). Refuses to run inside the audited repo (working-directory guard); uses `git -C <repo>` exclusively.

**Status:** scoping → built. v1.2.0 will ship this skill alongside `agent-project-bootstrap`. First intended audit target: **GardenTwin** (real product with longest multi-agent history, especially timely given the 2026-06-10 workforce reduction — a before/after audit will quantify the intervention-tax impact). Distribution: personal use for now.

### Added — v1.0 close-out: §10.2 self-hosting outcome notes + §10.2/§4.6 docs

- **`references/v1-self-hosting-notes.md` (new)** — the comprehensive §10.2 "empirical backbone"
  writeup: which capability verbs surfaced from observed need, where the spec held, where it bent
  (`write_path` collapse, `pull_both_repos`→`sync_repos`, F7/F8), and what was discarded as YAGNI.
  Companion to the short `docs/LEARNINGS.md` index.
- **ADR-001 §4.6** — added a caption clarifying the "Resulting repo shape" diagram is the
  *emitted project's* structure (root `canon/` + `adapters/`), not the skill repo's. Resolves the
  long-standing adapter-location ambiguity.
- **`USING-WITH-CODE-PUPPY.md`** — added a "Vault commit / `/vc` on code-puppy" section (the two
  equivalents: the emitted `/vc-<slug>` command, or describing the workflow in plain language).
  *Reconciled from PR #15, which is now closed.*
- **`STATUS.md`** — v1.0 close-out marked complete (§10.2 + adapter-location done; Step 2 → `[x]`).

## [1.1.1] — 2026-06-08

Documentation-only release. Pulls the user-facing docs (README, `SKILL.md`) forward to the
runtime-agnostic v1.0/v1.1 architecture, adds the required "install canon + adapters" step to
`ORCHESTRATE.md`, and relabels the forward backlog `v1.1+` → `v1.2+` now that v1.1 has shipped.
No behavior or template-logic change.

### Changed — relabel the forward backlog `v1.1+` → `v1.2+` (v1.1 shipped)

- v1.1 is shipped, so the deferred-items backlog is now "v1.2+ candidates" (was the stale
  "v1.1+ candidates"). Updated `STATUS.md` (section heading + 2 internal refs), `CLAUDE.md`
  (versioning note), and `references/persona.schema.md` (the archetype-support pointer). Status
  sync only.

### Changed — reconcile user-facing docs to v1.0/v1.1 (documentation only)

A new-user doc review found the older user-facing layer (README, `SKILL.md`) had not been pulled
forward to the runtime-agnostic architecture. No behavior change — docs/templates only.

- **README** — the *Runtime support* table now shows **Claude Tier 3** (v1.1 enforced subagents),
  not just code-puppy; added a "Two generations — which path to use" section distinguishing the
  runtime-agnostic path (`START`/`ORCHESTRATE`/`PARTICIPATE` + `persona.yaml` + adapters) from the
  legacy v0.3.x emit modes; clarified `/plugin install` (URL or local clone).
- **`SKILL.md`** — bumped frontmatter `0.3.2 → 1.1.0`; **fixed the canonicality banner** (it
  claimed "vault is canonical, repo is a snapshot" — sunset since v1.0; now repo-canonical, matching
  `CLAUDE.md`); added a "Two paths" section so an invoked skill knows the runtime-agnostic
  entrypoints exist; corrected the stale "cron targeted for v0.4.0" note (shipped v0.3.2); updated
  the File manifest to list the v1 canon/adapters/entrypoints.
- **`ORCHESTRATE.md`** — added the required **"Install the canon + adapters into the project"**
  step; the entrypoints/adapters reference `canon/…` and `adapters/<runtime>/…` paths that no emit
  step previously created, which would have left future joiners pointing at missing files.
- **`persona.schema.md`** — added an **Archetype support** note (only `dev` is rendered
  end-to-end by v1 adapters; `autonomous-*`/`librarian` remain legacy `AGENT.md` templates) and
  surfaced the optional `runtime.adapters` override in the example.
- **`STATUS.md`** — added v1.1+ candidates: archetype parity in `persona.yaml`, native code-puppy
  skill packaging; noted `join-collab-project` shares vault-project's re-integration gap.
- **`.claude-plugin/plugin.json`** — modernized the plugin `description` from the v0.3.x
  "Claude Code project / three modes" framing to the runtime-agnostic v1 reality (multi-runtime,
  `persona.yaml` + adapters; legacy modes still listed).

## [1.1.0] — 2026-06-04

The Claude Tier-3 milestone. The Claude adapter now renders native subagents with an enforced
tool allow-list, plus the v1.0 close-out work. First properly cut release since v0.3.2
(plugin.json bumped 0.3.2 → 1.1.0; forward-only — the partial v1.0.0/v1.0.1 tags are left as-is).

### Added — `USING-WITH-CODE-PUPPY.md` quickstart

- New top-level guide for running the bootstrap on code-puppy, which does not auto-discover the
  Claude skill format. Documents the invoke-by-file-path flow (START → ORCHESTRATE → code-puppy
  adapter), the launch-from-project-root requirement, a verified file map, and the Tier-3
  enforcement note. README links to it from the Installation section.

### Added — Claude Tier-3 subagent rendering (ADR-001 §10.8; v1.1 feature)

- **`adapters/claude/HYDRATE.md` now renders BOTH tiers from one configurable adapter** (not
  two folders):
  - **Tier 3 (new)** — hydrates a persona into a native Claude **subagent** at
    `.claude/agents/<slug>.md` with an **enforced** `tools:` allow-list. Whole-tool denials
    become real (a read-only persona gets `Read, Grep, Glob` only; `Write`/`Edit`/`Bash` are
    absent and unavailable). Sub-tool denials (e.g. allow `open_pr`, deny `merge_pr`) stay
    instruction-only in the body — same honesty boundary the code-puppy adapter documents.
  - **Tier 2** — unchanged `CLAUDE.md` rendering (capabilities instructed).
  - Capability → Claude tool mapping for the enforced layer: `read_*`→`Read,Grep,Glob`;
    `write_code`/`write_path`→`Write,Edit`; `open_pr`/`run_tests`→`Bash`.
- **Tier selection via a runtime-neutral `adapters.<runtime>` config envelope** (keeps the
  canonical schemas free of runtime tool names):
  - `manifest.adapters.claude.tier` — project default (`auto` | `2` | `3`, default `auto`).
  - `persona.yaml > runtime.adapters.claude.tier` — per-persona override.
  - `auto` self-assesses subagent support and degrades to Tier 2 when the session can't host
    subagents (CI / constrained sub-sessions). Explicit `2`/`3` always wins.
- **Schemas** (`manifest.schema.md`, `persona.schema.md`) gain the optional `adapters.<runtime>`
  / `runtime.adapters.<runtime>` override envelope (v1.1; additive, forward-compatible).
- **`tests/bi_runtime_accept.py`** extended: the same harness now asserts code-puppy (Tier 3) ≡
  Claude Tier 2 ≡ Claude Tier 3 produce an identical behavior contract — not a second
  top-level test. Both fixtures (dev `tess`, read-only `rex`) pass.
- **ADR-001** §10.5 / §10.8 updated (Tier-3 shipped; config-location rationale recorded).

### Fixed — correct the bi-runtime test invocation in docs

- The documented command `python tests/bi_runtime_accept.py` fails with `ModuleNotFoundError:
  yaml` on a stock interpreter. Corrected `CLAUDE.md` (release workflow + Testing section) and
  `CONTRIBUTING.md` to `uv run --with pyyaml python tests/bi_runtime_accept.py`, matching the
  harness's own dependency need.
- Fixed the harness docstring, which still pointed at the pre-move path
  `wip/acceptance/bi_runtime_accept.py`, to the current `tests/bi_runtime_accept.py`.

### Added — `docs/LEARNINGS.md` (minimum-viable lessons index)

- **`docs/LEARNINGS.md` (new)** captures the ADR-001 §10 dogfood lessons (`L1`–`L3`) and proven
  rules (`Proven #1`–`#2`). Resolves four previously dangling references — in
  `references/capability-vocab.v1.md` (proven #2, L3), `adapters/claude/HYDRATE.md` (L3), and
  `adapters/generic/HYDRATE.md` (L3). Minimum-viable by design; the comprehensive §10.2
  self-hosting outcome notes remain a tracked v1.0 close-out item in `STATUS.md`.

### Changed — de-Claude the emitted `COORDINATION.md` (ADR §10.6, finishes Step 6)

- Removed the three runtime-isms from the emitted `COORDINATION.md` template, mirroring PR #7's
  treatment of `CONVENTIONS.md`:
  - **Session-start checklist** — replaced the `git pull` / `grep` / `gh issue list` bash blocks
    with intent-level steps that point at `adapters/<runtime>/HYDRATE.md` for concrete syntax and
    `references/capability-vocab.v1.md` for the verbs.
  - **Ticket lifecycle** — abstracted the `gh issue edit … --add-assignee/--add-label`
    self-assignment to backlog-source language (`gh` is one runtime's shell, not the canon).
  - **Async handoff protocol** — generalized the Iris-specific "personal librarian" paragraph to
    any librarian-equivalent persona (`for: librarian`), and dropped the Obsidian-specific "vault"
    wording. Runtime-neutral, matching the canon. Cosmetic for existing scaffolds (no behavior
    change).

### Changed — meta-docs refresh for v1.0 development surface

- **`CLAUDE.md` rewritten** to reflect the post-ADR-001 reality: this repo is the canonical home and active development surface for v1.0+; the v0.x "vault canonical, repo snapshot" rule is sunset. Updates repo layout, persona expectation for a fresh agent landing in the repo, and release workflow.
- **`STATUS.md` (new)** at repo root tracks ADR-001 §10 progress (most of v1.0 shipped; `COORDINATION.md` de-Claude + §10.2 self-hosting outcome notes still open) and v1.1 candidates (Claude Tier-3 subagents, vault-project re-integration, cron live-wiring, additional adapters). Update on every PR that ships a step.
- **ADR-001 body header** corrected: `Status: Proposed` → `Status: Accepted (2026-05-30)`. Frontmatter already said accepted; this fixes the internal inconsistency.
- **`CONTRIBUTING.md`** adds a **"Documentation is part of every PR"** section codifying the rule that affected ADRs, `CLAUDE.md`, `README.md`, `CHANGELOG.md`, and `STATUS.md` updates land in the same PR as the code change — never as a follow-up. Surfaces explicit checklist + cosmetic-changes exception. Also notes the `uv run --with pyyaml python tests/bi_runtime_accept.py` gate for adapter / spec / canonical-contract changes.

## [1.0.1] — 2026-06-03

### Changed — README reflects the v1.0 runtime-agnostic architecture

- Rewrote the intro (no longer "a Claude Code plugin" only) and added a **Runtime support**
  section documenting the capability ladder, adapters, neutral entrypoints, and the canonical
  spec files. Points to ADR-001. Docs-only; no behavior change.

## [1.0.0] — 2026-06-03

### Added — runtime-agnostic spec + adapters (ADR-001 implementation, v1.0)

Implements ADR-001 (§10 phased rollout). The bootstrap pattern is no longer Claude-only: a
single runtime-neutral `persona.yaml` hydrates working personas on any runtime, at the highest
fidelity that runtime supports. Every capability verb and schema field was coined during real
adapter work and exercised on a real dogfood project (55%→100% coverage) — nothing speculative
(YAGNI).

- **Neutral entrypoints** in `assets/collab-repo/`:
  - `START.md` — front door; routes on directory state + documents runtime keys (§7.3).
  - `ORCHESTRATE.md` — Role 1 (bootstrap a new project), runtime-neutral.
  - `PARTICIPATE.md` — Role 2 (join a project) + the 3-tier capability ladder.
- **Adapters** in `assets/collab-repo/adapters/<runtime>/HYDRATE.md` (the only runtime-specific
  surface; Open/Closed for runtimes):
  - `generic/` — Tier-1 fallback (MANDATORY): re-read `persona.yaml` each turn, self-enforce.
  - `code-puppy/` — Tier-3: maps capabilities to enforced JSON sub-agent tool allow-lists.
  - `claude/` — Tier-2: renders `persona.yaml` → `CLAUDE.md` + `/vc`, mirroring v0.3.x shape.
- **Canonical spec docs** in `references/`: `capability-vocab.v1.md` (frozen 10-verb API),
  `persona.schema.md`, `manifest.schema.md` (relative paths + configurable backlog source).
- **`agents/__DEV__/persona.yaml`** — machine-truth companion to the existing `__DEV__/AGENT.md`
  (yaml canonical, md derived).
- **`tests/bi_runtime_accept.py`** — bi-runtime acceptance harness: proves one `persona.yaml`
  yields an identical behavior contract (identity, capabilities, guardrails) on code-puppy +
  Claude. Passes for both a `dev` and a read-only `reviewer` persona.

### Compatibility

- Purely additive. Existing v0.3.x scaffolds and invocations are unaffected.
- Claude native sub-agents (Tier-3 at home) deferred to a follow-up (ADR §10.8).

### Changed — de-Claude the emitted `CONVENTIONS.md` (ADR §10.6)

- Replaced the "Tool hierarchy" section's runtime tool names (`Read`/`Write`/`Edit`/`Bash`,
  `gh` CLI) and the Obsidian/MCP note with capability-level language + a pointer to
  `adapters/<runtime>/HYDRATE.md` and `references/capability-vocab.v1.md`. The emitted
  convention doc is now runtime-neutral, matching the canon. Additive/cosmetic for existing
  scaffolds (no behavior change).

## [0.3.2] — 2026-05-29

Same-day follow-up to v0.3.1, closing out the remaining items from an early
bootstrap-genesis decision (now superseded by [ADR-001](docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md)). All v0.3.1 invocations still work unchanged.

### Added — runtime-aware cron + FAILOVER templating

- **`runtime:` taxonomy** for AGENT.md frontmatter, replacing the older `schedule-skill` / `github-actions` strings. Supported values:
  - `launchd-cron` — macOS launchd; per-runner machine; laptop must be on.
  - `systemd-timer` — Linux systemd timer; per-runner machine; laptop must be on.
  - `cloud-routine` — Anthropic-hosted `/schedule` routine; always-on.
  - `gh-actions-cron` — GitHub Actions scheduled workflow; always-on.
  - `gh-actions-event` — GitHub Actions on PR / event webhook (for `__AUTONOMOUS_EVENT__` personas).
  Each AGENT.md template now carries a comment block documenting the taxonomy inline.
- **Per-runtime FAILOVER cron section snippets** under `assets/collab-repo/_failover-cron-sections/`:
  - `launchd-cron.md` — generated wrapper + plist; `launchctl bootstrap` / `bootout` commands.
  - `systemd-timer.md` — generated `.service` + `.timer`; `systemctl --user` lifecycle.
  - `cloud-routine.md` — `/schedule` invocation; per-account billing notes.
  - `gh-actions-cron.md` — workflow file pattern; PAT secret requirements.
  The skill picks the right snippet at scaffold time based on the persona's `runtime:` field and substitutes it into the templated `agents/<persona>/FAILOVER.md`'s `{{FAILOVER_CRON_SECTION}}` placeholder.
- **`workspace-template/setup.sh` gains opt-in cron stub generation** behind `REGISTER_CRON=yes`:
  - `launchd-cron` → generates `~/Workspace/<project>/<persona>/com.<project>.<persona>.plist` + wrapper script. Stub is generated, NOT loaded; you load it manually via `launchctl bootstrap` after reviewing the schedule. Idempotent (skips if plist already exists).
  - `systemd-timer` → generates `.service` + `.timer` + wrapper. Same opt-in-load pattern.
  - `cloud-routine` → prints the `/schedule` command to run in Claude Code.
  - `gh-actions-*` → no-op locally (cron lives in the code repo workflow).
  Generation happens only when `REGISTER_CRON=yes` is set; default behavior is workspace-only.

### Changed

- **`agents/librarian/FAILOVER.md`** "Enable the cron on your machine" section is now `{{FAILOVER_CRON_SECTION}}` (per-runtime). The skill fills it from the matching `_failover-cron-sections/*.md` snippet.
- **`agents/__AUTONOMOUS_EVENT__/AGENT.md`** frontmatter `runtime` field is now `gh-actions-event` (was `github-actions`).

### Compatibility

- v0.3.1 invocations work unchanged. Existing collab repos do not need to migrate.
- The old `runtime: schedule-skill` and `runtime: github-actions` values still parse — the new taxonomy is additive.

### Why generation but not auto-load

Cron registration is the kind of action where "almost right" is much worse than "explicitly opt-in." DST drift, double-registration across two laptops, accidental cron-from-the-wrong-runner — these are real failure modes. The stub-and-load split makes the dangerous step explicit and human-reviewed. Auto-load may land in a later release once we've gathered usage data on whether the explicit step actually catches errors in practice.

### Validated against

VANAR's launchd-cron pilot (Vikram's machine, daily 15:00 PT). The generated plist + wrapper produced by v0.3.2's `setup.sh REGISTER_CRON=yes` matches VANAR's hand-rolled artifacts byte-for-byte (modulo the manual TODO timestamp adjustment).

## [0.3.1] — 2026-05-29

Patch release codifying lessons from VANAR's pilot day (first real use of v0.3.0). All additions are template content; no interface changes. v0.3.0 invocations still work unchanged.

### Added — `collab-repo-project` mode emissions

- **`QUICKSTART.md`** — agent-led onboarding doc as a first-class artifact. Contains the canonical "Onboard me to {{PROJECT_NAME}}" prompt that human collaborators paste into Claude Code / code-puppy / their AI coding agent. ~30 min to first PR vs. ~45 min for the manual BOOTSTRAP.md path.
- **`wiki/log.md`** — genesis log entry seeded at scaffold time. Establishes the `find -newer wiki/log.md` timestamp baseline so the Librarian's first cron run isn't a silent no-op.
- **`wiki/index.md`** — standard catalog scaffold (log, entities, concepts, sources sections with placeholder descriptions).
- **`_handoff/{{DATE}}-bootstrap-to-librarian-genesis.md`** — one-time genesis handoff for the Librarian. Acknowledges the wiki has been seeded; first run flips it to `status: done` and the standard cycle takes over.
- **`workspace-template/{CLAUDE.md, AGENTS.md, setup.sh}`** — runtime-portable workspace bootstrap. `setup.sh <persona-slug>` clones both repos into `~/Workspace/{{PROJECT_NAME}}/<slug>/`, configures per-repo git identity, and drops the thin CLAUDE.md (Claude Code) + AGENTS.md (code-puppy and similar) pointers. Cron self-registration deferred to v0.4.0.

### Added — template content updates

- **CONVENTIONS.md `_handoff/` lifecycle:** new "Push policy" paragraph carving out `_handoff/` files as direct-push-permitted on `main` (they're coordination metadata, not substantive changes). Resolves a doc-fork that surfaced when persona AGENT.md "PR only" rules clashed with BOOTSTRAP "push origin main" guidance for the joined handoff.
- **BOOTSTRAP.md Step 3 (rewritten):** consolidated "fire up your VANAR workspace" with the new `~/Workspace/{{PROJECT_NAME}}/<your-slug>/` folder pattern (both repos in one folder) + an optional AI-agent bootstrap sub-section (CLAUDE.md / AGENTS.md template for Claude Code / code-puppy users).
- **BOOTSTRAP.md Step 6 (new):** "Announce yourself to the Librarian" — the joined collaborator drops a `_handoff/` so the Librarian picks them up on the next run and updates the wiki personas page.
- **Root `CLAUDE.md`:** `QUICKSTART.md` promoted to item 1 in "Read these first" (fast path); `BOOTSTRAP.md` becomes item 2 (deeper reference).
- **`agents/__DEV__/AGENT.md`:** optional two-clone note for project owner — owners often have a "library copy" clone (used by their personal Iris) separate from their dev working copy. Conditionally rendered.
- **`agents/__AUTONOMOUS_CRON__/AGENT.md`** + **`agents/__AUTONOMOUS_EVENT__/AGENT.md`:** new "First-run handling" section telling the persona to look for and process a `_handoff/*-bootstrap-to-*-genesis.md` file before its standard cycle.
- **`agents/librarian/AGENT.md`:** new "Drift checks" section listing concrete things to compare across files (AGENT.md frontmatter `runtime:` vs FAILOVER.md cron section; AGENT.md scope vs CONVENTIONS routing table; AGENT.md cadence vs actual cron file). Librarian surfaces drift; never auto-fixes.

### Compatibility

- v0.3.0 invocations work without changes. Existing collab repos do not need to migrate; v0.3.1 only affects new scaffolds.
- The `mode:collab-repo-project` artifact set is now ~24 files (was 20 in v0.3.0).

### Validated against

VANAR (first project to use the collab-repo-project mode). All v0.3.1 additions were hand-rolled into VANAR's collab repo during 2026-05-29 and validated by the Librarian (Vidya) successfully processing the manual genesis handoff and surfacing drift on her first scheduled cron run.

## [0.3.0] — 2026-05-29

### Added

- **Multi-mode dispatch.** SKILL.md restructured around three modes selected at invocation:
  - `vault-project` — original v0.2.0 behaviour (vault-based five-agent project scaffold), preserved verbatim.
  - `collab-repo-project` — emits a dedicated collab repo for projects with remote collaborators. Implements the "Option A" pattern: collab substrate (conventions, coordination, agent manuals, handoffs, decisions, findings, project wiki) lives in its own GitHub repo, separable from any personal vault.
  - `join-collab-project` — walks a human remote collaborator through cloning an existing collab repo, claiming a persona, setting per-repo git identity, and validating the round trip with a "hello" PR.
- **`assets/collab-repo/` template tree** (16 new files) for the `collab-repo-project` mode:
  - Root: `README.md`, `CONVENTIONS.md`, `COORDINATION.md` (with `## Hot files` section), `CLAUDE.md`, `BOOTSTRAP.md` (collaborator-facing), `BOOTSTRAP-ADMIN.md` (owner-only operations including optional trust-gating).
  - `agents/__DEV__/AGENT.md` — human dev persona template (workspace path, session-start ritual, ADR rules).
  - `agents/__AUTONOMOUS_EVENT__/AGENT.md` — webhook-triggered autonomous persona template (e.g. PR Reviewer, Backtest Runner). Cost ceilings, decision authority, hot-file flagging.
  - `agents/__AUTONOMOUS_CRON__/AGENT.md` — `/schedule`-triggered autonomous persona template (e.g. PM+UAT). Cadence, default runner, failover.
  - `agents/librarian/AGENT.md` + `agents/librarian/FAILOVER.md` — always emitted by default; centralized-with-failover model documented.
  - Subfolder stubs with READMEs: `_handoff/`, `decisions/`, `findings/`, `wiki/`.
- **New reference doc:** `references/collab-repo-design.md` — rationale for the collab-repo-project mode design choices (why a separate repo, why three persona archetypes, why centralized-with-failover librarian, why optional trust-gating, etc.).

### Changed

- `SKILL.md` is no longer a single emit sequence. It's now a dispatcher that documents mode selection, then provides three self-contained mode-specific emit sections. The `vault-project` section preserves v0.2.0 behaviour unchanged — existing usage is unaffected.
- File manifest updated to reflect the new asset tree.

### Compatibility

- v0.2.0 invocations (vault-project mode) work without changes. Existing users do not need to migrate.
- The `mode:` parameter is the new entry point. If unspecified, the skill prompts for mode selection.

## [0.2.0] — 2026-05-27

### Added
- New asset: `assets/commands/vc.md` — the `/vc` slash command for vault commits. Installed to `~/.claude/commands/vc.md` (user-global), available to every Claude Code session. Workflow: check vault state, stage thoughtfully (never `git add -A`), compose a commit message using the canonical `<persona>: <operation> | <description>` convention, commit, push, and verify the push against GitHub. Uses `{{VAULT_PATH}}` placeholder; derives the vault GitHub repo from `git remote get-url origin` so no new placeholder is required.
- SKILL.md: new emit step `3a` documenting the commands copy step; file manifest updated.
- README.md: new "Slash commands" section under *What gets generated*.

## [0.1.1] — 2026-05-22

### Added
- Workspace context files: `CLAUDE.md` (repo orientation + sync rules), `CHANGELOG.md`, `CONTRIBUTING.md`.
- Sync rule documented: vault is canonical, this repo is a release snapshot.

## [0.1.0] — 2026-05-22

### Added
- Initial release of the `agent-project-bootstrap` skill.
- Vault scaffolding templates, workspace scaffolding templates, reference docs.
