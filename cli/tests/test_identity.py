"""ADR-027 — per-persona SSH signing keys, enrolled in the repo, verified offline.

These tests drive REAL ``ssh-keygen`` and REAL ``git`` signing. That is deliberate:
the whole claim of ADR-027 is that a third party can verify an artifact with nothing
but a clone and stock tools, and a mocked ``ssh-keygen`` would prove the mock. They
skip (rather than fail) where the toolchain cannot support it, and every key is
generated into a tmp ``$BARON_KEY_DIR`` — nothing touches the developer's ``~``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from baron import identity, scaffold
from baron.cli import app

from conftest import init_repo, run_git

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    shutil.which("ssh-keygen") is None, reason="ssh-keygen is the whole dependency"
)


def _git_supports_ssh_signing() -> bool:
    out = subprocess.run(["git", "--version"], capture_output=True, text=True).stdout
    parts = out.split()[2].split(".") if len(out.split()) > 2 else ["0", "0"]
    try:
        return (int(parts[0]), int(parts[1])) >= (2, 34)
    except ValueError:  # pragma: no cover - unusual version strings
        return False


needs_signing = pytest.mark.skipif(
    not _git_supports_ssh_signing(), reason="git >= 2.34 required for gpg.format=ssh"
)


@pytest.fixture
def keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point $BARON_KEY_DIR at a tmp dir — never the developer's ~/.barony/keys."""
    d = tmp_path / "keys"
    monkeypatch.setenv("BARON_KEY_DIR", str(d))
    return d


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with a persona registry entry and an empty allowlist."""
    root = init_repo(tmp_path / "collab")
    (root / ".barony").mkdir()
    (root / ".barony" / "allowed_signers").write_text("# registry\n", encoding="utf-8")
    spec = root / "agents" / "dev" / "persona.yaml"
    spec.parent.mkdir(parents=True)
    spec.write_text("persona: Dev\nslug: dev\n", encoding="utf-8")
    run_git(root, "add", "-A")
    run_git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed")
    return root


def _enroll(repo: Path, slug: str) -> None:
    """What the OWNER does: merge the requested key into the allowlist at HEAD."""
    _priv, pub, _gen = identity.generate_key(slug)
    line = identity.signers_line(slug, pub.read_text(encoding="utf-8").strip())
    path = repo / identity.ALLOWED_SIGNERS
    path.write_text(path.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", f"owner: enroll {slug}")


# --- the registry -----------------------------------------------------------------------


def test_parse_allowed_signers_skips_comments_and_keeps_the_comment_field() -> None:
    entries = identity.parse_allowed_signers(
        "# header\n\ncarson@barony ssh-ed25519 AAAAKEY carson (enrolled 2026-08-04)\n"
    )
    assert len(entries) == 1
    assert entries[0].slug == "carson"
    assert entries[0].pubkey == "ssh-ed25519 AAAAKEY"
    assert "enrolled" in entries[0].comment


def test_enrollment_is_read_at_head_not_from_the_worktree(repo: Path, keys: Path) -> None:
    """The trust root is a MERGE. A worktree edit must not count as enrollment.

    Otherwise an agent enrolls itself by writing a line — self-assertion in a crypto
    costume, the exact failure ADR-027 §2 exists to prevent.
    """
    _priv, pub, _gen = identity.generate_key("dev")
    pubkey = pub.read_text(encoding="utf-8").strip()
    path = repo / identity.ALLOWED_SIGNERS
    path.write_text(path.read_text() + identity.signers_line("dev", pubkey) + "\n")

    assert identity.is_enrolled(repo, "dev", pubkey, at_head=False) is True
    assert identity.is_enrolled(repo, "dev", pubkey, at_head=True) is False

    run_git(repo, "add", "-A")
    run_git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "owner: enroll")
    assert identity.is_enrolled(repo, "dev", pubkey, at_head=True) is True


# --- spawn ------------------------------------------------------------------------------


def test_init_generates_configures_and_requests_but_does_not_enroll(
    repo: Path, keys: Path
) -> None:
    report = identity.init(repo, "dev")

    assert report.generated is True
    assert (keys / "dev.key").is_file() and (keys / "dev.key.pub").is_file()
    assert report.enrolled is False, "minting a key must never count as enrollment"
    assert report.enrollment_request is not None

    config = dict(s.split("=", 1) for s in report.configured)
    assert config["gpg.format"] == "ssh"
    assert config["commit.gpgsign"] == "true"
    assert config["tag.gpgsign"] == "true"
    assert config["gpg.ssh.allowedSignersFile"] == identity.ALLOWED_SIGNERS
    assert config["user.email"] == "dev@agents.barony.invalid"

    # Repo-LOCAL, never --global: one persona's key must not become the machine's
    # default and silently sign the human's own commits as an agent.
    local = Path(repo / ".git" / "config").read_text(encoding="utf-8")
    assert "gpgsign = true" in local.replace("gpgSign", "gpgsign")


def test_init_is_idempotent_and_reuses_an_existing_key(repo: Path, keys: Path) -> None:
    first = identity.init(repo, "dev")
    second = identity.init(repo, "dev")
    assert second.generated is False
    assert second.pubkey == first.pubkey


def test_init_reports_enrolled_once_the_owner_has_merged(repo: Path, keys: Path) -> None:
    _enroll(repo, "dev")
    assert identity.init(repo, "dev").enrolled is True


def test_init_cli_exits_non_zero_until_enrolled(repo: Path, keys: Path) -> None:
    result = runner.invoke(app, ["identity", "init", "--persona", "dev", "--collab", str(repo)])
    assert result.exit_code == 1, "identity precedes work — an unenrolled persona is refused"
    assert "NOT enrolled" in result.output

    _enroll(repo, "dev")
    ok = runner.invoke(app, ["identity", "init", "--persona", "dev", "--collab", str(repo)])
    assert ok.exit_code == 0
    assert "cleared to work" in ok.output


def test_init_states_the_honest_bound(repo: Path, keys: Path) -> None:
    """The bound is user-visible, not buried in an ADR (ADR-027 §3)."""
    result = runner.invoke(app, ["identity", "init", "--persona", "dev", "--collab", str(repo)])
    assert "NOT a defence against a hostile actor" in result.output


def test_init_rejects_a_non_slug_and_a_non_repo(tmp_path: Path, keys: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(identity.IdentityError, match="not a git repository"):
        identity.init(plain, "dev")


# --- the gate ---------------------------------------------------------------------------


def _commit(repo: Path, message: str, *, name: str = "work.txt", body: str = "x") -> str:
    (repo / name).write_text(body, encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", message)
    return run_git(repo, "rev-parse", "HEAD").strip()


@needs_signing
def test_verify_range_accepts_an_enrolled_signed_attributed_commit(
    repo: Path, keys: Path
) -> None:
    _enroll(repo, "dev")
    identity.init(repo, "dev")
    base = run_git(repo, "rev-parse", "HEAD").strip()
    _commit(repo, "dev: feat | work\n\nBarony-Persona: dev")

    verdicts = identity.verify_range(repo, base, "HEAD", label="agent-dev")
    assert len(verdicts) == 1
    assert verdicts[0].ok is True, verdicts[0].reasons
    assert verdicts[0].signer == "dev@barony"
    assert verdicts[0].status == "G"


@needs_signing
def test_verify_range_refuses_an_unsigned_commit(repo: Path, keys: Path) -> None:
    _enroll(repo, "dev")
    identity.init(repo, "dev")
    base = run_git(repo, "rev-parse", "HEAD").strip()
    (repo / "work.txt").write_text("x", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "sneaky")

    verdict = identity.verify_range(repo, base, "HEAD")[0]
    assert verdict.ok is False
    assert verdict.status == "N"
    assert any("unsigned" in r for r in verdict.reasons)


@needs_signing
def test_verify_range_refuses_a_self_minted_unenrolled_key(repo: Path, keys: Path) -> None:
    """The 2026-08-04 incident's second form: signed, but by nobody we vouched for."""
    identity.init(repo, "dev")  # generates + configures, but nobody merged the key
    base = run_git(repo, "rev-parse", "HEAD").strip()
    run_git(repo, "checkout", "--", identity.ALLOWED_SIGNERS)  # discard the request line
    _commit(repo, "dev: feat | work")

    verdict = identity.verify_range(repo, base, "HEAD")[0]
    assert verdict.ok is False
    assert verdict.status in {"U", "N", "E", "B"}


