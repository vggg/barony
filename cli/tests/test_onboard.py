"""`baron identity register|enroll|protect` — the ADR-027 runbook, mechanized.

**Nothing here touches a live GitHub account, and that is a property of the design,
not of the tests.** The planners are pure: they build a `Plan` of `PlannedCall`s and
return it, and the only code path that spawns a process is `subprocess_runner`, which
these tests replace with a recorder. So the assertions below are about the *plan* —
the exact argv and payload the operator is shown — which is also exactly what
`--apply` would execute, because the dry-run rendering IS the plan object.

The safety property under test, stated once: **no command acts without `--apply`.**
Every planner has a case here asserting the CLI ran, printed its call, and spawned
nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from baron import identity, onboard
from baron.cli import app

from conftest import init_repo, run_git

runner = CliRunner()

PUBKEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyMaterialForTestsOnly00 carson@barony"
OTHER = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDifferentKeyMaterialForTests000 dev@barony"


@pytest.fixture
def keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """$BARON_KEY_DIR in a tmp dir — never the developer's ~/.barony/keys."""
    d = tmp_path / "keys"
    d.mkdir()
    monkeypatch.setenv("BARON_KEY_DIR", str(d))
    return d


def write_key(keys: Path, slug: str, pubkey: str = PUBKEY) -> Path:
    """A public key on disk. No private half — the planners must never need one."""
    pub = keys / f"{slug}.key.pub"
    pub.write_text(pubkey + "\n", encoding="utf-8")
    return pub


class Recorder:
    """A runner that records instead of executing. Stands in for every subprocess."""

    def __init__(self, *, fail_at: int | None = None) -> None:
        self.calls: list[onboard.PlannedCall] = []
        self.fail_at = fail_at

    def __call__(self, call: onboard.PlannedCall) -> onboard.CallResult:
        self.calls.append(call)
        if self.fail_at is not None and len(self.calls) == self.fail_at:
            return onboard.CallResult(call=call, applied=True, returncode=1, stderr="boom")
        return onboard.CallResult(call=call, applied=True, returncode=0, stdout="{}")


def probe(value: object):
    """A stand-in for the read-only `gh api` idempotency probe."""
    return lambda argv: value


# --- register -------------------------------------------------------------------------


def test_register_plans_a_signing_key_post(keys: Path) -> None:
    write_key(keys, "carson")
    plan = onboard.plan_register("carson", probe=probe([]))

    assert len(plan.calls) == 1
    call = plan.calls[0]
    # The SIGNING-key endpoint, not /user/keys (authentication) — different list,
    # different meaning, and the wrong one grants push access while badging nothing.
    assert call.argv == (
        "gh", "api", "--method", "POST", "/user/ssh_signing_keys", "--input", "-",
    )
    payload = json.loads(call.stdin)
    assert payload == {"title": "carson", "key": PUBKEY}


def test_register_sends_only_the_public_half(keys: Path) -> None:
    write_key(keys, "carson")
    (keys / "carson.key").write_text("PRIVATE-KEY-MATERIAL", encoding="utf-8")
    plan = onboard.plan_register("carson", probe=probe([]))
    assert "PRIVATE-KEY-MATERIAL" not in json.dumps(plan.to_dict())


def test_register_is_idempotent_when_the_key_is_already_on_the_account(keys: Path) -> None:
    write_key(keys, "carson")
    plan = onboard.plan_register(
        "carson", probe=probe([{"id": 7, "title": "carson", "key": PUBKEY}])
    )
    assert plan.calls == []
    assert "ALREADY registered" in plan.skipped[0]


def test_register_warns_on_a_title_collision_with_different_key_material(keys: Path) -> None:
    """GitHub allows duplicate titles, so this would silently leave two `carson`s."""
    write_key(keys, "carson")
    plan = onboard.plan_register(
        "carson", probe=probe([{"id": 7, "title": "carson", "key": OTHER}])
    )
    assert plan.calls, "a different key under the same title must still be planned"
    assert any("DIFFERENT key material" in w for w in plan.warnings)


def test_register_plans_anyway_when_the_probe_cannot_answer(keys: Path) -> None:
    """Fail-closed toward doing the work: an unanswerable probe must not skip the step."""
    write_key(keys, "carson")
    plan = onboard.plan_register("carson", probe=probe(None))
    assert len(plan.calls) == 1
    assert any("idempotency check" in n for n in plan.notes)


def test_register_refuses_without_a_key(keys: Path) -> None:
    with pytest.raises(onboard.OnboardError, match="baron identity init"):
        onboard.plan_register("nobody", probe=probe([]))


