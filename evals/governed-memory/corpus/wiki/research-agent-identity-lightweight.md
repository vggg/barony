---
created: 2026-08-04
type: research
status: draft
project: demo
---

# Lightweight verifiable agent identity at spawn — options survey

> **This file is deliberately outside the four governed corpora.** `baron export`
> walks ADRs, decisions, findings and handoffs; `wiki/` is not one of them. It is
> in the fixture set to measure the **corpus ceiling** — the recall no retrieval
> strategy can reach, because the document is not in the index at all.

**Question.** What can an agent do automatically at startup, before it is allowed
to do any work, to obtain an identity a third party can later prove it used?

**Trigger.** An un-onboarded agent committed to `main` under the owner's git
identity. Unattributable from the repository alone.

## Verdict

Per-persona SSH signing keys, generated at spawn, enrolled once into an in-repo
`allowed_signers` file, verified offline with `git verify-commit`.

## Why not personal access tokens

Personal access tokens (PATs) authenticate an API caller to a forge; they do not
attest authorship of an artifact. A PAT held by a persona says nothing verifiable
about who wrote a commit once the commit is on disk, and a stranger with a clone
and no forge access can check nothing at all. PATs are also bearer secrets with a
rotation cost per persona, and the forge's own audit log — not the repository —
becomes the only place the answer lives.

## The honest caveat

Key generation is free; key enrolment is not self-authenticating. An agent that
mints its own key and adds itself to the signers file has proved nothing. The
enrolment gate must sit outside the agent's control.
