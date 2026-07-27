# PARTICIPATE — Role 2: Join an existing project (runtime-neutral)

> Recipe for an agent JOINING an already-bootstrapped project as a persona. Runtime-neutral;
> perform concrete actions via `adapters/<runtime>/HYDRATE.md`. Includes the capability ladder
> so any runtime — smart or dumb — can participate correctly.

## Steps

### 1. Locate the project + your persona
- Read `manifest.yaml`; find your persona entry and its `spec` (`agents/<slug>/persona.yaml`).
- Read `CONVENTIONS.md` + `COORDINATION.md`.

### 2. Hydrate yourself via the capability ladder
Pick the HIGHEST tier your runtime supports. Lower tiers always work (graceful degradation).

| Tier | Runtime can... | How you participate |
|---|---|---|
| **3 — native agents** | register sub-agents with an enforced tool allow-list | Adapter emits a persona agent file (see that runtime's adapter). Whole-tool denials are ENFORCED; sub-tool denials are instructed. |
| **2 — session context** | hold a persistent system prompt / context file | Adapter writes the persona into the runtime's session context file (see that runtime's adapter). Capabilities are instructed. |
| **1 — in-prompt (generic)** | only follow instructions each turn | Read `persona.yaml` every turn; self-enforce allow/deny; follow the ritual manually. Always works. |

> Enforcement honesty (from the spike): even at Tier 3, only WHOLE-TOOL denials are hard.
> Sub-tool denials (e.g. allow `open_pr` but deny `merge_pr`) are instruction-based at every
> tier. They still deliver real value (proven in Phase 2 — the "never git add -A" catch).

### 3. Run the session-start ritual
Execute `persona.yaml > session_ritual` in order, resolving intent tokens via the manifest:
- `sync_repos` → update every repo in `manifest.repos` (relative paths).
- `read_conventions` → read collab `CONVENTIONS.md` + `COORDINATION.md`.
- `check_handoffs` → find open `_handoff/` items for you or `all`.
- `check_backlog` → read `manifest.backlog` (file or tracker).

### 4. Do the work, within your capabilities
- Claim a backlog item; branch; work; report to `findings/`.
- Honor `capabilities.deny` ALWAYS, regardless of whether your runtime enforces it.
- Commit via the `/vc-<slug>` analog (never `git add -A`; correct git identity + prefix).
- Open a PR for substantive changes; `_handoff/` may be direct-pushed per CONVENTIONS.

### 5. Hand off + close
- Drop a `_handoff/` if another persona is needed.
- Update the backlog item's status; record outcomes.

## The golden rule

If in doubt about a capability, **deny yourself** and drop a `_handoff/` for the owner. Acting
outside your declared scope is the one thing no tier permits.
