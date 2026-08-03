"""Bi-runtime acceptance harness (v1.4 — parses the REAL adapter tables).

Earlier versions re-implemented the capability→tool mapping in Python and tested that
re-implementation against itself (tautological). This version parses the actual
machine-readable capability maps in each adapter's HYDRATE.md (the `capability-map:v1`
marker) plus the frozen vocabulary table in references/capability-vocab.v1.md, and asserts:

  (a) every verb in capability-vocab.v1.md is mapped in EVERY adapter (no extras, no gaps),
      and each adapter's Class column matches the vocabulary's enforceability class;
  (b) the tess and rex fixtures in tests/examples/ hydrate to an EQUIVALENT behavior
      contract on every adapter, per those parsed tables (identity, granted capability
      categories, denies, whole-tool denial honoring);
  (c) enforcement-tier claims are consistent: the generic (Tier 1) adapter claims
      `instructed` for everything; Tier-3 adapters (claude, code-puppy, pydantic-ai)
      claim `enforced` exactly for whole-tool verbs. Sub-tool rows are `instructed`,
      with exactly two per-adapter allowances, both limited to the five guard-covered
      verbs (write_path, merge_pr, push_main, force_push, edit_other_personas — the
      verbs capability-rules.v1.yaml defines detection for): the claude adapter may
      claim the exact qualified form `enforced-with-baron (instructed otherwise)`
      (the baron guard PreToolUse hook is external and degrades without baron,
      ADR-004 §2.4), and the pydantic-ai adapter may claim plain `enforced`
      (in-process interception cannot be absent — ADR-004 addendum §4.2). Any other
      wording, or either allowance on an open_pr/run_tests row, fails.

Editing a HYDRATE.md table incorrectly (dropping a verb, flipping a Grants category,
overclaiming enforcement) fails this test.

Run: python tests/bi_runtime_accept.py     (stdlib only — no PyYAML needed)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILL = os.path.join(ROOT, "skills", "barony")
ADAPTERS_DIR = os.path.join(SKILL, "assets", "collab-repo", "adapters")
VOCAB = os.path.join(SKILL, "references", "capability-vocab.v1.md")
PERSONA_SCHEMA = os.path.join(SKILL, "references", "persona.schema.md")
ADAPTERS = ["claude", "code-puppy", "generic", "pydantic-ai"]
TIER3_ADAPTERS = {"claude", "code-puppy", "pydantic-ai"}
MARKER = "capability-map:v1"
RITUAL_MARKER = "ritual-map:v1"
RITUAL_MARKER_END = "/ritual-map:v1"
# The three adapters that render ritual tokens from PROSE. pydantic-ai renders in
# code (baron.runtimes.pydantic_ai._RITUAL_LINES) and has no prose surface to parse;
# cli/tests/test_schemas.py guards that side.
PROSE_RITUAL_ADAPTERS = ["claude", "code-puppy", "generic"]
VALID_GRANTS = {"read", "write", "shell"}
# The five sub-tool verbs the capability-rules artifact defines detection for
# (cli/src/baron/data/capability-rules.v1.yaml). Only these rows may carry a
# guard-enforcement claim; open_pr/run_tests are not guard-parsed anywhere.
GUARD_VERBS = {"write_path", "merge_pr", "push_main", "force_push", "edit_other_personas"}
# The ONE accepted qualified form (exact string) for sub-tool denials that the
# baron guard PreToolUse hook enforces on Claude Code when baron is installed.
BARON_QUALIFIED = "enforced-with-baron (instructed otherwise)"
HOOK_GUARD_ADAPTERS = {"claude"}  # external hook wiring: qualified form allowed
NATIVE_GUARD_ADAPTERS = {"pydantic-ai"}  # in-process guard: plain `enforced` allowed
VALID_ENFORCEMENT = {"enforced", "instructed", BARON_QUALIFIED}

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"  FAIL: {msg}")


# ---------------------------------------------------------------------------
# Minimal YAML subset parser (stdlib-only) — enough for the persona fixtures.
# Supports: nested maps by indentation, lists of scalars, `- key: [a, b]` items,
# inline lists, quoted scalars, comments, and `>-` folded block scalars.
# ---------------------------------------------------------------------------
def _strip_comment(line):
    out, in_s, in_d = [], False, False
    for ch in line:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(tok):
    tok = tok.strip()
    if tok.startswith('"') and tok.endswith('"') and len(tok) >= 2:
        return tok[1:-1]
    if tok.startswith("'") and tok.endswith("'") and len(tok) >= 2:
        return tok[1:-1]
    return tok


def _parse_value(tok):
    tok = tok.strip()
    if tok.startswith("[") and tok.endswith("]"):
        inner = tok[1:-1].strip()
        return [_scalar(t) for t in inner.split(",")] if inner else []
    return _scalar(tok)


def parse_simple_yaml(path):
    with open(path, encoding="utf-8") as f:
        raw = [ln.rstrip("\n") for ln in f]
    lines = []
    for ln in raw:
        stripped = _strip_comment(ln)
        if stripped.strip():
            lines.append(stripped)

    def parse_block(idx, indent):
        """Parse lines starting at idx with exactly `indent` indentation."""
        # decide list vs map from the first line
        first = lines[idx].strip()
        container = [] if first.startswith("- ") or first == "-" else {}
        while idx < len(lines):
            ln = lines[idx]
            cur = len(ln) - len(ln.lstrip())
            if cur < indent:
                break
            if cur > indent:
                raise ValueError(f"unexpected indent at {path}: {ln!r}")
            body = ln.strip()
            if isinstance(container, list):
                if not body.startswith("-"):
                    break
                item = body[1:].strip()
                if ":" in item and not item.startswith("["):
                    k, _, v = item.partition(":")
                    container.append({_scalar(k): _parse_value(v)})
                else:
                    container.append(_parse_value(item))
                idx += 1
            else:
                k, _, v = body.partition(":")
                k = _scalar(k)
                v = v.strip()
                if v == ">-" or v == ">" or v == "|" or v == "|-":
                    # folded/literal block scalar: consume more-indented lines
                    idx += 1
                    parts = []
                    while idx < len(lines):
                        nxt = lines[idx]
                        ni = len(nxt) - len(nxt.lstrip())
                        if ni <= indent:
                            break
                        parts.append(nxt.strip())
                        idx += 1
                    container[k] = " ".join(parts)
                elif v == "":
                    # nested block
                    idx += 1
                    if idx < len(lines):
                        ni = len(lines[idx]) - len(lines[idx].lstrip())
                        if ni > indent:
                            container[k], idx = parse_block(idx, ni)
                        else:
                            container[k] = None
                    else:
                        container[k] = None
                else:
                    container[k] = _parse_value(v)
                    idx += 1
        return container, idx

    result, _ = parse_block(0, 0)
    return result


# ---------------------------------------------------------------------------
# Markdown table parsers
# ---------------------------------------------------------------------------
def parse_vocab(path):
    """Return {verb: class} from the frozen-vocabulary table."""
    verbs = {}
    with open(path, encoding="utf-8") as f:
        for ln in f:
            m = re.match(r"^\|\s*`([a-z_]+)`\s*\|[^|]*\|\s*([^|]+)\|", ln)
            if m:
                cls = m.group(2).strip()
                cls = "whole-tool" if cls.startswith("whole-tool") else (
                    "sub-tool" if cls.startswith("sub-tool") else cls)
                verbs[m.group(1)] = cls
    return verbs


def parse_ritual_tokens(path):
    """Ritual tokens from the canon's session-ritual table in persona.schema.md.

    Sourced from the prose spec rather than baron.schemas.RITUAL_TOKENS because this
    harness is stdlib-only and deliberately runs WITHOUT baron installed (ADR-006 §2).
    cli/tests/test_schemas.py guards the other direction — baron's constant against the
    same table — so the two meet in the middle on the canon.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"^##+\s*Session-ritual tokens.*?$", text, re.M)
    if not m:
        raise ValueError(f"no session-ritual token section in {path}")
    tokens = set()
    started = False
    for ln in text[m.end():].splitlines():
        row = re.match(r"^\|\s*`([a-z_]+)`\s*\|", ln)
        if row:
            started = True
            tokens.add(row.group(1))
            continue
        if started and ln.strip() and not ln.strip().startswith(("|", ">")):
            break
    if not tokens:
        raise ValueError(f"parsed no ritual tokens from {path}")
    return tokens


