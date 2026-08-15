"""Docs coverage — does this change say anywhere what it did? (stdlib only)

`CONTRIBUTING.md` has carried the rule since 2026-06-03: **documentation lands with code
in the same PR, never as a follow-up.** Until now it was prose, enforced by whoever
remembered it. This is the same move ADR-028 made for the merge gate and ADR-029 made for
the prior-art sweep — a convention nobody mechanizes is a convention that holds until the
first hurried Friday.

The rule it checks is deliberately the weakest one that is still true: a change touching
`cli/` or `skills/` should update **either** `CHANGELOG.md` **or** something under
`docs/`. Not both, not a specific file, not a word count.

## This check is ADVISORY, and the honesty matters more than the coverage

It **warns; it does not fail the build** (exit 0 unless `--strict`). Two reasons, and
neither is squeamishness:

1. **It cannot read prose.** It sees that `CHANGELOG.md` changed, not that the change
   describes what shipped. A one-word edit satisfies it. Anything claiming to *enforce*
   documentation on that evidence would be claiming a property it never measured — the
   failure `dashboard/check_snapshot.py` exists to prevent.
2. **The false positives are real and legitimate.** A pure refactor, a test-only change,
   a typo fix in a docstring — none of these owe the CHANGELOG anything, and a gate that
   cries wolf on them teaches contributors to skip past it, which costs more than the
   miss it prevents.

So: a warning is a **prompt to think**, and the honest description of what it caught is
"you may have forgotten," not "you forgot." Escalating it to blocking is a decision worth
making explicitly, once there is evidence the warning is being ignored rather than
answered — and `--strict` is there so CI can be switched over in one line when that
evidence exists.

Run:
    python tests/check_docs_coverage.py              # warn, exit 0
    python tests/check_docs_coverage.py --strict     # exit 1 on an uncovered change
    python tests/check_docs_coverage.py --base main  # compare against another ref
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: A change under one of these owes the reader an explanation somewhere.
PRODUCT_PREFIXES = ("cli/", "skills/")

#: Paths that are the product's own tests or vendored copies — real work, but not the
#: kind a CHANGELOG entry is for. Excluded so the warning keeps meaning something.
EXEMPT_PREFIXES = (
    "cli/tests/",
    # Vendored templates are kept byte-identical to skills/ by a drift guard; the
    # documentation belongs to the source they were synced from, not to the copy.
    "cli/src/baron/data/templates/",
)

#: Any one of these satisfies the check.
DOC_PREFIXES = ("docs/",)
DOC_FILES = ("CHANGELOG.md",)


def git(*args):
    proc = subprocess.run(
        ["git", "-C", ROOT, *args], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def base_ref(explicit=None):
    """The ref to diff against. Falls back until something resolves.

    CI hands us the PR base; a local run usually wants `origin/main`. A repo with
    neither (a fresh clone with no remote, a shallow CI checkout) gets None, and the
    check reports that it could not run rather than inventing a comparison.
    """
    candidates = [explicit] if explicit else []
    candidates += [os.environ.get("BARON_DOCS_BASE"), "origin/main", "main"]
    for ref in candidates:
        if ref and git("rev-parse", "--verify", f"{ref}^{{commit}}"):
            return ref
    return None


def changed_files(base):
    """Committed changes since the merge base, PLUS anything still in the worktree.

    CI only ever sees the first set. A contributor running this before pushing has the
    docs edit sitting unstaged, and a check that answered "you forgot" while the file
    was open in their editor would be wrong in the most annoying possible way.
    """
    merge_base = git("merge-base", base, "HEAD") or base
    committed = git("diff", "--name-only", f"{merge_base}...HEAD")
    if committed is None:
        return None
    worktree = git("diff", "--name-only", "HEAD") or ""
    untracked = git("ls-files", "--others", "--exclude-standard") or ""
    seen = []
    for chunk in (committed, worktree, untracked):
        for line in chunk.splitlines():
            if line and line not in seen:
                seen.append(line)
    return seen


def covered(paths):
    return any(
        p in DOC_FILES or p.startswith(DOC_PREFIXES) for p in paths
    )


def product_changes(paths):
    return [
        p for p in paths
        if p.startswith(PRODUCT_PREFIXES) and not p.startswith(EXEMPT_PREFIXES)
    ]


def main():
    strict = "--strict" in sys.argv
    explicit = None
    if "--base" in sys.argv:
        i = sys.argv.index("--base")
        if i + 1 < len(sys.argv):
            explicit = sys.argv[i + 1]

    print("== docs coverage (advisory) ==")
    base = base_ref(explicit)
    if base is None:
        print("  SKIP: no base ref resolved (no origin/main, no main) — nothing to diff")
        return 0
    paths = changed_files(base)
    if paths is None:
        print(f"  SKIP: could not diff against {base!r}")
        return 0
    if not paths:
        print(f"  ok: no changes against {base}")
        return 0

    product = product_changes(paths)
    if not product:
        print(f"  ok: no cli/ or skills/ changes against {base} ({len(paths)} file(s))")
        return 0
    if covered(paths):
        print(f"  ok: {len(product)} product file(s) changed, and CHANGELOG.md or docs/ "
              f"was updated alongside")
        return 0

    shown = product[:10]
    print(f"  WARN: {len(product)} file(s) under cli/ or skills/ changed, but neither")
    print(f"        CHANGELOG.md nor anything under docs/ did:")
    for p in shown:
        print(f"          {p}")
    if len(product) > len(shown):
        print(f"          ... and {len(product) - len(shown)} more")
    print("        CONTRIBUTING.md: documentation lands with code, in the SAME PR.")
    print("        If this change genuinely owes no docs (a refactor, a test fix), it")
    print("        owes none — this check cannot tell, which is why it only warns.")
    return 1 if strict else 0


if __name__ == "__main__":
    sys.exit(main())
