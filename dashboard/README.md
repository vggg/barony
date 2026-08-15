# Fleet dashboard

A static, server-less dashboard over the Barony fleet, published to GitHub Pages.
Three visual treatments render the **same** committed JSON snapshot:

| Path | Version | Look |
|---|---|---|
| `/` | index | Landing page linking the three |
| `/v1/` | **Calm control** *(primary)* | Dark, one violet accent, hierarchy from type and spacing |
| `/v2/` | Editorial / analyst | Bright paper, serif masthead, printed-briefing feel |
| `/v3/` | Ops wall | Dense monospace grid with sparklines, for an always-on monitor |

Panels are identical across versions: observer summary, KPI row, portfolio
project states, registered agents + identity state, fleet-health metrics,
observer flags, merge queue, and the owner action queue.

## The privacy boundary

The coordination collab repo (`_meta` + `barony`, ADR-025 monorepo) is **private
and stays private**. It is never published, never mirrored, and never read by CI.

What ships is a **one-way, curated projection**:

```
   PRIVATE                          PUBLIC (this repo)
   coordination monorepo  ──▶  build_data.py  ──▶  dashboard/data/fleet.json
   (baron status/health/export)   sanitise           committed, published
```

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

> `baron export` is single-project: run at a monorepo **root** it walks no
> subdirs and reports zero records. The builder therefore loops the registered
> projects itself and sums the per-project exports.

## Previewing locally

`fetch()` will not read `file://` URLs, so serve the directory:

```bash
python3 -m http.server -d dashboard 8080
# then open http://localhost:8080/  ·  /v1/  ·  /v2/  ·  /v3/
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
`dashboard/**`, and on manual dispatch.

**One-time owner step:** in *Settings → Pages → Build and deployment*, set
**Source** to **GitHub Actions**. Until that is set, the deploy step fails —
everything else in the workflow still runs.

## Layout

```
dashboard/
  index.html          landing page linking the three versions
  build-data.sh       regenerate the snapshot (wrapper)
  build_data.py       the sanitising projection — stdlib only
  check_snapshot.py   leak / shape / honesty gate — runs in CI
  data/fleet.json     the committed, published snapshot
  assets/fleet.js     the one shared data layer (fetch, derive, format, sparkline)
  v1/ v2/ v3/         index.html + style.css per version
```

`assets/fleet.js` is where DRY lives: every figure, label and caveat is derived
once, so a metric cannot say one thing on v1 and something else on v3. The three
versions differ only in presentation.
