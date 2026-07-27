"""Repo lint (stdlib only). Fails on:

  (a) unfilled {{placeholder}} tokens outside template directories — templates
      (skills/*/assets/, legacy/, tests/examples/) legitimately carry tokens; everything
      else must be fully filled. Code fences and inline code in markdown are exempt
      (schema docs show tokens as examples).
  (b) dead relative markdown links, repo-wide.
  (c) fixture-name leaks — the acceptance fixtures' display names ("Tess"/"Rex")
      appearing in shipped templates under skills/*/assets/.
  (d) version mismatch between .claude-plugin/plugin.json and the
      skills/barony/SKILL.md frontmatter.

Run: python tests/lint_repo.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directories (repo-relative, with trailing slash) whose files are templates/fixtures and
# may carry unfilled {{...}} tokens and fixture names.
TEMPLATE_DIRS = (
    "skills/barony/assets/",
    "skills/multi-agent-audit/assets/",
    "legacy/",
    "tests/examples/",
    # baron's vendored copy of the skill templates (ADR-006; kept byte-identical
    # to skills/barony/assets/collab-repo/ by cli/tests/test_template_sync.py).
    "cli/src/baron/data/templates/",
)
SKIP_DIRS = {".git", "__pycache__", ".claude", "node_modules", ".venv", ".pytest_cache"}

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"  FAIL: {msg}")


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def walk(exts=None):
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if exts and not name.lower().endswith(exts):
                continue
            yield os.path.join(dirpath, name)


def in_template_dir(path):
    r = rel(path)
    return any(r.startswith(t) for t in TEMPLATE_DIRS)


def strip_code(md_text):
    """Remove fenced code blocks and inline code spans from markdown text."""
    out, in_fence = [], False
    for line in md_text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(re.sub(r"`[^`]*`", "", line))
    return "\n".join(out)


# --- (a) unfilled placeholder tokens outside template dirs ---------------------------
def check_placeholders():
    print("(a) unfilled {{placeholder}} tokens outside template dirs")
    for path in walk((".md", ".yaml", ".yml", ".json")):
        if in_template_dir(path):
            continue
        if rel(path) == "CHANGELOG.md":
            continue  # history quotes template tokens verbatim; never rewritten
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        if path.endswith(".md"):
            text = strip_code(text)
        for tok in sorted(set(re.findall(r"\{\{[A-Za-z0-9_.\- ]+\}\}", text))):
            fail(f"[placeholder] {rel(path)}: {tok}")


# --- (b) dead relative markdown links ------------------------------------------------
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def check_links():
    print("(b) dead relative markdown links")
    for path in walk((".md",)):
        with open(path, encoding="utf-8", errors="replace") as f:
            text = strip_code(f.read())
        for target in LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if "{{" in target or "<" in target:
                continue  # templated / illustrative
            target_path = target.split("#", 1)[0]
            if not target_path:
                continue
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target_path))
            if not os.path.exists(resolved):
                fail(f"[dead-link] {rel(path)}: ({target})")


# --- (c) fixture-name leaks in shipped templates -------------------------------------
def check_fixture_leaks():
    print("(c) fixture-name leaks (Tess/Rex) in skills/*/assets/")
    name_re = re.compile(r"\b(Tess|Rex)\b")
    for path in walk():
        r = rel(path)
        if not (r.startswith("skills/") and "/assets/" in r):
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, 1):
                m = name_re.search(line)
                if m:
                    fail(f"[fixture-leak] {r}:{lineno}: '{m.group(1)}'")


# --- (d) plugin.json vs SKILL.md frontmatter version ---------------------------------
def check_versions():
    print("(d) plugin.json vs SKILL.md version")
    with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
        plugin_version = json.load(f)["version"]
    skill_path = os.path.join(ROOT, "skills", "barony", "SKILL.md")
    skill_version = None
    with open(skill_path, encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if m:
        vm = re.search(r"^version:\s*(\S+)\s*$", m.group(1), re.M)
        if vm:
            skill_version = vm.group(1)
    if skill_version is None:
        fail("[version] SKILL.md frontmatter has no version field")
    elif skill_version != plugin_version:
        fail(f"[version] plugin.json={plugin_version} != SKILL.md={skill_version}")
    else:
        print(f"  version {plugin_version} consistent")


def main():
    check_placeholders()
    check_links()
    check_fixture_leaks()
    check_versions()
    print()
    if FAILURES:
        print(f"REPO LINT: FAIL ({len(FAILURES)} finding(s))")
        sys.exit(1)
    print("REPO LINT: PASS")


if __name__ == "__main__":
    main()
