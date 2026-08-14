"""``baron init`` — deterministic collab-repo scaffold (ADR-006).

The non-conversational subset of the ORCHESTRATE.md recipe: create the collab
repo skeleton (CONVENTIONS/COORDINATION, manifest, canon/ + adapters/ from the
vendored templates, hydrated ``agents/<slug>/persona.yaml`` per persona, the
genesis handoff, ledger index headers, wiki stub, the lock-guard, strip-stale-verdict and baron-notify
strip-stale-verdict CI templates), then git-init and commit. Everything
emitted is deterministic — no interview, no runtime self-assessment.

What stays on the conversational path (canon/ORCHESTRATE.md, by design):
persona scope prose (init fills a generic edit-me scope), ``AGENT.md``
derivation, Tier-3 hydration (Claude subagents, code-puppy JSON agents — both
need an in-session capability/tier assessment), and per-persona workspace
creation. Init's runtime kits are the deterministic floor: the Tier-2 persona
``CLAUDE.md`` + ``baron guard`` hook settings for claude, the Tier-1
``AGENTS.md`` for generic (and code-puppy, as its documented fallback), and the
``agent_setup.py`` bootstrap for pydantic-ai.

Beside each kit init emits ``agents/<slug>/sidecar.sh`` (ADR-026) — the persona's
launcher: a thin wrapper over ``baron sidecar run`` whose only project-owned part
is the runtime invocation. Kit = what the persona *is*; sidecar = how it is
*deployed*.

``in_monorepo=True`` emits the same project into a **subdir** of a coordination
monorepo (ADR-025) instead of a repo of its own: the root owns git and
``.github/``, so those are skipped here, and the paths that reach out of the
project gain one level. Everything else is byte-identical — a monorepo subdir is
an ordinary Barony project, which is what lets every other command ignore the
distinction. See :mod:`baron.monorepo`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import clock, validate as validate_mod
from .gitutil import GitError, git, is_git_repo
from .runtimes import render_pydantic_ai_bootstrap
from .templates import read_template


class ScaffoldError(RuntimeError):
    """The scaffold could not be created (or the request is malformed)."""


#: archetype key (CLI surface) -> vendored persona template.
ARCHETYPE_TEMPLATES: dict[str, str] = {
    "dev": "collab-repo/agents/__DEV__/persona.yaml",
    "librarian": "collab-repo/agents/librarian/persona.yaml",
    "autonomous-event": "collab-repo/agents/__AUTONOMOUS_EVENT__/persona.yaml",
    "autonomous-cron": "collab-repo/agents/__AUTONOMOUS_CRON__/persona.yaml",
    "reviewer": "collab-repo/agents/__REVIEWER__/persona.yaml",
    "merger": "collab-repo/agents/__MERGER__/persona.yaml",
}

RUNTIMES: tuple[str, ...] = ("claude", "generic", "pydantic-ai", "code-puppy")

#: canon/ contents per ORCHESTRATE.md §2a: three entrypoints + four references.
CANON_ENTRYPOINTS = ("START.md", "ORCHESTRATE.md", "PARTICIPATE.md")
CANON_REFERENCES = (
    "capability-vocab.v1.md",
    "capability-rules.md",
    "persona.schema.md",
    "manifest.schema.md",
)
ADAPTERS = ("claude", "code-puppy", "pydantic-ai", "generic")

_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class Persona:
    archetype: str
    slug: str

    @property
    def name(self) -> str:
        return self.slug.replace("-", " ").title()


@dataclass
class InitReport:
    root: Path
    personas: list[Persona]
    runtime: str
    created: list[str] = field(default_factory=list)
    git_initialized: bool = False
    git_committed: bool = False
    notes: list[str] = field(default_factory=list)


def parse_personas(spec: str) -> list[Persona]:
    """Parse ``archetype:slug,...`` (e.g. ``dev:carson,librarian:iris``).

    A librarian persona is appended automatically when none is listed —
    every Barony project carries one (it owns wiki/ and the ledger numbers).
    """
    personas: list[Persona] = []
    seen: set[str] = set()
    for item in [p.strip() for p in spec.split(",") if p.strip()]:
        archetype, sep, slug = item.partition(":")
        if not sep or not archetype or not slug:
            raise ScaffoldError(
                f"--personas entry {item!r} is not archetype:slug "
                f"(archetypes: {', '.join(sorted(ARCHETYPE_TEMPLATES))})"
            )
        if archetype not in ARCHETYPE_TEMPLATES:
            raise ScaffoldError(
                f"unknown archetype {archetype!r} — pick from "
                f"{', '.join(sorted(ARCHETYPE_TEMPLATES))}"
            )
        if not _SLUG_RE.match(slug):
            raise ScaffoldError(
                f"persona slug {slug!r} must match [a-z][a-z0-9-]* (lowercase)"
            )
        if slug in seen:
            raise ScaffoldError(f"duplicate persona slug {slug!r}")
        seen.add(slug)
        personas.append(Persona(archetype, slug))
    if not personas:
        raise ScaffoldError("--personas is empty — need at least one archetype:slug")
    if not any(p.archetype == "librarian" for p in personas):
        if "librarian" in seen:
            raise ScaffoldError(
                "slug 'librarian' is taken by a non-librarian persona; "
                "name your librarian explicitly (librarian:<slug>)"
            )
        personas.append(Persona("librarian", "librarian"))
    return personas


# --- context ---------------------------------------------------------------------------


@dataclass
class _Context:
    """Everything the emitters need, resolved once."""

    project: str
    root: Path
    collab_dir: str  # basename of the collab repo directory
    date: str
    personas: list[Persona]
    runtime: str
    code_label: str  # display label for docs ("../gardenkit", a URL, or none-text)
    code_rel: str | None  # manifest-relative path to the code repo, if any
    code_remote: str | None
    #: True when this project is a subdir of a coordination monorepo (ADR-025):
    #: the root owns git and .github/, and the collab path gains one level.
    in_monorepo: bool = False

    @property
    def identity_domain(self) -> str:
        return f"{self.project.lower()}.local"

    @property
    def librarian(self) -> Persona:
        return next(p for p in self.personas if p.archetype == "librarian")


def _resolve_code_repo(code_repo: str | None, root: Path) -> tuple[str, str | None, str | None]:
    """(display_label, manifest_rel_path, remote_url) for --code-repo."""
    if code_repo is None:
        return "(no code repo yet)", None, None
    if "://" in code_repo or code_repo.startswith("git@"):
        base = code_repo.rstrip("/").rsplit("/", 1)[-1]
        base = base[:-4] if base.endswith(".git") else base
        return code_repo, f"../{base}", code_repo
    path = Path(code_repo).expanduser()
    resolved = path if path.is_absolute() else Path.cwd() / path
    rel = os.path.relpath(resolved.resolve(), root.resolve()).replace(os.sep, "/")
    remote: str | None = None
    if is_git_repo(resolved):
        proc = git(resolved, "remote", "get-url", "origin", check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            remote = proc.stdout.strip()
    return rel, rel, remote


# --- emitters --------------------------------------------------------------------------


_PLACEHOLDER_RE = validate_mod.PLACEHOLDER_RE


def _fill(text: str, mapping: dict[str, str], *, where: str) -> str:
    for key, value in mapping.items():
        text = text.replace("{{" + key + "}}", value)
    leftover = sorted(set(_PLACEHOLDER_RE.findall(text)))
    if leftover:
        raise ScaffoldError(
            f"template {where} still carries unfilled tokens {leftover} — "
            "the vendored templates and baron disagree; re-sync and report a bug"
        )
    return text


def _doc_mapping(ctx: _Context) -> dict[str, str]:
    return {
        "PROJECT_NAME": ctx.project,
        "PROJECT_DESCRIPTION": f"Multi-agent project {ctx.project}.",
        "CODE_REPO": ctx.code_label,
        "COLLAB_REPO": ctx.collab_dir,
        "OWNER_HANDLE": "owner",
        "LOCAL_COLLAB_PATH": ".",
        "LOCAL_CODE_PATH": ctx.code_rel or "(no code repo yet)",
        "HOT_FILES_TABLE_ROWS": "(none yet)",
        "YYYY-MM-DD": ctx.date,
        "DATE": ctx.date,
    }


def _hydrate_persona(persona: Persona, ctx: _Context) -> str:
    rel = ARCHETYPE_TEMPLATES[persona.archetype]
    text = read_template(rel)
    # Drop the template's leading comment block (it says "fill every {{...}}
    # token", which is done the moment this function returns).
    lines = text.splitlines()
    start = 0
    while start < len(lines) and lines[start].startswith("#"):
        start += 1
    body = "\n".join(lines[start:]).lstrip("\n")
    if persona.archetype == "librarian" and persona.slug != "librarian":
        # The librarian template carries its identity inline (no {{PERSONA_*}}
        # tokens); renaming the persona is a whole-word swap — except the
        # archetype line, which stays `librarian` (it names the archetype,
        # not the persona).
        sentinel = "\x00ARCHETYPE\x00"
        body = body.replace("archetype: librarian", sentinel)
        body = re.sub(r"\bLibrarian\b", persona.name, body)
        body = re.sub(r"\blibrarian\b", persona.slug, body)
        body = body.replace(sentinel, "archetype: librarian")
    scope_note = (
        f"{persona.name} — {persona.archetype} persona for {ctx.project}. "
        "Generic scaffold scope: replace with this persona's real focus."
    )
    filled = _fill(
        body,
        {
            "PERSONA_NAME": persona.name,
            "PERSONA_SLUG": persona.slug,
            "IDENTITY_DOMAIN": ctx.identity_domain,
            "PROJECT_NAME": ctx.project,
            "PERSONA_SCOPE_SUMMARY": scope_note,
            "PERSONA_PURPOSE_PARAGRAPH": scope_note,
            "PERSONA_SCOPE_LINE_1": f"Claim backlog items labelled agent-{persona.slug}",
            "PERSONA_SCOPE_LINE_2": f"Deliver changes via PR from branch {persona.slug}/<topic>",
            "PERSONA_SCOPE_LINE_3": "Record material findings/decisions via _handoff/ per CONVENTIONS.md",
        },
        where=rel,
    )
    header = (
        f"# {persona.name} — {persona.archetype} persona for {ctx.project}.\n"
        f"# Hydrated from the {persona.archetype} archetype template by `baron init` ({ctx.date}).\n"
        "# Canonical machine truth: schema canon/persona.schema.md; capability verbs\n"
        "# canon/capability-vocab.v1.md (frozen v1 — never invent verbs).\n"
    )
    if not filled.endswith("\n"):
        filled += "\n"
    return header + filled


def _manifest(ctx: _Context) -> str:
    lines = [
        "# manifest.yaml — canonical project spec (schema: canon/manifest.schema.md).",
        f"# Generated by `baron init` on {ctx.date}; edit freely — baron only reads it.",
        "project:",
        f"  name: {ctx.project}",
        f"  description: Multi-agent project {ctx.project}. Edit this description.",
        "paths:",
        "  strategy: relative          # required for portability — never absolute",
        "  root: .                     # resolved from the collab repo root",
        "repos:",
    ]
    if ctx.code_rel:
        lines += [
            "  - id: code",
            f"    path: {ctx.code_rel}",
        ]
        if ctx.code_remote:
            lines.append(f"    remote: {ctx.code_remote}")
        lines.append("    role: code")
    lines += [
        "  - id: collab",
        "    path: .",
        "    role: collab",
        "backlog:",
        "  source: file",
        "  location: backlog.md",
        "personas:",
    ]
    for p in ctx.personas:
        lines.append(f"  - slug: {p.slug}")
        lines.append(f"    spec: agents/{p.slug}/persona.yaml")
    if ctx.runtime == "claude":
        lines += [
            "adapters:",
            "  claude:",
            "    tier: auto              # auto | 2 | 3 (adapters/claude/HYDRATE.md)",
        ]
    if ctx.code_rel:
        # In a monorepo the collab root is one level deeper, so the worktrees root
        # stays a sibling of the MONOREPO — never a stray directory inside it.
        up = "../../" if ctx.in_monorepo else "../"
        lines += [
            "workspace:",
            f"  worktrees_root: {up}{ctx.project}-worktrees  # `baron worktree add <slug>` targets this",
        ]
    return "\n".join(lines) + "\n"


def _readme(ctx: _Context) -> str:
    roster = ", ".join(f"{p.slug} ({p.archetype})" for p in ctx.personas)
    return (
        f"# {ctx.project} — collaboration repo\n\n"
        f"Coordination substrate for {ctx.project}, scaffolded by `baron init` on {ctx.date}.\n"
        f"Personas: {roster}. The code lives in `{ctx.code_label}`; this repo holds\n"
        "everything else — rules, persona specs, handoffs, findings, decisions, wiki.\n\n"
        "| Surface | Where |\n"
        "|---|---|\n"
        "| Rules of the road | `CONVENTIONS.md`, `COORDINATION.md` |\n"
        "| Canonical spec + recipes | `canon/` (`START.md` routes; runtime mapping in `adapters/`) |\n"
        "| Personas (machine truth) | `agents/<slug>/persona.yaml` |\n"
        "| Async coordination | `_handoff/` (archive, never delete) |\n"
        "| Ledgers | `findings/index.md`, `decisions/index.md` (numbered by baron) |\n"
        "| Wiki (Librarian-owned) | `wiki/` |\n\n"
        "New here? Read `canon/START.md` — it routes joiners to `canon/PARTICIPATE.md`.\n"
        "Machine checks: `baron validate .` and `baron status`.\n"
    )


def _backlog(ctx: _Context) -> str:
    return (
        f"# {ctx.project} — backlog\n\n"
        "Work items (manifest `backlog.source: file`). Personas check this file via\n"
        "their session ritual; route an item with the persona's label, e.g.:\n\n"
        f"- [ ] agent-{ctx.personas[0].slug}: replace this line with the first real task\n"
    )


def _genesis_handoff(ctx: _Context) -> str:
    lib = ctx.librarian
    return (
        "---\n"
        f"created: {ctx.date}\n"
        "status: open\n"
        f"for: {lib.slug}\n"
        "from: bootstrap\n"
        "priority: low\n"
        "---\n\n"
        f"# {lib.name} — genesis acknowledgment\n\n"
        "One-time bootstrap handoff, written by `baron init` at scaffold time so the\n"
        "handoff surface starts non-empty and the first Librarian run has a task.\n\n"
        f"On your first run, {lib.name}:\n\n"
        f"1. Read your spec (`agents/{lib.slug}/persona.yaml`) and the project rules\n"
        "   (`CONVENTIONS.md`, `COORDINATION.md`).\n"
        "2. Verify the wiki stub is well-formed: `wiki/log.md` has the genesis entry,\n"
        "   `wiki/index.md` lists the standard sections.\n"
        "3. Replace the generic scope text in the persona specs with real scopes as the\n"
        "   owner defines them (surface, don't invent).\n"
        "4. Flip this handoff to `status: done` (`baron handoff close` or by hand) and\n"
        "   commit. The standard cycle (COORDINATION.md § Session-start checklist)\n"
        "   takes over from here.\n"
    )


def _ledger_index(ctx: _Context, kind: str) -> str:
    prefix = "F" if kind == "findings" else "D"
    tool = "finding" if kind == "findings" else "decision"
    return (
        f"# {ctx.project} — {kind} index\n\n"
        f"Numbered {kind} ledger ({prefix}1, {prefix}2, ...). Append entries with\n"
        f"`baron {tool} new` (house style: `### {prefix}<N> — <title> (<date>, <author>)`).\n"
        "Numbering is allocated race-safely via push-retry; gaps are reported, history\n"
        "is never renumbered.\n"
    )


def _wiki_log(ctx: _Context) -> str:
    roster = ", ".join(p.slug for p in ctx.personas)
    return (
        f"# {ctx.project} wiki — reconciliation log\n\n"
        "Append-only. Most recent entry at top. One entry per meaningful unit of work.\n\n"
        f"## [{ctx.date}] genesis | {ctx.project} bootstrap\n\n"
        f"{ctx.project} scaffolded by `baron init` — personas: {roster}; code repo:\n"
        f"`{ctx.code_label}`; collab repo: `{ctx.collab_dir}`. This entry seeds the\n"
        f"{ctx.librarian.name}'s `find -newer wiki/log.md` cycle with a day-one baseline.\n"
    )


# --- runtime kits ----------------------------------------------------------------------


_ALLOW_PHRASES = {
    "read_code": "Read the code repo.",
    "read_collab": "Read the collab repo.",
    "write_code": "Write code and tests in the code repo.",
    "open_pr": "Open pull requests.",
    "run_tests": "Run the test suite.",
    "merge_pr": "Merge pull requests (verify the preconditions in COORDINATION.md first).",
    "push_main": "Push to the default branch — only your owned direct-push surfaces (CONVENTIONS.md push policy).",
    "force_push": "Force-push (unusual — re-read your persona spec before using it).",
    "edit_other_personas": "Edit other personas' agents/<slug>/ files.",
}

_DENY_PHRASES = {
    "read_code": "Never read the code repo.",
    "read_collab": "Never read the collab repo.",
    "write_code": "Never write application code.",
    "open_pr": "Never open a pull request.",
    "run_tests": "Never run the test suite.",
    "merge_pr": "Never merge a pull request.",
    "push_main": "Never push to the default branch.",
    "force_push": "Never force-push.",
    "edit_other_personas": "Never edit another persona's agents/ files.",
}


def _capability_lines(entries: list, phrases: dict[str, str], write_path_fmt: str) -> list[str]:
    out: list[str] = []
    for entry in entries or []:
        if isinstance(entry, dict) and "write_path" in entry:
            scopes = ", ".join(f"{s}/" for s in entry["write_path"])
            out.append(write_path_fmt.format(scopes=scopes))
        elif isinstance(entry, str):
            out.append(phrases.get(entry, entry))
    return out


def _ritual_lines(tokens: list, persona: Persona, collab_rel: str) -> list[str]:
    """Render session_ritual tokens with paths relative to the kit's target
    working copy (see the kit README for the assumed layout)."""
    pulls = [f"`git -C {collab_rel} pull`"]
    if collab_rel != ".":
        pulls.insert(0, "`git -C . pull`")
    rendered = {
        "sync_repos": (
            "Sync repos: " + "; ".join(pulls) + " (skip repos that have no origin yet)."
        ),
        "read_conventions": (
            f"Read `{collab_rel}/CONVENTIONS.md` and `{collab_rel}/COORDINATION.md`."
        ),
        "check_handoffs": (
            f"In `{collab_rel}/_handoff/`, find files with `status: open` and "
            f"`for: {persona.slug}` or `for: all`."
        ),
        "check_review_feedback": (
            "Sweep review feedback BEFORE claiming new work: for each of your open PRs, "
            "compare the latest verdict comment's head SHA to the PR's current head. Act on "
            "the verdicts that are LIVE (SHA matches); a verdict at an older SHA is void and "
            "needs a re-review. Never treat a review-state label as the evidence "
            f"(`{collab_rel}/CONVENTIONS.md` § A label is not evidence)."
        ),
        "check_backlog": (
            f"Read `{collab_rel}/backlog.md` for items labelled `agent-{persona.slug}` "
            "(manifest backlog source). If `manifest.backlog.park_label` is declared, "
            "SKIP parked items — marked `<!-- <park_label> -->` in a file backlog, or "
            "carrying that label on a tracker. A parked item is work a ratified "
            "decision superseded (ADR-009)."
        ),
    }
    return [rendered.get(t, t) for t in tokens or [] if isinstance(t, str)]


def _kit_paths(ctx: _Context) -> str:
    """The collab repo's path relative to the working copy the kit targets."""
    return f"../{ctx.collab_dir}" if ctx.code_rel else "."