def parse_ritual_surface(path):
    """Return the set of ritual tokens declared after the ritual-map:v1 marker.

    Shape-tolerant by design: claude and code-puppy use pipe tables, generic uses a
    bullet list, and normalising them would be churn for its own sake. An entry must
    START its line with `|` or `-` followed immediately by the backticked token, so a
    token merely MENTIONED in surrounding prose is not miscounted as declared.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()
    pos = text.find(RITUAL_MARKER)
    if pos == -1:
        raise ValueError(f"no {RITUAL_MARKER} marker in {path}")
    end = text.find(RITUAL_MARKER_END, pos + len(RITUAL_MARKER))
    if end == -1:
        raise ValueError(f"no closing <!-- {RITUAL_MARKER_END} --> fence in {path}")
    tokens = set()
    for ln in text[pos:end].splitlines():
        # Entries are read ONLY inside the fence. An earlier cut scanned forward to
        # the next heading, which miscounted PROSE bullets after the surface as
        # declarations — the surface claimed a protection it did not have. The fence
        # also survives generic's wrapped continuation lines, which broke the cut
        # before that (it stopped at the first one and reported 4 of 5 missing).
        m = re.match(r"^\s*[|-]\s*`([a-z_]+)`", ln)
        if m:
            tokens.add(m.group(1))
    return tokens


def check_ritual_coverage(ritual_tokens):
    """(d) every ritual token is declared in every PROSE adapter surface.

    The gap this closes: `check_review_feedback` (ADR-008 §2) shipped to three of four
    runtimes because each renderer keeps its own surface and nothing cross-checked them.
    Both renderer styles fail SILENTLY — the code renderers echo the raw token, the prose
    surfaces simply omit the step — so nothing raised.
    """
    print("(d) ritual-token coverage across the prose adapter surfaces")
    for adapter in PROSE_RITUAL_ADAPTERS:
        path = os.path.join(ADAPTERS_DIR, adapter, "HYDRATE.md")
        try:
            declared = parse_ritual_surface(path)
        except ValueError as exc:
            fail(f"[ritual] {adapter}: {exc}")
            continue
        missing = sorted(ritual_tokens - declared)
        if missing:
            fail(f"[ritual] {adapter} declares no rendered step for: {missing}")
        extra = sorted(declared - ritual_tokens)
        if extra:
            fail(f"[ritual] {adapter} declares unknown ritual token(s): {extra}")
    if not FAILURES:
        print(f"  all {len(ritual_tokens)} ritual token(s) declared in "
              f"{len(PROSE_RITUAL_ADAPTERS)} prose adapter(s)")


def parse_adapter_map(path):
    """Return {verb: {class, grants, tools, enforcement}} from the capability-map table."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    pos = text.find(MARKER)
    if pos == -1:
        raise ValueError(f"no {MARKER} marker in {path}")
    rows = {}
    for ln in text[pos:].splitlines():
        m = re.match(r"^\|\s*`([a-z_]+)`\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|", ln)
        if not m:
            # stop at first non-table line after we started collecting rows
            if rows and ln.strip() and not ln.strip().startswith("|"):
                break
            continue
        verb = m.group(1)
        cls = m.group(2).strip()
        cls = "whole-tool" if cls.startswith("whole-tool") else (
            "sub-tool" if cls.startswith("sub-tool") else cls)
        grants = m.group(3).strip()
        tools = set(re.findall(r"`([^`]+)`", m.group(4)))
        # Full cell text (not first word): the baron-qualified enforcement form
        # is multi-word and only its EXACT wording is accepted.
        enforcement = re.sub(r"\*+", "", m.group(5)).strip()
        rows[verb] = {"class": cls, "grants": grants, "tools": tools,
                      "enforcement": enforcement}
    return rows


