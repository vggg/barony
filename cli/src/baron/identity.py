"""ADR-027 — per-persona SSH signing keys, enrolled in the repo, verified offline.

The mechanism, in three parts (ADR-027 §2, promoting the 2026-08-04 spike §4):

1. **enrol once** — a human merges the persona's public key into
   ``.barony/allowed_signers``. That merge is the trust root; an agent that minted
   its own key and added itself would have proved nothing.
2. **sign always** — ``commit.gpgsign=true`` with ``gpg.format=ssh``, plus detached
   ``ssh-keygen -Y sign`` signatures for handoffs and findings.
3. **verify at the gate** — ``git verify-commit`` over a PR's commit range plus the
   three-way cross-check *signature principal ↔ claimed persona ↔ persona.yaml*.

Everything here shells out to ``git`` and ``ssh-keygen``. Nothing is authored:
no CA, no registry service, no bespoke signature envelope (ADR-027 §4).

HONEST BOUND, repeated wherever it is user-visible: this establishes attribution
among COOPERATING agents. The private key sits unencrypted in the agent's
workspace, so it does NOT defend against a hostile actor with write access there.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .gitutil import GitError, git, is_git_repo

#: The in-repo registry. OpenSSH ``authorized_keys`` format: principal, then key.
#: A repo file, deliberately — invariant #1 (the clone is sufficient).
ALLOWED_SIGNERS = ".barony/allowed_signers"

#: CODEOWNERS makes this directory owner-only, which is what stops self-enrollment.
BARONY_DIR = ".barony"

#: Namespace for detached artifact signatures (``ssh-keygen -Y sign -n ...``).
HANDOFF_NAMESPACE = "barony-handoff"

#: The email a persona commits under. Distinct on purpose: even before any crypto,
#: this alone would have made the 2026-08-04 Codex commit visibly non-human.
EMAIL_DOMAIN = "agents.barony.invalid"

#: Principal suffix in ``allowed_signers`` — ``<slug>@barony``.
PRINCIPAL_DOMAIN = "barony"

#: The honest bound, printed by every command that could be mistaken for security.
BOUND = (
    "attribution among cooperating agents — NOT a defence against a hostile actor "
    "with write access to an agent's workspace (the private key is unencrypted there)"
)

_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*$")


class IdentityError(RuntimeError):
    """An identity operation could not be completed."""


def principal(slug: str) -> str:
    return f"{slug}@{PRINCIPAL_DOMAIN}"


def agent_email(slug: str) -> str:
    return f"{slug}@{EMAIL_DOMAIN}"


def slug_of_principal(value: str) -> str:
    """``carson@barony`` -> ``carson``. Anything else is returned unchanged."""
    return value[: -len(f"@{PRINCIPAL_DOMAIN}")] if value.endswith(f"@{PRINCIPAL_DOMAIN}") else value


def key_dir() -> Path:
    """Where private keys live — OUTSIDE the repo, so one is never committed by accident.

    ``$BARON_KEY_DIR`` overrides (ADR-027 §7.1 leaves the containerised case open).
    """
    override = os.environ.get("BARON_KEY_DIR")
    return Path(override).expanduser() if override else Path.home() / ".barony" / "keys"


def key_paths(slug: str) -> tuple[Path, Path]:
    """(private, public) key paths for ``slug``."""
    base = key_dir() / f"{slug}.key"
    return base, base.with_suffix(".key.pub")


# --- the registry ----------------------------------------------------------------------


@dataclass(frozen=True)
class SignerEntry:
    principal: str
    keytype: str
    keydata: str
    comment: str

    @property
    def pubkey(self) -> str:
        return f"{self.keytype} {self.keydata}"

    @property
    def slug(self) -> str:
        return slug_of_principal(self.principal)


def parse_allowed_signers(text: str) -> list[SignerEntry]:
    """Parse the ``allowed_signers`` format, skipping comments and blank lines."""
    entries: list[SignerEntry] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 3)
        if len(parts) < 3:
            continue
        entries.append(
            SignerEntry(
                principal=parts[0],
                keytype=parts[1],
                keydata=parts[2],
                comment=parts[3] if len(parts) > 3 else "",
            )
        )
    return entries


def read_allowed_signers(repo: Path, *, at_head: bool = False) -> list[SignerEntry]:
    """Registry entries from the worktree, or from HEAD when ``at_head``.

    ``at_head=True`` is the enrollment test: a key is enrolled only once the owner
    has MERGED it. An agent that writes the line into its own worktree has enrolled
    nothing, and reading the worktree would let it lie to itself (ADR-027 §2).
    """
    if at_head:
        if not is_git_repo(repo):
            return []
        proc = git(repo, "show", f"HEAD:{ALLOWED_SIGNERS}", check=False)
        if proc.returncode != 0:
            return []
        return parse_allowed_signers(proc.stdout)
    path = repo / ALLOWED_SIGNERS
    if not path.is_file():
        return []
    return parse_allowed_signers(path.read_text(encoding="utf-8"))


def is_enrolled(repo: Path, slug: str, pubkey: str, *, at_head: bool = True) -> bool:
    """Is ``slug``'s public key in the registry under its own principal?"""
    want = " ".join(pubkey.split()[:2])
    return any(
        e.slug == slug and e.pubkey == want
        for e in read_allowed_signers(repo, at_head=at_head)
    )


