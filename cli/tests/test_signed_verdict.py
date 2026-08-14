"""ADR-033 — the review verdict as a signed, in-repo artifact.

Like `test_identity.py`, these drive **real `ssh-keygen` and real git signing**. The
whole claim of ADR-033 is that a third party can establish who approved a commit with
nothing but a clone and stock tools; a mocked `ssh-keygen` would prove the mock. Keys
go into a tmp `$BARON_KEY_DIR` — nothing touches the developer's `~`.

The case that matters most is `test_dev_cannot_sign_a_verdict_for_its_own_work`: it is
the failure ADR-028 §4 said the gate could not stop, reproduced end-to-end with genuinely
valid signatures throughout, and refused.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from baron import identity, merge, signed_verdict
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
    except ValueError:  # pragma: no cover
        return False


needs_signing = pytest.mark.skipif(
    not _git_supports_ssh_signing(), reason="git >= 2.34 required for gpg.format=ssh"
)


@pytest.fixture
def keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "keys"
    monkeypatch.setenv("BARON_KEY_DIR", str(d))
    return d


def make_persona(repo: Path, slug: str, archetype: str) -> str:
    """Generate a key, enrol it, and register the persona. Returns the public key."""
    _priv, pub = identity.generate_key(slug)[:2]
    pubkey = pub.read_text(encoding="utf-8").strip()

    signers = repo / identity.ALLOWED_SIGNERS
    signers.parent.mkdir(parents=True, exist_ok=True)
    with signers.open("a", encoding="utf-8") as fh:
        fh.write(identity.signers_line(slug, pubkey) + "\n")

    spec = repo / "agents" / slug / "persona.yaml"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(f"persona: {slug.title()}\nslug: {slug}\narchetype: {archetype}\n",
                    encoding="utf-8")
    return pubkey


def commit_as(repo: Path, slug: str, message: str, *, touch: str = "code.py") -> str:
    """A commit SIGNED by `slug`'s key — the author, established cryptographically."""
    _priv, pub = identity.key_paths(slug)
    run_git(repo, "config", "gpg.format", "ssh")
    run_git(repo, "config", "user.signingKey", str(pub))
    run_git(repo, "config", "user.email", identity.agent_email(slug))
    run_git(repo, "config", "user.name", slug)
    run_git(repo, "config", "gpg.ssh.allowedSignersFile",
            str((repo / identity.ALLOWED_SIGNERS).resolve()))
    (repo / touch).write_text(message, encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-S", "-m", message)
    return run_git(repo, "rev-parse", "HEAD").strip()


@pytest.fixture
def project(tmp_path: Path, keys: Path) -> Path:
    """A repo with an enrolled reviewer (`tess`) and an enrolled dev (`rex`)."""
    repo = init_repo(tmp_path / "collab")
    make_persona(repo, "tess", "reviewer")
    make_persona(repo, "rex", "dev")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-m", "seed", "--no-verify")
    return repo


# --- the artifact ---------------------------------------------------------------------

HEAD = "a" * 40


def test_render_is_deterministic() -> None:
    kw = dict(state="PASS", head=HEAD, pr=7, repo="vggg/barony", reviewer="tess",
              reviewed_at="2026-08-14T10:00:00+00:00")
    assert signed_verdict.render_verdict(**kw) == signed_verdict.render_verdict(**kw)


def test_render_refuses_an_abbreviated_sha() -> None:
    """The gate compares exactly (ADR-028 §2.4); an artifact must not be able to carry
    a sha the gate would then have to prefix-match."""
    with pytest.raises(signed_verdict.VerdictError, match="40-hex"):
        signed_verdict.render_verdict(
            state="PASS", head="a1b2c3d", pr=7, repo="r", reviewer="tess",
            reviewed_at="now",
        )


def test_the_first_line_is_the_existing_verdict_contract() -> None:
    """One format everywhere: `merge.parse_verdicts` must read the artifact's first
    line without knowing anything about ADR-033."""
    text = signed_verdict.render_verdict(
        state="PASS", head=HEAD, pr=7, repo="r", reviewer="tess", reviewed_at="now",
    )
    parsed = merge.parse_verdicts([{"body": text, "author": {"login": "x"}}])
    assert (parsed[0].state, parsed[0].sha, parsed[0].malformed) == ("PASS", HEAD, False)


# --- the four legs --------------------------------------------------------------------


@needs_signing
def test_a_reviewer_signed_verdict_verifies(project: Path) -> None:
    head = commit_as(project, "rex", "the work")
    signed_verdict.sign(
        project, pr=7, head=head, state="PASS", reviewer="tess",
        repo="vggg/barony", reviewed_at="2026-08-14T10:00:00+00:00",
    )
    att = signed_verdict.verify(project, pr=7, head=head, repo="vggg/barony")

    assert att.ok, att.detail
    assert (att.signer, att.archetype, att.author, att.state) == ("tess", "reviewer", "rex", "PASS")


@needs_signing
def test_dev_cannot_sign_a_verdict_for_its_own_work(project: Path) -> None:
    """**The ADR-028 §4 hole, closed.**

    Every signature here is genuine: rex is really enrolled, and really signed both the
    commit and the verdict. Under the comment-based gate this is exactly the case that
    returned exit 0 — "the dev whose code is under review can post its own REVIEW:PASS".
    """
    head = commit_as(project, "rex", "the work")
    signed_verdict.sign(
        project, pr=7, head=head, state="PASS", reviewer="rex",
        repo="vggg/barony", reviewed_at="2026-08-14T10:00:00+00:00",
    )
    att = signed_verdict.verify(project, pr=7, head=head, repo="vggg/barony")

    assert not att.ok
    # rex fails on archetype first — it is a dev, and enrolment is not authority to
    # review. That leg fires before self-review is even reached, which is the correct
    # order: the narrower fact is the more useful refusal.
    assert att.reason == signed_verdict.NOT_REVIEWER
    assert "not 'reviewer'" in att.detail


@needs_signing
def test_a_reviewer_cannot_sign_a_verdict_on_its_own_commit(project: Path) -> None:
    """Self-review by a genuine reviewer — the case archetype alone does not catch."""
    head = commit_as(project, "tess", "tess wrote this")
    signed_verdict.sign(
        project, pr=7, head=head, state="PASS", reviewer="tess",
        repo="vggg/barony", reviewed_at="2026-08-14T10:00:00+00:00",
    )
    att = signed_verdict.verify(project, pr=7, head=head, repo="vggg/barony")

    assert not att.ok
    assert att.reason == signed_verdict.IS_AUTHOR
    assert "self-review" in att.detail


@needs_signing
def test_an_unenrolled_key_attests_nothing(project: Path, tmp_path: Path) -> None:
    head = commit_as(project, "rex", "the work")
    identity.generate_key("mallory")
    (project / "agents" / "mallory").mkdir(parents=True)
    (project / "agents" / "mallory" / "persona.yaml").write_text(
        "slug: mallory\narchetype: reviewer\n", encoding="utf-8"
    )
    signed_verdict.sign(
        project, pr=7, head=head, state="PASS", reviewer="mallory",
        repo="vggg/barony", reviewed_at="2026-08-14T10:00:00+00:00",
    )
    att = signed_verdict.verify(project, pr=7, head=head, repo="vggg/barony")

    assert not att.ok
    assert att.reason == signed_verdict.SIGNER_UNENROLLED


@needs_signing
def test_tampering_after_signing_is_caught(project: Path) -> None:
    head = commit_as(project, "rex", "the work")
    path, _sig = signed_verdict.sign(
        project, pr=7, head=head, state="FAIL", reviewer="tess",
        repo="vggg/barony", reviewed_at="2026-08-14T10:00:00+00:00",
    )
    path.write_text(path.read_text(encoding="utf-8").replace("FAIL", "PASS"),
                    encoding="utf-8")
    att = signed_verdict.verify(project, pr=7, head=head, repo="vggg/barony")

    assert not att.ok
    assert att.reason == signed_verdict.SIG_INVALID


@needs_signing
def test_a_verdict_cannot_be_replayed_onto_another_pr(project: Path) -> None:
    """The binding leg. The signature stays perfectly valid — only the file moves.

    This is why the gate re-derives (pr, sha, repo) from the SIGNED CONTENT and never
    from the filename: a filename is not covered by a signature.
    """
    head = commit_as(project, "rex", "the work")
    path, sig = signed_verdict.sign(
        project, pr=7, head=head, state="PASS", reviewer="tess",
        repo="vggg/barony", reviewed_at="2026-08-14T10:00:00+00:00",
    )
    target = signed_verdict.verdict_path(project, 99, head)
    target.write_bytes(path.read_bytes())
    target.with_name(target.name + ".sig").write_bytes(sig.read_bytes())

    att = signed_verdict.verify(project, pr=99, head=head, repo="vggg/barony")
    assert not att.ok
    assert att.reason == signed_verdict.NOT_BOUND
    assert "replayed from another pull request" in att.detail


@needs_signing
def test_a_verdict_cannot_be_replayed_onto_another_repo(project: Path) -> None:
    head = commit_as(project, "rex", "the work")
    signed_verdict.sign(
        project, pr=7, head=head, state="PASS", reviewer="tess",
        repo="vggg/barony", reviewed_at="2026-08-14T10:00:00+00:00",
    )
    att = signed_verdict.verify(project, pr=7, head=head, repo="vggg/other")
    assert not att.ok
    assert att.reason == signed_verdict.NOT_BOUND


@needs_signing
def test_a_stale_verdict_is_a_binding_failure(project: Path) -> None:
    old = commit_as(project, "rex", "v1")
    signed_verdict.sign(
        project, pr=7, head=old, state="PASS", reviewer="tess",
        repo="vggg/barony", reviewed_at="2026-08-14T10:00:00+00:00",
    )
    new = commit_as(project, "rex", "v2")
    # The artifact for the NEW head does not exist at all.
    att = signed_verdict.verify(project, pr=7, head=new, repo="vggg/barony")
    assert not att.ok
    assert att.reason == signed_verdict.UNSIGNED


@needs_signing
def test_an_unsigned_commit_leaves_the_author_unresolved(project: Path, tmp_path: Path) -> None:
    """Fail-closed: an author baron cannot name is NOT an author that differs."""
    (project / "x.py").write_text("x", encoding="utf-8")
    run_git(project, "add", "-A")
    run_git(project, "commit", "-m", "unsigned", "--no-gpg-sign")
    head = run_git(project, "rev-parse", "HEAD").strip()
    signed_verdict.sign(
        project, pr=7, head=head, state="PASS", reviewer="tess",
        repo="vggg/barony", reviewed_at="2026-08-14T10:00:00+00:00",
    )
    att = signed_verdict.verify(project, pr=7, head=head, repo="vggg/barony")
    assert not att.ok
    assert att.reason == signed_verdict.AUTHOR_UNKNOWN


@needs_signing
def test_a_missing_signature_file_is_a_claim_not_an_attestation(project: Path) -> None:
    head = commit_as(project, "rex", "the work")
    path, sig = signed_verdict.sign(
        project, pr=7, head=head, state="PASS", reviewer="tess",
        repo="vggg/barony", reviewed_at="2026-08-14T10:00:00+00:00",
    )
    sig.unlink()
    att = signed_verdict.verify(project, pr=7, head=head, repo="vggg/barony")
    assert not att.ok
    assert att.reason == signed_verdict.UNSIGNED


@needs_signing
def test_the_handoff_namespace_does_not_verify_as_a_verdict(project: Path) -> None:
    """Domain separation: a signature over a handoff must not be presentable as a
    verdict, which is the entire reason the two namespaces differ."""
    head = commit_as(project, "rex", "the work")
    path = signed_verdict.verdict_path(project, 7, head)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        signed_verdict.render_verdict(
            state="PASS", head=head, pr=7, repo="vggg/barony", reviewer="tess",
            reviewed_at="2026-08-14T10:00:00+00:00",
        ),
        encoding="utf-8",
    )
    identity.sign_file(path, "tess", namespace=identity.HANDOFF_NAMESPACE)

    att = signed_verdict.verify(project, pr=7, head=head, repo="vggg/barony")
    assert not att.ok
    assert att.reason == signed_verdict.SIG_INVALID


