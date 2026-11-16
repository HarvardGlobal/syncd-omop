#!/usr/bin/env bash
# Step 8 - Open the OHDSI ARES viewer for the SYNCD OMOP database.
# ARES is a static web app; it reads the files that scripts/07_run_ares.R wrote to
# omop_viz/ares_app/site/data. Stop the server with Ctrl+C.
# Usage (from the project root): scripts/08_view_ares.sh [port=8085]
set -euo pipefail
PORT="${1:-8085}"
SITE="$(cd "$(dirname "$0")/.." && pwd)/omop_viz/ares_app/site"
echo "ARES running at http://localhost:$PORT  (Ctrl+C to stop)"
( sleep 1 && open "http://localhost:$PORT/#/network/overview" ) >/dev/null 2>&1 &
exec python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$SITE"
