"""P2.3 — spec↔runtime drift: personas declared in the canon but never
registered as runtime agents.

The failure this closes (badminton-analyzer pilot, 2026-07): the collab repo
declared eight personas; the Claude subagent registry held six. ``terrence`` and
``carson`` existed only as ``persona.yaml``. Routing work to one of them did not
fail loudly — it fell through to whatever agent the runtime did have, so a cron
ran under the WRONG persona: wrong identity, wrong commit prefix, wrong
capability set. The canon said one thing, the machine did another, and nothing
compared them.

The signal is PARTIAL registration, not absence
-----------------------------------------------
The obvious check — "a registry exists but this persona is not in it" — is wrong,
and wrong in the direction that breaks working projects. Three legitimate states
produce zero registered agents:

- a **Tier-2** Claude project. ``adapters/claude/HYDRATE.md`` is explicit: at
  Tier 2 you "do NOT emit a dead subagent file". Zero subagents is correct there.
- a **freshly scaffolded** project. ``baron init`` writes persona *specs*; Tier-3
  hydration is conversational (ADR-006 §3). Zero is the correct intermediate state.
- a **Tier-1** runtime (generic, and code-puppy's documented fallback).

Meanwhile ``tier: auto`` — the default ``baron init`` writes — cannot be resolved
statically at all: it is a per-session self-assessment.

So baron does not ask "does a registry exist?" It asks **"has this project
registered SOME of its personas and not others?"** Partial registration is
positive evidence that the project does hydrate agents on this runtime, which
makes the gaps genuine drift. All-or-nothing is silent. That is self-calibrating:
it needs no declared tier, and it cannot fail a project that simply doesn't
hydrate agents.

Honest limits, stated rather than discovered later
--------------------------------------------------
- A project with **exactly one** persona cannot produce a partial state, so a
  single unregistered persona is invisible. Unavoidable with this signal.
- If **every** persona is unregistered — the whole fleet drifted at once — that
  reads as "not hydrated" and stays silent. The pilot shape (some registered,
  some not) is the one this catches, and it is the shape that actually occurred.
- Registration is matched by the filename the adapter writes (``<slug>.md``), and
  additionally by a ``name:`` frontmatter match, since that is what Claude keys
  the subagent on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: runtime key -> (registry subdirectory, per-persona filename template).
#: Sources: adapters/claude/HYDRATE.md step 3a (``<code_repo>/.claude/agents/<slug>.md``
#: — project-scoped, TRAVELS WITH THE REPO) and adapters/code-puppy/HYDRATE.md
#: (``.code_puppy/agents/`` — note the underscore; the adapter flags the
#: dot-vs-underscore separator as a footgun).
REGISTRIES: dict[str, tuple[str, str]] = {
    "claude": (".claude/agents", "{slug}.md"),
    "code-puppy": (".code_puppy/agents", "{slug}.json"),
}

#: Runtimes with no inspectable registry: pydantic-ai hydrates in-process via
#: ``build_agent`` (there is no file), generic is Tier-1 prose. Declared so an
#: unknown adapter key can be told apart from a known-but-registryless one.
NO_REGISTRY: tuple[str, ...] = ("pydantic-ai", "generic")

_NAME_RE = re.compile(r"^name:\s*(\S+)\s*$", re.M)


@dataclass(frozen=True)
class DriftFinding:
    severity: str  # "error" | "warning"
    check: str  # "runtime-drift" | "runtime-drift-scope"
    message: str


def _search_roots(collab_root: Path, manifest: dict) -> list[Path]:
    """Where a registry may live, most-specific first.

    Honours ``manifest.paths.root`` — repo paths are documented as relative to it,
    not to the manifest's own directory (``manifest.schema.md``).
    """
    paths = manifest.get("paths")
    base = collab_root
    if isinstance(paths, dict) and isinstance(paths.get("root"), str):
        base = (collab_root / paths["root"]).resolve()
    roots: list[Path] = [collab_root, base]
    repos = manifest.get("repos")
    if isinstance(repos, list):
        for repo in repos:
            if not isinstance(repo, dict):
                continue
            rel = repo.get("path")
            if isinstance(rel, str) and rel not in {".", ""}:
                roots.append((base / rel).resolve())
    # De-duplicate, preserving order.
    seen: set[Path] = set()
    out: list[Path] = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _persona_slugs(manifest: dict) -> list[str]:
    personas = manifest.get("personas")
    if not isinstance(personas, list):
        return []
    return [
        e["slug"]
        for e in personas
        if isinstance(e, dict) and isinstance(e.get("slug"), str)
    ]


def _registered(directory: Path, slug: str, filename: str) -> bool:
    """Is ``slug`` registered in ``directory``?

    Filename first (that is what the adapter writes), then a ``name:`` frontmatter
    scan — Claude keys a subagent on its frontmatter ``name``, so a file named
    differently but declaring the right name IS a valid registration.
    """
    if (directory / filename.format(slug=slug)).is_file():
        return True
    for candidate in sorted(directory.glob("*.md")):
        try:
            head = candidate.read_text(encoding="utf-8", errors="replace")[:512]
        except OSError:
            continue
        m = _NAME_RE.search(head)
        if m and m.group(1).strip("\"'") == slug:
            return True
    return False


def _claude_tier(manifest: dict) -> str | None:
    adapters = manifest.get("adapters")
    if isinstance(adapters, dict) and isinstance(adapters.get("claude"), dict):
        tier = adapters["claude"].get("tier")
        if tier is not None:
            return str(tier)
    return None


def check(
    collab_root: Path, manifest: dict, *, home: Path | None = None
) -> list[DriftFinding]:
    """Compare declared personas against each declared runtime's agent registry."""
    home = Path.home() if home is None else home
    findings: list[DriftFinding] = []
    slugs = _persona_slugs(manifest)
    adapters = manifest.get("adapters")
    if not slugs or not isinstance(adapters, dict):
        return findings

    for runtime in adapters:
        if runtime not in REGISTRIES:
            continue  # NO_REGISTRY runtimes and unknown keys: nothing to inspect
        # An explicit Tier 2 means "no subagents by design" — HYDRATE.md forbids
        # emitting one. Checking a registry there would report every persona.
        if runtime == "claude" and _claude_tier(manifest) == "2":
            continue

        subdir, filename = REGISTRIES[runtime]
        dirs = [root / subdir for root in _search_roots(collab_root, manifest)]
        dirs.append(home / subdir)
        present = [d for d in dirs if d.is_dir()]
        if not present:
            continue

        registered: dict[str, list[Path]] = {}
        for slug in slugs:
            hits = [d for d in present if _registered(d, slug, filename)]
            if hits:
                registered[slug] = hits

        # All or nothing -> this project does not hydrate agents here (Tier 1/2,
        # unhydrated, or a fresh scaffold). Not drift.
        if not registered or len(registered) == len(slugs):
            pass
        else:
            for slug in slugs:
                if slug in registered:
                    continue
                where = ", ".join(str(d) for d in present)
                findings.append(
                    DriftFinding(
                        "error",
                        "runtime-drift",
                        f"{runtime}: persona '{slug}' is declared in manifest.personas "
                        f"but has no agent registered, while "
                        f"{len(registered)}/{len(slugs)} sibling personas do "
                        f"({', '.join(sorted(registered))}) — so this project DOES "
                        f"hydrate agents here and '{slug}' was missed. Work routed to "
                        f"it will silently run as some other agent: wrong identity, "
                        f"wrong commit prefix, wrong capabilities. Register it per "
                        f"adapters/{runtime}/HYDRATE.md, or remove it from the "
                        f"manifest. Looked in: {where}."
                    )
                )

        # Scope caveat: the user-level registry is shared by every project on the
        # machine, so a same-named agent from elsewhere satisfies the check.
        user_dir = home / subdir
        for slug, hits in sorted(registered.items()):
            if hits == [user_dir]:
                findings.append(
                    DriftFinding(
                        "warning",
                        "runtime-drift-scope",
                        f"{runtime}: persona '{slug}' resolves only via {user_dir}, "
                        f"which is shared across every project on this machine — a "
                        f"same-named agent from another project would satisfy this "
                        f"check. Prefer a repo-scoped registration (it travels with "
                        f"the clone; see adapters/{runtime}/HYDRATE.md)."
                    )
                )
    return findings