# --- gate integration -------------------------------------------------------------------


def _pr(head: str, *, number: int = 7) -> dict:
    return {
        "number": number, "state": "OPEN", "isDraft": False, "headRefOid": head,
        "url": "https://example.invalid/pr/7", "labels": [], "reviewDecision": "",
        "comments": [{"author": {"login": "vggg"}, "body": f"REVIEW:PASS {head}",
                      "createdAt": "2026-08-14T10:00:00Z"}],
        "checks": [{"name": "ci", "state": "SUCCESS"}],
    }


def test_default_posture_passes_unattested_but_says_so() -> None:
    """ADR-027 §7.3 precedent: absence warns, it does not break every existing project."""
    result = merge.evaluate(_pr(HEAD), attestation=None)
    signed = next(p for p in result.preconditions if p.name == "verdict_signed")

    assert result.allowed
    assert signed.ok
    assert "UNATTRIBUTED" in signed.detail
    # An unattested pass must not render as a clean one.
    assert "UNATTRIBUTED" in "\n".join(merge.render(result))


def test_require_signed_verdict_refuses_when_unattested() -> None:
    result = merge.evaluate(_pr(HEAD), attestation=None, require_signed_verdict=True)
    assert not result.allowed
    assert result.refusal.name == "verdict_signed"


