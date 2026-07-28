# Migrating a clone-per-persona workspace to worktrees (baron M6)

Step-by-step conversion of a `workspace.clones` topology (one full clone per
persona) to the branch-per-persona worktree topology (`git worktree`, one
shared object store, `workspace.worktrees_root`). The worktree topology
*prevents* the stranding classes `baron status` only detects on clones
(ADR-003 §2.7): with one object store there is no "committed in a clone
nobody else can see" state — a persona's commits are visible to every working
copy the moment they exist.

Commands below use `baron worktree add|list|remove` (see
[`cli/README.md`](../cli/README.md)) plus plain git. Nothing here touches the
collab repo's content except `manifest.yaml`.

## Before you start

- Pick the migration moment: no persona session should be mid-task in a clone
  while you retire it.
- Have `baron` installed and the collab repo's `manifest.yaml` listing the
  clones under `workspace.clones` (that is what `baron status` sweeps).

## Step 1 — drain every clone (fetch/push everything)

For EACH persona clone in `workspace.clones`:

```bash
git -C <clone> status              # nothing uncommitted (commit or stash-drop deliberately)
git -C <clone> push origin --all   # every local branch reaches origin
git -C <clone> fetch --prune
```

Unpushed work on a clone you retire is work destroyed — this step is the
whole reason the migration has a checklist.

## Step 2 — verify with baron status

```bash
baron status --collab <collab> --fetch
```

Every clone must show NO `ahead` and NO `dirty` findings. `unmerged-branch`
reds are fine *if* the branch is pushed (it lives on origin; the worktree
topology will still see it) — park deliberate ones with a waiver
(`baron waiver add`). Do not proceed past a red `ahead`.

## Step 3 — create the worktrees

From the canonical code repo (the one that stays):

```bash
baron worktree add <persona> --root <worktrees_root>    # one per persona
baron worktree list
```

Each persona gets `<worktrees_root>/<persona>` on branch `persona/<persona>`
(created from the default branch). If a persona had a pushed feature branch
mid-flight, bring it into the worktree: `git -C <worktrees_root>/<persona>
checkout <branch>`.

**Per-worktree git identity (do not skip).** Worktrees share `.git/config`, so
without this every persona commits as the canonical repo's identity and the
commit-prefix/identity discipline silently breaks:

```bash
git -C <canonical> config extensions.worktreeConfig true
git -C <worktrees_root>/<persona> config --worktree user.name  <Persona>
git -C <worktrees_root>/<persona> config --worktree user.email <persona@project.local>
```

Also push each resting branch with an upstream so the session ritual's
`git pull` works: `git -C <worktrees_root>/<persona> push -u origin
persona/<persona>`. (Both learned in the 2026-07-23 pilot migration.)

## Step 4 — repoint the manifest

In `manifest.yaml`: remove the migrated entries from `workspace.clones` and
set `workspace.worktrees_root` (relative to `paths.root`, F7):

```yaml
workspace:
  worktrees_root: ../worktrees
```

`baron status` now sweeps each worktree's checked-out branch exactly like it
swept the clones (schema v1.2; the branch sweep runs once on the shared repo,
not once per worktree).

## Step 5 — repoint persona session context

Each persona's session `CLAUDE.md` (Tier 2) or workspace pointer carries the
old clone path. Update:

- the workspaces table / repo paths → `<worktrees_root>/<persona>`,
- any `git -C <old-clone-path>` ritual lines,
- the `baron guard` hook's `--persona-file` path in
  `.claude/settings.json` if it was relative to the old clone.

Re-hydrating from `persona.yaml` (adapter HYDRATE.md) is the clean way —
the yaml is canonical; the session files are derived.

**Low-churn alternative (used by the 2026-07-23 pilot migration):** leave every
path in the session files untouched by symlinking the old clone path to the
worktree — `mv <old-clone> <old-clone>.retired-<date> && ln -s
<relative-path-to-worktree> <old-clone-path>` — and add a short dated topology
note to the session `CLAUDE.md` instead of rewriting its paths. git works
transparently through the symlink; verify with `git -C <old-clone-path>
status` and a `config user.name` check.

## Step 6 — retire the old clones

Only after `baron status --fetch` is green on the new topology:

```bash
rm -rf <old-clone>        # its commits are on origin (step 1) and in the shared store
```

Keep one until the first real session on the new topology has pushed
something end-to-end, if you want a belt with the suspenders.

## Rollback (honest section)

The migration is low-risk because step 1 makes origin authoritative before
anything is deleted:

- **Before step 6** rollback is trivial: `baron worktree remove <persona>` for
  each worktree, restore the `workspace.clones` block in `manifest.yaml`, and
  keep using the clones — nothing was destroyed.
- **After step 6** the clones are gone but nothing of record went with them:
  re-clone (`git clone <remote> <path>`) and re-add the manifest entries.
  What you CANNOT recover after step 6: anything that was never pushed —
  stashes, uncommitted files you chose to drop, local-only branches you
  skipped in step 1. That is why step 2's "no red `ahead`, no `dirty`" gate is
  non-negotiable, and why step 1 says *deliberately*.
- Worktree gotcha: a worktree registers itself in the shared repo's
  `.git/worktrees/`; never delete a worktree directory with `rm -rf` alone —
  use `baron worktree remove`. If a worktree dir *was* moved or deleted outside
  baron, the stale registration is repairable without touching any commit:
  - `baron worktree prune --dry-run` then `baron worktree prune` — clears the
    stale registrations left behind by a deleted/moved worktree dir (wraps
    `git worktree prune`).
  - `baron worktree repair [<new-path>…]` — re-registers a worktree (or the main
    repo) that was *moved* on disk, fixing its admin links (wraps
    `git worktree repair`). Both only touch `.git/worktrees/` admin state — no
    branch or commit is affected.