def signers_line(slug: str, pubkey: str, *, note: str = "") -> str:
    keytype, keydata = (pubkey.split() + ["", ""])[:2]
    suffix = f" {note}" if note else ""
    return f"{principal(slug)} {keytype} {keydata}{suffix}"


# --- spawn: `baron identity init` -------------------------------------------------------


@dataclass
class IdentityReport:
    slug: str
    repo: Path
    private_key: Path
    public_key: Path
    pubkey: str
    generated: bool = False
    configured: list[str] = field(default_factory=list)
    enrolled: bool = False
    enrollment_request: Path | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "slug": self.slug,
            "principal": principal(self.slug),
            "repo": self.repo.as_posix(),
            "private_key": self.private_key.as_posix(),
            "public_key": self.public_key.as_posix(),
            "pubkey": self.pubkey,
            "generated": self.generated,
            "configured": self.configured,
            "enrolled": self.enrolled,
            "enrollment_request": (
                self.enrollment_request.as_posix() if self.enrollment_request else None
            ),
            "allowed_signers": ALLOWED_SIGNERS,
            "bound": BOUND,
            "notes": self.notes,
        }


def generate_key(slug: str) -> tuple[Path, Path, bool]:
    """Ensure a keypair exists for ``slug``. Returns (private, public, generated)."""
    private, public = key_paths(slug)
    if private.is_file() and public.is_file():
        return private, public, False
    if shutil.which("ssh-keygen") is None:
        raise IdentityError("ssh-keygen not found on PATH — it is the whole dependency")
    private.parent.mkdir(parents=True, exist_ok=True)
    # 0700: the key is unencrypted (-N ""), so the directory mode is the only
    # protection there is. Said plainly rather than implied — see BOUND.
    try:
        private.parent.chmod(0o700)
    except OSError:  # pragma: no cover - exotic filesystems
        pass
    if private.exists():
        private.unlink()  # a half-generated pair; ssh-keygen refuses to overwrite
    proc = subprocess.run(
        [
            "ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private),
            "-C", principal(slug),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise IdentityError(
            f"ssh-keygen failed for {slug}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return private, public, True


#: Repo-LOCAL git config only. `--global` would make one persona's key the machine's
#: default and silently sign the human's own commits as an agent.
def _git_config(repo: Path, key: str, value: str) -> str:
    git(repo, "config", key, value)
    return f"{key}={value}"


def configure_git(repo: Path, slug: str, public_key: Path, *, git_name: str | None = None) -> list[str]:
    """Point this repo's git at the persona's key. Repo-local, never ``--global``."""
    settings = [
        ("user.name", git_name or f"{slug.replace('-', ' ').title()} (Barony agent)"),
        ("user.email", agent_email(slug)),
        ("gpg.format", "ssh"),
        ("user.signingKey", str(public_key)),
        ("commit.gpgsign", "true"),
        ("tag.gpgsign", "true"),
        ("gpg.ssh.allowedSignersFile", ALLOWED_SIGNERS),
    ]
    return [_git_config(repo, k, v) for k, v in settings]


def _enrollment_request(repo: Path, slug: str, pubkey: str) -> Path:
    """Stage the allowlist line in the worktree — a PR-ready change, NOT an enrollment.

    The agent cannot merge this: `.github/CODEOWNERS` makes `.barony/` owner-only.
    Writing it here is what makes the request one `git commit && gh pr create` away.
    """
    path = repo / ALLOWED_SIGNERS
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    line = signers_line(slug, pubkey, note=f"# {slug} (enrollment requested)")
    if any(e.slug == slug and e.pubkey == " ".join(pubkey.split()[:2]) for e in parse_allowed_signers(existing)):
        return path
    text = existing if existing.endswith("\n") or not existing else existing + "\n"
    path.write_text(text + line + "\n", encoding="utf-8")
    return path


def init(
    repo: Path,
    slug: str,
    *,
    git_name: str | None = None,
    request_enrollment: bool = True,
) -> IdentityReport:
    """The spawn-time flow (ADR-027 §2; spike §4.1).

    Steady state (key present AND enrolled at HEAD) is: configure git, proceed.
    First spawn: generate, configure, emit an enrollment REQUEST, and report
    ``enrolled=False`` — the caller exits non-zero, because identity precedes work.
    """
    if not _SLUG_RE.match(slug):
        raise IdentityError(f"persona slug {slug!r} must match [a-z][a-z0-9-]* (lowercase)")
    if not is_git_repo(repo):
        raise IdentityError(f"{repo} is not a git repository — the registry is a repo file")
    private, public, generated = generate_key(slug)
    pubkey = public.read_text(encoding="utf-8").strip()
    report = IdentityReport(
        slug=slug, repo=repo, private_key=private, public_key=public,
        pubkey=pubkey, generated=generated,
    )
    try:
        report.configured = configure_git(repo, slug, public, git_name=git_name)
    except GitError as exc:
        raise IdentityError(f"could not configure repo-local git identity: {exc}") from exc
    report.enrolled = is_enrolled(repo, slug, pubkey, at_head=True)
    if not report.enrolled and request_enrollment:
        report.enrollment_request = _enrollment_request(repo, slug, pubkey)
        report.notes.append(
            f"enrollment request written to {ALLOWED_SIGNERS} — commit it, open a PR, "
            "and have the OWNER merge it. You cannot merge it yourself (CODEOWNERS), "
            "and that is the trust root: a self-minted key proves nothing until then."
        )
        if slug not in registry_slugs(repo):
            # Spike §4.1 step 4: the key and the DECLARED CAPABILITIES land together,
            # so the owner approves an identity and its scope in one look — not a
            # bare key now and an unreviewed persona later.
            report.notes.append(
                f"agents/{slug}/persona.yaml does not exist — put it in the SAME "
                "enrollment PR, so the owner approves the key and the persona's "
                "declared capabilities together. `baron verify identity` requires it."
            )
    return report


# --- the gate: `baron verify identity` --------------------------------------------------


@dataclass
class CommitVerdict:
    sha: str
    ok: bool
    status: str = "?"          # git's %G? — G good, B bad, U untrusted, N none, E error
    signer: str = ""           # %GS — the principal from allowed_signers
    key: str = ""              # %GK
    claimed: str = ""          # the persona the commit/PR claims
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "sha": self.sha, "ok": self.ok, "status": self.status,
            "signer": self.signer, "key": self.key, "claimed": self.claimed,
            "reasons": self.reasons,
        }


#: `Persona:`/`Signed-off-by`-style trailer a persona may stamp to claim itself.
_TRAILER_RE = re.compile(r"^Barony-Persona:\s*(\S+)\s*$", re.MULTILINE)


def registry_slugs(repo: Path) -> set[str]:
    """Persona slugs with a `persona.yaml` in this project (the third leg of the check)."""
    slugs: set[str] = set()
    agents = repo / "agents"
    if not agents.is_dir():
        return slugs
    for spec in sorted(agents.glob("*/persona.yaml")):
        try:
            data = yaml.safe_load(spec.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(data, dict) and isinstance(data.get("slug"), str):
            slugs.add(data["slug"])
    return slugs


def _claims(repo: Path, sha: str, label: str | None) -> dict[str, str]:
    """Every persona claim attached to this commit, by source.

    Both are checked INDEPENDENTLY. Letting the trailer "win" over the label would
    reopen the misattribution hole from the other side: a PR routed as
    `agent-librarian` whose commits are trailered `dev` is exactly the confusion
    the cross-check exists to catch, and it would pass a first-match rule.
    """
    out: dict[str, str] = {}
    proc = git(repo, "log", "-1", "--format=%B", sha, check=False)
    match = _TRAILER_RE.search(proc.stdout or "")
    if match:
        out["trailer"] = slug_of_principal(match.group(1))
    if label and label.startswith("agent-"):
        out["label"] = label[len("agent-"):]
    return out


def verify_range(
    repo: Path,
    base: str,
    head: str = "HEAD",
    *,
    label: str | None = None,
    require_registry: bool = True,
) -> list[CommitVerdict]:
    """Verify every commit in ``base..head``. Fail-closed: unknown => not ok.

    Three legs per commit (ADR-027 §2.1): the signature verifies against the in-repo
    allowlist; the trust status is good; and the signer principal, the persona the
    commit claims, and the persona registry all name the SAME persona.
    """
    # Point git at the in-repo allowlist explicitly: CI checks out a fresh clone with
    # no repo-local config, and a missing allowedSignersFile makes EVERY commit
    # "untrusted" — which would pass a check that only looked for "no bad signature".
    git(repo, "config", "gpg.ssh.allowedSignersFile", str((repo / ALLOWED_SIGNERS).resolve()))
    known = registry_slugs(repo) if require_registry else set()
    enrolled = {e.slug for e in read_allowed_signers(repo)}
    proc = git(repo, "rev-list", f"{base}..{head}", check=False)
    if proc.returncode != 0:
        raise IdentityError(
            f"could not list commits {base}..{head}: {proc.stderr.strip()} "
            "(in CI, fetch enough history — actions/checkout needs fetch-depth: 0)"
        )
    verdicts: list[CommitVerdict] = []
    for sha in [s for s in proc.stdout.split() if s]:
        verdicts.append(
            _verify_commit(repo, sha, label=label, known=known, enrolled=enrolled,
                           require_registry=require_registry)
        )
    return verdicts


def _verify_commit(
    repo: Path,
    sha: str,
    *,
    label: str | None,
    known: set[str],
    enrolled: set[str],
    require_registry: bool,
) -> CommitVerdict:
    fmt = git(repo, "log", "-1", "--format=%G?%x09%GS%x09%GK", sha, check=False)
    parts = (fmt.stdout.rstrip("\n").split("\t") + ["", "", ""])[:3]
    verdict = CommitVerdict(sha=sha, ok=False, status=parts[0] or "?", signer=parts[1],
                            key=parts[2])
    reasons = verdict.reasons

    if git(repo, "verify-commit", sha, check=False).returncode != 0:
        reasons.append(
            "signature does not verify against " + ALLOWED_SIGNERS
            + (" (commit is unsigned)" if verdict.status == "N" else "")
        )
    if verdict.status != "G":
        reasons.append(
            f"trust status {verdict.status!r}, expected 'G' "
            "(B=bad, U=untrusted/unknown key, N=unsigned, E=verification error)"
        )
    signer_slug = slug_of_principal(verdict.signer) if verdict.signer else ""
    if not signer_slug:
        reasons.append("no signer principal — the key is not in " + ALLOWED_SIGNERS)
    elif signer_slug not in enrolled:
        reasons.append(f"signer {verdict.signer!r} is not an enrolled principal")

    claims = _claims(repo, sha, label)
    verdict.claimed = ", ".join(f"{src}={who}" for src, who in sorted(claims.items()))
    for source, claimed in sorted(claims.items()):
        if signer_slug and claimed != signer_slug:
            reasons.append(
                f"{source} claims persona {claimed!r} but the commit is signed by "
                f"{signer_slug!r} — misattribution (ADR-027 §2.1)"
            )
    if require_registry and signer_slug and signer_slug not in known:
        reasons.append(
            f"signer {signer_slug!r} has no agents/{signer_slug}/persona.yaml registry entry"
        )
    verdict.ok = not reasons
    return verdict


# --- detached signatures for handoffs and findings --------------------------------------


def sign_file(path: Path, slug: str, *, namespace: str = HANDOFF_NAMESPACE) -> Path:
    """Write ``<file>.sig`` — ``ssh-keygen -Y sign``, verbatim (ADR-027 §4.3)."""
    private, _public = key_paths(slug)
    if not private.is_file():
        raise IdentityError(
            f"no signing key for {slug!r} at {private} — run `baron identity init` first"
        )
    if not path.is_file():
        raise IdentityError(f"nothing to sign: {path}")
    proc = subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-q", "-f", str(private), "-n", namespace, str(path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise IdentityError(
            f"ssh-keygen -Y sign failed for {path.name}: "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return path.with_name(path.name + ".sig")


@dataclass
class FileVerdict:
    file: Path
    ok: bool
    signed: bool
    signer: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "file": self.file.as_posix(), "ok": self.ok, "signed": self.signed,
            "signer": self.signer, "reason": self.reason,
        }


def verify_file(
    repo: Path,
    path: Path,
    *,
    expect_slug: str | None = None,
    namespace: str = HANDOFF_NAMESPACE,
    require_signature: bool = False,
) -> FileVerdict:
    """Verify ``<file>.sig`` against the in-repo allowlist.

    Default posture (ADR-027 §7.3, shipped OFF): a MISSING signature is reported
    unsigned but not a failure — turning that into a refusal is a fleet-wide
    breaking change and should be signed, not defaulted. A signature that is
    PRESENT and does not verify is always a failure.
    """
    sig = path.with_name(path.name + ".sig")
    if not sig.is_file():
        return FileVerdict(
            file=path, ok=not require_signature, signed=False,
            reason="no .sig alongside the file"
            + ("" if not require_signature else " and a signature is required"),
        )
    allowlist = repo / ALLOWED_SIGNERS
    if not allowlist.is_file():
        return FileVerdict(file=path, ok=False, signed=True,
                           reason=f"{ALLOWED_SIGNERS} is missing — nothing to verify against")
    who = principal(expect_slug) if expect_slug else _sig_principal(repo, sig)
    if not who:
        return FileVerdict(file=path, ok=False, signed=True,
                           reason="no enrolled principal matches this signature")
    with path.open("rb") as fh:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", str(allowlist), "-I", who,
             "-n", namespace, "-s", str(sig)],
            stdin=fh, capture_output=True, text=True,
        )
    if proc.returncode != 0:
        return FileVerdict(
            file=path, ok=False, signed=True, signer=who,
            reason=(proc.stderr.strip() or proc.stdout.strip() or "signature did not verify")
            + f" (as {who})",
        )
    return FileVerdict(file=path, ok=True, signed=True, signer=who)


def _sig_principal(repo: Path, sig: Path) -> str:
    """Which enrolled principal does this signature's key belong to?

    ``ssh-keygen -Y verify`` demands the identity up front, so when the caller has
    no expectation we resolve it from the signature's own public key and the
    allowlist — a key not in the allowlist resolves to nothing, which is a refusal.
    """
    proc = subprocess.run(
        ["ssh-keygen", "-Y", "find-principals", "-f", str(repo / ALLOWED_SIGNERS),
         "-s", str(sig)],
        capture_output=True, text=True,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.split()[0]
    return ""
