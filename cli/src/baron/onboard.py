"""``baron identity register|enroll|protect`` — the ADR-027 runbook, mechanized.

[docs/runbooks/identity-signing.md](../../../docs/runbooks/identity-signing.md) is a
list of owner actions: register each persona's public key as a GitHub **signing key**,
open the ``.barony/allowed_signers`` enrollment PR, turn on the ``main`` ruleset. Every
step is deterministic, and a hand-run checklist executed once per persona is exactly the
kind of thing that gets done inconsistently, or half-done, or skipped on persona seven.

So this module turns each step into a command. What it does **not** do is move the
trust boundary:

**The human gate is untouched.** ``enroll`` opens the enrollment *request* — a PR — and
stops. It never merges, and there is deliberately no ``--merge``: ``.barony/`` is
CODEOWNERS-owned precisely so an agent cannot enroll itself, and an agent that could
merge its own enrollment could mint peers (ADR-027 §2, §7.2). Mechanizing the *request*
is a convenience; mechanizing the *approval* would delete the design.

**Dry-run is the default, everywhere.** ``register`` and ``protect`` change GitHub
account and repository security settings; ``enroll`` pushes a branch and opens a PR.
Each prints the exact argv and payload it would send and exits without sending it.
``--apply`` is the only thing that executes. A command whose default is "act" reads
identically to one whose default is "explain" right up until it has acted.

**No credential is handled here, ever.** Every call runs through the ``gh`` CLI under
the operator's existing ``gh auth`` session. baron does not accept a ``--token`` flag,
does not read one from the environment, does not store one and does not print one. The
authority is the operator's, exercised by the operator's tool — which is also why
``--apply`` on ``register``/``protect`` is an owner action, not an agent one.

**Bound, same as everywhere else in ADR-027:** this establishes attribution among
cooperating agents. It is not a defence against a hostile actor with write access to an
agent's workspace.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import identity as identity_mod
from .gitutil import GitError, git, is_git_repo

#: The required status check the ruleset wires up — `baron verify identity` in CI.
#: Named here because `protect` and the scaffolded workflow must agree on the string;
#: a ruleset requiring a check nobody publishes blocks every merge forever.
VERIFY_CHECK = "verify-identity"

#: The ruleset's name on GitHub. Stable, so re-running `protect` can detect its own
#: prior run rather than stacking a second near-identical ruleset beside the first.
RULESET_NAME = "barony-main-signed"

#: Rebase-merge adds head-branch commits to the base WITHOUT signature verification —
#: a documented platform gap (ADR-027 §2.2c). Allowing it would silently defeat the
#: require-signed-commits rule this very ruleset turns on.
ALLOWED_MERGE_METHODS = ["squash", "merge"]


class OnboardError(RuntimeError):
    """An onboarding step could not be planned or applied."""


# --- the planned call ---------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedCall:
    """One command this module would run, described completely enough to audit.

    The dry-run rendering IS this dataclass. That is the point: there is no second
    code path that "describes" what a different code path then does, so the printed
    plan cannot drift away from the executed one.
    """

    argv: tuple[str, ...]
    summary: str
    effect: str = ""          # what changes, in the operator's terms
    undo: str = ""            # how to reverse it, stated up front
    stdin: str = ""           # payload piped to the command (JSON, for `gh api --input -`)
    cwd: Optional[Path] = None

    def to_dict(self) -> dict[str, object]:
        return {
            "argv": list(self.argv),
            "summary": self.summary,
            "effect": self.effect,
            "undo": self.undo,
            "stdin": self.stdin,
            "cwd": self.cwd.as_posix() if self.cwd else None,
        }

    def render(self) -> list[str]:
        lines = [f"  $ {' '.join(self.argv)}"]
        if self.stdin:
            for line in self.stdin.splitlines():
                lines.append(f"      | {line}")
        if self.effect:
            lines.append(f"    effect: {self.effect}")
        if self.undo:
            lines.append(f"    undo:   {self.undo}")
        return lines


@dataclass
class CallResult:
    call: PlannedCall
    applied: bool
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return not self.applied or self.returncode == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "call": self.call.to_dict(),
            "applied": self.applied,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "ok": self.ok,
        }


@dataclass
class Plan:
    """A step's calls plus everything the operator should know before ``--apply``."""

    action: str
    calls: list[PlannedCall] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "calls": [c.to_dict() for c in self.calls],
            "notes": self.notes,
            "warnings": self.warnings,
            "skipped": self.skipped,
            "bound": identity_mod.BOUND,
        }