@needs_signing
def test_gate_refuses_a_broken_signature_even_in_default_posture(project: Path) -> None:
    """Posture softens ABSENT evidence only. Broken evidence is always red."""
    head = commit_as(project, "rex", "the work")
    path, _ = signed_verdict.sign(
        project, pr=7, head=head, state="PASS", reviewer="tess",
        repo="vggg/barony", reviewed_at="2026-08-14T10:00:00+00:00",
    )
    path.write_text(path.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    att = signed_verdict.verify(project, pr=7, head=head, repo="vggg/barony")
    result = merge.evaluate(_pr(head), attestation=att, require_signed_verdict=False)

    assert not result.allowed
    assert result.refusal.reason == signed_verdict.SIG_INVALID


@needs_signing
def test_gate_passes_and_names_the_reviewer(project: Path) -> None:
    head = commit_as(project, "rex", "the work")
    signed_verdict.sign(
        project, pr=7, head=head, state="PASS", reviewer="tess",
        repo="vggg/barony", reviewed_at="2026-08-14T10:00:00+00:00",
    )
    att = signed_verdict.verify(project, pr=7, head=head, repo="vggg/barony")
    result = merge.evaluate(_pr(head), attestation=att, require_signed_verdict=True)

    assert result.allowed
    out = "\n".join(merge.render(result))
    assert "tess@barony" in out
    assert "rex@barony" in out
    # The bound stays attached to the good news, which is where it is easiest to drop.
    assert "hostile workspace" in out
    assert result.to_dict()["attestation"]["signer"] == "tess"


def test_verdict_signed_is_scored_after_verdict_at_head() -> None:
    """A missing verdict must be reported as missing, not as unsigned — the first
    failing precondition is THE refusal, so their order is the message."""
    pr = _pr(HEAD)
    pr["comments"] = []
    result = merge.evaluate(pr, attestation=None, require_signed_verdict=True)
    assert result.refusal.name == "verdict_at_head"
    assert result.refusal.reason == merge.NO_VERDICT


# --- CLI ---------------------------------------------------------------------------------


@needs_signing
def test_review_sign_then_verify_via_cli(project: Path) -> None:
    head = commit_as(project, "rex", "the work")
    signed = runner.invoke(app, [
        "review", "sign", "--pr", "7", "--head", head, "--state", "PASS",
        "--persona", "tess", "--repo", "vggg/barony", "--collab", str(project),
    ])
    assert signed.exit_code == 0, signed.output
    assert signed_verdict.verdict_path(project, 7, head).is_file()
    # An unpushed verdict attests nothing to anyone else — say it at the moment of signing.
    assert "commit and push" in signed.output

    verified = runner.invoke(app, [
        "review", "verify", "--pr", "7", "--head", head, "--repo", "vggg/barony",
        "--collab", str(project),
    ])
    assert verified.exit_code == 0, verified.output
    assert "tess@barony" in verified.output


@needs_signing
def test_review_verify_exits_nonzero_on_self_review(project: Path) -> None:
    head = commit_as(project, "tess", "tess wrote this")
    runner.invoke(app, [
        "review", "sign", "--pr", "7", "--head", head, "--state", "PASS",
        "--persona", "tess", "--repo", "vggg/barony", "--collab", str(project),
    ])
    result = runner.invoke(app, [
        "review", "verify", "--pr", "7", "--head", head, "--repo", "vggg/barony",
        "--collab", str(project),
    ])
    assert result.exit_code == 1
    assert signed_verdict.IS_AUTHOR in result.output


def test_review_sign_rejects_a_bad_state(project: Path) -> None:
    result = runner.invoke(app, [
        "review", "sign", "--pr", "7", "--head", HEAD, "--state", "MAYBE",
        "--persona", "tess", "--collab", str(project),
    ])
    assert result.exit_code == 2
    assert "PASS or FAIL" in result.output


@needs_signing
def test_signing_leaves_no_unsigned_artifact_behind(project: Path) -> None:
    """A failed sign must not leave a bare .md that reads like a verdict."""
    with pytest.raises(signed_verdict.VerdictError):
        signed_verdict.sign(
            project, pr=7, head=HEAD, state="PASS", reviewer="nokey",
            repo="vggg/barony", reviewed_at="2026-08-14T10:00:00+00:00",
        )
    assert not signed_verdict.verdict_path(project, 7, HEAD).exists()
