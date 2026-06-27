#!/usr/bin/env bash
# bump-version.sh — Calendar versioning: YYYY-MM-DD.build
# Build increments within the same day, resets to 1 on a new day.
#
# Usage:  ./scripts/bump-version.sh          # auto-detect and bump
#         ./scripts/bump-version.sh --dry-run # print new version without writing

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_CFG="$REPO_ROOT/backend/app/config.py"
FRONTEND_APP="$REPO_ROOT/frontend/src/App.tsx"

TODAY=$(date +%Y-%m-%d)

# --- Read current version from backend config (single source of truth) ---
CURRENT=$(sed -n 's/^VERSION = "\([^"]*\)"/\1/p' "$BACKEND_CFG")

# Split into date and build parts
CURRENT_DATE="${CURRENT%%.*}"
if [[ "$CURRENT" == *.* ]]; then
    CURRENT_BUILD="${CURRENT##*.}"
else
    CURRENT_BUILD=0
fi

# --- Compute new version ---
if [[ "$CURRENT_DATE" == "$TODAY" ]]; then
    NEW_BUILD=$((CURRENT_BUILD + 1))
else
    NEW_BUILD=1
fi
NEW_VERSION="${TODAY}.${NEW_BUILD}"

if [[ "${1:-}" == "--dry-run" ]]; then
    echo "$NEW_VERSION"
    exit 0
fi

# --- Write to backend ---
sed -i '' "s|^VERSION = \".*\"|VERSION = \"${NEW_VERSION}\"|" "$BACKEND_CFG"

# --- Write to frontend ---
sed -i '' "s|^const VERSION = \".*\";|const VERSION = \"${NEW_VERSION}\";|" "$FRONTEND_APP"

echo "Version bumped: ${CURRENT} → ${NEW_VERSION}"
