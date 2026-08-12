"""Static emission harness — *does adapter X emit a mechanism capable of
omitting the runtime tools that verb Y grants?*

**Why this exists (ADR-020).** `rules.label("read_code")` says `instructed`.
Round 3 justified that with one measurement (`pydantic-ai`) and called the other
three adapters *unmeasured* — an honest admission, but it left `baron rules list`
speaking for four adapters on the evidence of one. This harness closes the gap
for the three that were missing.

**The asymmetry that makes it cheap.** Proving the *presence* of enforcement
needs a live runtime — you have to watch a tool call be refused. Proving the
*absence* of a baron-emitted enforcement mechanism is static: enumerate what
`baron init` writes and show that none of it is a construct a runtime reads as
a tool allow/deny list. For the read verbs the answer is negative on all four
adapters, so static inspection is sufficient for three of them and the fourth
(`pydantic-ai`, which emits executable Python) keeps its live gate test.

**The honest bound, and it is in the API.** A negative verdict means *baron
emits no mechanism*. It does **not** mean the runtime cannot enforce the verb.
A user who hand-writes `permissions.deny` into `.claude/settings.json`, or who
follows `adapters/claude/HYDRATE.md` step 3a and hand-authors a Tier-3 subagent
with a minimal `tools:` allow-list, gets real whole-tool enforcement — from
their own artifact, not from one baron generated. `baron rules list` speaks for
what baron ships, and only that.

**Refuse, don't ignore** (the rule `rules.py`'s parser is built on, applied
here). Every artifact baron emits into a runtime kit must be classified in
:data:`KIT_ARTIFACTS`. An artifact the harness has never seen lands in
``Verdict.unclassified`` and the caller must fail — a silent pass on an
unrecognised artifact is exactly how a mechanism would sneak in. Same for
:data:`KIND_CODE`: static inspection cannot clear executable output, so the
harness refuses to and names the live test that can.

**Slice one of the per-runtime capability matrix.** The registry below is keyed
`(adapter, verb)` because the follow-up is the full 4×10 matrix; this pass fills
in the two read verbs. Adding a verb means adding its runtime tool names to
:data:`READ_TOOLS`' sibling tables and a mechanism entry if a new construct can
omit them — not writing a fourth bespoke test.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from typer.testing import CliRunner

from baron import clock, scaffold
from baron.cli import app

runner = CliRunner()

# --- what an artifact is ----------------------------------------------------------------

#: A human/model reads it. Prose cannot omit a tool; at most it can *instruct*.
KIND_PROSE = "prose"
#: A runtime parses it as configuration — the only place a declarative
#: omission mechanism can live.
KIND_CONFIG = "config"
#: Executable output. Static inspection CANNOT clear it (what it registers is a
#: runtime property), so the harness refuses to and names the live measurement.
KIND_CODE = "code"

#: adapter -> the COMPLETE set of artifacts `baron init` writes into
#: ``agents/<slug>/runtime/``, and what a runtime does with each. Closed on
#: purpose: an artifact missing from here is reported as unclassified.
KIT_ARTIFACTS: dict[str, dict[str, str]] = {
    "claude": {
        "README.md": KIND_PROSE,
        "CLAUDE.md": KIND_PROSE,
        ".claude/settings.json": KIND_CONFIG,
    },
    "code-puppy": {
        "README.md": KIND_PROSE,
        "AGENTS.md": KIND_PROSE,
    },
    "generic": {
        "README.md": KIND_PROSE,
        "AGENTS.md": KIND_PROSE,
    },
    "pydantic-ai": {
        "README.md": KIND_PROSE,
        "agent_setup.py": KIND_CODE,
    },
}

#: adapter -> the runtime tool names the read verbs grant, per each adapter's
#: own HYDRATE.md verb→tool table. An omission mechanism for `read_code` /
#: `read_collab` is one that could remove these. `generic` is empty because
#: Tier 1 has no allow-list surface at all ("the runtime hands you everything,
#: and you self-enforce" — adapters/generic/HYDRATE.md §2).
READ_TOOLS: dict[str, tuple[str, ...]] = {
    "claude": ("Read", "Grep", "Glob"),
    "code-puppy": ("read_file", "list_files", "grep"),
    "generic": (),
    "pydantic-ai": ("read_file", "list_directory", "search_files"),
}

#: The verbs this slice covers. The matrix follow-up widens it.
READ_VERBS = ("read_code", "read_collab")

# --- the emission -----------------------------------------------------------------------


@dataclass(frozen=True)
class Artifact:
    path: str  # POSIX, relative to the kit root
    kind: str  # KIND_PROSE | KIND_CONFIG | KIND_CODE | "" when unclassified
    text: str


@dataclass(frozen=True)
class Emission:
    """Everything baron generated into one persona's runtime kit."""

    adapter: str
    slug: str
    root: Path  # the scaffolded collab repo
    kit: Path  # <root>/agents/<slug>/runtime
    artifacts: tuple[Artifact, ...]

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(a.path for a in self.artifacts)

    def of_kind(self, kind: str) -> tuple[Artifact, ...]:
        return tuple(a for a in self.artifacts if a.kind == kind)

    def normalized(self, path: str) -> str:
        """One artifact's text with the persona slug masked.

        The slug is the ONE thing the emitters legitimately vary per persona
        (it is in the hook's `--persona-file` path), so masking it is what makes
        two personas' configs byte-comparable.
        """
        text = next(a.text for a in self.artifacts if a.path == path)
        return text.replace(self.slug, "<slug>")


