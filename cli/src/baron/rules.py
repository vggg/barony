"""Loader for the versioned capability-rules artifact (ADR-004 addendum §4.1,
ADR-016).

``data/capability-rules.v1.yaml`` is THE single machine-readable source for the
verb→enforcement rule table: command patterns (git push/merge, gh pr merge),
file-operation scoping semantics, and the conservative-deny ambiguity policy.
It ships as baron package data (``importlib.resources``) so every consumer —
``baron guard`` (the Claude Code PreToolUse hook) and the runtime adapters
under :mod:`baron.runtimes` — reads the same rules instead of restating them.

**Representation (ADR-016).** The parsed rules are a *list* of typed rules —
:class:`CommandRule` and :class:`PathRule`, each with a stable ``id``, a
``matcher`` drawn from a closed set, and a ``source`` provenance tag — not a
flat field-per-rule record. The flat names guard grew up with
(``push_force_flags``, ``gh_pr_merge_subcommand``, ``universal_write_components``,
…) survive as derived read-only properties with identical names and types, so
:mod:`baron.guard` and :mod:`baron.runtimes.pydantic_ai` are untouched by the
change. The list form is what makes an *additional* rule representable at all;
the flat form structurally could not hold one.

**What this module does NOT do.** It does not load project-level rules. There
is no ``.baron/rules.yaml`` discovery, no merge, no precedence. :func:`load_rules`
reads packaged data only. :func:`parse_text` will validate an arbitrary rules
document (that is what ``baron rules validate --file`` uses) but validating a
file does not make it effective anywhere — see ADR-016 §5 for why the loader is
deferred and what one-way doors it has to settle first.

**Version negotiation.** ``rules_version`` is matched EXACTLY against
:data:`SUPPORTED_RULES_VERSION` and ``vocabulary`` EXACTLY against
:data:`SUPPORTED_VOCABULARY`. A consumer must refuse rules it does not
understand rather than silently mis-enforce them; a refusal reaches guard as a
:class:`RulesError` and guard fails CLOSED.

**Refuse, don't ignore.** The same principle applies inside the document. The
parser enumerates the keys and rules the document actually carries and refuses
any it does not implement — an unrecognised key at any level, a rule slot this
baron has no matcher for, an unknown ``matcher`` (or one other than the matcher
guard implements for that rule), a missing built-in rule, a missing required
parameter. Silently dropping an unrecognised rule is the worst failure mode an
enforcement artifact has: the document says a thing is blocked and nothing
blocks it.

**Enforcement labelling is measured, not asserted.** :meth:`CapabilityRules.label`
returns ``enforced`` only where guard mechanically checks the verb. See
:data:`LABEL_CAVEAT` for why the whole-tool read verbs do not qualify.

The prose contract for consumers lives in the skill:
``skills/barony/references/capability-rules.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

import yaml

RULES_RESOURCE = "data/capability-rules.v1.yaml"
#: The rules_version this baron understands. A consumer must refuse rules it
#: does not understand rather than silently mis-enforce them. Negotiation is
#: EXACT-match, deliberately: widening it to a supported range is a
#: compatibility contract that cannot be tightened later (ADR-016 §5.3).
SUPPORTED_RULES_VERSION = 1
#: The capability vocabulary the rules are written against. Rules mapping a
#: different vocabulary are refused for the same reason as an unknown version.
SUPPORTED_VOCABULARY = "capability-vocab.v1"

# --- closed matcher sets ---------------------------------------------------------------
# A matcher names the *shape* of the check guard performs. The set is closed:
# guard hand-dispatches on it, so a rule naming an unknown matcher is a rule no
# consumer can honestly enforce and is refused at parse time. Adding a matcher
# is new detection code in guard.py, not a config line (docs/BACKLOG.md
# § "User-extensible guard rules" — the expensive half).

#: A listed flag (or flag prefix) appears in the subcommand's arguments.
MATCHER_FLAG_PRESENT = "flag_present"
#: A refspec carries the configured prefix (``+refspec`` = a force push).
MATCHER_REFSPEC_PREFIX = "refspec_prefix"
#: A refspec's destination resolves to the repo's default branch.
MATCHER_REFSPEC_DEFAULT_BRANCH = "refspec_default_branch"
#: The repo's CURRENT branch is the default branch.
MATCHER_CURRENT_BRANCH_IS_DEFAULT = "current_branch_is_default"
#: A subcommand path (``gh pr merge``) appears in the token stream.
MATCHER_SUBCOMMAND_PRESENT = "subcommand_present"

COMMAND_MATCHERS = frozenset(
    {
        MATCHER_FLAG_PRESENT,
        MATCHER_REFSPEC_PREFIX,
        MATCHER_REFSPEC_DEFAULT_BRANCH,
        MATCHER_CURRENT_BRANCH_IS_DEFAULT,
        MATCHER_SUBCOMMAND_PRESENT,
    }
)

#: Path components that are always writable (gating them bricks the substrate).
MATCHER_UNIVERSAL_WRITE = "universal_write"
#: The persona spec-dir rule: own slug writable, another slug needs a verb.
MATCHER_SPEC_DIR = "spec_dir"

PATH_MATCHERS = frozenset({MATCHER_UNIVERSAL_WRITE, MATCHER_SPEC_DIR})

#: Provenance of a rule. Only ``builtin`` exists today; the tag is here so a
#: future project-level loader cannot omit it (and so `baron rules list`/`diff`
#: can always say where a rule came from).
SOURCE_BUILTIN = "builtin"

# --- stable rule ids -------------------------------------------------------------------
# The ids ARE the public handle for a rule (`baron rules explain` prints them,
# `baron rules diff` joins on them). Renaming one is a breaking change.

RULE_PUSH_FORCE_FLAGS = "git.push.force_flags"
RULE_PUSH_PLUS_REFSPEC = "git.push.plus_refspec"
RULE_PUSH_ALL_BRANCHES = "git.push.all_branches"
RULE_PUSH_DEFAULT_BRANCH = "git.push.default_branch_target"
RULE_MERGE_ON_DEFAULT_BRANCH = "git.merge.on_default_branch"
RULE_GH_PR_MERGE = "gh.pr_merge"
RULE_UNIVERSAL_WRITE = "file_ops.universal_write"
RULE_SPEC_DIR = "file_ops.spec_dir"

#: Value-option scopes: options that consume the following token and so must be
#: skipped while parsing. Keyed by ``<program>`` (global) or
#: ``<program>.<subcommand>``.
SCOPE_GIT_GLOBAL = "git"
SCOPE_GIT_PUSH = "git.push"

#: The verb the spec-dir path rule requires for another persona's spec dir.
#: The v1 artifact carries the components but not this verb, and `guard.py`
#: names it literally; `test_rules.py` asserts the two agree so the pair cannot
#: drift silently. Moving it into the artifact is a `rules_version` bump.
SPEC_DIR_VERB = "edit_other_personas"

# --- enforcement labelling -------------------------------------------------------------
# House rule (ADR-002/ADR-008): never claim enforcement that was not mechanised.
# Three states describing WHO could enforce a verb — but only one of them earns
# the word "enforced" (see `label`), because only one of them is something baron
# itself does.

#: guard mechanically checks this verb (detection is `command` or `file-op`).
#: This is the ONLY state that labels as `enforced`.
ENFORCEMENT_GUARD = "guard"
#: No guard detection, but the class is whole-tool, so a runtime adapter with a
#: tool allow-list *could* enforce it by omitting the tool. Whether any adapter
#: actually does is a property of that adapter, not of this table — and the one
#: adapter baron ships does NOT (see :data:`LABEL_CAVEAT`). Labels as
#: `instructed`, because nothing baron ships enforces it.
ENFORCEMENT_ADAPTER_DEPENDENT = "adapter-dependent"
#: No guard detection and sub-tool class — the denial is prose in the persona
#: body and nothing checks it.
ENFORCEMENT_INSTRUCTED = "instructed"

#: Why `adapter-dependent` does not mean `enforced`. MEASURED, not assumed:
#: `cli/tests/test_pydantic_ai.py::test_denying_read_code_does_not_omit_read_tools`
#: hydrates a persona that denies `read_code` and asserts the read tools are
#: still there. If an adapter ever does omit them, that test is what changes
#: first, and the label follows it — not the other way round.
LABEL_CAVEAT = (
    "`enforced` means baron's guard mechanically checks the call. "
    "`adapter-dependent` verbs are NOT checked by guard and are NOT enforced by "
    "the pydantic-ai adapter baron ships: it constructs FileSystem "
    "unconditionally, so read_file/list_directory/search_files remain available "
    "to a persona that denies read_code (measured by "
    "test_denying_read_code_does_not_omit_read_tools). A runtime with a tool "
    "allow-list could enforce them by omitting the tool; no adapter baron ships "
    "does, so they label as `instructed`."
)


class RulesError(RuntimeError):
    """A rules artifact is missing, unparseable, or unsupported."""


@dataclass(frozen=True)
class CommandRule:
    """One command-detection rule: ``<program> <subcommand...>`` + a matcher."""

    id: str
    program: str  # "git" | "gh"
    subcommand: tuple[str, ...]  # ("push",) / ("pr", "merge")
    matcher: str  # one of COMMAND_MATCHERS
    verb: str  # the capability verb a match implies
    flags: tuple[str, ...] = ()  # MATCHER_FLAG_PRESENT
    flag_prefixes: tuple[str, ...] = ()  # MATCHER_FLAG_PRESENT
    prefix: str = ""  # MATCHER_REFSPEC_PREFIX
    fallback_branches: tuple[str, ...] = ()  # MATCHER_REFSPEC_DEFAULT_BRANCH
    source: str = SOURCE_BUILTIN

    @property
    def kind(self) -> str:
        return "command"


@dataclass(frozen=True)
class PathRule:
    """One file-operation scoping rule over normalized path components."""

    id: str
    matcher: str  # one of PATH_MATCHERS
    components: tuple[str, ...]
    verb: str = ""  # "" when a match needs no verb (universal write zones)
    source: str = SOURCE_BUILTIN

    @property
    def kind(self) -> str:
        return "path"


Rule = CommandRule | PathRule


@dataclass(frozen=True)
class CapabilityRules:
    """The typed view of a capability-rules artifact that guard logic consumes.

    The rule LIST (``command_rules`` / ``path_rules``) is the representation;
    every ``push_*`` / ``gh_*`` / ``*_component`` name below is a derived
    read-only property kept for the consumers that predate ADR-016.
    """

    rules_version: int
    vocabulary: str
    ambiguity_policy: str
    #: verb -> {"class": ..., "detection": ..., "notes": ...}
    verbs: dict[str, dict[str, str]]
    command_rules: tuple[CommandRule, ...]
    path_rules: tuple[PathRule, ...]
    #: scope -> options that consume the following token (parsing mechanics,
    #: not policy). Keyed by SCOPE_GIT_GLOBAL / SCOPE_GIT_PUSH.
    value_options: dict[str, tuple[str, ...]]

    _index: dict[str, Rule] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        index: dict[str, Rule] = {}
        for rule in (*self.command_rules, *self.path_rules):
            if rule.id in index:
                raise RulesError(f"capability-rules: duplicate rule id {rule.id!r}")
            index[rule.id] = rule
        object.__setattr__(self, "_index", index)

    # --- rule access ---------------------------------------------------------

    @property
    def rules(self) -> tuple[Rule, ...]:
        """Every rule, command rules first — the order `baron rules` prints."""
        return (*self.command_rules, *self.path_rules)

    def rule(self, rule_id: str) -> Rule:
        try:
            return self._index[rule_id]
        except KeyError:
            raise RulesError(f"capability-rules: no rule with id {rule_id!r}") from None

    def _command(self, rule_id: str) -> CommandRule:
        rule = self.rule(rule_id)
        if not isinstance(rule, CommandRule):
            raise RulesError(f"capability-rules: rule {rule_id!r} is not a command rule")
        return rule

    def _path(self, rule_id: str) -> PathRule:
        rule = self.rule(rule_id)
        if not isinstance(rule, PathRule):
            raise RulesError(f"capability-rules: rule {rule_id!r} is not a path rule")
        return rule

    # --- enforcement labelling ----------------------------------------------

    def enforcement(self, verb: str) -> str:
        """Who *could* enforce `verb` — see the ENFORCEMENT_* constants."""
        entry = self.verbs.get(verb, {})
        if entry.get("detection", "none") != "none":
            return ENFORCEMENT_GUARD
        if entry.get("class") == "whole-tool":
            return ENFORCEMENT_ADAPTER_DEPENDENT
        return ENFORCEMENT_INSTRUCTED

    def label(self, verb: str) -> str:
        """The blunt two-state label: ``enforced`` or ``instructed``.

        ``enforced`` iff guard mechanically checks the verb. ``adapter-dependent``
        deliberately labels ``instructed``: no adapter baron ships omits the
        tools that would make it real (:data:`LABEL_CAVEAT`).
        """
        return "enforced" if self.enforcement(verb) == ENFORCEMENT_GUARD else "instructed"

    def caveat(self, verb: str) -> str:
        """The honesty qualifier for `verb`'s label, or ``""`` if none applies."""
        return LABEL_CAVEAT if self.enforcement(verb) == ENFORCEMENT_ADAPTER_DEPENDENT else ""

    # --- derived legacy accessors (pre-ADR-016 names, unchanged types) -------

    @property
    def git_global_value_options(self) -> tuple[str, ...]:
        return self.value_options.get(SCOPE_GIT_GLOBAL, ())

    @property
    def push_value_options(self) -> tuple[str, ...]:
        return self.value_options.get(SCOPE_GIT_PUSH, ())

    @property
    def push_force_flags(self) -> tuple[str, ...]:
        return self._command(RULE_PUSH_FORCE_FLAGS).flags

    @property
    def push_force_flag_prefixes(self) -> tuple[str, ...]:
        return self._command(RULE_PUSH_FORCE_FLAGS).flag_prefixes

    @property
    def push_force_verb(self) -> str:
        return self._command(RULE_PUSH_FORCE_FLAGS).verb

    @property
    def push_plus_refspec_prefix(self) -> str:
        return self._command(RULE_PUSH_PLUS_REFSPEC).prefix

    @property
    def push_all_branch_flags(self) -> tuple[str, ...]:
        return self._command(RULE_PUSH_ALL_BRANCHES).flags

    @property
    def push_all_branches_verb(self) -> str:
        return self._command(RULE_PUSH_ALL_BRANCHES).verb

    @property
    def push_default_branch_fallbacks(self) -> tuple[str, ...]:
        return self._command(RULE_PUSH_DEFAULT_BRANCH).fallback_branches

    @property
    def push_default_branch_verb(self) -> str:
        return self._command(RULE_PUSH_DEFAULT_BRANCH).verb

    @property
    def merge_on_default_branch_verb(self) -> str:
        return self._command(RULE_MERGE_ON_DEFAULT_BRANCH).verb

    @property
    def gh_pr_merge_subcommand(self) -> tuple[str, ...]:
        return self._command(RULE_GH_PR_MERGE).subcommand

    @property
    def gh_pr_merge_verb(self) -> str:
        return self._command(RULE_GH_PR_MERGE).verb

    @property
    def universal_write_components(self) -> tuple[str, ...]:
        return self._path(RULE_UNIVERSAL_WRITE).components

    @property
    def spec_dir_component(self) -> str:
        components = self._path(RULE_SPEC_DIR).components
        return components[0] if components else ""