def test_register_title_override(keys: Path) -> None:
    write_key(keys, "carson")
    plan = onboard.plan_register("carson", title="barony-carson", probe=probe([]))
    assert json.loads(plan.calls[0].stdin)["title"] == "barony-carson"


# --- protect --------------------------------------------------------------------------


def test_protect_ruleset_carries_every_adr_027_rule() -> None:
    body = onboard.ruleset_payload()
    types = {r["type"] for r in body["rules"]}
    assert {"required_signatures", "required_status_checks", "pull_request"} <= types

    pr_rule = next(r for r in body["rules"] if r["type"] == "pull_request")
    # CODEOWNERS over `.barony/` is documentation until this is on.
    assert pr_rule["parameters"]["require_code_owner_review"] is True

    checks = next(r for r in body["rules"] if r["type"] == "required_status_checks")
    assert checks["parameters"]["required_status_checks"] == [{"context": "verify-identity"}]


def test_protect_excludes_rebase_merge() -> None:
    """ADR-027 §2.2(c): rebase-merge adds commits to the base UNVERIFIED, which would
    quietly defeat the required_signatures rule sitting right beside it."""
    body = onboard.ruleset_payload()
    pr_rule = next(r for r in body["rules"] if r["type"] == "pull_request")
    methods = pr_rule["parameters"]["allowed_merge_methods"]
    assert "rebase" not in methods
    assert set(methods) == {"squash", "merge"}


def test_protect_plans_the_ruleset_post(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "collab")
    run_git(repo, "remote", "add", "origin", "git@github.com:vggg/barony.git")
    plan = onboard.plan_protect(repo, probe=probe([]))

    assert plan.calls[0].argv[:5] == ("gh", "api", "--method", "POST", "/repos/vggg/barony/rulesets")
    assert "SECURITY CHANGE" in plan.calls[0].effect
    assert plan.calls[0].undo
    # The two ways to brick a repo with this command, both said before --apply.
    assert any("blocks every merge" in w for w in plan.warnings)
    assert any("Once required_signatures is active" in w for w in plan.warnings)


def test_protect_refuses_to_stack_a_second_ruleset(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "collab")
    run_git(repo, "remote", "add", "origin", "git@github.com:vggg/barony.git")
    plan = onboard.plan_protect(
        repo, probe=probe([{"id": 42, "name": onboard.RULESET_NAME}])
    )
    assert plan.calls == []
    assert "already has a ruleset" in plan.skipped[0]


def test_protect_needs_a_resolvable_repo(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "collab")
    with pytest.raises(onboard.OnboardError, match="--repo owner/name"):
        onboard.plan_protect(repo, probe=probe([]))


def test_protect_accepts_an_explicit_repo(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "collab")
    plan = onboard.plan_protect(repo, target_repo="vggg/other", probe=probe([]))
    assert "/repos/vggg/other/rulesets" in plan.calls[0].argv


# --- enroll ---------------------------------------------------------------------------


def _repo_with_request(tmp_path: Path, keys: Path, slug: str = "carson") -> Path:
    """A repo whose worktree carries the request line but whose HEAD does not."""
    repo = init_repo(tmp_path / "collab")
    write_key(keys, slug)
    signers = repo / identity.ALLOWED_SIGNERS
    signers.parent.mkdir(parents=True, exist_ok=True)
    signers.write_text(identity.signers_line(slug, PUBKEY) + "\n", encoding="utf-8")
    return repo


def test_enroll_plans_branch_commit_push_pr(tmp_path: Path, keys: Path) -> None:
    repo = _repo_with_request(tmp_path, keys)
    (repo / "agents" / "carson").mkdir(parents=True)
    (repo / "agents" / "carson" / "persona.yaml").write_text("slug: carson\n", encoding="utf-8")

    plan = onboard.plan_enroll(repo, "carson")
    verbs = [c.argv[:2] for c in plan.calls]
    assert ("git", "checkout") in verbs
    assert ("git", "add") in verbs
    assert ("git", "commit") in verbs
    assert ("git", "push") in verbs
    assert ("gh", "pr") in verbs

    add = next(c for c in plan.calls if c.argv[:2] == ("git", "add"))
    # The key and the declared capabilities are approved in ONE look (spike §4.1.4).
    assert identity.ALLOWED_SIGNERS in add.argv
    assert "agents/carson/persona.yaml" in add.argv