# --- generating one ---------------------------------------------------------------------


@dataclass(frozen=True)
class Repo:
    """A collab repo generated by the real `baron init`."""

    root: Path
    adapter: str
    project: str


def scaffold_repo(dest: Path, adapter: str, *, project: str = "gardenkit") -> Repo:
    """Run the REAL `baron init` for `adapter`. Returns the collab repo."""
    result = runner.invoke(
        app,
        [
            "init",
            project,
            "--dir",
            str(dest),
            "--personas",
            "dev:carson,librarian:iris",
            "--runtime",
            adapter,
        ],
    )
    assert result.exit_code == 0, result.output
    return Repo(root=dest, adapter=adapter, project=project)


def _context(repo: Repo) -> scaffold._Context:
    """Rebuild the context `baron init` emitted with.

    Reaching into `_Context` is deliberate and contained to this one function:
    the emitters are only reachable through `baron init`, which hydrates
    personas from archetype templates and therefore cannot produce a persona
    that DENIES a read verb — the exact input this harness needs.
    :func:`emit_kit` re-emits an init-created persona first and asserts the
    bytes match, so a drifting reconstruction fails loudly instead of silently
    measuring something baron does not emit.
    """
    return scaffold._Context(
        project=repo.project,
        root=repo.root,
        collab_dir=repo.root.name,
        date=clock.today().isoformat(),
        personas=[scaffold.Persona("dev", "carson"), scaffold.Persona("librarian", "iris")],
        runtime=repo.adapter,
        code_label="(no code repo yet)",
        code_rel=None,
        code_remote=None,
    )


def read_kit(repo: Repo, slug: str) -> Emission:
    """Everything on disk in one persona's runtime kit, classified."""
    kit = repo.root / "agents" / slug / "runtime"
    known = KIT_ARTIFACTS[repo.adapter]
    artifacts = []
    for path in sorted(p for p in kit.rglob("*") if p.is_file()):
        rel = path.relative_to(kit).as_posix()
        artifacts.append(
            Artifact(path=rel, kind=known.get(rel, ""), text=path.read_text(encoding="utf-8"))
        )
    return Emission(
        adapter=repo.adapter, slug=slug, root=repo.root, kit=kit, artifacts=tuple(artifacts)
    )


