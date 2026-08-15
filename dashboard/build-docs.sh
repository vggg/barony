#!/usr/bin/env bash
# Regenerate the published doc pages from docs/*.md.
#
# Unlike build-data.sh this touches nothing private — it reads two markdown files
# already in this repo and writes their styled projections:
#
#   docs/product-overview.md     -> dashboard/overview/index.html
#   docs/capability-value-map.md -> dashboard/value-map/index.html
#
# The markdown is the source of truth. Never edit the emitted HTML: run this and
# commit the result. `build_docs.py --check` is the CI drift guard.
#
#   ./dashboard/build-docs.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "barony · doc pages"
python3 dashboard/build_docs.py "$@"

echo
echo "Preview locally:"
echo "  python3 -m http.server -d dashboard 8080   # then open /overview/ and /value-map/"
