# The published site

`dashboard/` is the GitHub Pages root for `vggg.github.io/barony/`. It holds two
kinds of page, both static and both built from a committed source rather than at
request time:

| Path | Page | Source |
|---|---|---|
| `/` | Site index — the map of everything below | hand-written `index.html` |
| `/overview/` | **Product overview** | `docs/product-overview.md` |
| `/value-map/` | **Capability → value → metric** | `docs/capability-value-map.md` |
| `/v1/` | Fleet dashboard — **Calm control** *(primary)* | `data/fleet.json` |
| `/v2/` | Fleet dashboard — Editorial / analyst | `data/fleet.json` |
| `/v3/` | Fleet dashboard — Ops wall | `data/fleet.json` |

All three dashboard versions render the **same** committed snapshot; their panels
are identical (observer summary, KPI row, portfolio project states, registered
agents + identity state, fleet-health metrics, observer flags, merge queue, owner
action queue) and they differ only in presentation.

The two document pages share one hand-written stylesheet, `assets/site.css` — the
v1 "calm control" treatment applied to prose, so the whole site reads as one
thing.

## The document pages

`docs/product-overview.md` and `docs/capability-value-map.md` stay the source of
truth. The pages under `overview/` and `value-map/` are a **styled projection** of
them, committed so Pages can serve them with no build step:

```bash
./dashboard/build-docs.sh                    # render both pages
python3 dashboard/build_docs.py --check      # the CI drift guard
```

Never edit the emitted HTML — the next build overwrites it, and `--check` fails
the build in the meantime. Prose changes go in the markdown; layout changes go in
`build_docs.py` (structure) or `assets/site.css` (styling).

`--check` runs in CI on every push and PR, and again before every Pages deploy.
Staleness is the failure mode worth gating: an edited paragraph that never reached
the site publishes last week's copy under this week's URL, and nothing about the
page looks wrong.

The renderer is stdlib-only and deliberately implements just the markdown subset
those two documents use. An unsupported construct should surface as a visible
rendering bug rather than be silently half-handled.

In the capability map, the `Status` column's leading verdict is promoted to a
coloured pill — emerald **proven**, violet **instrumented**, amber
**aspirational** — with mixed verdicts keeping both pills rather than being
rounded to the flattering one.

## The privacy boundary

The coordination collab repo (`_meta` + `barony`, ADR-025 monorepo) is **private
and stays private**. It is never published, never mirrored, and never read by CI.

What ships is a **one-way, curated projection**:

```
   PRIVATE                          PUBLIC (this repo)
   coordination monorepo  ──▶  build_data.py  ──▶  dashboard/data/fleet.json
   (baron status/health/export)   sanitise           committed, published
```

The document pages are outside that boundary entirely: they read two markdown
files already public in this repo.

`dashboard/build_data.py` runs only read-only `baron` reporters, then strips:

- **absolute local paths** — reduced to their last two components, so a finding
  still says *which* working copy it is about with no home directory or username;
- **the event-plane directory** and the collab root;
- **record bodies and handoff filenames** — counts only.

What does ship is either already public (PR numbers, branch names and titles on
`vggg/barony`) or synthetic (the `*@barony.local` persona git identities).

`dashboard/check_snapshot.py` is the gate: it fails on a leaked path, a leaked
credential, a malformed snapshot, or a metric that claims a number it never
measured. It runs in CI on every push and PR, and again before every Pages
deploy — so a leaky snapshot cannot land or publish.

## Regenerating the snapshot

Never hand-edit `data/fleet.json` — a hand-edited snapshot is a lie the
dashboard would render faithfully. Regenerate it:

```bash
./dashboard/build-data.sh                                  # default collab path
BARONY_COLLAB=~/path/to/collab ./dashboard/build-data.sh   # or point it somewhere
python3 dashboard/check_snapshot.py                        # verify before committing
git diff dashboard/data/fleet.json                         # review what changed
```

The script builds `baron` from this repo's own `cli/` source via
`uv run --project cli`, so it is never behind an installed copy. Override with
`BARON_CMD` if you want a different binary.

### The build fetches first

