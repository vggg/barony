# Governed-memory evaluation fixtures (P3.3)

The labeled corpus behind `baron memeval`. Run it from the repo root:

```bash
uv run --project cli baron memeval --fixtures evals/governed-memory
uv run --project cli baron memeval --fixtures evals/governed-memory --json | jq '.approaches[0].retrieval.per_query'
```

**Honest bound.** This measures retrieval and propagation quality **on
fixtures**. It is not a live audit of any repository and it observes no running
fleet. A number here is a statement about this fixture set and nothing else. Its
purpose is comparison — the same labeled set, scored the same way, across
approaches — so that
[P3.4](../../docs/adr/ADR-031-governed-memory-eval-harness.md) can choose a
knowledge backend on a measured delta instead of a guess.

## Layout

| Path | What it is |
|---|---|
| `fixtures.yaml` | build manifest (ordered commits, the two uncitable sources, the out-of-corpus file), labeled queries, labeled events |
| `corpus/` | a collab-repo-shaped tree: `docs/adr/`, `decisions/index.md`, `findings/index.md`, `_handoff/`, plus one `wiki/` note that `baron export` deliberately does not walk |

The harness copies `corpus/` into a throwaway directory, `git init`s it, and
replays the manifest's commits — so every record carries a real
`path + commit_sha` and the citation check has something to resolve. Nothing is
written back here.

## The case set

`fixtures.yaml` covers every case P3.3 names, and
`cli/tests/test_memeval.py::test_fixture_set_covers_every_case_the_spec_names`
fails if one goes missing: routine commit, release, accepted / proposed / parked
/ superseded ADR, thesis-changing finding, duplicate event, bad or missing
source SHA.

Three fixtures exist to price things that are usually assumed away:

- `_handoff/2026-08-13-1700-tess-uncited-draft.md` is **never committed**. It
  holds an answer to query `Q8` that no strategy can retrieve — the retrieval
  cost of ADR-015's citation gate, measured rather than argued.
- `_handoff/2026-08-12-1100-rex-modified-note.md` is committed and then edited,
  so it is skipped by the gate and emitted only under `--allow-dirty`.
- `wiki/research-agent-identity-lightweight.md` is in the tree and **outside the
  four exported corpora**. It is gold for the flagship query and unreachable by
  construction, which is what the reported **retrieval ceiling** counts.

## The flagship fixture

Query `Q1-identity-flagship` is the 2026-08-04 incident this repo actually lived
through: an un-onboarded agent committed under the owner's git identity, nothing
in the repo could attribute it, a survey was written, and a decision promoted
it. In the corpus that is finding `F4`, the handoff that carries the survey
pointer, `ADR-027`, and — a day later — a second persona re-deriving the same
question in a second handoff.

It is the case the harness exists to prevent, so its numbers are pinned in the
test suite. **Measured result:** the lexical baseline retrieves all three
in-corpus gold records, the first at rank 1; its only miss is the survey note,
because that note is not in the exported corpus at all. The failure mode is
corpus coverage, not ranking.

## Editing the fixtures

- Gold keys are `<kind>:<id>` exactly as `baron export` emits them — `adr:ADR-027`,
  `finding:F4`, `decision:D6`, or a handoff's filename stem.
- A gold key that names nothing in the corpus is legal and meaningful: it is
  counted against the ceiling, not treated as a typo.
- Any file added under `corpus/` must be named by a commit in the manifest, or
  marked `uncommitted`. An untracked stray would silently vanish from every
  measurement, so `materialize()` refuses to build instead.
- Do not tune the corpus until a strategy scores the way you expected. The Q2
  vocabulary-gap probe failed to defeat term overlap and is reported that way.