def _kit_readme(persona: Persona, ctx: _Context) -> str:
    target = (
        "this persona's code-repo working copy (a sibling clone; adjust the relative\n"
        "paths if you use worktrees under the manifest's `workspace.worktrees_root`)"
        if ctx.code_rel
        else "the collab repo root (this project has no code repo yet)"
    )
    lines = [
        f"# {persona.name} — {ctx.runtime} runtime kit (generated by `baron init`)",
        "",
        f"Copy the contents of this directory into {target}.",
        "Everything here is DERIVED from `agents/" + persona.slug + "/persona.yaml` —",
        "regenerate on change (re-run hydration per `adapters/" + _adapter_dir(ctx.runtime) + "/HYDRATE.md`),",
        "never hand-edit.",
        "",
    ]
    if ctx.runtime == "claude":
        lines += [
            "- `CLAUDE.md` — Tier-2 persona context (instructed; auto-loaded by Claude Code).",
            "- `.claude/settings.json` — PreToolUse hook wiring `baron guard` (upgrades the",
            "  five guard-covered denials to enforced WHEN baron is installed; degrades to",
            "  instructed otherwise — honest degradation, never a bricked session).",
            "",
            "Tier-3 (native subagent with an enforced tool allow-list) needs an in-session",
            "capability check — follow `adapters/claude/HYDRATE.md` step 3a from your runtime.",
        ]
    elif ctx.runtime == "pydantic-ai":
        lines += [
            "- `agent_setup.py` — ready-to-edit bootstrap (pick a model; `test` runs offline).",
            "  Running it needs the extra: `pip install 'barony[pydantic-ai]'`.",
            "  Run from the collab root so the relative persona path resolves.",
        ]
    else:
        lines += [
            "- `AGENTS.md` — Tier-1 context file (instruction-only; auto-loaded by",
            "  AGENTS.md-aware runtimes, the re-read target everywhere else).",
        ]
        if ctx.runtime == "code-puppy":
            lines += [
                "",
                "code-puppy's native Tier-3 JSON agent needs an in-session hydration —",
                "follow `adapters/code-puppy/HYDRATE.md`; this AGENTS.md is its documented",
                "always-works fallback.",
            ]
    return "\n".join(lines) + "\n"