`baron status` reads **local git only**. A shared clone that nobody pulls — every
session working in its own worktree — keeps remote-tracking refs for branches that
were merged and deleted on origin weeks ago, and reports each one as a live
`unmerged-branch` red. Published, that is a wall of red about this laptop rather
than about the fleet. It happened: one snapshot carried ~21 phantom reds.

So before reading anything, the build refreshes every working copy the projects'
manifests name (`repos[]`, `workspace.clones[]`, `workspace.worktrees_root` — the
same targets `baron status` evaluates):

- `git fetch origin --prune --prune-tags --tags` on each distinct object store
  (worktrees share one with their main clone, so it runs once);
- `git merge --ff-only origin/<default>` **only** where the copy is clean and
  already sitting on its default branch. Never a checkout, never a rebase, never a
  merge commit — a snapshot build must not be able to lose work.

Every outcome lands in `generator.refresh` (labels only, never paths), and the
`honesty` block states plainly how current the git data is. A fetch that cannot
reach origin is **recorded, not swallowed**: the snapshot says which copies are
stale, `owner_actions` gains a `freshness` warning, and `check_snapshot.py` fails
the build if a stale snapshot carries no caveat. `--no-refresh` reads the clones
exactly as found and declares itself stale.

> `baron export` is single-project: run at a monorepo **root** it walks no
> subdirs and reports zero records. The builder therefore loops the registered
> projects itself and sums the per-project exports.

## Previewing locally

`fetch()` will not read `file://` URLs, so serve the directory:

```bash
python3 -m http.server -d dashboard 8080
# then open http://localhost:8080/  ·  /overview/  ·  /value-map/  ·  /v1/  ·  /v2/  ·  /v3/
```

## Honest reporting

The dashboard is a showcase, so its numbers are held to a stricter standard than
a pretty chart usually is:

- A metric with an **empty denominator** renders as `n/a` with its basis stated —
  never as a flattering 0% or 100%. `mutation_kill` shows `n/a` today because no
  mutations have been run; that is not a pass.
- **Single-observation** figures are labelled `n=1` and described as indicative,
  not as a trend.
- The event plane is currently **shared at the monorepo root**, so verdicts roll
  up to the portfolio but cannot be attributed to a project. The coverage panel
  says so rather than showing two clean per-project boards.
- Capabilities that are **specified but not deployed against this fleet** —
  per-persona commit signing (ADR-027) and the observer archetype (ADR-030) — are
  shown as *not active* with a note. Both ADRs are now on main; neither is running
  here. An empty watchlist is not a clean one.

## Hosting

`.github/workflows/pages.yml` uploads `dashboard/` as the Pages artifact, so the
site root is this directory. It runs on pushes to `main` that touch
`dashboard/**` or either of the two source documents, and on manual dispatch. It
re-runs both gates — the snapshot guard and the doc-page drift check — before
uploading, so a stale or leaky tree cannot publish.

**One-time owner step:** in *Settings → Pages → Build and deployment*, set
**Source** to **GitHub Actions**. Until that is set, the deploy step fails —
everything else in the workflow still runs.

## Layout

```
dashboard/
  index.html          site index — the one page with no generated source
  build-data.sh       regenerate the fleet snapshot (wrapper)
  build_data.py       the sanitising projection — stdlib only
  check_snapshot.py   leak / shape / honesty gate — runs in CI
  build-docs.sh       regenerate the document pages (wrapper)
  build_docs.py       markdown -> HTML renderer + `--check` drift guard — stdlib only
  data/fleet.json     the committed, published snapshot
  assets/fleet.js     the one shared data layer (fetch, derive, format, sparkline)
  assets/site.css     the one stylesheet for the index + document pages
  overview/           GENERATED from docs/product-overview.md
  value-map/          GENERATED from docs/capability-value-map.md
  v1/ v2/ v3/         index.html + style.css per dashboard version
```

`assets/fleet.js` is where DRY lives for the dashboards: every figure, label and
caveat is derived once, so a metric cannot say one thing on v1 and something else
on v3. `build_docs.py` is the same discipline for the prose — the markdown is
written once and projected, never re-typed into HTML.