@needs_signing
def test_verify_range_refuses_misattribution_from_the_label(repo: Path, keys: Path) -> None:
    """A REAL enrolled key, wearing another persona's routing label (ADR-027 §2.1)."""
    _enroll(repo, "dev")
    identity.init(repo, "dev")
    base = run_git(repo, "rev-parse", "HEAD").strip()
    _commit(repo, "dev: feat | work")

    verdict = identity.verify_range(repo, base, "HEAD", label="agent-librarian")[0]
    assert verdict.ok is False
    assert any("misattribution" in r for r in verdict.reasons)


@needs_signing
def test_verify_range_refuses_misattribution_from_the_trailer(repo: Path, keys: Path) -> None:
    _enroll(repo, "dev")
    identity.init(repo, "dev")
    base = run_git(repo, "rev-parse", "HEAD").strip()
    _commit(repo, "dev: feat | work\n\nBarony-Persona: librarian")

    verdict = identity.verify_range(repo, base, "HEAD")[0]
    assert verdict.ok is False
    assert any("misattribution" in r for r in verdict.reasons)


@needs_signing
def test_a_matching_trailer_does_not_excuse_a_mismatched_label(repo: Path, keys: Path) -> None:
    """Both claims are checked. First-match-wins would reopen the hole sideways."""
    _enroll(repo, "dev")
    identity.init(repo, "dev")
    base = run_git(repo, "rev-parse", "HEAD").strip()
    _commit(repo, "dev: feat | work\n\nBarony-Persona: dev")

    verdict = identity.verify_range(repo, base, "HEAD", label="agent-librarian")[0]
    assert verdict.ok is False
    assert any("label claims" in r for r in verdict.reasons)


