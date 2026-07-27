"""baron — the Barony collab-repo CLI (Phase 2: conventions -> mechanisms).

Design principle (ADR-003): the markdown/git substrate IS the database. baron is a
disciplined reader/writer over the same human-legible files the personas use
(manifest.yaml, persona.yaml, findings/index.md, decisions/index.md, _handoff/*.md,
wiki/status.md). It never introduces another store, and every file it writes stays
fully human/agent-legible.
"""

__version__ = "0.4.0"