#: A runner executes one call. Injected so tests exercise the real planners against a
#: recording fake: the plan is the thing worth testing, and a test that reached a live
#: GitHub account to prove it would be a test nobody could run twice.
Runner = Callable[[PlannedCall], CallResult]


def subprocess_runner(call: PlannedCall) -> CallResult:
    """Execute a planned call for real. The ONLY place this module spawns anything."""
    proc = subprocess.run(
        list(call.argv),
        cwd=str(call.cwd) if call.cwd else None,
        input=call.stdin if call.stdin else None,
        capture_output=True,
        text=True,
    )
    return CallResult(
        call=call, applied=True, returncode=proc.returncode,
        stdout=proc.stdout.strip(), stderr=proc.stderr.strip(),
    )


def apply(plan: Plan, *, runner: Runner = subprocess_runner) -> list[CallResult]:
    """Run a plan's calls in order, stopping at the first failure.

    Stopping matters: these steps are ordered (branch, then commit, then push, then
    PR), and continuing past a failed push would open a PR against a branch that is
    not there — an error message pointing at the wrong step.
    """
    results: list[CallResult] = []
    for call in plan.calls:
        result = runner(call)
        results.append(result)
        if not result.ok:
            break
    return results


def require_gh() -> None:
    if shutil.which("gh") is None:
        raise OnboardError(
            "GitHub CLI (`gh`) not found on PATH. Every call here runs under YOUR "
            "existing `gh auth` session — baron neither accepts nor stores a token."
        )


def _gh_json(argv: list[str], *, cwd: Optional[Path] = None) -> object:
    """A READ-ONLY `gh api` probe, used for idempotency. Failure is not fatal.

    These run even in dry-run mode, deliberately: "this key is already registered"
    is exactly the fact an operator wants BEFORE deciding to `--apply`, and a GET
    changes nothing. A probe that cannot answer degrades to "unknown" and the plan
    keeps the call — fail-closed toward doing the work, not toward skipping it.
    """
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout or "null")
    except ValueError:
        return None


# --- `baron identity register` ------------------------------------------------------------


def _pubkey_fields(pubkey: str) -> tuple[str, str]:
    parts = pubkey.split()
    if len(parts) < 2:
        raise OnboardError(f"unparseable public key: {pubkey[:40]!r}")
    return parts[0], parts[1]


def plan_register(
    slug: str,
    *,
    title: Optional[str] = None,
    probe: Callable[[list[str]], object] = lambda argv: _gh_json(argv),
) -> Plan:
    """Register a persona's PUBLIC key as a GitHub **signing key** on the account.

    Signing key, not authentication key — a distinct GitHub key type. An SSH key
    added under "Authentication" grants push access and does nothing for the Verified
    badge; the two lists are separate, and pasting into the wrong one is the single
    most likely way to do this step and believe it worked.

    GitHub places no limit on signing keys per account and records WHICH key signed
    each commit. That is the whole trick behind ADR-027: one account, N distinguishable
    personas, no machine accounts and no per-persona token anywhere.

    Only the PUBLIC half leaves the machine. The private key is never read here.
    """
    plan = Plan(action="register")
    _, public = identity_mod.key_paths(slug)
    if not public.is_file():
        raise OnboardError(
            f"no public key for {slug!r} at {public} — run `baron identity init "
            f"--persona {slug}` first (it generates the pair)"
        )
    pubkey = public.read_text(encoding="utf-8").strip()
    keytype, keydata = _pubkey_fields(pubkey)
    key_title = title or slug

    existing = probe(["gh", "api", "/user/ssh_signing_keys"])
    if isinstance(existing, list):
        for row in existing:
            if not isinstance(row, dict):
                continue
            if " ".join(str(row.get("key") or "").split()[:2]) == f"{keytype} {keydata}":
                plan.skipped.append(
                    f"this key is ALREADY registered on the account as "
                    f"{str(row.get('title') or '?')!r} (id {row.get('id')}) — nothing to do"
                )
                return plan
        if any(str(r.get("title") or "") == key_title for r in existing if isinstance(r, dict)):
            plan.warnings.append(
                f"another signing key is already titled {key_title!r} with DIFFERENT key "
                f"material. GitHub allows duplicate titles, so this will succeed and leave "
                f"two same-named entries — pass --title to tell them apart, or delete the "
                f"stale one first."
            )
    else:
        plan.notes.append(
            "could not read the account's existing signing keys (not authenticated, or "
            "no `read:public_key` scope) — planning the call without an idempotency check"
        )

    payload = json.dumps({"title": key_title, "key": pubkey}, indent=2)
    plan.calls.append(
        PlannedCall(
            argv=("gh", "api", "--method", "POST", "/user/ssh_signing_keys", "--input", "-"),
            stdin=payload,
            summary=f"register {slug}'s public key as a GitHub signing key titled {key_title!r}",
            effect=(
                "adds a SIGNING key (not an authentication key) to the authenticated "
                "GitHub ACCOUNT — account-wide, not repo-scoped. Grants no access; it "
                "only lets GitHub attribute and badge commits signed by this key."
            ),
            undo="Settings -> SSH and GPG keys -> delete the key, or `gh api --method DELETE /user/ssh_signing_keys/<id>`",
        )
    )
    plan.notes.append(
        f"only the PUBLIC half is sent. {identity_mod.key_paths(slug)[0]} never leaves this machine."
    )
    plan.notes.append(
        "this buys the Verified badge, which names the ACCOUNT. Per-persona attribution "
        "comes from the key, and it is the CI check that reads the key — so this step is "
        "not what makes the gate work (ADR-027 §3)."
    )
    return plan


