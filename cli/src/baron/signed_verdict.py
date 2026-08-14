"""ADR-031 — the review verdict as a SIGNED, in-repo artifact.

The hole this closes is [ADR-028 §7 Q4](../../../docs/adr/ADR-028-mechanized-merge-gate.md),
stated there in one sentence:

    baron can verify that a `REVIEW:PASS` exists at the current head. It **cannot
    verify who posted it.** The dev whose code is under review can post its own
    `REVIEW:PASS`, and the gate — correctly, given its inputs — returns exit 0.

ADR-027 does not reach it: a PR comment is *forge* state, not repo state, with no
signature and no per-persona login behind it. ADR-028 §7 Q4 named two candidate routes
and preferred the second — *"a signed verdict artifact in-repo under ADR-027 §2.3's
detached-signature scheme … keeps the record in git, which is the standing preference"*.
This module is that route.

The mechanism, entirely off-the-shelf (ADR-027 §4.3: no custom envelope)::

    .barony/verdicts/pr-<n>-<sha12>.md        the verdict, canonical bytes
    .barony/verdicts/pr-<n>-<sha12>.md.sig    ssh-keygen -Y sign, namespace barony-verdict

and the gate runs ``ssh-keygen -Y verify`` against the same ``.barony/allowed_signers``
that already backs commits and handoffs. Nothing new is trusted.

Four legs, and the third and fourth are the ones that are actually new
--------------------------------------------------------------------
1. **The signature verifies** against the in-repo allowlist. Standard SSHSIG.
2. **The artifact binds itself to (repo, PR, sha).** The signature covers bytes; the
   bytes name which PR and which commit they judge. Without this leg a genuine
   ``REVIEW:PASS`` signed for one PR could be copied onto another — a replay, using a
   perfectly valid signature. The gate re-derives the binding from the *content*, never
   from the filename, because a filename is not signed.
3. **The signer is a reviewer-capable persona** — ``agents/<slug>/persona.yaml`` with
   ``archetype: reviewer``. Enrollment says *who*; the persona registry says *what they
   are for*. A dev's key is a real enrolled key, and without this leg it would produce a
   real verified verdict.
4. **The signer is not the author.** Reviewer ≠ author, established **from the repo
   alone, offline**: the head commit's own signature principal (ADR-027's ``%GS``) is the
   author, and it must differ from the verdict's signer. This is the leg that makes
   self-review mechanically impossible rather than discouraged in prose.

The honest bound, carried in the command output as well as here
---------------------------------------------------------------
**This establishes attribution among cooperating agents. It does not defend against a
hostile workspace.** Whoever holds a persona's unencrypted private key *is* that persona,
so an attacker with write access to the reviewer's workspace can sign whatever it likes.
What this buys is that a verdict now has an *author* who can be named from a clone, that
a persona cannot sign as another persona, and that the specific accident this fleet
actually produces — a dev approving its own work under one shared login — stops being
possible. That is a real property and it is smaller than "the merge is now safe"; the
distance between those two sentences is where Barony's credibility lives.

**And it does not make a verdict correct.** A reviewer-capable persona can sign a
careless PASS. This gate answers *who* judged, never *how well* — the reviewer-quality
axis is ADR-024's escape-rate metrics, and it is a different measurement entirely.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from . import identity as identity_mod
from .gitutil import git, is_git_repo

#: Detached-signature namespace. DISTINCT from `barony-handoff` on purpose: ssh-keygen's
#: namespace is domain separation, and sharing one would let a signature produced over a
#: handoff be presented as a signature over a verdict.
VERDICT_NAMESPACE = "barony-verdict"

#: Where signed verdicts live. Under `.barony/` so the CODEOWNERS rule that already
#: protects `allowed_signers` covers them too.
VERDICT_DIR = ".barony/verdicts"

#: The archetype permitted to sign a verdict. `persona.yaml` is the canonical machine
#: truth for a persona (references/persona.schema.md), and `archetype` is the field that
#: says what a persona is FOR — the question this leg asks.
REVIEWER_ARCHETYPE = "reviewer"

_VERDICT_LINE_RE = re.compile(r"^REVIEW:(PASS|FAIL)[ \t]+([0-9a-f]{40})[ \t]*$", re.M)
_FIELD_RE = re.compile(r"^(pr|repo|reviewer|reviewed_at):[ \t]*(.*)$", re.M)


class VerdictError(RuntimeError):
    """A signed verdict could not be written."""


def verdict_path(collab: Path, pr: int, head: str) -> Path:
    """``.barony/verdicts/pr-<n>-<sha12>.md``.

    The filename is a convenience for humans and for lookup. It is NOT evidence: the
    binding the gate scores is re-derived from the signed content, because bytes outside
    the file are not covered by the signature.
    """
    return collab / VERDICT_DIR / f"pr-{pr}-{head[:12]}.md"


def render_verdict(
    *, state: str, head: str, pr: int, repo: str, reviewer: str, reviewed_at: str,
    findings: str = "",
) -> str:
    """The canonical artifact. Deterministic — the same inputs give the same bytes.

    The first line is the SAME `REVIEW:<STATE> <full-sha>` contract the PR comment has
    always used (ADR-002 §4, ADR-008 §1), so one format is parsed everywhere and the
    reviewer template did not have to learn a second one.
    """
    if state not in ("PASS", "FAIL"):
        raise VerdictError(f"verdict state must be PASS or FAIL, not {state!r}")
    if not re.fullmatch(r"[0-9a-f]{40}", head or ""):
        raise VerdictError(
            f"head must be a full 40-hex sha, not {head!r} — the gate compares it exactly "
            "and will not prefix-match (ADR-028 §2.4)"
        )
    body = findings.strip()
    return (
        f"REVIEW:{state} {head}\n"
        f"pr: {pr}\n"
        f"repo: {repo}\n"
        f"reviewer: {reviewer}\n"
        f"reviewed_at: {reviewed_at}\n"
        "\n" + (body + "\n" if body else "")
    )


@dataclass(frozen=True)
class VerdictDoc:
    """A parsed verdict artifact — what the signature actually covers."""

    state: str
    sha: str
    pr: int
    repo: str
    reviewer: str
    reviewed_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state, "sha": self.sha, "pr": self.pr, "repo": self.repo,
            "reviewer": self.reviewer, "reviewed_at": self.reviewed_at,
        }


def parse_verdict(text: str) -> Optional[VerdictDoc]:
    match = _VERDICT_LINE_RE.search(text)
    if not match:
        return None
    fields = {k: v.strip() for k, v in _FIELD_RE.findall(text)}
    try:
        pr = int(fields.get("pr", "0"))
    except ValueError:
        return None
    return VerdictDoc(
        state=match.group(1), sha=match.group(2).lower(), pr=pr,
        repo=fields.get("repo", ""), reviewer=fields.get("reviewer", ""),
        reviewed_at=fields.get("reviewed_at", ""),
    )


# --- signing -------------------------------------------------------------------------


def sign(
    collab: Path,
    *,
    pr: int,
    head: str,
    state: str,
    reviewer: str,
    repo: str = "",
    reviewed_at: str,
    findings: str = "",
) -> tuple[Path, Path]:
    """Write and sign a verdict. Returns (artifact, signature).

    The signing key is the reviewer's own (`~/.barony/keys/<slug>.key`), so a persona
    can only ever produce a verdict signed as itself — the misattribution leg of
    ADR-027 §2.1, applied to verdicts.
    """
    path = verdict_path(collab, pr, head)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_verdict(
            state=state, head=head, pr=pr, repo=repo, reviewer=reviewer,
            reviewed_at=reviewed_at, findings=findings,
        ),
        encoding="utf-8",
    )
    try:
        sig = identity_mod.sign_file(path, reviewer, namespace=VERDICT_NAMESPACE)
    except identity_mod.IdentityError as exc:
        path.unlink(missing_ok=True)  # never leave an unsigned artifact behind
        raise VerdictError(str(exc)) from exc
    return path, sig


# --- the persona registry leg ----------------------------------------------------------


def persona_archetype(collab: Path, slug: str) -> Optional[str]:
    """``archetype`` from ``agents/<slug>/persona.yaml``, or None when there is none."""
    spec = collab / "agents" / slug / "persona.yaml"
    if not spec.is_file():
        return None
    try:
        data = yaml.safe_load(spec.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if isinstance(data, dict) and isinstance(data.get("archetype"), str):
        return data["archetype"].strip().lower()
    return None


def commit_signer(repo_dir: Path, sha: str) -> Optional[str]:
    """The persona slug that SIGNED ``sha`` — the author, established cryptographically.

    ``%GS`` is git's own resolution of the signature against
    ``gpg.ssh.allowedSignersFile``, i.e. the same allowlist the verdict verifies
    against. Deliberately NOT the git author field: that is a self-asserted string, and
    the 2026-08-04 incident is precisely what happens when it is trusted (ADR-027 §1).

    Returns None when the commit is absent, unsigned, or its signature does not resolve
    — every one of which the caller must treat as "author unknown", not "author differs".
    """
    if not is_git_repo(repo_dir):
        return None
    allowlist = (repo_dir / identity_mod.ALLOWED_SIGNERS).resolve()
    if allowlist.is_file():
        git(repo_dir, "config", "gpg.ssh.allowedSignersFile", str(allowlist), check=False)
    if git(repo_dir, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode != 0:
        return None
    proc = git(repo_dir, "log", "-1", "--format=%G?%x09%GS", sha, check=False)
    if proc.returncode != 0:
        return None
    parts = (proc.stdout.rstrip("\n").split("\t") + ["", ""])[:2]
    if parts[0] != "G" or not parts[1]:
        return None
    return identity_mod.slug_of_principal(parts[1])


# --- verification ----------------------------------------------------------------------

#: Refusal slugs. Distinct per leg, on purpose: "your verdict is unsigned" and "your
#: verdict was signed by the persona that wrote the code" need entirely different
#: actions from whoever reads the refusal.
UNSIGNED = "verdict_unsigned"
SIG_INVALID = "verdict_signature_invalid"
NOT_BOUND = "verdict_not_bound"
SIGNER_UNENROLLED = "verdict_signer_unenrolled"
NOT_REVIEWER = "verdict_signer_not_reviewer"
IS_AUTHOR = "verdict_signer_is_author"
AUTHOR_UNKNOWN = "verdict_author_unresolved"


@dataclass
class Attestation:
    """What the repo can prove about who approved this head, offline."""

    pr: int
    head: str
    present: bool = False
    ok: bool = False
    signer: str = ""            # the persona slug the signature resolves to
    author: str = ""            # the persona slug that signed the head commit
    state: str = ""             # PASS | FAIL, from the signed content
    archetype: str = ""
    reason: str = ""            # slug, empty when ok
    detail: str = ""
    path: Optional[Path] = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "pr": self.pr, "head": self.head, "present": self.present, "ok": self.ok,
            "signer": self.signer, "author": self.author, "state": self.state,
            "archetype": self.archetype, "reason": self.reason, "detail": self.detail,
            "path": self.path.as_posix() if self.path else None, "notes": self.notes,
        }


def _fail(att: Attestation, reason: str, detail: str) -> Attestation:
    att.ok = False
    att.reason = reason
    att.detail = detail
    return att


def verify(
    collab: Path,
    *,
    pr: int,
    head: str,
    repo: str = "",
    code_repo: Optional[Path] = None,
) -> Attestation:
    """Verify the signed verdict for (``pr``, ``head``). Pure repo I/O — no forge.

    Fail-closed at every leg, including the ones that merely *cannot be answered*: an
    unresolvable author is ``verdict_author_unresolved``, not a pass. Absence of
    evidence has never been evidence anywhere else in this gate (ADR-028 §2.2) and is
    not here either.
    """
    head = (head or "").lower()
    att = Attestation(pr=pr, head=head)
    path = verdict_path(collab, pr, head)
    att.path = path
    sig = path.with_name(path.name + ".sig")

    if not path.is_file():
        att.present = False
        return _fail(
            att, UNSIGNED,
            f"no signed verdict at {VERDICT_DIR}/{path.name} — nothing attests WHO "
            f"approved {head[:12]}",
        )
    att.present = True
    if not sig.is_file():
        return _fail(
            att, UNSIGNED,
            f"{path.name} exists but {sig.name} does not — an unsigned artifact is a "
            f"claim, not an attestation. Re-run `baron review sign`.",
        )

    allowlist = collab / identity_mod.ALLOWED_SIGNERS
    if not allowlist.is_file():
        return _fail(
            att, SIGNER_UNENROLLED,
            f"{identity_mod.ALLOWED_SIGNERS} is missing — there is nothing to verify "
            f"against, so no signature can mean anything",
        )

    principal = identity_mod.sig_principal(collab, sig)
    if not principal:
        return _fail(
            att, SIGNER_UNENROLLED,
            f"the signing key on {path.name} is not enrolled in "
            f"{identity_mod.ALLOWED_SIGNERS} — a self-minted key attests nothing",
        )
    att.signer = identity_mod.slug_of_principal(principal)

    with path.open("rb") as fh:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", str(allowlist), "-I", principal,
             "-n", VERDICT_NAMESPACE, "-s", str(sig)],
            stdin=fh, capture_output=True, text=True,
        )
    if proc.returncode != 0:
        return _fail(
            att, SIG_INVALID,
            f"signature on {path.name} does NOT verify as {principal}: "
            f"{proc.stderr.strip() or proc.stdout.strip() or 'verification failed'} — "
            f"the artifact was altered after signing, or signed for another purpose",
        )

    doc = parse_verdict(path.read_text(encoding="utf-8"))
    if doc is None:
        return _fail(
            att, NOT_BOUND,
            f"{path.name} carries a valid signature but no parseable "
            f"`REVIEW:PASS|FAIL <40-hex>` line — a signature over unreadable content "
            f"attests to nothing the gate can score",
        )
    att.state = doc.state

    # Leg 2: the binding. Re-derived from the SIGNED CONTENT, never the filename —
    # a filename is not covered by the signature, so trusting it would let a valid
    # verdict be replayed onto another PR by copying the file.
    if doc.sha != head:
        return _fail(
            att, NOT_BOUND,
            f"the signed verdict names sha {doc.sha[:12]} but the head is {head[:12]} — "
            f"a valid signature over the WRONG commit. Re-review at the current head.",
        )
    if doc.pr != pr:
        return _fail(
            att, NOT_BOUND,
            f"the signed verdict names PR #{doc.pr}, not #{pr} — a valid signature "
            f"replayed from another pull request",
        )
    if repo and doc.repo and doc.repo != repo:
        return _fail(
            att, NOT_BOUND,
            f"the signed verdict names repo {doc.repo!r}, not {repo!r} — a valid "
            f"signature replayed from another repository",
        )
    if doc.reviewer and doc.reviewer != att.signer:
        return _fail(
            att, NOT_BOUND,
            f"the verdict claims reviewer {doc.reviewer!r} but is signed by "
            f"{att.signer!r} — misattribution inside a valid signature (ADR-027 §2.1)",
        )

    # Leg 3: enrolment says WHO; the persona registry says what they are FOR.
    att.archetype = persona_archetype(collab, att.signer) or ""
    if not att.archetype:
        return _fail(
            att, NOT_REVIEWER,
            f"signer {att.signer!r} has no agents/{att.signer}/persona.yaml — the gate "
            f"cannot establish that this persona is a reviewer",
        )
    if att.archetype != REVIEWER_ARCHETYPE:
        return _fail(
            att, NOT_REVIEWER,
            f"signer {att.signer!r} is archetype {att.archetype!r}, not "
            f"{REVIEWER_ARCHETYPE!r} — its key is genuinely enrolled, which is exactly "
            f"why this leg exists: enrolment is not authority to review",
        )

    # Leg 4: reviewer != author, from the repo alone.
    author_repo = code_repo if code_repo is not None else collab
    att.author = commit_signer(author_repo, head) or ""
    if not att.author:
        return _fail(
            att, AUTHOR_UNKNOWN,
            f"could not resolve who SIGNED commit {head[:12]} in "
            f"{author_repo.as_posix()} (absent, unsigned, or unverifiable), so "
            f"reviewer-is-not-author cannot be established. Fail-closed: pass "
            f"--code-repo pointing at a checkout containing the head commit.",
        )
    if att.author == att.signer:
        return _fail(
            att, IS_AUTHOR,
            f"the verdict is signed by {att.signer!r} and commit {head[:12]} is ALSO "
            f"signed by {att.signer!r} — that is self-review. A reviewer that wrote the "
            f"code has reviewed its own work (ADR-002 §4).",
        )

    att.ok = True
    att.detail = (
        f"REVIEW:{att.state} at {head[:12]} signed by {principal} "
        f"(archetype {att.archetype}); commit author is {att.author!r} — distinct"
    )
    return att


__all__ = [
    "AUTHOR_UNKNOWN",
    "Attestation",
    "IS_AUTHOR",
    "NOT_BOUND",
    "NOT_REVIEWER",
    "REVIEWER_ARCHETYPE",
    "SIG_INVALID",
    "SIGNER_UNENROLLED",
    "UNSIGNED",
    "VERDICT_DIR",
    "VERDICT_NAMESPACE",
    "VerdictDoc",
    "VerdictError",
    "commit_signer",
    "parse_verdict",
    "persona_archetype",
    "render_verdict",
    "sign",
    "verdict_path",
    "verify",
]