def _adapter_dir(runtime: str) -> str:
    return runtime if runtime in ADAPTERS else "generic"


def _persona_data(root: Path, persona: Persona) -> dict:
    return yaml.safe_load(
        (root / "agents" / persona.slug / "persona.yaml").read_text(encoding="utf-8")
    )


def _claude_settings(persona: Persona, ctx: _Context) -> str:
    collab_rel = _kit_paths(ctx)
    persona_path = (
        f"${{CLAUDE_PROJECT_DIR}}/{collab_rel}/agents/{persona.slug}/persona.yaml"
        if collab_rel != "."
        else f"${{CLAUDE_PROJECT_DIR}}/agents/{persona.slug}/persona.yaml"
    )
    command = f'baron guard --persona-file "{persona_path}"'
    # One command, dispatched inside baron on hook_event_name (ADR-012 §2).
    #
    # PreToolUse is ENFORCEMENT and is byte-frozen — matcher, command and the
    # 15s timeout are pinned by test_scaffold.py, because this block already
    # exists in every downstream repo `baron init` has ever generated and a
    # change here silently diverges them.
    #
    # The rest are EVIDENCE: they can only emit, never block (ADR-012 §3).
    # Newly scaffolded repos get IDENTICAL OBSERVABLE BEHAVIOUR to before,
    # because the event plane's default sink is null — wiring them now costs
    # nothing and means turning telemetry on later is one env var, not a
    # re-hydration of every persona kit. Shorter timeout: an evidence hook that
    # hangs delays a session for no benefit, so it gets a third of the
    # enforcement budget.
    evidence = [
        {"type": "command", "command": command, "timeout": 5},
    ]
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash|Edit|Write|NotebookEdit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command,
                            "timeout": 15,
                        }
                    ],
                }
            ],
            # Tool-scoped evidence: same matcher as enforcement, so the stream
            # covers exactly the calls the guard adjudicates.
            "PostToolUse": [
                {"matcher": "Bash|Edit|Write|NotebookEdit", "hooks": evidence}
            ],
            "PostToolUseFailure": [
                {"matcher": "Bash|Edit|Write|NotebookEdit", "hooks": evidence}
            ],
            # Session-scoped evidence: no matcher — these events carry no tool
            # name, and a matcher would silently never fire.
            "SessionStart": [{"hooks": evidence}],
            "SessionEnd": [{"hooks": evidence}],
        }
    }
    return json.dumps(settings, indent=2) + "\n"


