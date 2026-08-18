#!/usr/bin/env bash
# Regenerate dashboard/data/fleet.json from the PRIVATE coordination repo.
#
# The snapshot committed to this public repo is a curated projection: read-only
# `baron` reporters in, sanitised JSON out. Rerun this instead of editing the
# JSON by hand — a hand-edited snapshot is a lie the dashboard would render.
#
# The build FETCHES FIRST: every working copy the fleet's manifests name is
# `git fetch origin --prune`ed (and fast-forwarded when it is clean and on its
# default branch) before `baron status` / `baron health` read it. `baron` reads
# local git only, so an unpulled clone reports branches already merged and
# deleted on origin as live stalls — and the snapshot publishes that as red. If
# a fetch cannot reach origin the snapshot records the failure instead of
# passing stale refs off as current.
#
#   ./dashboard/build-data.sh
#   BARONY_COLLAB=~/some/other/collab ./dashboard/build-data.sh
#   ./dashboard/build-data.sh --no-refresh      # read the clones exactly as-is
#
# Then review the diff before committing:
#   git diff dashboard/data/fleet.json
set -euo pipefail

cd "$(dirname "$0")/.."

: "${BARONY_COLLAB:=$HOME/Workspace/fleet-coordination}"
export BARONY_COLLAB

echo "barony · fleet snapshot"
echo "  collab (private): ${BARONY_COLLAB}"
echo "  output (public):  dashboard/data/fleet.json"
echo "  working copies:   fetched --prune before reading (pass --no-refresh to skip)"
echo

python3 dashboard/build_data.py "$@"

echo
echo "Review before committing — the snapshot is published:"
echo "  git diff --stat dashboard/data/fleet.json"
