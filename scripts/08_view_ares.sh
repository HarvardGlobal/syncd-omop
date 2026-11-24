#!/usr/bin/env bash
# Step 8 - Open the OHDSI ARES viewer for the SYNCD OMOP database.
# ARES is a static web app; it reads the files that scripts/07_run_ares.R wrote to
# omop_viz/ares_app/site/data. Stop the server with Ctrl+C.
# Usage (from the project root): scripts/08_view_ares.sh [port=8085]
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=lib/env.sh
source "$(dirname "$0")/lib/env.sh"

# Port: first argument, else ARES_PORT from .env, else 8085.
PORT="${1:-${ARES_PORT:-8085}}"
SITE="$PROJECT_ROOT/omop_viz/ares_app/site"
URL="http://localhost:$PORT/#/network/overview"

command -v python3 >/dev/null || { echo "python3 is required to serve the viewer." >&2; exit 1; }

echo "ARES running at $URL  (Ctrl+C to stop)"
# Opens the browser on Linux, macOS or WSL; on a headless box the URL above is enough.
( sleep 1 && open_url "$URL" ) &
exec python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$SITE"
