"""Access to the vendored collab-repo templates (``baron init``'s emit source).

The canonical templates live in the skill — ``skills/barony/assets/collab-repo/``
plus the four canon references — where the Claude plugin reads them in place. A
pip-installed baron has no repo checkout, so the same files ship as package
data under ``data/templates/`` (ADR-006), vendored by
``cli/scripts/sync_templates.py`` and drift-guarded by
``cli/tests/test_template_sync.py``: the two trees must stay byte-identical.
"""

from __future__ import annotations

from importlib.resources import files

TEMPLATES_RESOURCE = "data/templates"


class TemplateError(RuntimeError):
    """A packaged template is missing (broken install or vendoring)."""


def template_root():  # -> importlib.resources Traversable (3.10-compatible: untyped)
    return files("baron").joinpath(TEMPLATES_RESOURCE)


def read_template(rel: str) -> str:
    """Read one packaged template by path relative to ``data/templates/``
    (e.g. ``collab-repo/CONVENTIONS.md``, ``references/persona.schema.md``)."""
    resource = template_root().joinpath(rel)
    try:
        return resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise TemplateError(
            f"packaged template missing: {rel} — broken install, or the vendored "
            "tree is stale (python cli/scripts/sync_templates.py)"
        ) from exc