def emit_kit(repo: Repo, slug: str, persona_yaml: str) -> Emission:
    """Emit the adapter's runtime kit for a hand-written persona spec.

    Self-checks the context reconstruction first: re-emitting `carson`'s kit
    must reproduce what `baron init` already wrote, byte for byte.
    """
    before = {a.path: a.text for a in read_kit(repo, "carson").artifacts}
    ctx = _context(repo)
    scaffold._emit_runtime_kit(repo.root, scaffold.Persona("dev", "carson"), ctx, [])
    after = {a.path: a.text for a in read_kit(repo, "carson").artifacts}
    assert after == before, (
        "the harness's _Context reconstruction no longer reproduces `baron init`'s "
        "own output — fix _context() before trusting any verdict from this harness"
    )

    spec = repo.root / "agents" / slug / "persona.yaml"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(persona_yaml, encoding="utf-8")
    scaffold._emit_runtime_kit(repo.root, scaffold.Persona("dev", slug), ctx, [])
    return read_kit(repo, slug)


# --- the mechanism registry --------------------------------------------------------------


@dataclass(frozen=True)
class Mechanism:
    """A construct that, IF baron emitted it, could omit a runtime tool."""

    id: str
    adapter: str
    construct: str
    documented_at: str
    omits: tuple[str, ...]  # verbs whose tools it could remove; ("*",) = any
    find: Callable[[Emission], tuple[str, ...]]  # evidence found; () = absent


#: Keys in `.claude/settings.json` that gate tool availability. Anything from
#: this set appearing anywhere in the emitted document is a mechanism.
CLAUDE_TOOL_GATING_KEYS = frozenset(
    {"permissions", "allow", "deny", "ask", "allowedTools", "disallowedTools", "tools"}
)

#: The keys the emitted hook wiring is allowed to use. Broader than the gating
#: set above and checked as a closed allowlist, so a NEW key — gating or not —
#: has to be looked at by a human before this harness will pass again.
CLAUDE_SETTINGS_KEYS = frozenset(
    {
        "hooks",
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "SessionStart",
        "SessionEnd",
        "matcher",
        "type",
        "command",
        "timeout",
    }
)


def _json_keys(node: object) -> set[str]:
    if isinstance(node, dict):
        out = set(node)
        for value in node.values():
            out |= _json_keys(value)
        return out
    if isinstance(node, list):
        out: set[str] = set()
        for item in node:
            out |= _json_keys(item)
        return out
    return set()


def settings_keys(emission: Emission) -> set[str]:
    """Every key, at every depth, of the emitted `.claude/settings.json`."""
    keys: set[str] = set()
    for artifact in emission.artifacts:
        if artifact.path.endswith(".json"):
            keys |= _json_keys(json.loads(artifact.text))
    return keys


def _claude_gating_keys(emission: Emission) -> tuple[str, ...]:
    return tuple(sorted(settings_keys(emission) & CLAUDE_TOOL_GATING_KEYS))


def _claude_subagents(emission: Emission) -> tuple[str, ...]:
    return tuple(p for p in emission.paths if p.startswith(".claude/agents/"))


def _agent_json(emission: Emission) -> tuple[str, ...]:
    return tuple(p for p in emission.paths if p.endswith(".json"))


MECHANISMS: tuple[Mechanism, ...] = (
    Mechanism(
        id="claude.settings.tool-gating",
        adapter="claude",
        construct="a `permissions` / `allowedTools` / `disallowedTools` block in "
        ".claude/settings.json — the declarative way to remove a tool from a session",
        documented_at="https://code.claude.com/docs/en/settings",
        omits=("*",),
        find=_claude_gating_keys,
    ),
    Mechanism(
        id="claude.subagent.tools",
        adapter="claude",
        construct="a Tier-3 subagent at .claude/agents/<slug>.md whose frontmatter "
        "`tools:` line is a minimal allow-list (omit the tool and the action is impossible)",
        documented_at="adapters/claude/HYDRATE.md §3a",
        omits=("*",),
        find=_claude_subagents,
    ),
    Mechanism(
        id="code-puppy.agent-json.tools",
        adapter="code-puppy",
        construct="a code-puppy agent JSON whose `tools` list is filtered against "
        "TOOL_REGISTRY — only listed tools are registered for the agent",
        documented_at="adapters/code-puppy/HYDRATE.md §2",
        omits=("*",),
        find=_agent_json,
    ),
)