# --- `baron identity enroll` --------------------------------------------------------------


def _current_branch(repo: Path) -> str:
    """The checked-out branch, or "" when HEAD is detached.

    ``symbolic-ref`` rather than ``rev-parse --abbrev-ref``: the latter FAILS on an
    unborn HEAD (a fresh `git init` with no commits), which would silently read as
    "not on main" and skip the branch step — committing the enrollment request
    straight onto the default branch, which is the one place it must not go.
    """
    proc = git(repo, "symbolic-ref", "--short", "HEAD", check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def plan_enroll(
    repo: Path,
    slug: str,
    *,
    branch: Optional[str] = None,
    base: str = "main",
) -> Plan:
    """Open the ``.barony/allowed_signers`` enrollment PR — the REQUEST, not the grant.

    The merge stays human, by design and not by omission: `.github/CODEOWNERS` makes
    `.barony/` owner-only, `baron identity init` reads enrollment from **HEAD** so a
    line an agent wrote into its own worktree enrolls nothing, and there is no
    `--merge` flag here. That one human approval is the entire trust root of ADR-027
    (§2) — a persona that could approve its own enrollment could mint peers (§7.2).

    The persona's `persona.yaml` goes in the SAME PR when it exists, so the owner
    approves an identity and its declared capabilities in one look rather than a bare
    key now and an unreviewed persona later (spike §4.1 step 4).
    """
    plan = Plan(action="enroll")
    root = repo.resolve()
    if not is_git_repo(root):
        raise OnboardError(f"{root} is not a git repository — the registry is a repo file")

    signers = root / identity_mod.ALLOWED_SIGNERS
    _, public = identity_mod.key_paths(slug)
    if not public.is_file():
        raise OnboardError(
            f"no public key for {slug!r} at {public} — run `baron identity init "
            f"--persona {slug}` first"
        )
    pubkey = public.read_text(encoding="utf-8").strip()

    if identity_mod.is_enrolled(root, slug, pubkey, at_head=True):
        plan.skipped.append(
            f"{identity_mod.principal(slug)} is ALREADY enrolled at HEAD — nothing to "
            f"request. `baron identity init --persona {slug}` will now exit 0."
        )
        return plan
    if not signers.is_file() or not identity_mod.is_enrolled(root, slug, pubkey, at_head=False):
        raise OnboardError(
            f"{identity_mod.ALLOWED_SIGNERS} carries no request line for {slug!r}. Run "
            f"`baron identity init --persona {slug}` first — it writes the line this "
            f"command turns into a PR. (Refusing to write it here on purpose: init is "
            f"where the key, the git config and the request are kept consistent.)"
        )

    work = branch or f"identity/enroll-{slug}"
    paths = [identity_mod.ALLOWED_SIGNERS]
    persona_yaml = Path("agents") / slug / "persona.yaml"
    if (root / persona_yaml).is_file():
        paths.append(persona_yaml.as_posix())
    else:
        plan.warnings.append(
            f"agents/{slug}/persona.yaml does not exist. `baron verify identity` REQUIRES "
            f"a registry entry, so this persona's commits will fail the gate even once "
            f"enrolled. Write it and re-run, so the owner approves the key and the "
            f"declared capabilities together."
        )

    if _current_branch(root) == base:
        plan.calls.append(
            PlannedCall(
                argv=("git", "checkout", "-b", work), cwd=root,
                summary=f"branch {work} off {base}",
                effect="local only", undo=f"git checkout {base} && git branch -D {work}",
            )
        )
    else:
        plan.notes.append(
            f"already on branch {_current_branch(root)!r} (not {base!r}) — committing "
            f"there rather than branching, so an in-progress branch is not abandoned"
        )

    plan.calls.append(
        PlannedCall(
            argv=("git", "add", *paths), cwd=root,
            summary="stage the enrollment request", effect="stages " + ", ".join(paths),
            undo="git restore --staged " + " ".join(paths),
        )
    )
    plan.calls.append(
        PlannedCall(
            argv=(
                "git", "commit", "-m",
                f"{slug}: identity | enrollment request for "
                f"{identity_mod.principal(slug)} (ADR-027)",
            ),
            cwd=root,
            summary="commit the request",
            effect="local commit",
            undo="git reset --soft HEAD~1",
        )
    )
    plan.calls.append(
        PlannedCall(
            argv=("git", "push", "-u", "origin", work), cwd=root,
            summary=f"push {work}",
            effect="publishes the branch to origin",
            undo=f"git push origin --delete {work}",
        )
    )
    body = (
        f"Enrollment request for `{identity_mod.principal(slug)}` (ADR-027).\n\n"
        f"Adds this persona's **public** signing key to `{identity_mod.ALLOWED_SIGNERS}`.\n\n"
        f"**Merging this PR is the trust root.** Until it lands, `baron identity init "
        f"--persona {slug}` exits non-zero and the persona will not start work. baron "
        f"cannot merge it and has no flag that would: `.barony/` is CODEOWNERS-owned so "
        f"that a persona cannot enroll itself.\n\n"
        f"Before approving, check that the slug is the persona you expect"
        + (
            f" and read `agents/{slug}/persona.yaml` in this PR — you are approving the "
            f"identity and its declared capabilities together.\n"
            if persona_yaml.as_posix() in paths
            else " — note this PR carries NO `persona.yaml`, so `baron verify identity` "
            "will still refuse this persona's commits.\n"
        )
        + f"\nBound: {identity_mod.BOUND}.\n"
    )
    plan.calls.append(
        PlannedCall(
            argv=(
                "gh", "pr", "create", "--base", base, "--head", work,
                "--title", f"identity: enroll {identity_mod.principal(slug)}",
                "--body", body,
            ),
            cwd=root,
            summary="open the enrollment PR",
            effect="opens a PR on the forge. It is a REQUEST — baron never merges it.",
            undo="gh pr close <number> --delete-branch",
        )
    )
    plan.notes.append(
        "this opens the request and stops. The OWNER merges it — there is no --merge "
        "flag, and that omission is the design (ADR-027 §2)."
    )
    return plan


# --- `baron identity protect` -------------------------------------------------------------


def repo_slug(repo: Path, *, remote: str = "origin") -> Optional[str]:
    """``owner/name`` from a git remote."""
    from .merge import _slug_from_remote

    proc = git(repo, "remote", "get-url", remote, check=False)
    if proc.returncode != 0:
        return None
    return _slug_from_remote(proc.stdout.strip())


def ruleset_payload(*, check: str = VERIFY_CHECK, name: str = RULESET_NAME) -> dict:
    """The `main` ruleset ADR-027 §2.2(c) and the runbook §3 describe, as an API body.

    Three rules carry the ADR, and one omission does:

    - ``required_signatures`` — the platform backstop. Unsigned commits cannot land.
    - ``required_status_checks`` -> ``verify-identity`` — the REAL gate. A check that
      is not *required* is a report, and a report can be merged around.
    - ``pull_request`` -> ``require_code_owner_review`` — what actually gives
      `.github/CODEOWNERS` teeth over `.barony/`. Without it the CODEOWNERS file is
      documentation, and self-enrollment is back.
    - ``allowed_merge_methods`` **excludes rebase**: rebase-merge adds head-branch
      commits to the base without signature verification, which would quietly defeat
      ``required_signatures`` above.
    """
    return {
        "name": name,
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "required_signatures"},
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": True,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": False,
                    "allowed_merge_methods": list(ALLOWED_MERGE_METHODS),
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [{"context": check}],
                },
            },
        ],
    }