# ---------------------------------------------------------------------------
# Fixture hydration via the PARSED tables
# ---------------------------------------------------------------------------
def verb_list(items):
    """Normalize a capabilities list to [(verb, scopes_tuple)]."""
    out = []
    for it in items:
        if isinstance(it, dict):
            (k, v), = it.items()
            out.append((k, tuple(v) if isinstance(v, list) else (v,)))
        else:
            out.append((it, ()))
    return out


def hydrate(persona, amap):
    allow = verb_list(persona["capabilities"]["allow"])
    deny = verb_list(persona["capabilities"]["deny"])
    grants = {amap[v]["grants"] for v, _ in allow if v in amap}
    tools = set()
    for v, _ in allow:
        if v in amap:
            tools |= amap[v]["tools"]
    ident = persona["identity"]
    return {
        "identity": (ident["git_name"], ident["commit_prefix"], ident["routing_label"]),
        "grants": grants,
        "can_write": "write" in grants,
        "can_shell": "shell" in grants,
        "denies": {v for v, _ in deny},
        "tools": tools,
        "allow": {v for v, _ in allow},
    }


def main():
    vocab = parse_vocab(VOCAB)
    print(f"vocabulary: {len(vocab)} verbs — {sorted(vocab)}")
    if len(vocab) != 10:
        fail(f"expected the frozen 10-verb v1 vocabulary, parsed {len(vocab)}")

    maps = {}
    for name in ADAPTERS:
        path = os.path.join(ADAPTERS_DIR, name, "HYDRATE.md")
        try:
            maps[name] = parse_adapter_map(path)
        except ValueError as e:
            fail(str(e))
            continue

    # --- (a) coverage + class agreement per adapter ---
    for name, amap in maps.items():
        missing = set(vocab) - set(amap)
        extra = set(amap) - set(vocab)
        if missing:
            fail(f"[{name}] verbs missing from capability map: {sorted(missing)}")
        if extra:
            fail(f"[{name}] non-v1 verbs in capability map: {sorted(extra)}")
        for verb, row in amap.items():
            if verb in vocab and row["class"] != vocab[verb]:
                fail(f"[{name}] {verb}: class '{row['class']}' != vocab '{vocab[verb]}'")
            if row["grants"] not in VALID_GRANTS:
                fail(f"[{name}] {verb}: invalid Grants '{row['grants']}'")
            if row["enforcement"] not in VALID_ENFORCEMENT:
                fail(f"[{name}] {verb}: invalid Deny enforcement '{row['enforcement']}'")

    # --- cross-adapter Grants agreement (the runtime-neutral semantic) ---
    for verb in vocab:
        cats = {name: maps[name][verb]["grants"]
                for name in maps if verb in maps[name]}
        if len(set(cats.values())) > 1:
            fail(f"Grants for {verb} disagree across adapters: {cats}")

    # --- (c) enforcement-tier consistency ---
    for name, amap in maps.items():
        for verb, row in amap.items():
            if verb not in vocab:
                continue
            if name not in TIER3_ADAPTERS:
                if row["enforcement"] != "instructed":
                    fail(f"[{name}] Tier-1 adapter claims '{row['enforcement']}' for {verb}"
                         " (everything at Tier 1 is instructed)")
            else:
                expected = "enforced" if vocab[verb] == "whole-tool" else "instructed"
                allowed = {expected}
                if vocab[verb] == "sub-tool" and verb in GUARD_VERBS:
                    if name in HOOK_GUARD_ADAPTERS:
                        # baron guard hook (external, degrades without baron):
                        # guard-covered rows may claim the exact qualified
                        # form (and only that form) instead.
                        allowed.add(BARON_QUALIFIED)
                    if name in NATIVE_GUARD_ADAPTERS:
                        # in-process interception (cannot be absent): guard-
                        # covered rows may claim plain `enforced`.
                        allowed.add("enforced")
                if row["enforcement"] not in allowed:
                    fail(f"[{name}] {verb}: Deny enforcement '{row['enforcement']}' but the"
                         f" {vocab[verb]} class allows only {sorted(allowed)}")
        # Tier-3 adapters must name real tools; generic must not
        for verb, row in amap.items():
            if name in TIER3_ADAPTERS and not row["tools"]:
                fail(f"[{name}] {verb}: no runtime tools listed for a Tier-3 adapter")
            if name not in TIER3_ADAPTERS and row["tools"]:
                fail(f"[{name}] {verb}: Tier-1 adapter should not bind runtime tools")

    # --- (b) fixtures hydrate consistently across adapters ---
    for slug in ("tess", "rex"):
        path = os.path.join(HERE, "examples", slug, "persona.yaml")
        persona = parse_simple_yaml(path)
        used = {v for v, _ in verb_list(persona["capabilities"]["allow"])
                } | {v for v, _ in verb_list(persona["capabilities"]["deny"])}
        bad = used - set(vocab)
        if bad:
            fail(f"[{slug}] fixture uses non-v1 verbs: {sorted(bad)}")

        contracts = {name: hydrate(persona, maps[name]) for name in maps}
        ref_name = ADAPTERS[0]
        ref = contracts[ref_name]
        print(f"\n[{slug}] identity={ref['identity']} grants={sorted(ref['grants'])} "
              f"denies={sorted(ref['denies'])}")
        for name, c in contracts.items():
            for key in ("identity", "grants", "can_write", "can_shell", "denies"):
                if c[key] != ref[key]:
                    fail(f"[{slug}] {key} diverges: {ref_name}={ref[key]!r} vs {name}={c[key]!r}")
            # whole-tool denial honoring on Tier-3 adapters: if a denied verb's granted
            # category is not needed by ANY allowed verb, its tools must be absent.
            if name in TIER3_ADAPTERS:
                for verb in c["denies"]:
                    row = maps[name].get(verb)
                    if row and vocab.get(verb) == "whole-tool" and row["grants"] not in c["grants"]:
                        leaked = row["tools"] & c["tools"]
                        if leaked:
                            fail(f"[{slug}] [{name}] whole-tool denial of {verb} leaks tools"
                                 f" {sorted(leaked)}")
            print(f"        {name:10} can_write={c['can_write']} can_shell={c['can_shell']}"
                  f" tools={len(c['tools'])}")

    # --- (d) ritual-token coverage across the prose adapter surfaces ---
    try:
        ritual = parse_ritual_tokens(PERSONA_SCHEMA)
        print(f"ritual tokens: {len(ritual)} — {sorted(ritual)}")
        check_ritual_coverage(ritual)
    except ValueError as exc:
        fail(f"[ritual] {exc}")

    print()
    if FAILURES:
        print(f"BI-RUNTIME ACCEPTANCE: FAIL ({len(FAILURES)} failure(s))")
        sys.exit(1)
    print("BI-RUNTIME ACCEPTANCE: PASS")
    print("Every v1 verb is mapped in every adapter; fixtures hydrate to an equivalent")
    print("behavior contract on claude, code-puppy, generic, and pydantic-ai;")
    print("enforcement claims are consistent with the frozen vocabulary's")
    print("enforceability classes.")


if __name__ == "__main__":
    main()
