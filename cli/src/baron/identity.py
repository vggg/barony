"""Per-persona identity resolution (ADR-027).

Git-commit identity was already solved by ``identity.git_name`` /
``identity.git_email``. **Forge identity was the gap**: every persona acted through
one ambient ``gh`` credential, so the PR author, the verdict author and — worst — the
*merger* all read as the human owner. An autonomous merger that merges with the
owner's authority is indistinguishable from the owner, which is what made it
untrustworthy (ADR-027 §1).

This module closes it by **named indirection**, and by nothing else:

    persona.yaml says   identity.forge.token_env: BARON_FORGE_TOKEN_MERGER
    the environment holds the value
    baron carries the NAME, resolves it at cycle start, and injects it

**Baron never issues, stores, prints, logs, serializes or commits a credential
value.** :func:`describe` reports the variable *name* and a *boolean* — not a
redacted prefix, because a prefix is a value. Only :func:`env_overlay` and
:func:`acting_as` touch the value at all, and they hand it straight to a child
process environment.

Whether the variable holds a machine-account PAT or a GitHub App installation token
is invisible here — which is exactly what makes ADR-027 §3.1's PAT-first
recommendation reversible to a GitHub App at zero code cost.

Boundary (ADR-007 / ADR-027 §4): baron *resolves governed identity*. It does not
create accounts or apps, does not mint or refresh tokens, and reads credentials from
nowhere but the process environment.
"""

from __future__ import annotations

import contextlib
import os
import re
from dataclasses import dataclass
from typing import Iterator, Mapping, MutableMapping

#: Verbs whose exercise is a FORGE action — a persona allowed any of these acts on
#: the code host under some account, so it needs a declared identity (ADR-027 §3.4).
FORGE_VERBS: frozenset[str] = frozenset(
    {"open_pr", "merge_pr", "push_main", "force_push"}
)

#: Prefix of the derived per-persona credential variable.
TOKEN_ENV_PREFIX = "BARON_FORGE_TOKEN_"

#: Environment override forcing the fail-closed posture for every persona
#: (the per-persona field is ``identity.forge.required``).
REQUIRE_ENV = "BARON_REQUIRE_IDENTITY"

DEFAULT_PROVIDER = "github"

#: Variables a resolved forge credential populates for the child process. Both `gh`
#: spellings are set: `gh` prefers GH_TOKEN, Actions-shaped tooling reads GITHUB_TOKEN.
FORGE_TOKEN_VARS: tuple[str, ...] = ("GH_TOKEN", "GITHUB_TOKEN")

#: Set for the child so a runtime (or a nested baron) knows who it is acting as.
BARON_ACTING_PERSONA = "BARON_ACTING_PERSONA"

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")


class IdentityError(RuntimeError):
    """A persona's identity could not be resolved under a fail-closed posture."""


def token_env_name(slug: str) -> str:
    """The default credential variable for ``slug``: ``BARON_FORGE_TOKEN_<SLUG>``.

    Non-alphanumerics fold to ``_`` so a kebab slug (``code-reviewer``) yields a
    legal shell name (``BARON_FORGE_TOKEN_CODE_REVIEWER``).
    """
    normalized = _NON_ALNUM.sub("_", slug).strip("_").upper()
    return f"{TOKEN_ENV_PREFIX}{normalized}" if normalized else TOKEN_ENV_PREFIX.rstrip("_")


@dataclass(frozen=True)
class Identity:
    """One persona's resolved identity. Holds NO credential value — only the name
    of the variable that would hold one, and whether it is currently set."""

    slug: str
    git_name: str
    git_email: str
    provider: str
    login: str | None
    token_env: str
    token_env_declared: bool  # True when persona.yaml named it explicitly
    resolved: bool  # the variable is set and non-empty in the consulted environment
    required: bool  # fail closed when unresolved
    declared: bool  # persona.yaml carries an `identity.forge` block at all

    @property
    def actor(self) -> str:
        """How this persona presents on the forge, for reporting."""
        if self.resolved and self.login:
            return self.login
        if self.login:
            return f"{self.login} (credential unresolved)"
        return "ambient (no forge identity declared)"

    def to_dict(self) -> dict[str, object]:
        """JSON-safe. Deliberately carries no credential value."""
        return {
            "slug": self.slug,
            "git_name": self.git_name,
            "git_email": self.git_email,
            "forge": {
                "declared": self.declared,
                "provider": self.provider,
                "login": self.login,
                "token_env": self.token_env,
                "token_env_declared": self.token_env_declared,
                "resolved": self.resolved,
                "required": self.required,
            },
        }


