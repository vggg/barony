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
# Three honest states, not two:

#: guard mechanically checks this verb (detection is `command` or `file-op`).
ENFORCEMENT_GUARD = "guard"
#: no guard detection, but the class is whole-tool — the RUNTIME ADAPTER can
#: enforce it by omitting the tool. Not guard's enforcement, and only real on a
#: runtime with an allow-list.
ENFORCEMENT_TOOL_OMISSION = "tool-omission"
#: no guard detection and sub-tool class — the denial is prose in the persona
#: body and nothing checks it.
ENFORCEMENT_INSTRUCTED = "instructed"


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
        """How `verb` is actually enforced — see the ENFORCEMENT_* constants."""
        entry = self.verbs.get(verb, {})
        if entry.get("detection", "none") != "none":
            return ENFORCEMENT_GUARD
        if entry.get("class") == "whole-tool":
            return ENFORCEMENT_TOOL_OMISSION
        return ENFORCEMENT_INSTRUCTED

    def label(self, verb: str) -> str:
        """The blunt two-state label: ``enforced`` or ``instructed``."""
        return (
            "instructed"
            if self.enforcement(verb) == ENFORCEMENT_INSTRUCTED
            else "enforced"
        )

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


def _parse(data: object) -> CapabilityRules:
    if not isinstance(data, dict):
        raise RulesError("capability-rules: top level is not a mapping")
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
        if not isinstance(entry, dict):
            raise RulesError(f"capability-rules: verbs.{verb} is not a mapping")
        verbs[str(verb)] = {k: str(v) for k, v in entry.items()}

    commands = data.get("commands")
    if not isinstance(commands, dict):
        raise RulesError("capability-rules: no commands table")
    git = commands.get("git") or {}
    push = git.get("push") or {}
    push_rules = push.get("rules") or {}
    merge_rules = (git.get("merge") or {}).get("rules") or {}
    gh_rules = (commands.get("gh") or {}).get("rules") or {}
    force = push_rules.get("force_flags") or {}
    plus = push_rules.get("plus_refspec") or {}
    allb = push_rules.get("all_branches") or {}
    dflt = push_rules.get("default_branch_target") or {}
    on_default = merge_rules.get("on_default_branch") or {}
    pr_merge = gh_rules.get("pr_merge") or {}

    file_ops = data.get("file_ops")
    if not isinstance(file_ops, dict):
        raise RulesError("capability-rules: no file_ops table")

    def verb_of(rule: object, where: str) -> str:
        verb = rule.get("verb") if isinstance(rule, dict) else None
        if not isinstance(verb, str) or verb not in verbs:
            raise RulesError(
                f"capability-rules: {where}.verb missing or not in the verbs table"
            )
        return verb

    if SPEC_DIR_VERB not in verbs:
        raise RulesError(
            f"capability-rules: file_ops.spec_dir verb {SPEC_DIR_VERB!r} is not in "
            "the verbs table"
        )

    command_rules = (
        CommandRule(
            id=RULE_PUSH_FORCE_FLAGS,
            program="git",
            subcommand=("push",),
            matcher=MATCHER_FLAG_PRESENT,
            verb=verb_of(force, "push.rules.force_flags"),
            flags=_strs(force.get("flags"), "push.rules.force_flags.flags"),
            flag_prefixes=_strs(
                force.get("flag_prefixes"), "push.rules.force_flags.flag_prefixes"
            ),
        ),
        CommandRule(
            id=RULE_PUSH_PLUS_REFSPEC,
            program="git",
            subcommand=("push",),
            matcher=MATCHER_REFSPEC_PREFIX,
            verb=verb_of(plus, "push.rules.plus_refspec"),
            prefix=str(plus.get("prefix", "+")),
        ),
        CommandRule(
            id=RULE_PUSH_ALL_BRANCHES,
            program="git",
            subcommand=("push",),
            matcher=MATCHER_FLAG_PRESENT,
            verb=verb_of(allb, "push.rules.all_branches"),
            flags=_strs(allb.get("flags"), "push.rules.all_branches.flags"),
        ),
        CommandRule(
            id=RULE_PUSH_DEFAULT_BRANCH,
            program="git",
            subcommand=("push",),
            matcher=MATCHER_REFSPEC_DEFAULT_BRANCH,
            verb=verb_of(dflt, "push.rules.default_branch_target"),
            fallback_branches=_strs(
                dflt.get("fallback_branches"),
                "push.rules.default_branch_target.fallback_branches",
            ),
        ),
        CommandRule(
            id=RULE_MERGE_ON_DEFAULT_BRANCH,
            program="git",
            subcommand=("merge",),
            matcher=MATCHER_CURRENT_BRANCH_IS_DEFAULT,
            verb=verb_of(on_default, "merge.rules.on_default_branch"),
        ),
        CommandRule(
            id=RULE_GH_PR_MERGE,
            program="gh",
            subcommand=_strs(pr_merge.get("subcommand"), "gh.rules.pr_merge.subcommand"),
            matcher=MATCHER_SUBCOMMAND_PRESENT,
            verb=verb_of(pr_merge, "gh.rules.pr_merge"),
        ),
    )

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

    for rule in command_rules:
        if rule.matcher not in COMMAND_MATCHERS:
            raise RulesError(
                f"capability-rules: rule {rule.id!r} names unknown matcher "
                f"{rule.matcher!r} — no consumer can enforce it"
            )
    for path_rule in path_rules:
        if path_rule.matcher not in PATH_MATCHERS:
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
