"""baron — the Barony collab-repo CLI (Phase 2: conventions -> mechanisms).

Design principle (ADR-003): the markdown/git substrate IS the database. baron is a
disciplined reader/writer over the same human-legible files the personas use
(manifest.yaml, persona.yaml, findings/index.md, decisions/index.md, _handoff/*.md,
wiki/status.md). It never introduces another store, and every file it writes stays
fully human/agent-legible.
"""

# Derive from installed package metadata so the constant, `baron --version`, and
# pyproject.toml can never drift (they did: the constant sat at 0.4.0 while the
# package shipped 0.5.1). Falls back only for an uninstalled source tree.
from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("barony")
except PackageNotFoundError:  # pragma: no cover - source-tree-without-install only
    __version__ = "0.0.0+source"