def plan_protect(
    repo: Path,
    *,
    target_repo: Optional[str] = None,
    check: str = VERIFY_CHECK,
    name: str = RULESET_NAME,
    probe: Callable[[list[str]], object] = lambda argv: _gh_json(argv),
) -> Plan:
    """Enable the signed-commits + required-check ruleset on the repo's default branch.

    This is the layer-(c) backstop of ADR-027 §2.2. It is the most disruptive step in
    the runbook — after it, nothing lands on the default branch without a PR, a green
    ``verify-identity``, and a signature — so the dry-run default matters most here.
    """
    plan = Plan(action="protect")
    root = repo.resolve()
    slug = target_repo or repo_slug(root)
    if not slug:
        raise OnboardError(
            "could not determine the repository from `origin` — pass --repo owner/name"
        )

    existing = probe(["gh", "api", f"/repos/{slug}/rulesets"])
    if isinstance(existing, list):
        for row in existing:
            if isinstance(row, dict) and str(row.get("name") or "") == name:
                plan.skipped.append(
                    f"{slug} already has a ruleset named {name!r} (id {row.get('id')}). "
                    f"Refusing to add a second: two overlapping rulesets on one branch "
                    f"are the hardest branch-protection state to reason about. Review it "
                    f"with `gh api /repos/{slug}/rulesets/{row.get('id')}`, and delete it "
                    f"first if you mean to replace it."
                )
                return plan
    else:
        plan.notes.append(
            f"could not list existing rulesets on {slug} (not authenticated, or no admin "
            f"rights) — planning the call without checking for a prior run. Creating this "
            f"ruleset needs repository ADMIN."
        )

    payload = json.dumps(ruleset_payload(check=check, name=name), indent=2)
    plan.calls.append(
        PlannedCall(
            argv=("gh", "api", "--method", "POST", f"/repos/{slug}/rulesets", "--input", "-"),
            stdin=payload,
            summary=f"create branch ruleset {name!r} on {slug}'s default branch",
            effect=(
                f"REPOSITORY SECURITY CHANGE on {slug}: after this, the default branch "
                f"requires a pull request with code-owner review, a passing "
                f"{check!r} check, and signed commits. Direct pushes, force-pushes, "
                f"branch deletion and rebase-merges are refused — including yours."
            ),
            undo=f"gh api --method DELETE /repos/{slug}/rulesets/<id> (find it with `gh api /repos/{slug}/rulesets`)",
        )
    )
    plan.warnings.append(
        f"the {check!r} check must actually be published by a workflow before this bites. "
        f"A ruleset that requires a check nothing ever reports blocks every merge, "
        f"permanently — verify the workflow runs on PRs first (`baron init` scaffolds it)."
    )
    plan.warnings.append(
        "enroll your personas BEFORE this lands. Once required_signatures is active, an "
        "unenrolled persona cannot land anything, including its own enrollment PR."
    )
    plan.notes.append(
        "rebase-merge is excluded on purpose: it adds head-branch commits to the base "
        "without verifying signatures, which would defeat required_signatures (ADR-027 §2.2c)."
    )
    return plan


