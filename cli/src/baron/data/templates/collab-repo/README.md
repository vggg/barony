# {{PROJECT_NAME}} — Collaboration Repo

{{PROJECT_DESCRIPTION}}

This is the collaboration substrate for {{PROJECT_NAME}}. It holds:
- Project rules and protocols (`CONVENTIONS.md`, `COORDINATION.md`)
- Operating manuals for every persona on the team (`agents/<persona>/AGENT.md`)
- Cross-persona async messages (`_handoff/`)
- Project-level decisions (`decisions/`)
- Findings, UAT reports, research outputs (`findings/`)
- The project's own wiki, synthesised by the Librarian (`wiki/`)

The *code* for {{PROJECT_NAME}} lives at [`{{CODE_REPO}}`](https://github.com/{{CODE_REPO}}). This repo holds everything else.

## New here?

Read [`BOOTSTRAP.md`](BOOTSTRAP.md) end-to-end. It walks you through claiming a persona, setting your git identity, and opening your first PR to validate the round trip.

## Project owner?

See [`BOOTSTRAP-ADMIN.md`](BOOTSTRAP-ADMIN.md) for owner-only operations (trust-gating, persona management, label setup).

## How this fits

- **Code repo (`{{CODE_REPO}}`)** owns: the actual application, PR/issue work state, code review, merge history.
- **This collab repo (`{{COLLAB_REPO}}`)** owns: persona manuals, project rules, async coordination, decisions, findings, the project wiki.
- **The Librarian** synthesises activity in this repo into the `wiki/` folder. Read `wiki/log.md` for "what's happening lately."