def resolve(
    data: Mapping[str, object], slug: str, *, env: Mapping[str, str] | None = None
) -> Identity:
    """Read one persona spec into an :class:`Identity`.

    Never raises on a missing credential — absence is a *state*
    (``resolved=False``), reported by the caller. See :func:`require` for the
    fail-closed check.
    """
    environ = os.environ if env is None else env
    ident = data.get("identity")
    ident = ident if isinstance(ident, dict) else {}
    forge = ident.get("forge")
    declared = isinstance(forge, dict)
    forge = forge if declared else {}

    login = forge.get("login")
    declared_env = forge.get("token_env")
    token_env = str(declared_env) if declared_env else token_env_name(slug)
    required = bool(forge.get("required", False))
    if str(environ.get(REQUIRE_ENV, "")).strip().lower() in {"1", "true", "yes"}:
        required = True

    return Identity(
        slug=slug,
        git_name=str(ident.get("git_name") or ""),
        git_email=str(ident.get("git_email") or ""),
        provider=str(forge.get("provider") or DEFAULT_PROVIDER),
        login=str(login) if login else None,
        token_env=token_env,
        token_env_declared=bool(declared_env),
        resolved=bool(str(environ.get(token_env, "")).strip()),
        required=required,
        declared=declared,
    )


def require(identity: Identity) -> None:
    """Enforce the fail-closed posture (ADR-027 §3.3). No-op when not required."""
    if identity.required and not identity.resolved:
        raise IdentityError(
            f"persona {identity.slug!r} requires its own forge identity but "
            f"${identity.token_env} is unset — refusing to act under ambient "
            "credentials. Export the persona's token (see "
            "docs/runbooks/forge-identity.md), or clear "
            "identity.forge.required / $" + REQUIRE_ENV
        )


# --- applying an identity --------------------------------------------------------------


def git_env(identity: Identity) -> dict[str, str]:
    """Git authorship variables. Empty when the persona declares no git identity."""
    out: dict[str, str] = {}
    if identity.git_name:
        out["GIT_AUTHOR_NAME"] = identity.git_name
        out["GIT_COMMITTER_NAME"] = identity.git_name
    if identity.git_email:
        out["GIT_AUTHOR_EMAIL"] = identity.git_email
        out["GIT_COMMITTER_EMAIL"] = identity.git_email
    return out


def env_overlay(
    identity: Identity, *, env: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The full environment overlay for a cycle acting as ``identity``.

    Git authorship always; the forge token only when the named variable actually
    holds something. The token VALUE is copied here — this is the one function that
    touches it — and goes straight into a child environment. Never log this dict.
    """
    environ = os.environ if env is None else env
    out = git_env(identity)
    out[BARON_ACTING_PERSONA] = identity.slug
    if identity.resolved:
        value = environ[identity.token_env]
        for var in FORGE_TOKEN_VARS:
            out[var] = value
    return out


def credential_config(identity: Identity) -> list[str]:
    """``git -c`` arguments authenticating an HTTPS push as ``identity``.

    The helper interpolates the credential variable **by name at git's runtime**, so
    the value never appears in ``argv``, in a config file, or on disk — only in the
    environment the child already inherits. The leading empty ``credential.helper``
    clears inherited helpers, so an ambient keychain entry cannot silently win and
    push the persona's work as the owner.

    Empty when the credential is unresolved: no overlay, ambient behaviour, and the
    caller reports it (ADR-027 §3.3).
    """
    if not identity.resolved:
        return []
    var = identity.token_env
    helper = (
        "!f() { test \"$1\" = get && "
        f'printf \'username=x-access-token\\npassword=%s\\n\' "${var}"; }}; f'
    )
    return ["-c", "credential.helper=", "-c", f"credential.helper={helper}"]


@contextlib.contextmanager
def acting_as(
    identity: Identity, *, environ: MutableMapping[str, str] | None = None
) -> Iterator[Identity]:
    """Apply ``identity`` to the process environment for the duration of a cycle.

    Process-wide is the *correct* scope here and not a shortcut: a sidecar cycle IS
    one persona acting, and every git/`gh` call it makes — baron's own commits, the
    session-end bookkeeping, the runtime subprocess and anything that subprocess
    spawns — must carry the same actor. Threading an env dict through every call
    site would leave exactly the gaps (a nested `gh` in the runtime) this ADR exists
    to close.

    Fully restored on exit, including variables that were previously unset.
    """
    target = os.environ if environ is None else environ
    overlay = env_overlay(identity, env=target)
    previous: dict[str, str | None] = {k: target.get(k) for k in overlay}
    try:
        target.update(overlay)
        yield identity
    finally:
        for key, was in previous.items():
            if was is None:
                target.pop(key, None)
            else:
                target[key] = was


# --- reporting -------------------------------------------------------------------------


def describe(identity: Identity) -> str:
    """A one-line operator-facing summary. Carries no credential value."""
    git = f"{identity.git_name} <{identity.git_email}>" if identity.git_email else "—"
    if not identity.declared:
        return (
            f"{identity.slug}: git {git} · forge NOT DECLARED — "
            "acts under ambient credentials"
        )
    state = "resolved" if identity.resolved else "UNRESOLVED"
    tail = "" if identity.resolved else " (unset — acts under ambient credentials)"
    req = " · required" if identity.required else ""
    return (
        f"{identity.slug}: git {git} · forge {identity.provider}:"
        f"{identity.login or '—'} via ${identity.token_env} {state}{tail}{req}"
    )