def _strs(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise RulesError(f"capability-rules: {where} must be a list of strings")
    return tuple(value)


# --- strict document grammar -----------------------------------------------------------
# ADR-016 §5.4's refuse-don't-ignore rule applies to the document itself: the
# parser enumerates the keys actually PRESENT and refuses any it does not
# recognise. Silently dropping an unrecognised rule is the worst possible
# failure mode for an enforcement artifact — the document says a thing is
# blocked and nothing blocks it.


def _mapping(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RulesError(f"capability-rules: {where} must be a mapping")
    return {str(k): v for k, v in value.items()}


def _only(mapping: dict[str, object], allowed: frozenset[str], where: str) -> None:
    """Refuse any key `where` does not recognise (never ignore it)."""
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise RulesError(
            f"capability-rules: {where} has unrecognised key(s) "
            f"{', '.join(repr(k) for k in unknown)} — refusing rather than "
            f"silently ignoring them (recognised: {', '.join(sorted(allowed))})"
        )


_TOP_LEVEL_KEYS = frozenset(
    {"rules_version", "vocabulary", "ambiguity_policy", "verbs", "commands", "file_ops"}
)
_VERB_ENTRY_KEYS = frozenset({"class", "detection", "notes"})
_FILE_OPS_KEYS = frozenset({"universal_write_components", "spec_dir_component"})


@dataclass(frozen=True)
class _CommandSlot:
    """A built-in command-rule slot: a document key guard knows how to read.

    ``matcher`` is the matcher :mod:`baron.guard` *actually implements* for this
    slot. The document must name the same one (or the artifact would be
    describing a check nobody performs), so the field is validated against this,
    not merely against the closed set.
    """

    program: str
    subcommand: tuple[str, ...]  # () = the rule supplies its own
    matcher: str
    params: tuple[str, ...]  # required parameter keys, beyond verb/matcher


#: rule id -> slot. The ids are structural: ``<section prefix><document key>``.
_COMMAND_SLOTS: dict[str, _CommandSlot] = {
    RULE_PUSH_FORCE_FLAGS: _CommandSlot(
        "git", ("push",), MATCHER_FLAG_PRESENT, ("flags", "flag_prefixes")
    ),
    RULE_PUSH_PLUS_REFSPEC: _CommandSlot(
        "git", ("push",), MATCHER_REFSPEC_PREFIX, ("prefix",)
    ),
    RULE_PUSH_ALL_BRANCHES: _CommandSlot(
        "git", ("push",), MATCHER_FLAG_PRESENT, ("flags",)
    ),
    RULE_PUSH_DEFAULT_BRANCH: _CommandSlot(
        "git", ("push",), MATCHER_REFSPEC_DEFAULT_BRANCH, ("fallback_branches",)
    ),
    RULE_MERGE_ON_DEFAULT_BRANCH: _CommandSlot(
        "git", ("merge",), MATCHER_CURRENT_BRANCH_IS_DEFAULT, ()
    ),
    RULE_GH_PR_MERGE: _CommandSlot("gh", (), MATCHER_SUBCOMMAND_PRESENT, ("subcommand",)),
}

#: (document path to the rules block, rule-id prefix). Enumerated so that a
#: rules block appearing anywhere else in the document is refused too.
_COMMAND_SECTIONS: tuple[tuple[str, str], ...] = (
    ("commands.git.push.rules", "git.push."),
    ("commands.git.merge.rules", "git.merge."),
    ("commands.gh.rules", "gh."),
)


def _matcher_of(body: dict[str, object], rule_id: str, slot: _CommandSlot) -> str:
    """Read the rule's ``matcher`` from the document and validate it.

    Optional but AUTHORITATIVE. Absent -> the slot's matcher (so a document
    written against an earlier v1 parser still reads identically). Present ->
    it must be in the closed set AND must be the matcher guard implements for
    this slot; anything else is refused, because accepting it would print an
    enforcement label over a check nobody performs.
    """
    raw = body.get("matcher")
    if raw is None:
        return slot.matcher
    if not isinstance(raw, str):
        raise RulesError(f"capability-rules: {rule_id}.matcher must be a string")
    if raw not in COMMAND_MATCHERS:
        raise RulesError(
            f"capability-rules: rule {rule_id!r} names unknown matcher {raw!r} — "
            f"no consumer can enforce it (known: {', '.join(sorted(COMMAND_MATCHERS))})"
        )
    if raw != slot.matcher:
        raise RulesError(
            f"capability-rules: rule {rule_id!r} declares matcher {raw!r} but guard "
            f"implements {slot.matcher!r} for that rule — refusing to describe a "
            "check that is not the one performed"
        )
    return raw


def _command_rule(
    rule_id: str, body: dict[str, object], verbs: dict[str, dict[str, str]]
) -> CommandRule:
    slot = _COMMAND_SLOTS[rule_id]
    _only(body, frozenset({"verb", "matcher", *slot.params}), rule_id)
    verb = body.get("verb")
    if not isinstance(verb, str) or verb not in verbs:
        raise RulesError(
            f"capability-rules: {rule_id}.verb missing or not in the verbs table"
        )
    missing = [p for p in slot.params if p not in body]
    if missing:
        raise RulesError(
            f"capability-rules: rule {rule_id!r} is missing required key(s) "
            f"{', '.join(repr(m) for m in missing)}"
        )
    subcommand = slot.subcommand or _strs(body.get("subcommand"), f"{rule_id}.subcommand")
    prefix = body.get("prefix", "")
    if "prefix" in slot.params and not isinstance(prefix, str):
        raise RulesError(f"capability-rules: {rule_id}.prefix must be a string")
    return CommandRule(
        id=rule_id,
        program=slot.program,
        subcommand=subcommand,
        matcher=_matcher_of(body, rule_id, slot),
        verb=verb,
        flags=_strs(body["flags"], f"{rule_id}.flags") if "flags" in slot.params else (),
        flag_prefixes=(
            _strs(body["flag_prefixes"], f"{rule_id}.flag_prefixes")
            if "flag_prefixes" in slot.params
            else ()
        ),
        prefix=str(prefix) if "prefix" in slot.params else "",
        fallback_branches=(
            _strs(body["fallback_branches"], f"{rule_id}.fallback_branches")
            if "fallback_branches" in slot.params
            else ()
        ),
    )


def _dig(data: dict[str, object], path: str) -> dict[str, object]:
    """Walk a dotted document path, requiring a mapping at every level."""
    node: dict[str, object] = data
    for i, part in enumerate(path.split(".")):
        if part not in node:
            raise RulesError(f"capability-rules: missing section {path!r}")
        node = _mapping(node[part], ".".join(path.split(".")[: i + 1]))
    return node


def _parse_command_rules(
    data: dict[str, object], verbs: dict[str, dict[str, str]]
) -> tuple[CommandRule, ...]:
    """Build the command rules from the keys the DOCUMENT actually carries."""
    commands = _mapping(data.get("commands"), "commands")
    _only(commands, frozenset({"git", "gh"}), "commands")
    git = _mapping(commands.get("git", {}), "commands.git")
    _only(git, frozenset({"global_value_options", "push", "merge"}), "commands.git")
    _only(
        _mapping(git.get("push", {}), "commands.git.push"),
        frozenset({"value_options", "rules"}),
        "commands.git.push",
    )
    _only(
        _mapping(git.get("merge", {}), "commands.git.merge"),
        frozenset({"rules"}),
        "commands.git.merge",
    )
    _only(
        _mapping(commands.get("gh", {}), "commands.gh"),
        frozenset({"rules"}),
        "commands.gh",
    )

    rules: list[CommandRule] = []
    for path, prefix in _COMMAND_SECTIONS:
        block = _dig(data, path)
        for key in block:
            rule_id = f"{prefix}{key}"
            if rule_id not in _COMMAND_SLOTS:
                raise RulesError(
                    f"capability-rules: {path}.{key} is not a rule this baron "
                    f"implements — refusing rather than silently ignoring it "
                    f"(implemented here: "
                    f"{', '.join(sorted(k for k in _COMMAND_SLOTS if k.startswith(prefix)))})"
                )
            rules.append(_command_rule(rule_id, _mapping(block[key], rule_id), verbs))

    found = {rule.id for rule in rules}
    absent = sorted(set(_COMMAND_SLOTS) - found)
    if absent:
        raise RulesError(
            f"capability-rules: document omits built-in rule(s) "
            f"{', '.join(repr(a) for a in absent)} — guard reads them, so an "
            "artifact without them cannot be enforced"
        )
    # Table order is the order `baron rules` prints and `guard` documents.
    order = list(_COMMAND_SLOTS)
    return tuple(sorted(rules, key=lambda r: order.index(r.id)))


def _parse(data: object) -> CapabilityRules:
    if not isinstance(data, dict):
        raise RulesError("capability-rules: top level is not a mapping")
    data = {str(k): v for k, v in data.items()}
    _only(data, _TOP_LEVEL_KEYS, "capability-rules")
    version = data.get("rules_version")
    if version != SUPPORTED_RULES_VERSION:
        raise RulesError(
            f"capability-rules: rules_version {version!r} is not the supported "
            f"version {SUPPORTED_RULES_VERSION} — refusing to mis-enforce"
        )
    vocabulary = data.get("vocabulary")
    if vocabulary != SUPPORTED_VOCABULARY:
        raise RulesError(
            f"capability-rules: vocabulary {vocabulary!r} is not the supported "
            f"vocabulary {SUPPORTED_VOCABULARY!r} — refusing to mis-enforce"
        )
    verbs_raw = data.get("verbs")
    if not isinstance(verbs_raw, dict) or not verbs_raw:
        raise RulesError("capability-rules: no verbs table")
    verbs: dict[str, dict[str, str]] = {}
    for verb, entry in verbs_raw.items():
        entry_map = _mapping(entry, f"verbs.{verb}")
        _only(entry_map, _VERB_ENTRY_KEYS, f"verbs.{verb}")
        verbs[str(verb)] = {k: str(v) for k, v in entry_map.items()}

    git = _mapping(_mapping(data.get("commands"), "commands").get("git", {}), "commands.git")
    push = _mapping(git.get("push", {}), "commands.git.push")

    file_ops = _mapping(data.get("file_ops"), "file_ops")
    _only(file_ops, _FILE_OPS_KEYS, "file_ops")

    if SPEC_DIR_VERB not in verbs:
        raise RulesError(
            f"capability-rules: file_ops.spec_dir verb {SPEC_DIR_VERB!r} is not in "
            "the verbs table"
        )

    command_rules = _parse_command_rules(data, verbs)

    spec_dir_component = str(file_ops.get("spec_dir_component", ""))
    path_rules = (
        PathRule(
            id=RULE_UNIVERSAL_WRITE,
            matcher=MATCHER_UNIVERSAL_WRITE,
            components=_strs(
                file_ops.get("universal_write_components"),
                "file_ops.universal_write_components",
            ),
        ),
        PathRule(
            id=RULE_SPEC_DIR,
            matcher=MATCHER_SPEC_DIR,
            components=(spec_dir_component,) if spec_dir_component else (),
            verb=SPEC_DIR_VERB,
        ),
    )

    # Command-rule matchers are validated against the closed set in
    # `_matcher_of`, from the document. PATH-rule matchers are NOT
    # document-supplied — `file_ops` is a flat block whose keys name the
    # scoping semantics directly, so there is nowhere for a document to state a
    # matcher and nothing for it to get wrong. This loop is therefore a
    # developer-edit guard only, and is deliberately labelled as one rather than
    # counted as document validation (ADR-016 §3.2).
    for path_rule in path_rules:
        if path_rule.matcher not in PATH_MATCHERS:  # pragma: no cover - dev-edit guard
            raise RulesError(
                f"capability-rules: rule {path_rule.id!r} names unknown matcher "
                f"{path_rule.matcher!r} — no consumer can enforce it"
            )

    return CapabilityRules(
        rules_version=int(version),
        vocabulary=str(vocabulary),
        ambiguity_policy=str(data.get("ambiguity_policy", "")),
        verbs=verbs,
        command_rules=command_rules,
        path_rules=path_rules,
        value_options={
            SCOPE_GIT_GLOBAL: _strs(
                git.get("global_value_options"), "commands.git.global_value_options"
            ),
            SCOPE_GIT_PUSH: _strs(
                push.get("value_options"), "commands.git.push.value_options"
            ),
        },
    )


def diff_rules(base: CapabilityRules, other: CapabilityRules) -> dict[str, object]:
    """Structural diff of two parsed rule tables, joined on rule id.

    Pure and side-effect free so ``baron rules diff`` is a renderer over it and
    the add/remove branches can be exercised directly against constructed
    values. That matters: **no document can currently produce a rule addition or
    removal** — the built-in rule set is closed and every slot is mandatory, so
    a document with an extra rule is refused at parse time and one with a rule
    missing is too. ``rules_added`` / ``rules_removed`` exist for the deferred
    project-rules loader (ADR-016 §5) and are covered by unit tests over
    constructed :class:`CapabilityRules`, not by a document fixture.
    """
    base_rules = {rule.id: rule for rule in base.rules}
    other_rules = {rule.id: rule for rule in other.rules}
    header: list[str] = []
    if base.rules_version != other.rules_version:
        header.append(f"rules_version {base.rules_version} -> {other.rules_version}")
    if base.vocabulary != other.vocabulary:
        header.append(f"vocabulary {base.vocabulary} -> {other.vocabulary}")
    if base.ambiguity_policy != other.ambiguity_policy:
        header.append(
            f"ambiguity_policy {base.ambiguity_policy} -> {other.ambiguity_policy}"
        )
    return {
        "header": header,
        "rules_added": sorted(set(other_rules) - set(base_rules)),
        "rules_removed": sorted(set(base_rules) - set(other_rules)),
        "rules_changed": sorted(
            rid
            for rid in set(base_rules) & set(other_rules)
            if base_rules[rid] != other_rules[rid]
        ),
        "verbs_added": sorted(set(other.verbs) - set(base.verbs)),
        "verbs_removed": sorted(set(base.verbs) - set(other.verbs)),
    }


def parse_text(text: str, *, origin: str = "<text>") -> CapabilityRules:
    """Parse + validate a rules document from YAML text.

    Used by :func:`load_rules` for the packaged artifact and by
    ``baron rules validate --file`` for a candidate one. **Validating a file
    does not activate it** — nothing outside the packaged artifact is consumed
    by guard today (ADR-016 §5).
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RulesError(f"{origin}: not valid YAML: {exc}") from exc
    return _parse(data)


def parse_file(path: Path) -> CapabilityRules:
    """Parse + validate a rules document from disk (see :func:`parse_text`)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RulesError(f"cannot read rules file {path}: {exc}") from exc
    return parse_text(text, origin=path.as_posix())


@lru_cache(maxsize=1)
def load_rules() -> CapabilityRules:
    """Load and validate the packaged rules artifact (cached).

    Packaged data only — deliberately takes no path/collab argument, so the
    process-global cache stays correct (ADR-016 §5.5).
    """
    resource = files("baron").joinpath(RULES_RESOURCE)
    try:
        text = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise RulesError(f"capability-rules artifact not packaged: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RulesError(f"capability-rules artifact is not valid YAML: {exc}") from exc
    return _parse(data)