def _context_file(persona: Persona, ctx: _Context, data: dict, *, tier2: bool) -> str:
    """The persona context file: CLAUDE.md (claude, Tier 2) or AGENTS.md (generic,
    Tier 1) — same derived sections, different enforcement honesty notes."""
    collab_rel = _kit_paths(ctx)
    identity = data.get("identity", {})
    scope = data.get("scope", {})
    caps = data.get("capabilities", {})
    allow_lines = _capability_lines(
        caps.get("allow"), _ALLOW_PHRASES, "Write the collab scopes: {scopes}."
    )
    deny_lines = _capability_lines(
        caps.get("deny"), _DENY_PHRASES, "Never write the collab scopes: {scopes}."
    )
    ritual = _ritual_lines(data.get("session_ritual"), persona, collab_rel)

    workspaces = [f"| collab | `{collab_rel}` | rules, personas, handoffs, ledgers, wiki |"]
    if ctx.code_rel:
        workspaces.insert(0, "| code | `.` | application code (this working copy) |")

    if tier2:
        enforcement_note = (
            "Capabilities here are INSTRUCTED (Tier 2). The `.claude/settings.json` in\n"
            "this kit wires the `baron guard` PreToolUse hook, which enforces the five\n"
            "guard-covered denials deterministically when baron is installed on this\n"
            "machine; without baron they degrade back to instructed."
        )
        never_heading = "## What never happens (self-enforced; `baron guard` hardens five of these when installed)"
    else:
        enforcement_note = (
            "Everything in this file is instruction-only (Tier 1) — nothing is enforced.\n"
            "Re-read it (or the canonical persona.yaml) whenever context may have drifted."
        )
        never_heading = "## What never happens (instruction-only at this tier — nothing here is enforced)"

    generated = (
        f"<!-- GENERATED from agents/{persona.slug}/persona.yaml by `baron init` "
        f"({ctx.date}) — do not hand-edit; re-derive on change. -->"
    )
    frontmatter = (
        "---\n"
        f"persona: {persona.name}\n"
        f"slug: {persona.slug}\n"
        f"archetype: {data.get('archetype', persona.archetype)}\n"
        "status: active\n"
        f"created: {ctx.date}\n"
        "---\n"
    )
    focus = "\n".join(f"- {line}" for line in scope.get("focus", []) or [])
    lines = [
        frontmatter + generated,
        f"# {persona.name} — {data.get('archetype', persona.archetype)} persona for {ctx.project}",
        f"You are {persona.name}. Canonical spec: `{collab_rel}/agents/{persona.slug}/persona.yaml`\n"
        "(this file is derived from it).\n\n" + enforcement_note,
        "## Identity\n\n"
        f"- Git author: {identity.get('git_name', persona.name)} / {identity.get('git_email', '')}\n"
        f"- Commit prefix: `{identity.get('commit_prefix', persona.slug + ':')}`\n"
        f"- Routing label: `{identity.get('routing_label', 'agent-' + persona.slug)}`\n\n"
        "Before committing, set per-repo git config:\n\n"
        f"    git config user.name \"{identity.get('git_name', persona.name)}\"\n"
        f"    git config user.email \"{identity.get('git_email', '')}\"",
        "## Workspaces\n\n| Repo | Path | Owns |\n|---|---|---|\n" + "\n".join(workspaces),
        "## Scope\n\n" + str(scope.get("summary", "")).strip() + ("\n\n" + focus if focus else ""),
        "## Session-start ritual (every session, in order)\n\n"
        + "\n".join(f"{i}. {step}" for i, step in enumerate(ritual, 1)),
        "## What you may do\n\n" + "\n".join(f"- {l}" for l in allow_lines),
        never_heading + "\n\n"
        + "\n".join(f"- {l}" for l in deny_lines)
        + "\n- Never `git add -A` / `git add .` (stage only intended files; avoids leaking secrets).",
        "## Commit workflow\n\n"
        f"Stage only intended files; commit as `{identity.get('commit_prefix', persona.slug + ':')} <type> | <description>`;\n"
        "push per CONVENTIONS.md (`_handoff/` may be direct-pushed; substantive changes go via PR).",
    ]
    return "\n\n".join(lines) + "\n"