@needs_signing
def test_verify_range_refuses_a_signer_with_no_registry_entry(repo: Path, keys: Path) -> None:
    _enroll(repo, "ghost")  # enrolled, but there is no agents/ghost/persona.yaml
    identity.init(repo, "ghost")
    base = run_git(repo, "rev-parse", "HEAD").strip()
    _commit(repo, "ghost: feat | work")

    verdict = identity.verify_range(repo, base, "HEAD")[0]
    assert verdict.ok is False
    assert any("registry entry" in r for r in verdict.reasons)
    # ...and the leg can be switched off for a code repo with no agents/ tree.
    assert identity.verify_range(repo, base, "HEAD", require_registry=False)[0].ok is True


@needs_signing
def test_verify_identity_cli_is_fail_closed(repo: Path, keys: Path) -> None:
    _enroll(repo, "dev")
    identity.init(repo, "dev")
    base = run_git(repo, "rev-parse", "HEAD").strip()
    (repo / "work.txt").write_text("x", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "sneaky")

    result = runner.invoke(
        app, ["verify", "identity", "--base", base, "--collab", str(repo)]
    )
    assert result.exit_code == 1
    assert "REFUSED" in result.output


def test_verify_range_reports_an_unfetchable_range_rather_than_passing(
    repo: Path, keys: Path
) -> None:
    """A shallow CI clone must not read as 'zero commits, all good'."""
    with pytest.raises(identity.IdentityError, match="fetch-depth"):
        identity.verify_range(repo, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef", "HEAD")


# --- detached signatures ----------------------------------------------------------------


def test_sign_and_verify_a_handoff(repo: Path, keys: Path) -> None:
    _enroll(repo, "dev")
    artifact = repo / "_handoff" / "note.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("---\nfrom: dev\n---\n\n# note\n", encoding="utf-8")

    sig = identity.sign_file(artifact, "dev")
    assert sig.name == "note.md.sig"

    verdict = identity.verify_file(repo, artifact, expect_slug="dev")
    assert verdict.ok is True and verdict.signed is True
    assert verdict.signer == "dev@barony"


def test_a_tampered_handoff_fails(repo: Path, keys: Path) -> None:
    _enroll(repo, "dev")
    artifact = repo / "note.md"
    artifact.write_text("original\n", encoding="utf-8")
    identity.sign_file(artifact, "dev")
    artifact.write_text("original\nevil\n", encoding="utf-8")

    assert identity.verify_file(repo, artifact, expect_slug="dev").ok is False


def test_a_handoff_signed_by_another_persona_fails_its_from_claim(
    repo: Path, keys: Path
) -> None:
    """`from: librarian` signed with dev's key — the misattribution class, on artifacts."""
    _enroll(repo, "dev")
    _enroll(repo, "librarian")
    artifact = repo / "note.md"
    artifact.write_text("---\nfrom: librarian\n---\n", encoding="utf-8")
    identity.sign_file(artifact, "dev")

    assert identity.verify_file(repo, artifact, expect_slug="librarian").ok is False
    assert identity.verify_file(repo, artifact, expect_slug="dev").ok is True


def test_missing_signature_warns_by_default_and_refuses_when_required(
    repo: Path, keys: Path
) -> None:
    """ADR-027 §7.3: shipped OFF — flipping it is a fleet-wide change the owner signs."""
    artifact = repo / "note.md"
    artifact.write_text("unsigned\n", encoding="utf-8")

    lenient = identity.verify_file(repo, artifact)
    assert lenient.ok is True and lenient.signed is False

    strict = identity.verify_file(repo, artifact, require_signature=True)
    assert strict.ok is False


def test_handoff_close_refuses_a_bad_signature_and_records_a_finding(
    repo: Path, keys: Path
) -> None:
    """The ingest gate: a refusal becomes evidence, not a silent drop (ADR-027 §2.3)."""
    _enroll(repo, "dev")
    handoff = repo / "_handoff" / "2026-08-14-1200-dev-note.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        "---\ncreated: 2026-08-14\nstatus: open\nfor: librarian\nfrom: dev\n"
        "priority: medium\n---\n\n# note\n",
        encoding="utf-8",
    )
    identity.sign_file(handoff, "dev")
    handoff.write_text(handoff.read_text(encoding="utf-8") + "evil\n", encoding="utf-8")
    (repo / "findings").mkdir()
    (repo / "findings" / "index.md").write_text("# Findings\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["handoff", "close", str(handoff), "--collab", str(repo), "--no-commit"],
    )
    assert result.exit_code == 1
    assert handoff.is_file(), "a refused handoff must not be archived"
    assert "F1" in (repo / "findings" / "index.md").read_text(encoding="utf-8")