def test_enroll_never_plans_a_merge(tmp_path: Path, keys: Path) -> None:
    """The trust root. If this test ever fails, the design is gone, not just a flag."""
    repo = _repo_with_request(tmp_path, keys)
    plan = onboard.plan_enroll(repo, "carson")
    flat = " ".join(" ".join(c.argv) for c in plan.calls)
    assert "pr merge" not in flat
    assert "--merge" not in flat
    assert any("OWNER merges it" in n for n in plan.notes)


def _options(*path: str) -> dict[str, str]:
    """{flag: help} for a command, by INTROSPECTION rather than by scraping --help.

    Rendered help wraps and truncates at the terminal width, so an assertion over it
    passes locally at 120 columns and fails in CI at 80 — testing the renderer, not the
    interface. The parameter list is the interface.
    """
    import typer.main

    cmd = typer.main.get_command(app)
    for name in path:
        cmd = cmd.commands[name]
    return {opt: (p.help or "") for p in cmd.params for opt in p.opts}


def test_enroll_cli_has_no_merge_flag() -> None:
    opts = _options("identity", "enroll")
    assert "--merge" not in opts
    assert "--apply" in opts


def test_enroll_warns_when_persona_yaml_is_missing(tmp_path: Path, keys: Path) -> None:
    repo = _repo_with_request(tmp_path, keys)
    plan = onboard.plan_enroll(repo, "carson")
    assert any("persona.yaml does not exist" in w for w in plan.warnings)
    body = next(c for c in plan.calls if c.argv[:2] == ("gh", "pr")).argv[-1]
    assert "NO `persona.yaml`" in body


def test_enroll_skips_when_already_enrolled_at_head(tmp_path: Path, keys: Path) -> None:
    repo = _repo_with_request(tmp_path, keys)
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-m", "enrol carson", "--no-verify")

    plan = onboard.plan_enroll(repo, "carson")
    assert plan.calls == []
    assert "ALREADY enrolled at HEAD" in plan.skipped[0]


def test_enroll_refuses_without_a_request_line(tmp_path: Path, keys: Path) -> None:
    repo = init_repo(tmp_path / "collab")
    write_key(keys, "carson")
    with pytest.raises(onboard.OnboardError, match="baron identity init"):
        onboard.plan_enroll(repo, "carson")


# --- the dry-run contract -------------------------------------------------------------


@pytest.mark.parametrize("action", ["register", "protect"])
def test_account_touching_commands_are_dry_run_by_default(
    action: str, tmp_path: Path, keys: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The load-bearing safety test: no --apply, no subprocess. At all."""
    write_key(keys, "carson")
    repo = init_repo(tmp_path / "collab")
    run_git(repo, "remote", "add", "origin", "git@github.com:vggg/barony.git")

    spawned: list = []
    monkeypatch.setattr(
        onboard, "subprocess_runner",
        lambda call: spawned.append(call) or onboard.CallResult(call, True),
    )
    monkeypatch.setattr(onboard, "_gh_json", lambda argv, cwd=None: [])

    args = ["identity", action, "--collab", str(repo)]
    if action == "register":
        args = ["identity", "register", "--persona", "carson"]
    result = runner.invoke(app, args)

    assert result.exit_code == 0, result.output
    assert spawned == [], "a dry run spawned a process"
    assert "DRY RUN" in result.output
    assert "NOT EXECUTED" in result.output
    assert "gh api --method POST" in result.output


def test_dry_run_prints_the_exact_payload(keys: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_key(keys, "carson")
    monkeypatch.setattr(onboard, "_gh_json", lambda argv, cwd=None: [])
    result = runner.invoke(app, ["identity", "register", "--persona", "carson", "--json"])
    payload = json.loads(result.output)
    assert payload["applied"] is False
    assert payload["results"] == []
    assert json.loads(payload["calls"][0]["stdin"])["key"] == PUBKEY


def test_apply_stops_at_the_first_failure(tmp_path: Path, keys: Path) -> None:
    """Ordered steps: opening a PR after a failed push would blame the wrong step."""
    repo = _repo_with_request(tmp_path, keys)
    plan = onboard.plan_enroll(repo, "carson")
    rec = Recorder(fail_at=2)

    results = onboard.apply(plan, runner=rec)
    assert len(rec.calls) == 2, "execution continued past a failure"
    assert results[-1].ok is False


def test_no_command_surface_accepts_a_token() -> None:
    """baron never handles a credential — the calls run under the operator's `gh auth`."""
    for action in ("register", "enroll", "protect"):
        opts = _options("identity", action)
        assert not any("token" in flag.lower() for flag in opts), action
        # and every one of them says so where the operator reads it
        assert "never" in opts["--apply"].lower(), action