#: The runtime invocation each emitted sidecar defaults to (ADR-026). Empty means
#: "fill the PROJECT-OWNED SLOT": baron knows of no headless one-shot invocation for
#: that runtime, and inventing one would be a launcher that fails at 3am, not a
#: turnkey deployable. The slot is always overridable with $BARON_SIDECAR_CMD.
_SIDECAR_RUNTIME_CMD: dict[str, str] = {
    "claude": (
        "claude -p --permission-mode acceptEdits "
        "--allowedTools Bash,Read,Grep,Glob,Write,Edit"
    ),
    "code-puppy": "",
    "pydantic-ai": "",
    "generic": "",
}


def _sidecar_script(persona: Persona, ctx: _Context, data: dict) -> str:
    """``agents/<slug>/sidecar.sh`` — the persona's launcher (ADR-026).

    A thin wrapper over ``baron sidecar run``: baron owns sync/sweep/commit/push,
    the script owns the runtime invocation, because the model loop is the
    runtime's (ADR-007). ``runtime.trigger`` from the persona spec decides the
    loop form (ADR-026 §6 Q2) and is rendered into the header.
    """
    runtime_block = data.get("runtime")
    trigger = "interactive"
    if isinstance(runtime_block, dict) and runtime_block.get("trigger"):
        trigger = str(runtime_block["trigger"])
    return _fill(
        read_template("collab-repo/agents/__SIDECAR__/sidecar.sh"),
        {
            "PERSONA_NAME": persona.name,
            "PERSONA_SLUG": persona.slug,
            "PROJECT_NAME": ctx.project,
            "DATE": ctx.date,
            "RUNTIME": ctx.runtime,
            "TRIGGER": trigger,
            "RUNTIME_CMD": _SIDECAR_RUNTIME_CMD.get(ctx.runtime, ""),
        },
        where="collab-repo/agents/__SIDECAR__/sidecar.sh",
    )


