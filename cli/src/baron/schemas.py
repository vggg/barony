"""Declarative schemas for persona.yaml and manifest.yaml.

Formalized from the prose specs in ``skills/barony/references/``:

- ``capability-vocab.v1.md`` — the FROZEN v1 10-verb vocabulary. Embedded here as
  :data:`CAPABILITY_VERBS`; ``tests/test_schemas.py`` parses the prose spec's verb
  table and asserts it matches (drift guard).
- ``persona.schema.md`` (v1.2 — the v1.2 addition is the ``check_review_feedback``
  ritual token in :data:`RITUAL_TOKENS`) — :data:`PERSONA_SPEC`.
- ``manifest.schema.md`` (v1.1, plus the v1.2 optional ``workspace`` additions
  documented there) — :data:`MANIFEST_SPEC`.

Severity conventions (consumed by validate.py):

- **error** (fails ``baron validate``): missing required field, type mismatch,
  capability verb outside the frozen vocabulary, allow/deny overlap, unfilled
  ``{{PLACEHOLDER}}`` tokens, closed-enum violations (``paths.strategy``,
  ``repos[].role``).
- **warning** (reported, exit 0): unknown fields (forward-compat — unknown
  ``adapters.<runtime>`` blocks are ignored by design) and open-enum values
  outside the documented set (``archetype``, ``backlog.source``,
  ``runtime.trigger``, session-ritual tokens) — field practice grows these
  faster than the schema (e.g. badminton-analyzer's ``advisor`` archetype).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

# --- Capability vocabulary v1 (FROZEN) ------------------------------------------------
# Drift guard: tests/test_schemas.py re-derives this list from
# references/capability-vocab.v1.md and asserts equality.
CAPABILITY_VERBS: tuple[str, ...] = (
    "read_code",
    "read_collab",
    "write_code",
    "write_path",
    "open_pr",
    "run_tests",
    "merge_pr",
    "push_main",
    "force_push",
    "edit_other_personas",
)

#: Verbs that take a parameter list (``write_path: [<scope>, ...]``).
PARAMETRIC_VERBS: frozenset[str] = frozenset({"write_path"})

#: Named convenience scopes for write_path (data, not vocabulary — any str is legal).
WRITE_PATH_SCOPES: tuple[str, ...] = ("findings", "_handoff", "wiki", "decisions")

ARCHETYPES: tuple[str, ...] = ("dev", "librarian", "autonomous-event", "autonomous-cron")
RITUAL_TOKENS: tuple[str, ...] = (
    "sync_repos",
    "read_conventions",
    "check_handoffs",
    "check_review_feedback",
    "check_backlog",
)
TRIGGERS: tuple[str, ...] = ("interactive", "event", "cron")
PATH_STRATEGIES: tuple[str, ...] = ("relative", "absolute")
REPO_ROLES: tuple[str, ...] = ("code", "collab")
BACKLOG_SOURCES: tuple[str, ...] = ("file", "github_issues", "jira")


@dataclass(frozen=True)
class Node:
    """One declarative schema node.

    kind: "str" | "map" | "list" | "any"
    """

    kind: str
    required: bool = True
    fields: Mapping[str, "Node"] | None = None  # for kind == "map"
    item: "Node | None" = None  # for kind == "list"
    enum: tuple[str, ...] | None = None  # for kind == "str"
    enum_severity: str = "error"
    opaque: bool = False  # accept anything below this point (adapter-owned)
    nonempty: bool = False  # for kind == "list"


def _map(fields: Mapping[str, Node], *, required: bool = True, opaque: bool = False) -> Node:
    return Node("map", required=required, fields=fields, opaque=opaque)


PERSONA_SPEC: Node = _map(
    {
        "persona": Node("str"),
        "slug": Node("str"),
        "archetype": Node("str", enum=ARCHETYPES, enum_severity="warning"),
        "identity": _map(
            {
                "git_name": Node("str"),
                "git_email": Node("str"),
                "commit_prefix": Node("str"),
                "routing_label": Node("str"),
            }
        ),
        "capabilities": _map(
            {
                # Items are verbs (str) or parametric maps ({write_path: [scope,...]});
                # validated by validate._check_capabilities, not the generic walker.
                "allow": Node("list", item=Node("any")),
                "deny": Node("list", item=Node("any")),
            }
        ),
        "scope": _map(
            {
                "summary": Node("str"),
                "focus": Node("list", item=Node("str"), nonempty=True),
            }
        ),
        "session_ritual": Node(
            "list",
            item=Node("str", enum=RITUAL_TOKENS, enum_severity="warning"),
            nonempty=True,
        ),
        "runtime": _map(
            {
                "trigger": Node(
                    "str", required=False, enum=TRIGGERS, enum_severity="warning"
                ),
                "model_hint": Node("str", required=False),
                "adapters": _map({}, required=False, opaque=True),
            },
            required=False,
        ),
    }
)


MANIFEST_SPEC: Node = _map(
    {
        "project": _map({"name": Node("str"), "description": Node("str")}),
        "paths": _map(
            {
                "strategy": Node("str", enum=PATH_STRATEGIES),
                "root": Node("str", required=False),
            }
        ),
        "repos": Node(
            "list",
            nonempty=True,
            item=_map(
                {
                    "id": Node("str"),
                    "path": Node("str"),
                    "role": Node("str", enum=REPO_ROLES),
                    "remote": Node("str", required=False),
                }
            ),
        ),
        "backlog": _map(
            {
                "source": Node("str", enum=BACKLOG_SOURCES, enum_severity="warning"),
                "location": Node("str"),
                # v1.3 (ADR-009 §3.2): the label a parked item carries so the rendered
                # check_backlog query excludes it. Optional — but without it the only
                # discharge for a park obligation is CLOSING the item, which is
                # deliberate: the default fails toward the strong condition.
                "park_label": Node("str", required=False),
            }
        ),
        "personas": Node(
            "list",
            nonempty=True,
            item=_map({"slug": Node("str"), "spec": Node("str")}),
        ),
        "adapters": _map({}, required=False, opaque=True),
        # Observation plane (ADR-013). Declared so a manifest can carry the
        # intent without `baron validate` emitting unknown-field warnings.
        # HONEST BOUND: nothing reads this yet — BARON_EVENTS_SINK is the only
        # live selector in v1 (ADR-013 §7). `options` is opaque: sink-owned.
        "events": _map(
            {
                "sink": Node("str", required=False),
                "options": _map({}, required=False, opaque=True),
            },
            required=False,
        ),
        # v1.2 optional additions (see manifest.schema.md): where persona working
        # copies live locally, so `baron status` can sweep them for divergence.
        "workspace": _map(
            {
                "clones": Node(
                    "list",
                    required=False,
                    item=_map({"persona": Node("str"), "path": Node("str")}),
                ),
                "worktrees_root": Node("str", required=False),
            },
            required=False,
        ),
    }
)