# --- rendering ------------------------------------------------------------------------------


def render(plan: Plan, *, applied: bool, results: Optional[list[CallResult]] = None) -> list[str]:
    """The dry-run/apply report. Same plan object either way, by construction."""
    mode = "APPLY" if applied else "DRY RUN"
    lines = [f"=== baron identity {plan.action} — {mode} ==="]
    for note in plan.skipped:
        lines.append(f"  skip:    {note}")
    for warning in plan.warnings:
        lines.append(f"  WARNING: {warning}")
    if not plan.calls:
        lines.append("  nothing to do.")
    for i, call in enumerate(plan.calls, 1):
        lines.append(f"  [{i}] {call.summary}")
        lines.extend(call.render())
    for note in plan.notes:
        lines.append(f"  note:    {note}")
    if plan.calls and not applied:
        lines.append(
            "  NOT EXECUTED. Re-run with --apply to perform the calls above, under your "
            "own `gh auth` session (baron never handles a token)."
        )
    for result in results or []:
        state = "ok" if result.ok else f"FAILED rc={result.returncode}"
        lines.append(f"  ran:     {state}  {result.call.summary}")
        if not result.ok and (result.stderr or result.stdout):
            lines.append(f"           {result.stderr or result.stdout}")
    lines.append(f"  bound:   {identity_mod.BOUND}")
    return lines


__all__ = [
    "ALLOWED_MERGE_METHODS",
    "CallResult",
    "OnboardError",
    "Plan",
    "PlannedCall",
    "RULESET_NAME",
    "Runner",
    "VERIFY_CHECK",
    "apply",
    "plan_enroll",
    "plan_protect",
    "plan_register",
    "render",
    "repo_slug",
    "require_gh",
    "ruleset_payload",
    "subprocess_runner",
]
