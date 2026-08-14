---
created: 2026-08-13
type: decision
status: accepted
accepted: 2026-08-13
adr: 026
project: barony
authors: Atlas (design proposal for Vikram)
decided_by: Vikram
related:
  - "[[docs/adr/ADR-007-session-boundary]]"
  - "[[docs/adr/ADR-010-baron-notify-wake]]"
  - "[[docs/adr/ADR-024-fleet-health]]"
---

# ADR-026 (ACCEPTED): the persona sidecar — a persona as a deployable unit

> **§6 Q4 is SUPERSEDED by [ADR-027](ADR-027-agent-identity.md) (2026-08-14)** — the
> "deferred per-persona signing keys" it pointed at are now specified and built.
>
> **ACCEPTED 2026-08-13 (Vikram) — §6 answered as recommended:** launcher first (emit
> `agents/<slug>/sidecar.sh` + a `baron sidecar` subcommand), loop configurable per persona,
> containerise once a fleet needs laptop-off durability, identity via the deferred per-persona signing
> keys, ephemeral-vs-long-running as a manifest field. Generalises the badminton `fleet-runner` into an
> emitted, portable deployment unit.

## 1. Problem

Deploying a fleet today is bespoke: baron is a shared CLI + repo files, the runtime (`claude -p`, …)
is separate, and the launcher is a hand-written `fleet-runner/` launchd job on one machine. There is
no **turnkey per-persona deployable** — nothing you can `docker run` (or `./run reviewer`) to bring one
persona online, self-coordinating through the collab repo. That gap is what keeps autonomous fleets
"works on the author's laptop" rather than reproducible.

## 2. Decision (proposed)

Package a persona as a **sidecar**: one deployable unit bundling

    [ baron CLI ] + [ the emitted runtime kit: agents/<slug>/runtime/ ] + [ a work loop ]

The **work loop** is either notify-driven (sweep `_handoff`/mailbox on a `repository_dispatch` wake,
ADR-010) or scheduled (a cron sweep, the fleet-runner pattern). The **collab repo is the shared state**:
the sidecar clones/pulls, reads its addressed handoffs, does a unit of work, pushes, and either exits
(ephemeral) or waits for the next signal (long-running, ADR-026 pairs with the Q2 "persistent but
stateless-per-task" model). Two form factors, same contract:

- **now — a launcher.** `baron sidecar run <persona> --collab <repo>` (or an emitted
  `agents/<slug>/sidecar.sh`) wrapping the runtime kit + loop. This is the fleet-runner, generalised
  and emitted by `baron init` instead of hand-written.
- **later — a container.** `baron init` emits a per-persona `Dockerfile` / compose service so a persona
  is a **pod**: the collab repo is the shared state, scale replicas, run anywhere. Cloud-native without
  a broker or database — git is the bus.

## 3. Why it fits (the building blocks already exist)

- The CLI is **pip-installable** (`barony` on PyPI).
- `baron init` **already emits a per-persona runtime kit** (`agents/<slug>/runtime/` with `CLAUDE.md`,
  `.claude/settings.json`, README) — the persona half of a sidecar is already generated.
- `baron notify` is the **wake signal**; the fleet-runner is the **MVP of the loop**.
So the sidecar is an assembly + packaging layer over parts baron already ships, not new machinery.

## 4. Boundary (ADR-007)

The sidecar **runs** the runtime and its loop; baron still does not own the agent loop — it emits the
kit, fires the signal, and provides the coordination substrate the loop reads/writes. A long-running
sidecar must stay **stateless per task** (re-read git as truth each cycle) or it forfeits baron's
audit-by-diff guarantee.

## 5. Evidence / relation

First-party: the badminton `fleet-runner/` (launchd + headless `claude -p` + GitHub Actions) is this
pattern, hand-built and running. Generalising it is the **Workstream-D observability/ops anchor**, and
it composes with ADR-010 (notify = the sidecar's wake) and ADR-024 (`baron health` measures the fleet
the sidecars run).

## 6. §6 — Owner decisions (not self-decided)

1. **Surface:** a `baron sidecar` subcommand, an emitted `agents/<slug>/sidecar.sh`, or both?
2. **Loop default:** notify-driven, cron, or configurable per persona?
3. **Container timing:** emit the Dockerfile now, or ship the launcher first and containerise once a
   fleet needs laptop-off durability? (Recommend: launcher first — it's the cheap proof.)
4. **Identity/credentials:** how does a sidecar get its per-persona git identity + runtime credential
   (ties to the deferred per-persona signing keys)?
   > **SUPERSEDED by [ADR-027](ADR-027-agent-identity.md) (2026-08-14).** The signing keys are no
   > longer deferred and no longer unspecified: per-persona SSH keys, generated at spawn, enrolled
   > once into `.barony/allowed_signers`, verified offline. A sidecar gets its identity by running
   > `baron identity init`, which refuses to let the persona work until the key is enrolled. No
   > per-persona *forge* credential is introduced — agents still push under the owner's identity.
5. **Ephemeral vs. long-running** per persona (pairs with the Q2 decision): a manifest field?
