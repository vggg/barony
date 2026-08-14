"""Acceptance for per-persona agent identity (ADR-027).

The property under test throughout is **indirection**: baron carries the NAME of a
credential variable and never a value. Every fixture below uses an obviously fake
token name and an obviously fake token value — if a real credential is ever needed to
make this suite pass, the design has regressed.

Covered:
- the derived variable name, and the declared override;
- resolution states (declared / undeclared / resolved / unresolved) and the
  fail-closed posture;
- that no reporting surface — `describe`, `to_dict`, the sidecar report — leaks a
  value, not even a prefix;
- the push credential config, including that the value stays out of argv;
- `baron validate`'s config-level gate and its deliberately non-breaking severity;
- `baron identity`;
- a sidecar cycle acting end-to-end under the persona's own identity.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from baron import identity, sidecar
from baron.cli import app
from baron.validate import validate_file, validate_path

from conftest import init_repo

runner = CliRunner()

#: Obviously fake. Never a real credential, in this file or any other.
FAKE_TOKEN = "fake-token-not-a-secret"

_SPEC = {
    "persona": "Mo",
    "slug": "mo",
    "identity": {
        "git_name": "Mo",
        "git_email": "mo@acmeproj.local",
        "commit_prefix": "mo:",
        "routing_label": "agent-mo",
        "forge": {"provider": "github", "login": "acmeproj-mo"},
    },
}


def _spec(**forge_overrides: object) -> dict:
    data = json.loads(json.dumps(_SPEC))
    data["identity"]["forge"].update(forge_overrides)
    return data


# --- the variable name ------------------------------------------------------------------


@pytest.mark.parametrize(
    "slug,expected",
    [
        ("mo", "BARON_FORGE_TOKEN_MO"),
        ("code-reviewer", "BARON_FORGE_TOKEN_CODE_REVIEWER"),
        ("iris.2", "BARON_FORGE_TOKEN_IRIS_2"),
    ],
)
def test_default_token_env_is_derived_and_shell_legal(slug: str, expected: str) -> None:
    """A kebab or dotted slug must still yield a legal shell variable name — the
    owner exports this by hand, so an illegal name is a runbook that cannot be run."""
    assert identity.token_env_name(slug) == expected


def test_declared_token_env_overrides_the_derived_one() -> None:
    ident = identity.resolve(
        _spec(token_env="ACME_BOT_TOKEN"), "mo", env={"ACME_BOT_TOKEN": FAKE_TOKEN}
    )
    assert ident.token_env == "ACME_BOT_TOKEN"
    assert ident.token_env_declared is True
    assert ident.resolved is True


# --- resolution states ------------------------------------------------------------------


def test_unresolved_when_the_variable_is_unset_but_never_raises() -> None:
    """Absence is a STATE, not a failure (ADR-027 §3.3) — otherwise every project
    predating this ADR breaks on upgrade."""
    ident = identity.resolve(_spec(), "mo", env={})
    assert ident.declared is True
    assert ident.resolved is False
    assert ident.login == "acmeproj-mo"
    identity.require(ident)  # not required -> no raise


def test_an_empty_variable_is_unresolved_not_resolved() -> None:
    assert identity.resolve(_spec(), "mo", env={"BARON_FORGE_TOKEN_MO": "  "}).resolved is False


def test_undeclared_forge_block_resolves_to_ambient() -> None:
    ident = identity.resolve({"slug": "rex", "identity": {"git_name": "Rex"}}, "rex", env={})
    assert ident.declared is False
    assert ident.login is None
    assert "ambient" in ident.actor


def test_required_and_unresolved_fails_closed() -> None:
    ident = identity.resolve(_spec(required=True), "mo", env={})
    with pytest.raises(identity.IdentityError) as exc:
        identity.require(ident)
    assert "BARON_FORGE_TOKEN_MO" in str(exc.value)
    assert FAKE_TOKEN not in str(exc.value)


def test_required_and_resolved_passes() -> None:
    ident = identity.resolve(
        _spec(required=True), "mo", env={"BARON_FORGE_TOKEN_MO": FAKE_TOKEN}
    )
    identity.require(ident)


def test_the_environment_can_force_the_fail_closed_posture_fleet_wide() -> None:
    ident = identity.resolve(_spec(), "mo", env={identity.REQUIRE_ENV: "1"})
    assert ident.required is True


# --- the value never leaks --------------------------------------------------------------


def test_no_reporting_surface_carries_the_credential_value() -> None:
    """Not even a prefix: a prefix IS a value (ADR-027 §3.5)."""
    env = {"BARON_FORGE_TOKEN_MO": FAKE_TOKEN}
    ident = identity.resolve(_spec(), "mo", env=env)
    rendered = identity.describe(ident) + json.dumps(ident.to_dict())
    assert FAKE_TOKEN not in rendered
    assert FAKE_TOKEN[:6] not in rendered
    # ...but the NAME is present, because that is what the operator acts on.
    assert "BARON_FORGE_TOKEN_MO" in rendered


def test_describe_names_the_unset_variable_so_the_fix_is_obvious() -> None:
    text = identity.describe(identity.resolve(_spec(), "mo", env={}))
    assert "UNRESOLVED" in text and "$BARON_FORGE_TOKEN_MO" in text


# --- applying an identity ---------------------------------------------------------------


def test_env_overlay_sets_git_authorship_and_both_gh_token_spellings() -> None:
    env = {"BARON_FORGE_TOKEN_MO": FAKE_TOKEN}
    overlay = identity.env_overlay(identity.resolve(_spec(), "mo", env=env), env=env)
    assert overlay["GIT_AUTHOR_NAME"] == "Mo"
    assert overlay["GIT_COMMITTER_EMAIL"] == "mo@acmeproj.local"
    assert overlay["GH_TOKEN"] == FAKE_TOKEN
    assert overlay["GITHUB_TOKEN"] == FAKE_TOKEN
    assert overlay[identity.BARON_ACTING_PERSONA] == "mo"


def test_env_overlay_omits_the_token_when_unresolved() -> None:
    overlay = identity.env_overlay(identity.resolve(_spec(), "mo", env={}), env={})
    assert "GH_TOKEN" not in overlay
    assert overlay["GIT_AUTHOR_NAME"] == "Mo"  # git identity still applies


def test_acting_as_restores_the_environment_including_previously_unset_vars() -> None:
    env = {"BARON_FORGE_TOKEN_MO": FAKE_TOKEN, "GH_TOKEN": "owners-ambient-token"}
    ident = identity.resolve(_spec(), "mo", env=env)
    with identity.acting_as(ident, environ=env):
        assert env["GH_TOKEN"] == FAKE_TOKEN
        assert env["GIT_AUTHOR_NAME"] == "Mo"
    assert env["GH_TOKEN"] == "owners-ambient-token"  # the owner's is put back
    assert "GIT_AUTHOR_NAME" not in env  # was unset before; must be unset after


def test_credential_config_interpolates_by_name_so_no_secret_reaches_argv() -> None:
    env = {"BARON_FORGE_TOKEN_MO": FAKE_TOKEN}
    config = identity.credential_config(identity.resolve(_spec(), "mo", env=env))
    joined = " ".join(config)
    assert FAKE_TOKEN not in joined
    assert "$BARON_FORGE_TOKEN_MO" in joined
    # The leading empty helper clears inherited ones, so an ambient keychain entry
    # cannot silently win and push the persona's work as the owner.
    assert config[:2] == ["-c", "credential.helper="]


def test_credential_config_is_empty_when_unresolved() -> None:
    assert identity.credential_config(identity.resolve(_spec(), "mo", env={})) == []


def test_the_credential_helper_is_valid_shell_that_git_can_actually_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The helper is a shell snippet handed to a real git. A quoting slip here fails
    at push time, in the dark, on someone's cron — so exercise git itself."""
    import subprocess

    monkeypatch.setenv("BARON_FORGE_TOKEN_MO", FAKE_TOKEN)
    config = identity.credential_config(identity.resolve(_spec(), "mo"))
    proc = subprocess.run(
        ["git", *config, "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    assert "username=x-access-token" in proc.stdout
    assert f"password={FAKE_TOKEN}" in proc.stdout


# --- validate (ADR-027 §3.4) -------------------------------------------------------------

_FORGE_PERSONA = """\
persona: Mo
slug: mo
archetype: merger
identity:
  git_name: Mo
  git_email: mo@acmeproj.local
  commit_prefix: "mo:"
  routing_label: agent-mo
{forge}capabilities:
  allow: [read_code, read_collab, merge_pr]
  deny: [force_push, edit_other_personas]
scope:
  summary: Merge gate.
  focus: [Merge approved PRs]
session_ritual: [sync_repos, read_conventions, check_handoffs]
"""

_FORGE_BLOCK = """\
  forge:
    provider: github
    login: acmeproj-mo
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_forge_block_is_a_warning_not_an_error(tmp_path: Path) -> None:
    """Non-breaking by design: this describes every project predating ADR-027, and
    erroring by default would fail a fleet over a credential never asked for."""
    path = _write(tmp_path, "persona.yaml", _FORGE_PERSONA.format(forge=""))
    findings = validate_file(path)
    hits = [f for f in findings if f.check == "forge-identity"]
    assert len(hits) == 1
    assert hits[0].severity == "warning"
    assert "merge_pr" in hits[0].message
    assert "BARON_FORGE_TOKEN_MO" in hits[0].message


def test_require_identity_promotes_it_to_an_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "persona.yaml", _FORGE_PERSONA.format(forge=""))
    hits = [f for f in validate_file(path, require_identity=True) if f.check == "forge-identity"]
    assert [f.severity for f in hits] == ["error"]


def test_a_persona_with_no_forge_verbs_is_never_flagged(tmp_path: Path) -> None:
    text = _FORGE_PERSONA.format(forge="").replace(
        "allow: [read_code, read_collab, merge_pr]", "allow: [read_code, read_collab]"
    )
    path = _write(tmp_path, "persona.yaml", text)
    assert [f for f in validate_file(path, require_identity=True) if f.check == "forge-identity"] == []


def test_a_declared_block_without_a_login_is_always_an_error(tmp_path: Path) -> None:
    """A malformed declaration, not an un-migrated one — so no existing project can
    trip it, and there is no reason to be lenient."""
    block = "  forge:\n    provider: github\n"
    path = _write(tmp_path, "persona.yaml", _FORGE_PERSONA.format(forge=block))
    hits = [f for f in validate_file(path) if f.check == "forge-identity"]
    assert [f.severity for f in hits] == ["error"]
    assert "login" in hits[0].message


def test_a_complete_forge_block_validates_clean(tmp_path: Path) -> None:
    path = _write(tmp_path, "persona.yaml", _FORGE_PERSONA.format(forge=_FORGE_BLOCK))
    assert [f for f in validate_file(path, require_identity=True)] == []


def test_required_must_be_a_boolean(tmp_path: Path) -> None:
    block = _FORGE_BLOCK + "    required: yes-please\n"
    path = _write(tmp_path, "persona.yaml", _FORGE_PERSONA.format(forge=block))
    assert any(f.severity == "error" and f.check == "type" for f in validate_file(path))


def test_a_shared_forge_login_across_personas_warns(tmp_path: Path) -> None:
    """Legal, but it silently collapses the attribution this ADR exists to buy."""
    for slug in ("mo", "zed"):
        d = tmp_path / "agents" / slug
        d.mkdir(parents=True)
        (d / "persona.yaml").write_text(
            _FORGE_PERSONA.format(forge=_FORGE_BLOCK).replace("slug: mo", f"slug: {slug}"),
            encoding="utf-8",
        )
    findings, _files, _skipped = validate_path(tmp_path, runtime_drift=False)
    shared = [f for f in findings if "shared by" in f.message]
    assert len(shared) == 2
    assert {f.severity for f in shared} == {"warning"}


def test_manifest_require_forge_promotes_without_the_flag(tmp_path: Path) -> None:
    (tmp_path / "manifest.yaml").write_text(
        "project: {name: acmeproj, description: d}\n"
        "paths: {strategy: relative, root: .}\n"
        "repos:\n  - {id: collab, path: ., role: collab}\n"
        "backlog: {source: file, location: backlog.md}\n"
        "identity: {require_forge: true}\n"
        "personas:\n  - {slug: mo, spec: agents/mo/persona.yaml}\n",
        encoding="utf-8",
    )
    agents = tmp_path / "agents" / "mo"
    agents.mkdir(parents=True)
    (agents / "persona.yaml").write_text(_FORGE_PERSONA.format(forge=""), encoding="utf-8")
    findings, _files, _skipped = validate_path(tmp_path, runtime_drift=False)
    hits = [f for f in findings if f.check == "forge-identity"]
    assert [f.severity for f in hits] == ["error"]


# --- `baron init` proposes the provisioning ----------------------------------------------


def _init(tmp_path: Path) -> Path:
    dest = tmp_path / "acmeproj-collab"
    result = runner.invoke(
        app,
        ["init", "acmeproj", "--dir", str(dest), "--personas", "dev:rex,merger:mo"],
    )
    assert result.exit_code == 0, result.output
    return dest


def test_init_proposes_a_forge_handle_and_never_emits_a_credential(
    tmp_path: Path, fixed_clock: object
) -> None:
    dest = _init(tmp_path)
    text = (dest / "agents" / "mo" / "persona.yaml").read_text(encoding="utf-8")
    assert "login: acmeproj-mo" in text
    assert "BARON_FORGE_TOKEN_MO" in text  # the NAME, in a comment
    # No YAML key that could ever hold a value — `token_env` is the only one allowed,
    # and even that is commented out. (Prose in comments may say "token"; keys may not.)
    keys = [
        line.split(":", 1)[0].strip()
        for line in text.splitlines()
        if ":" in line and not line.strip().startswith("#")
    ]
    assert not [k for k in keys if k in {"token", "secret", "password", "pat"}]


def test_the_scaffolded_merger_fails_closed_but_the_dev_does_not(
    tmp_path: Path, fixed_clock: object
) -> None:
    """The merger is the archetype whose whole point is that it must not act with the
    owner's authority — so it is the one the scaffold ships as required."""
    dest = _init(tmp_path)
    assert "required: true" in (dest / "agents" / "mo" / "persona.yaml").read_text()
    assert "required: false" in (dest / "agents" / "rex" / "persona.yaml").read_text()


def test_a_fresh_scaffold_validates_clean_under_require_identity(
    tmp_path: Path, fixed_clock: object
) -> None:
    dest = _init(tmp_path)
    findings, _files, _skipped = validate_path(
        dest, runtime_drift=False, require_identity=True
    )
    assert [f.to_dict() for f in findings] == []


# --- `baron identity` ---------------------------------------------------------------------


def test_identity_command_reports_names_and_state_never_values(
    tmp_path: Path, fixed_clock: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = _init(tmp_path)
    monkeypatch.setenv("BARON_FORGE_TOKEN_MO", FAKE_TOKEN)
    monkeypatch.delenv("BARON_FORGE_TOKEN_REX", raising=False)
    result = runner.invoke(app, ["identity", "--collab", str(dest)])
    assert result.exit_code == 0, result.output
    assert FAKE_TOKEN not in result.output
    assert "acmeproj-mo" in result.output
    assert "$BARON_FORGE_TOKEN_REX" in result.output
    assert "UNRESOLVED" in result.output


def test_identity_json_is_machine_readable_and_credential_free(
    tmp_path: Path, fixed_clock: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = _init(tmp_path)
    monkeypatch.setenv("BARON_FORGE_TOKEN_MO", FAKE_TOKEN)
    result = runner.invoke(app, ["identity", "--collab", str(dest), "--json"])
    assert result.exit_code == 0, result.output
    assert FAKE_TOKEN not in result.output
    payload = json.loads(result.output)
    mo = next(p for p in payload["personas"] if p["slug"] == "mo")
    assert mo["forge"] == {
        "declared": True,
        "provider": "github",
        "login": "acmeproj-mo",
        "token_env": "BARON_FORGE_TOKEN_MO",
        "token_env_declared": False,
        "resolved": True,
        "required": True,
    }


def test_identity_rejects_an_unknown_persona(tmp_path: Path, fixed_clock: object) -> None:
    dest = _init(tmp_path)
    result = runner.invoke(app, ["identity", "--collab", str(dest), "--persona", "nobody"])
    assert result.exit_code == 2
    assert "not a persona of this project" in result.output


# --- the sidecar acts as the persona ------------------------------------------------------

_SIDECAR_MANIFEST = """\
project: {name: acmeproj, description: identity fixture}
paths: {strategy: relative, root: .}
repos:
  - {id: collab, path: ., role: collab}
backlog: {source: file, location: backlog.md}
personas:
  - {slug: mo, spec: agents/mo/persona.yaml}
"""


def _sidecar_project(tmp_path: Path, *, forge: str) -> Path:
    collab = tmp_path / "collab"
    (collab / "agents" / "mo").mkdir(parents=True)
    (collab / "_handoff").mkdir(parents=True)
    (collab / "manifest.yaml").write_text(_SIDECAR_MANIFEST, encoding="utf-8")
    (collab / "backlog.md").write_text("# backlog\n\n- [ ] agent-mo: do the thing\n", encoding="utf-8")
    (collab / "agents" / "mo" / "persona.yaml").write_text(
        _FORGE_PERSONA.format(forge=forge).replace(
            "session_ritual: [sync_repos, read_conventions, check_handoffs]",
            "session_ritual: [sync_repos, read_conventions, check_handoffs]\nruntime:\n  trigger: cron",
        ),
        encoding="utf-8",
    )
    init_repo(collab)
    return collab


def test_a_cycle_reports_who_it_acts_as(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    collab = _sidecar_project(tmp_path, forge=_FORGE_BLOCK)
    monkeypatch.setenv("BARON_FORGE_TOKEN_MO", FAKE_TOKEN)
    report = sidecar.run_cycle(collab, "mo", dry_run=True)
    assert report.identity is not None
    assert report.identity.resolved is True
    rendered = sidecar.render_cycle(report)
    assert "acting as: mo" in rendered
    assert "acmeproj-mo" in rendered
    assert FAKE_TOKEN not in rendered
    assert FAKE_TOKEN not in json.dumps(report.to_dict())


def test_an_unresolved_credential_degrades_with_a_named_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Degrade, but say so — a silent fall back to the owner's credential is exactly
    the failure ADR-027 exists to end."""
    collab = _sidecar_project(tmp_path, forge=_FORGE_BLOCK)
    monkeypatch.delenv("BARON_FORGE_TOKEN_MO", raising=False)
    report = sidecar.run_cycle(collab, "mo", dry_run=True)
    note = " ".join(report.notes)
    assert "UNRESOLVED" in note and "BARON_FORGE_TOKEN_MO" in note
    assert "ambiently logged in" in note


def test_require_identity_refuses_the_cycle_rather_than_acting_as_the_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collab = _sidecar_project(tmp_path, forge=_FORGE_BLOCK)
    monkeypatch.delenv("BARON_FORGE_TOKEN_MO", raising=False)
    with pytest.raises(sidecar.SidecarError) as exc:
        sidecar.run_cycle(collab, "mo", cmd="true", require_identity=True)
    assert "BARON_FORGE_TOKEN_MO" in str(exc.value)


def test_the_runtime_subprocess_inherits_the_personas_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of a process-wide overlay: a `gh` the RUNTIME spawns must be
    the persona too, not the owner. Threading an env dict through baron's own call
    sites would leave exactly this gap."""
    import sys

    collab = _sidecar_project(tmp_path, forge=_FORGE_BLOCK)
    monkeypatch.setenv("BARON_FORGE_TOKEN_MO", FAKE_TOKEN)
    out = tmp_path / "seen.json"
    probe = (
        f"{sys.executable} -c "
        f"\"import os,json;json.dump({{k:os.environ.get(k) for k in "
        f"['GH_TOKEN','GITHUB_TOKEN','GIT_AUTHOR_NAME','BARON_ACTING_PERSONA']}}, "
        f"open(r'{out}','w'))\""
    )
    sidecar.run_cycle(collab, "mo", cmd=probe, push=False)
    seen = json.loads(out.read_text(encoding="utf-8"))
    assert seen["GH_TOKEN"] == FAKE_TOKEN
    assert seen["GITHUB_TOKEN"] == FAKE_TOKEN
    assert seen["GIT_AUTHOR_NAME"] == "Mo"
    assert seen["BARON_ACTING_PERSONA"] == "mo"


def test_the_overlay_does_not_outlive_the_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collab = _sidecar_project(tmp_path, forge=_FORGE_BLOCK)
    monkeypatch.setenv("BARON_FORGE_TOKEN_MO", FAKE_TOKEN)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    sidecar.run_cycle(collab, "mo", cmd="true", push=False)
    import os

    assert "GH_TOKEN" not in os.environ
    assert "GIT_AUTHOR_NAME" not in os.environ