def _emit_runtime_kit(root: Path, persona: Persona, ctx: _Context, created: list[str]) -> None:
    kit = root / "agents" / persona.slug / "runtime"
    data = _persona_data(root, persona)

    def write(rel: str, content: str) -> None:
        path = kit / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(path.relative_to(root).as_posix())

    write("README.md", _kit_readme(persona, ctx))
    if ctx.runtime == "claude":
        write("CLAUDE.md", _context_file(persona, ctx, data, tier2=True))
        write(".claude/settings.json", _claude_settings(persona, ctx))
    elif ctx.runtime == "pydantic-ai":
        write(
            "agent_setup.py",
            render_pydantic_ai_bootstrap(
                Path("agents") / persona.slug / "persona.yaml", collab_root=Path(".")
            ),
        )
    else:  # generic, code-puppy (Tier-1 fallback per its HYDRATE.md)
        write("AGENTS.md", _context_file(persona, ctx, data, tier2=False))

    # The sidecar sits BESIDE the kit it launches (agents/<slug>/sidecar.sh):
    # kit = what the persona is, sidecar = how it is deployed (ADR-026).
    script = kit.parent / "sidecar.sh"
    script.write_text(_sidecar_script(persona, ctx, data), encoding="utf-8")
    script.chmod(0o755)
    created.append(script.relative_to(root).as_posix())


