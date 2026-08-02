"""P2.3 — spec↔runtime drift: personas declared in the canon but never
registered as runtime agents.

The failure this closes (badminton-analyzer pilot, 2026-07): the collab repo
declared eight personas; the Claude subagent registry held six. Two personas —
``terrence`` and ``carson`` — existed only as ``persona.yaml``. Routing work to
one of them did not fail loudly; it fell through to whatever agent the runtime
did have, so a cron ran under the WRONG persona: wrong identity, wrong commit
prefix, and wrong capability set. The canon said one thing, the machine did
another, and nothing compared them.

Why this is opt-out rather than opt-in
--------------------------------------
A registry is **machine-local** by design (ADR-002 §7: per-persona runtime state
lives outside the clone). So this check is environment-dependent in a way the
rest of ``baron validate`` is not, and it must never turn a green CI red merely
because CI has no ``~/.claude/agents``. Hence three states, mirroring
ADR-009 §4:

- **registered** — a spec file exists for the persona: silent.
- **missing** — a registry EXISTS for a declared runtime but this persona is not
  in it: **error**. This is the real drift, and it is what the pilot hit.
- **unverifiable** — no registry found anywhere for that runtime (a fresh
  machine, a CI runner, a Tier-1/Tier-2 project that hydrates no agents): a
  single **warning** naming where it looked. Never an error.

Only runtimes the project explicitly declares in ``manifest.adapters`` are
checked. baron does not guess: a stray ``~/.claude/agents`` on a laptop must not
make a generic-tier project fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

#: runtime key -> (registry subdirectory, per-persona filename template).
#: Sources: adapters/claude/HYDRATE.md (Tier-3 subagents) and
#: adapters/code-puppy/HYDRATE.md (JSON agents; note the underscore in the
#: directory name — the adapter calls that out explicitly as a footgun).
REGISTRIES: dict[str, tuple[str, str]] = {
    "claude": (".claude/agents", "{slug}.md"),
    "code-puppy": (".code_puppy/agents", "{slug}.json"),
}

#: Runtimes with no discoverable registry: pydantic-ai hydrates in-process via
#: `build_agent` (there is no file to inspect) and generic is Tier-1 prose.
#: Declared here so the omission reads as deliberate rather than forgotten.
NO_REGISTRY: tuple[str, ...] = ("pydantic-ai", "generic")


@dataclass(frozen=True)
class DriftFinding:
    severity: str  # "error" | "warning"
    check: str  # "runtime-drift" | "runtime-drift-unverifiable"
    message: str


def _search_roots(collab_root: Path, manifest: dict, home: Path) -> list[Path]:
    """Where a registry may live, most-specific first.

    Project-level beats user-level: a persona registered under the project is
    unambiguously this project's. The user-level directory is shared across every
    project on the machine, which is why a match there is reported with a caveat.
    """
    roots: list[Path] = [collab_root]
    repos = manifest.get("repos")
    if isinstance(repos, list):
        for repo in repos:
            if not isinstance(repo, dict):
                continue
            rel = repo.get("path")
            if isinstance(rel, str) and rel not in {".", ""}:
                roots.append((collab_root / rel).resolve())
    roots.append(home)
    return roots


def _declared_runtimes(manifest: dict) -> list[str]:
    adapters = manifest.get("adapters")
    if not isinstance(adapters, dict):
        return []
    return [key for key in adapters if key in REGISTRIES]


def _persona_slugs(manifest: dict) -> list[str]:
    personas = manifest.get("personas")
    if not isinstance(personas, list):
        return []
    out = []
    for entry in personas:
        if isinstance(entry, dict) and isinstance(entry.get("slug"), str):
            out.append(entry["slug"])
    return out


def check(
    collab_root: Path, manifest: dict, *, home: Path | None = None
) -> list[DriftFinding]:
    """Compare declared personas against each declared runtime's agent registry."""
    home = Path.home() if home is None else home
    findings: list[DriftFinding] = []
    slugs = _persona_slugs(manifest)
    if not slugs:
        return findings

    for runtime in _declared_runtimes(manifest):
        subdir, filename = REGISTRIES[runtime]
        roots = _search_roots(collab_root, manifest, home)
        registries = [(root / subdir) for root in roots]
        present = [d for d in registries if d.is_dir()]

        if not present:
            looked = ", ".join(str(d) for d in registries)
            findings.append(
                DriftFinding(
                    "warning",
                    "runtime-drift-unverifiable",
                    f"{runtime}: no agent registry found, so persona registration could "
                    f"not be checked (looked in: {looked}). Not an error — registries are "
                    f"machine-local (ADR-002 §7) and absent on CI runners.",
                )
            )
            continue

        for slug in slugs:
            hits = [d for d in present if (d / filename.format(slug=slug)).is_file()]
            if not hits:
                where = ", ".join(str(d) for d in present)
                findings.append(
                    DriftFinding(
                        "error",
                        "runtime-drift",
                        f"{runtime}: persona '{slug}' is declared in manifest.personas "
                        f"but has no agent registered in {where}. Work routed to "
                        f"'{slug}' will silently run as some other agent — wrong "
                        f"identity, wrong commit prefix, wrong capabilities. Hydrate it "
                        f"per adapters/{runtime}/HYDRATE.md, or remove it from the "
                        f"manifest.",
                    )
                )
            elif all(hit == (home / subdir) for hit in hits):
                findings.append(
                    DriftFinding(
                        "warning",
                        "runtime-drift",
                        f"{runtime}: persona '{slug}' resolves only via the user-level "
                        f"registry {home / subdir}, which is shared across every project "
                        f"on this machine — a same-named agent from another project would "
                        f"satisfy this check. Prefer a project-level registration.",
                    )
                )
    return findings