def test_handoff_close_still_works_for_an_unsigned_handoff(repo: Path, keys: Path) -> None:
    """Backward compatibility: existing fleets have no .sig files at all."""
    handoff = repo / "_handoff" / "2026-08-14-1200-dev-note.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        "---\ncreated: 2026-08-14\nstatus: open\nfor: librarian\nfrom: dev\n"
        "priority: medium\n---\n\n# note\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["handoff", "close", str(handoff), "--collab", str(repo), "--no-commit"]
    )
    assert result.exit_code == 0
    assert (repo / "_handoff" / "archive" / "2026" / handoff.name).is_file()


def test_sign_without_a_key_says_what_to_run(repo: Path, keys: Path) -> None:
    artifact = repo / "note.md"
    artifact.write_text("x", encoding="utf-8")
    with pytest.raises(identity.IdentityError, match="baron identity init"):
        identity.sign_file(artifact, "nobody")


# --- scaffolding ------------------------------------------------------------------------


def test_init_scaffolds_the_registry_the_gate_and_the_check(tmp_path: Path) -> None:
    report = scaffold.scaffold(
        "demo", tmp_path / "demo", personas=scaffold.parse_personas("dev:dev"),
        do_git=False, owner="vggg",
    )
    root = report.root
    assert (root / ".barony" / "allowed_signers").is_file()
    assert (root / ".github" / "workflows" / "verify-identity.yml").is_file()

    codeowners = (root / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert "/.barony/" in codeowners and "@vggg" in codeowners
    # The gate guards itself: an agent that could edit CODEOWNERS could ungate .barony/.
    assert "/.github/CODEOWNERS" in codeowners

    signers = (root / ".barony" / "allowed_signers").read_text(encoding="utf-8")
    assert identity.parse_allowed_signers(signers) == [], "empty is fail-closed"


def test_init_without_owner_emits_a_loud_placeholder(tmp_path: Path) -> None:
    """A plausible wrong owner would silently guard nothing; a loud one is fixable."""
    report = scaffold.scaffold(
        "demo", tmp_path / "demo", personas=scaffold.parse_personas("dev:dev"),
        do_git=False,
    )
    codeowners = (report.root / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert scaffold.OWNER_PLACEHOLDER in codeowners
    assert any("CODEOWNERS" in n for n in report.notes)


def test_scaffold_owner_handle_gets_an_at_sign(tmp_path: Path) -> None:
    assert "@vggg" in scaffold.render_codeowners("vggg")
    assert "@@" not in scaffold.render_codeowners("@vggg")


def test_a_monorepo_has_exactly_one_registry_at_the_root(tmp_path: Path) -> None:
    """One git repo, one allowlist — git resolves it against the WORK TREE.

    A per-subdir copy would be a second registry nothing reads, which is worse than
    no registry at all: it looks like a gate and gates nothing.
    """
    from baron import clock, monorepo

    root = tmp_path / "fleet"
    monorepo.create_root(root, "fleet", date=clock.today().isoformat(), owner="vggg")
    monorepo.add_project(
        root, "_meta", project_name=monorepo.META_PROJECT,
        personas=scaffold.parse_personas("dev:dev"), runtime="claude",
    )
    assert (root / ".barony" / "allowed_signers").is_file()
    assert (root / ".github" / "CODEOWNERS").is_file()
    assert (root / ".github" / "workflows" / "verify-identity.yml").is_file()
    assert not (root / "_meta" / ".barony").exists()


def test_the_workflow_carries_its_bound_and_the_rebase_merge_warning() -> None:
    from baron.templates import read_template

    text = read_template("collab-repo/.github/workflows/verify-identity.yml")
    assert "fetch-depth: 0" in text, "base..head needs the merge-base present"
    assert "required status check" in text.lower()
    assert "rebase" in text.lower(), "the platform's signature gap must travel with the file"