# --- the scaffold ----------------------------------------------------------------------


def scaffold(
    project_name: str,
    dest: Path,
    *,
    code_repo: str | None = None,
    personas: list[Persona],
    runtime: str = "claude",
    do_git: bool = True,
    in_monorepo: bool = False,
) -> InitReport:
    if not _NAME_RE.match(project_name):
        raise ScaffoldError(
            f"project name {project_name!r} must match [A-Za-z0-9][A-Za-z0-9._-]* "
            "(it becomes the git identity domain <slug>@<project>.local)"
        )
    if runtime not in RUNTIMES:
        raise ScaffoldError(f"unknown runtime {runtime!r} — pick from {', '.join(RUNTIMES)}")
    if dest.exists() and any(dest.iterdir()):
        raise ScaffoldError(
            f"{dest} already exists and is not empty — refusing to scaffold over it"
        )
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()

    code_label, code_rel, code_remote = _resolve_code_repo(code_repo, root)
    ctx = _Context(
        project=project_name,
        root=root,
        # In a monorepo the "collab repo" a runtime kit points back at is
        # <monorepo>/<project>, so the kit's relative paths need both levels.
        collab_dir=f"{root.parent.name}/{root.name}" if in_monorepo else root.name,
        date=clock.today().isoformat(),
        personas=personas,
        runtime=runtime,
        code_label=code_label,
        code_rel=code_rel,
        code_remote=code_remote,
        in_monorepo=in_monorepo,
    )
    report = InitReport(root=root, personas=personas, runtime=runtime)
    created = report.created

    def write(rel: str, content: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(rel)

    def copy(template_rel: str, rel: str, mapping: dict[str, str] | None = None) -> None:
        text = read_template(template_rel)
        if mapping is not None:
            text = _fill(text, mapping, where=template_rel)
        write(rel, text)

    docs = _doc_mapping(ctx)
    # Rules + docs (filled) and generated surfaces.
    copy("collab-repo/CONVENTIONS.md", "CONVENTIONS.md", docs)
    copy("collab-repo/COORDINATION.md", "COORDINATION.md", docs)
    write("README.md", _readme(ctx))
    write("manifest.yaml", _manifest(ctx))
    write("backlog.md", _backlog(ctx))
    # canon/ + adapters/ — verbatim (ORCHESTRATE.md §2a: copy, never hand-edit).
    for name in CANON_ENTRYPOINTS:
        copy(f"collab-repo/{name}", f"canon/{name}")
    for name in CANON_REFERENCES:
        copy(f"references/{name}", f"canon/{name}")
    for adapter in ADAPTERS:
        copy(f"collab-repo/adapters/{adapter}/HYDRATE.md", f"adapters/{adapter}/HYDRATE.md")
    # Personas (canonical yaml, hydrated).
    for persona in personas:
        write(f"agents/{persona.slug}/persona.yaml", _hydrate_persona(persona, ctx))
    # Coordination surfaces.
    copy("collab-repo/_handoff/README.md", "_handoff/README.md", docs)
    write(f"_handoff/{ctx.date}-bootstrap-to-{ctx.librarian.slug}-genesis.md", _genesis_handoff(ctx))
    copy("collab-repo/findings/README.md", "findings/README.md", docs)
    write("findings/index.md", _ledger_index(ctx, "findings"))
    copy("collab-repo/decisions/README.md", "decisions/README.md", docs)
    write("decisions/index.md", _ledger_index(ctx, "decisions"))
    copy("collab-repo/wiki/README.md", "wiki/README.md", docs)
    copy("collab-repo/wiki/index.md", "wiki/index.md", docs)
    write("wiki/log.md", _wiki_log(ctx))
    # CI is owned ONCE per git repo. In a monorepo that repo is the root, which
    # already carries the three workflows (baron.monorepo.create_root) — emitting
    # them again per subdir would give GitHub N copies of the same triggers.
    if not in_monorepo:
        copy("collab-repo/.github/workflows/lock-guard.yml", ".github/workflows/lock-guard.yml")
        copy(
            "collab-repo/.github/workflows/strip-stale-verdict.yml",
            ".github/workflows/strip-stale-verdict.yml",
        )
        copy(
            "collab-repo/.github/workflows/baron-notify.yml",
            ".github/workflows/baron-notify.yml",
        )
    # Runtime kits (deterministic floor; Tier-3 stays conversational — see module doc).
    for persona in personas:
        _emit_runtime_kit(root, persona, ctx, created)

    # Self-check: everything just written must pass `baron validate`.
    #
    # runtime_drift=False scopes this to the SPEC init actually wrote. The drift
    # check (P2.3) reads the surrounding environment — registries in sibling repos
    # and under ~/ — which init neither created nor can fix, so a failure there
    # would be init blaming itself for someone else's machine. Concretely: a user
    # whose ~/.claude/agents already holds an agent matching ONE of the new
    # persona slugs would hit the partial-registration signal and see `baron init`
    # fail its own output. Init validates what it emitted; `baron validate` (which
    # init prints as the next step) validates the environment.
    findings, _files, _skipped = validate_mod.validate_path(root, runtime_drift=False)
    errors = [f for f in findings if f.severity == "error"]
    if errors:
        detail = "; ".join(f"{f.file}: {f.message}" for f in errors[:5])
        raise ScaffoldError(f"scaffold failed its own validation (bug): {detail}")

    if do_git:
        if shutil.which("git") is None:
            report.notes.append("git not found — skipped repo init; run `git init -b main` later")
        else:
            try:
                git(root, "init", "-q", "-b", "main")
                report.git_initialized = True
                git(root, "add", "--", *created)
                git(root, "commit", "-q", "-m",
                    f"baron: init | scaffold {project_name} collab repo "
                    f"({len(personas)} personas, runtime {runtime})")
                report.git_committed = True
            except GitError as exc:
                report.notes.append(
                    f"git setup incomplete ({exc}) — the files are all written; "
                    "commit manually once git identity is configured"
                )
    return report
