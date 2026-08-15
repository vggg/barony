#!/usr/bin/env bash
# Regenerate dashboard/data/fleet.json from the PRIVATE coordination repo.
#
# The snapshot committed to this public repo is a curated projection: read-only
# `baron` reporters in, sanitised JSON out. Rerun this instead of editing the
# JSON by hand — a hand-edited snapshot is a lie the dashboard would render.
#
#   ./dashboard/build-data.sh
#   BARONY_COLLAB=~/some/other/collab ./dashboard/build-data.sh
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
echo

python3 dashboard/build_data.py "$@"

echo
echo "Review before committing — the snapshot is published:"
echo "  git diff --stat dashboard/data/fleet.json"
