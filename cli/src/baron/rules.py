"""Loader for the versioned capability-rules artifact (ADR-004 addendum §4.1).

``data/capability-rules.v1.yaml`` is THE single machine-readable source for the
verb→enforcement rule table: command patterns (git push/merge, gh pr merge),
file-operation scoping semantics, and the conservative-deny ambiguity policy.
It ships as baron package data (``importlib.resources``) so every consumer —
``baron guard`` (the Claude Code PreToolUse hook) and the runtime adapters
under :mod:`baron.runtimes` — reads the same rules instead of restating them.

The prose contract for consumers lives in the skill:
``skills/barony/references/capability-rules.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files

import yaml

RULES_RESOURCE = "data/capability-rules.v1.yaml"
#: The rules_version this baron understands. A consumer must refuse rules it
#: does not understand rather than silently mis-enforce them.
SUPPORTED_RULES_VERSION = 1


class RulesError(RuntimeError):
    """The packaged rules artifact is missing, unparseable, or unsupported."""


@dataclass(frozen=True)
class CapabilityRules:
    """The typed view of capability-rules.v1.yaml that guard logic consumes."""

    rules_version: int
    ambiguity_policy: str
    #: verb -> {"class": ..., "detection": ..., "notes": ...}
    verbs: dict[str, dict[str, str]]

    # git parsing tables
    git_global_value_options: tuple[str, ...]
    push_value_options: tuple[str, ...]
    push_force_flags: tuple[str, ...]
    push_force_flag_prefixes: tuple[str, ...]
    push_force_verb: str
    push_plus_refspec_prefix: str
    push_all_branch_flags: tuple[str, ...]
    push_all_branches_verb: str
    push_default_branch_fallbacks: tuple[str, ...]
    push_default_branch_verb: str
    merge_on_default_branch_verb: str

    # gh
    gh_pr_merge_subcommand: tuple[str, ...]
    gh_pr_merge_verb: str

    # file-op scoping
    universal_write_components: tuple[str, ...]
    spec_dir_component: str


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

    return CapabilityRules(
        rules_version=int(version),
        ambiguity_policy=str(data.get("ambiguity_policy", "")),
        verbs=verbs,
        git_global_value_options=_strs(
            git.get("global_value_options"), "commands.git.global_value_options"
        ),
        push_value_options=_strs(push.get("value_options"), "commands.git.push.value_options"),
        push_force_flags=_strs(force.get("flags"), "push.rules.force_flags.flags"),
        push_force_flag_prefixes=_strs(
            force.get("flag_prefixes"), "push.rules.force_flags.flag_prefixes"
        ),
        push_force_verb=verb_of(force, "push.rules.force_flags"),
        push_plus_refspec_prefix=str(plus.get("prefix", "+")),
        push_all_branch_flags=_strs(allb.get("flags"), "push.rules.all_branches.flags"),
        push_all_branches_verb=verb_of(allb, "push.rules.all_branches"),
        push_default_branch_fallbacks=_strs(
            dflt.get("fallback_branches"),
            "push.rules.default_branch_target.fallback_branches",
        ),
        push_default_branch_verb=verb_of(dflt, "push.rules.default_branch_target"),
        merge_on_default_branch_verb=verb_of(on_default, "merge.rules.on_default_branch"),
        gh_pr_merge_subcommand=_strs(
            pr_merge.get("subcommand"), "gh.rules.pr_merge.subcommand"
        ),
        gh_pr_merge_verb=verb_of(pr_merge, "gh.rules.pr_merge"),
        universal_write_components=_strs(
            file_ops.get("universal_write_components"),
            "file_ops.universal_write_components",
        ),
        spec_dir_component=str(file_ops.get("spec_dir_component", "")),
    )


@lru_cache(maxsize=1)
def load_rules() -> CapabilityRules:
    """Load and validate the packaged rules artifact (cached)."""
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
