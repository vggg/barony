# Contributing

## Scope

Refinements to the multi-agent pattern emitted by this skill are welcome. Pattern evolution is governed by the ADR process (`docs/adr/`); see [ADR-001](docs/adr/ADR-001-runtime-agnostic-multi-agent-bootstrap.md) for the v1.0 direction (runtime-agnostic spec + adapters — Claude Code, code-puppy, pydantic-ai, and a generic Tier-1 fallback as of v1.6).

If you want to explore a fundamentally different coordination substrate (something other than a git repo of markdown/yaml), fork this and publish a separate skill rather than expanding this one's scope.

## Before opening a PR

Open an issue first describing what you want to change and why. Small fixes (typos, broken links, minor wording) don't need an issue.

## How to test

1. Fork this repo.
2. Install from your fork: `/plugin install /path/to/your/fork`
3. Invoke in a throwaway directory: ask Claude to use the `barony` skill to set up a test project (on another runtime, invoke the neutral canon files by path — see [`USING-WITH-CODE-PUPPY.md`](USING-WITH-CODE-PUPPY.md)). Or skip the plugin entirely: `pip install barony && baron init …`.
4. Verify the emitted files match your intended changes and all placeholders resolve correctly.

For PRs touching adapters, references, or the canonical contract files, also run the tests before pushing (stdlib only — no dependencies):

```bash
python3 tests/bi_runtime_accept.py
python3 tests/lint_repo.py
python3 tests/check_docs_coverage.py   # advisory — see "Documentation is part of every PR"
```

The acceptance harness parses the machine-readable capability maps in the adapters' `HYDRATE.md` files and validates that one `persona.yaml` hydrates to an equivalent behavior contract on every adapter (Claude Code, code-puppy, pydantic-ai, generic) with consistent enforcement claims. The lint catches unfilled placeholders, dead relative links, fixture-name leaks, and plugin/SKILL version drift. CI (`.github/workflows/ci.yml`) runs both on every push and PR. PRs touching `cli/` (baron, including the capability-rules artifact and the runtime hydrators) also run `uv run --project cli pytest cli/tests`.

## Documentation is part of every PR

A PR that ships behavior, structure, or developer-experience changes without updating the relevant docs is not done. Same PR — not a follow-up.

Checklist (apply each line if relevant to the change):

- [ ] **Affected ADRs** — status frontmatter AND body headers reflect reality (no internal inconsistency between `status:` and the table header)
- [ ] **`CLAUDE.md`** — updated if conventions / layout / repo rules / canonicality changed
- [ ] **`README.md`** — updated if user-facing usage / modes / version / installation changed
- [ ] **`CHANGELOG.md`** — one line per PR minimum, under `[Unreleased]` between releases
- [ ] **`STATUS.md`** — mark multi-step plan progress (e.g. ADR-001 §10 step N done)

Reviewers must request docs before merging, not after.

**Exception:** strictly cosmetic single-file changes (typo fixes, broken link updates, status syncs) may skip the broader checklist — but still update `CHANGELOG.md` under `[Unreleased]`.

### The advisory check

The rule above was prose from 2026-06-03 to 2026-08-14, which meant it held exactly as
well as whoever remembered it. CI now runs it:

```bash
python3 tests/check_docs_coverage.py            # warn, exit 0
python3 tests/check_docs_coverage.py --strict   # exit 1 on an uncovered change
```

It warns when a PR changes `cli/` or `skills/` but touches neither `CHANGELOG.md` nor
anything under `docs/`. That is the weakest form of the rule, on purpose.

**It is advisory, and the honesty is the point.** It sees that a file changed, not that
the change *describes what shipped* — a one-word CHANGELOG edit satisfies it. And its
false positives are real: a refactor, a test-only fix, or a docstring typo genuinely owes
no docs. A gate that cried wolf on those would teach people to click past it, which costs
more than the miss it prevents. So it prints and exits 0. Answer the warning; don't route
around it. Escalating it to `--strict` in CI is a one-line change, and the right moment to
make it is when there is evidence the warning is being ignored rather than answered.

Excluded from "product change": `cli/tests/` and the vendored `cli/src/baron/data/templates/`
(a drift-guarded copy — its documentation belongs to the source it was synced from).

## What's in scope

- Template content and wording improvements
- New placeholders (with corresponding SKILL.md inventory updates)
- Emit process clarity (clearer steps, better verification instructions)
- Reference documentation (`references/design-decisions.md`, `references/obsidian-setup.md`)
- Persona archetype templates (`assets/collab-repo/agents/`)
- Bug fixes and leak prevention
- Runtime adapters per ADR-001 (`adapters/<runtime>/HYDRATE.md` and supporting canonical files)
- Persona archetypes per ADR-001 (dev / autonomous-event / autonomous-cron / librarian, plus future archetypes the spec defines)
- ADR amendments (PRs against `docs/adr/`)

## What's out of scope

- Self-modifying or self-updating skill behaviour
- Non-git coordination substrates (publish a separate skill for this)

## License

This project is MIT licensed. By submitting a pull request, you agree that your contributions will be licensed under the same MIT license.
