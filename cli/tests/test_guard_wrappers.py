"""L2 (ADR-034 §4.3a) — one level of recursion into inline program strings.

``bash -c 'git push origin main'`` used to run its payload UNINSPECTED. That
was documented on purpose (guard's module docstring, `docs/DECISIONS-FOR-REVIEW.md`
§E item 7) and it is the wrapper people reach **by accident**, not only
adversarially — which is why it is the one closed here.

**The bound is the point of this file, as much as the fix.** Half of these
tests assert what still gets through: ``python -c``, ``eval``, base64
indirection, a script file, ``xargs``. Deep recursion is an arms race against
an adversary ADR-004 §2.2 explicitly does not model, paid for in false
positives that spend the credibility the mechanism runs on (ADR-017 §3.6). A
test file that only showed the wins would be the over-claim this project exists
to avoid.

Where a payload is uninspectable — untokenisable, or nested past the depth cap —
the artifact's ``ambiguity_policy: conservative-deny`` applies, NARROWED to
``merge_pr``/``push_main``/``force_push``. A persona holding those three sees no
change at all; that narrowing is what keeps the false-positive cost off
personas the fence was never about.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baron import guard, rules

#: Denies all three high-stakes verbs — the shape the conservative-deny lands on.
DEV = guard.GuardPersona(
    slug="dara",
    allow=frozenset({"read_code", "write_code", "open_pr", "run_tests"}),
    deny=frozenset({"merge_pr", "push_main", "force_push"}),
    allow_scopes=(),
    deny_scopes=(),
)

#: Holds all three. Every conservative-deny in this file must be INVISIBLE to it.
MERGER = guard.GuardPersona(
    slug="mona",
    allow=frozenset({"read_code", "merge_pr", "push_main", "force_push"}),
    deny=frozenset({"write_code"}),
    allow_scopes=(),
    deny_scopes=(),
)


def check(command: str, cwd: Path, persona: guard.GuardPersona = DEV):
    return guard.evaluate_bash(command, cwd, persona)


# --- the class that is now closed ------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "bash -c 'git push origin main'",
        'bash -c "git push origin main"',
        "sh -c 'git push origin main'",
        "zsh -c 'git push origin main'",
        "dash -c 'git push origin main'",
        "ksh -c 'git push origin main'",
        "/bin/bash -c 'git push origin main'",
        "/usr/bin/env bash -c 'git push origin main'",
        "env FOO=1 bash -c 'git push origin main'",
        "env -i bash -c 'git push origin main'",
        "env -u HOME bash -c 'git push origin main'",
        # the payload is a compound command; every top-level piece is inspected
        "bash -c 'cd /tmp && git push origin main'",
        "bash -c 'echo hi; git push origin main'",
        # the wrapper is not the first thing on the line
        "echo hi && bash -c 'git push origin main'",
    ],
)
def test_a_wrapped_denied_command_is_now_adjudicated(command: str, tmp_path: Path) -> None:
    decision = check(command, tmp_path)
    assert not decision.allowed, f"{command!r} passed uninspected"
    assert "push_main" in decision.verbs
    assert "inside a shell wrapper" in decision.reason
    # It is a real capability judgement, not a structural refusal: the merger
    # persona runs the identical command untouched.
    assert decision.adjudicated is True
    assert check(command, tmp_path, MERGER).allowed


def test_wrapped_gh_pr_merge_is_adjudicated(tmp_path: Path) -> None:
    decision = check("bash -c 'gh pr merge 12 --squash'", tmp_path)
    assert not decision.allowed
    assert "merge_pr" in decision.verbs
    assert check("bash -c 'gh pr merge 12 --squash'", tmp_path, MERGER).allowed


def test_wrapping_something_harmless_stays_harmless(tmp_path: Path) -> None:
    """The recursion must not turn every wrapper into a denial."""
    for command in (
        "bash -c 'ls -la'",
        "bash -c 'git status'",
        "bash -c 'npm test'",
        "bash -c 'git push origin dara/42-fix'",
    ):
        decision = check(command, tmp_path)
        assert decision.allowed, f"{command!r}: {decision.reason}"


# --- ambiguity: conservative-deny, narrowed --------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        # unbalanced quoting inside the payload — untokenisable
        """bash -c "git push 'origin main" """.strip(),
        # nested past the depth cap of 1
        "bash -c 'bash -c \"git push origin main\"'",
    ],
)
def test_an_uninspectable_payload_is_conservatively_denied(
    command: str, tmp_path: Path
) -> None:
    decision = check(command, tmp_path)
    assert not decision.allowed, f"{command!r} passed"
    assert set(decision.verbs) <= {"merge_pr", "push_main", "force_push"}
    assert "uninspectable" in decision.reason


def test_the_conservative_deny_is_narrowed_to_three_verbs(tmp_path: Path) -> None:
    """The whole cost of (a) lands on personas that deny these three anyway.

    A persona holding them runs an uninspectable wrapper unchanged — so the
    mechanism never shouts at the persona it was not built for.
    """
    command = "bash -c 'bash -c \"whatever\"'"
    assert check(command, tmp_path, MERGER).allowed
    # And a persona denying only ONE of them is denied on exactly that one.
    partial = guard.GuardPersona(
        slug="p",
        allow=frozenset({"read_code", "push_main", "force_push"}),
        deny=frozenset({"merge_pr"}),
        allow_scopes=(),
        deny_scopes=(),
    )
    decision = check(command, tmp_path, partial)
    assert not decision.allowed
    assert decision.verbs == ("merge_pr",)


def test_the_policy_comes_from_the_artifact_not_the_code(tmp_path: Path) -> None:
    """`commands.wrappers` is data, like every other rule (ADR-016 §4.2)."""
    policy = rules.load_rules().wrapper_policy
    assert policy.enabled
    assert policy.max_depth == 1
    assert policy.unparsed_conservative_verbs == ("merge_pr", "push_main", "force_push")
    assert "bash" in policy.programs and "-c" in policy.inline_flags


def test_a_disabled_wrapper_policy_restores_the_old_posture(
    monkeypatch, tmp_path: Path
) -> None:
    """Absent `commands.wrappers`, a rules_version-2 document is pre-ADR-034.

    Silence in an add-only block means "not configured", and reading it as
    anything else would have baron enforce a policy no document asked for.
    """
    from dataclasses import replace

    disabled = replace(rules.load_rules(), wrapper_policy=rules.WrapperPolicy())
    monkeypatch.setattr(guard, "_rules", lambda: disabled)
    assert check("bash -c 'git push origin main'", tmp_path).allowed


# --- the bound: what still gets through ------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        # a non-shell interpreter — a whole parser away, deliberately not built
        "python3 -c \"import os; os.system('git push origin main')\"",
        "perl -e 'system(\"git push origin main\")'",
        "node -e \"require('child_process').exec('git push origin main')\"",
        # indirection through the shell's own features
        "eval \"$PUSH_CMD\"",
        "echo 'git push origin main' | bash",
        "echo Z2l0IHB1c2ggb3JpZ2luIG1haW4= | base64 -d | sh",
        "xargs -I{} git {} < commands.txt",
        # a script file: its CONTENTS are never read
        "./deploy.sh",
        "bash deploy.sh",
    ],
)
def test_the_uncovered_wrapper_forms_are_still_uncovered(
    command: str, tmp_path: Path
) -> None:
    """NOT a wish list — the published bound of ADR-034 §4.3a, pinned.

    If one of these ever starts failing, the honest response is to decide
    whether the new coverage was intended and to move the bound in the docs,
    NOT to delete the case. A silently-widened claim is the failure mode this
    project names.
    """
    assert check(command, tmp_path).allowed, (
        f"{command!r} is now caught — that is a SCOPE CHANGE. Update ADR-034 "
        "§4.3a, guard.py's module docstring and cli/README before moving this "
        "case; the published bound must match the code."
    )


def test_the_home_settings_unwire_via_shell_is_still_open(tmp_path: Path) -> None:
    """ADR-034 §6's first bound, in the form an agent would actually use it.

    Guard governs capability verbs in shell, not general shell. A redirect into
    the home settings file is neither a git/gh verb nor a Write tool call, so
    nothing here sees it — this is exactly why the positioning stays "a policy
    guard for cooperating agents, not a security boundary".
    """
    assert check("echo '{}' > ~/.claude/settings.json", tmp_path).allowed
