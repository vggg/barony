# Demo — decisions index

### D1 — Collab repo and code repo stay separate (2026-07-02, Vikram)

Signed as ADR-001.

### D2 — Handoff priority becomes a required field (2026-07-28, Vikram)

Signed as ADR-005. Supersedes the prose-priority arrangement recorded in D-less
form under ADR-002.

### D3 — Telemetry transport is parked, not rejected (2026-08-03, Vikram)

Branch kept as history. See ADR-004.

### D4 — Ship v1.8.0 without the sink default resolved (2026-08-06, Vikram)

The release goes out with sinks off. ADR-003 stays proposed.

### D5 — Agent identity is worth an ADR, not a backlog item (2026-08-05, Vikram)

F4 is not a bug report, it is a hole in the thesis. Commissioned the options
spike and asked for a decision record rather than a fix.

### D6 — Correct D4: the sink default is `null` by signed decision, not by accident (2026-08-10, Vikram)

D4 shipped a default nobody had signed. Recording it now: `null` is the chosen
default, and a default nobody signed and a default somebody signed look identical
in a diff.
