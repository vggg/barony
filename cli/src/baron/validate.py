"""M1 — ``baron validate``: validate persona.yaml / manifest.yaml files.

Template rule (documented, per repo CI convention): files whose repo path
contains a template marker directory (``assets/collab-repo/`` or ``legacy/``)
legitimately carry ``{{PLACEHOLDER}}`` tokens and often don't parse as YAML at
all — **discovery skips them entirely** (reported as skipped, never failing).
An explicitly named single file is always validated. Fixture paths
(``tests/examples/``) are validated but exempt from the placeholder check only
(they carry ``{{IDENTITY_DOMAIN}}`` by design).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import yaml

from . import drift
from .schemas import (
    CAPABILITY_VERBS,
    MANIFEST_SPEC,
    PARAMETRIC_VERBS,
    PERSONA_SPEC,
    Node,
)

#: Discovery skips paths containing these markers (emit-time templates —
#: the skill's assets, the deprecated legacy tree, and baron's own vendored
#: copy of the templates, ADR-006).
TEMPLATE_SKIP_MARKERS: tuple[str, ...] = (
    "assets/collab-repo/",
    "legacy/",
    "baron/data/templates/",
)
#: The placeholder check is additionally waived for fixture paths.
PLACEHOLDER_EXEMPT_MARKERS: tuple[str, ...] = TEMPLATE_SKIP_MARKERS + ("tests/examples/",)

PLACEHOLDER_RE = re.compile(r"\{\{[A-Za-z0-9_.\- ]+\}\}")


@dataclass
class Finding:
    file: str
    kind: str  # "persona" | "manifest" | "unknown"
    severity: str  # "error" | "warning"
    check: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _posix(path: Path) -> str:
    return path.as_posix()


def is_template_path(path: Path) -> bool:
    p = _posix(path)
    return any(marker in p for marker in TEMPLATE_SKIP_MARKERS)


def is_placeholder_exempt(path: Path) -> bool:
    p = _posix(path)
    return any(marker in p for marker in PLACEHOLDER_EXEMPT_MARKERS)


def discover(root: Path) -> tuple[list[Path], list[Path]]:
    """Find validatable files under ``root``. Returns (files, skipped_templates)."""
    names = {"persona.yaml", "manifest.yaml"}
    found: list[Path] = []
    skipped: list[Path] = []
    for path in sorted(root.rglob("*.yaml")):
        if path.name not in names:
            continue
        if any(part in {".git", "node_modules", "__pycache__"} for part in path.parts):
            continue
        if is_template_path(path):
            skipped.append(path)
        else:
            found.append(path)
    return found, skipped


def detect_kind(path: Path, data: object) -> str:
    if "persona" in path.name:
        return "persona"
    if "manifest" in path.name:
        return "manifest"
    if isinstance(data, dict):
        if "repos" in data and "project" in data:
            return "manifest"
        if "capabilities" in data and "slug" in data:
            return "persona"
    return "unknown"


# --- generic declarative walker -------------------------------------------------------

_TYPE_NAMES = {"str": "string", "map": "mapping", "list": "list"}


def _walk(
    node: Node, value: object, path: str, out: list[Finding], file: str, kind: str
) -> None:
    def add(severity: str, check: str, message: str) -> None:
        out.append(Finding(file=file, kind=kind, severity=severity, check=check, message=message))

    if node.opaque:
        return
    if node.kind == "any":
        return
    if node.kind == "str":
        if not isinstance(value, str):
            add("error", "type", f"{path}: expected {_TYPE_NAMES['str']}, got {type(value).__name__}")
            return
        if node.enum is not None and value not in node.enum:
            add(
                node.enum_severity,
                "enum",
                f"{path}: {value!r} not in documented set {list(node.enum)}",
            )
        return
    if node.kind == "list":
        if not isinstance(value, list):
            add("error", "type", f"{path}: expected list, got {type(value).__name__}")
            return
        if node.nonempty and not value:
            add("error", "empty", f"{path}: must not be empty")
        if node.item is not None:
            for i, item in enumerate(value):
                _walk(node.item, item, f"{path}[{i}]", out, file, kind)
        return
    if node.kind == "map":
        if not isinstance(value, dict):
            add("error", "type", f"{path}: expected mapping, got {type(value).__name__}")
            return
        fields = node.fields or {}
        for key in value:
            if key not in fields:
                add("warning", "unknown-field", f"{path}.{key}: unknown field")
        for name, child in fields.items():
            if name not in value:
                if child.required:
                    add("error", "missing-field", f"{path}.{name}: required field missing")
                continue
            _walk(child, value[name], f"{path}.{name}", out, file, kind)
        return
    raise AssertionError(f"unhandled node kind {node.kind!r}")


# --- capability-specific checks -------------------------------------------------------


def _parse_cap_entries(
    entries: object, side: str, out: list[Finding], file: str
) -> tuple[set[str], set[str], bool]:
    """Return (plain_verbs, write_path_scopes, has_bare_write_path) for one side."""
    verbs: set[str] = set()
    scopes: set[str] = set()
    bare_write_path = False

    def add(check: str, message: str) -> None:
        out.append(Finding(file=file, kind="persona", severity="error", check=check, message=message))

    if not isinstance(entries, list):
        return verbs, scopes, bare_write_path
    for i, entry in enumerate(entries):
        where = f"capabilities.{side}[{i}]"
        if isinstance(entry, str):
            if entry not in CAPABILITY_VERBS:
                add("verb", f"{where}: {entry!r} is not a v1 capability verb")
            elif entry in PARAMETRIC_VERBS:
                bare_write_path = True
                verbs.add(entry)
            else:
                verbs.add(entry)
        elif isinstance(entry, dict):
            if len(entry) != 1:
                add("verb", f"{where}: parametric entry must have exactly one key")
                continue
            (verb, params), = entry.items()
            if verb not in PARAMETRIC_VERBS:
                add("verb", f"{where}: {verb!r} is not a parametric v1 verb")
                continue
            if not isinstance(params, list) or not all(isinstance(s, str) for s in params):
                add("verb", f"{where}: {verb} scopes must be a list of strings")
                continue
            scopes.update(params)
        else:
            add("verb", f"{where}: expected a verb or a parametric mapping")
    return verbs, scopes, bare_write_path


def _check_capabilities(data: dict, out: list[Finding], file: str) -> None:
    caps = data.get("capabilities")
    if not isinstance(caps, dict):
        return
    a_verbs, a_scopes, a_bare = _parse_cap_entries(caps.get("allow"), "allow", out, file)
    d_verbs, d_scopes, d_bare = _parse_cap_entries(caps.get("deny"), "deny", out, file)

    def add(message: str) -> None:
        out.append(Finding(file=file, kind="persona", severity="error", check="overlap", message=message))

    overlap = (a_verbs & d_verbs) - PARAMETRIC_VERBS
    if overlap:
        add(f"capabilities: verbs in both allow and deny: {sorted(overlap)}")
    scope_overlap = a_scopes & d_scopes
    if scope_overlap:
        add(f"capabilities: write_path scopes in both allow and deny: {sorted(scope_overlap)}")
    # A bare `write_path` (all scopes) on one side overlaps any write_path on the other.
    if (a_bare and (d_bare or d_scopes)) or (d_bare and a_scopes):
        add("capabilities: bare write_path on one side overlaps write_path on the other")


# --- file / tree entry points ---------------------------------------------------------


def validate_file(path: Path) -> list[Finding]:
    file = _posix(path)
    out: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [Finding(file, "unknown", "error", "read", str(exc))]

    if not is_placeholder_exempt(path):
        for token in sorted(set(PLACEHOLDER_RE.findall(text))):
            out.append(
                Finding(file, "unknown", "error", "placeholder", f"unfilled template token {token}")
            )

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        out.append(Finding(file, "unknown", "error", "parse", f"YAML parse error: {exc}"))
        return out

    kind = detect_kind(path, data)
    for f in out:
        f.kind = kind
    if kind == "persona":
        _walk(PERSONA_SPEC, data, "persona", out, file, kind)
        if isinstance(data, dict):
            _check_capabilities(data, out, file)
    elif kind == "manifest":
        _walk(MANIFEST_SPEC, data, "manifest", out, file, kind)
    else:
        out.append(
            Finding(file, kind, "warning", "kind", "cannot determine schema (persona/manifest)")
        )
    return out


def validate_path(
    target: Path, *, runtime_drift: bool = True, home: Path | None = None
) -> tuple[list[Finding], list[Path], list[Path]]:
    """Validate a file or a tree. Returns (findings, files_checked, skipped_templates).

    When ``target`` is a directory holding a ``manifest.yaml``, also compares the
    declared personas against each declared runtime's agent registry (P2.3, see
    :mod:`baron.drift`). Pass ``runtime_drift=False`` to skip that — the rest of
    validate reads only spec files, while the drift check reads machine-local
    state, so it is the one part that can legitimately differ between machines.
    """
    if target.is_file():
        return validate_file(target), [target], []
    files, skipped = discover(target)
    findings: list[Finding] = []
    for f in files:
        findings.extend(validate_file(f))
    if runtime_drift:
        findings.extend(_runtime_drift_findings(target, files, home))
    return findings, files, skipped


def _runtime_drift_findings(
    root: Path, files: Iterable[Path], home: Path | None
) -> list[Finding]:
    """Run the spec↔runtime drift check for each manifest discovered under ``root``."""
    out: list[Finding] = []
    for path in files:
        if path.name != "manifest.yaml":
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue  # the schema pass already reported this file
        if not isinstance(data, dict):
            continue
        for hit in drift.check(path.parent, data, home=home):
            out.append(
                Finding(_posix(path), "manifest", hit.severity, hit.check, hit.message)
            )
    return out


def has_errors(findings: Iterable[Finding]) -> bool:
    return any(f.severity == "error" for f in findings)