#: Adapters with NO known omission mechanism to look for, and why. Listed
#: explicitly so "no mechanism entry" can never be confused with "nobody looked".
NO_KNOWN_MECHANISM: dict[str, str] = {
    "generic": (
        "Tier 1 has no tool allow-list surface to emit into — the runtime hands the "
        "agent everything and the persona self-enforces (adapters/generic/HYDRATE.md "
        "§2, §7: 'It emits no ENFORCED artifact')."
    ),
}

#: Artifacts static inspection refuses to clear, and the live test that does.
LIVE_MEASUREMENTS: dict[str, str] = {
    "pydantic-ai": (
        "test_pydantic_ai.py::test_denying_read_code_does_not_omit_read_tools — the "
        "emitted agent_setup.py is executable, so what it registers is measured by "
        "running it, never by reading it"
    ),
}


# --- the probe ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Verdict:
    adapter: str
    verb: str
    inspected: tuple[str, ...]
    #: ``"<mechanism id>: <evidence>"`` — EMPTY means baron emits no mechanism.
    mechanisms: tuple[str, ...]
    #: Artifacts static inspection cannot clear, with the live test that can.
    needs_live_measurement: tuple[str, ...]
    #: Emitted artifacts absent from KIT_ARTIFACTS. Non-empty ⇒ the caller must fail.
    unclassified: tuple[str, ...]

    @property
    def prose_only(self) -> bool:
        return not self.inspected


def _accounted_for(adapter: str) -> bool:
    """Has anyone decided what to look for on this adapter?

    An adapter with no mechanism registered, no recorded reason there is none,
    and no live measurement would sail through :func:`probe` with a clean
    verdict it did nothing to earn. "Nobody looked" must not read as "nothing
    found" — the same distinction the label itself is about.
    """
    return (
        any(m.adapter == adapter for m in MECHANISMS)
        or adapter in NO_KNOWN_MECHANISM
        or adapter in LIVE_MEASUREMENTS
    )


def probe(emission: Emission, verb: str) -> Verdict:
    """Does `emission`'s adapter emit a mechanism capable of omitting `verb`'s tools?"""
    assert _accounted_for(emission.adapter), (
        f"no mechanism is registered for {emission.adapter!r}, and no reason is recorded "
        "for there being none — register one, or record why in NO_KNOWN_MECHANISM / "
        "LIVE_MEASUREMENTS, before this harness will answer for it"
    )
    unclassified = tuple(a.path for a in emission.artifacts if not a.kind)
    inspected = tuple(
        a.path
        for a in emission.artifacts
        if a.kind in (KIND_CONFIG, KIND_CODE)
    )
    needs_live = tuple(
        f"{a.path}: {LIVE_MEASUREMENTS.get(emission.adapter, 'no live measurement named')}"
        for a in emission.of_kind(KIND_CODE)
    )
    hits: list[str] = []
    for mechanism in MECHANISMS:
        if mechanism.adapter != emission.adapter:
            continue
        if mechanism.omits != ("*",) and verb not in mechanism.omits:
            continue
        evidence = mechanism.find(emission)
        if evidence:
            hits.append(f"{mechanism.id}: {', '.join(evidence)}")
    return Verdict(
        adapter=emission.adapter,
        verb=verb,
        inspected=inspected,
        mechanisms=tuple(hits),
        needs_live_measurement=needs_live,
        unclassified=unclassified,
    )


def assert_emits_no_omission_mechanism(verdict: Verdict) -> None:
    """The negative result, asserted with the reason it is trustworthy."""
    assert not verdict.unclassified, (
        f"{verdict.adapter} emits artifacts this harness has never classified: "
        f"{list(verdict.unclassified)} — add them to omission.KIT_ARTIFACTS (and a "
        "Mechanism entry if a runtime could read one as a tool allow-list) before "
        "this verdict means anything"
    )
    assert not verdict.needs_live_measurement, (
        f"{verdict.adapter} emits executable output; static inspection may not clear "
        f"it: {list(verdict.needs_live_measurement)}"
    )
    assert not verdict.mechanisms, (
        f"{verdict.adapter} DOES emit a mechanism capable of omitting "
        f"{verdict.verb}'s tools: {list(verdict.mechanisms)} — re-measure the label "
        "in baron.rules before changing this assertion"
    )
