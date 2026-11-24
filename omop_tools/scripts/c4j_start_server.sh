#!/usr/bin/env bash
# Start the Comorbidity4j 3.5 web server locally (http://localhost:${C4J_PORT:-8181}/comorbidity4web/).
# Downloads the release on first use. Spring 5.0 inside it needs Java 8, or --add-opens on newer Java.
#
# Usage: omop_tools/scripts/c4j_start_server.sh      (Ctrl+C to stop)
#
# Settings (optional, in .env):
#   C4J_PORT  server port (default 8181); c4j_run_analysis.sh reads the same value
#   C4J_JAVA  full path to the java binary to use
#
# Java, first match wins:
#   1. C4J_JAVA
#   2. a Java 8 found by macOS's /usr/libexec/java_home (only exists on macOS)
#   3. $JAVA_HOME/bin/java
#   4. java on PATH
# Whatever is chosen, its version decides whether the --add-opens flags are needed.
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=../../scripts/lib/env.sh
source "$(dirname "$0")/../../scripts/lib/env.sh"

ROOT="$PROJECT_ROOT/omop_tools"
B="$ROOT/comorbidity4j_bin/comorbidity4j-3.5"
PORT="${C4J_PORT:-8181}"

if [ ! -f "$B/comorbidity4j-3.5.jar" ]; then
  command -v unzip >/dev/null || { echo "unzip is required for the first-run download." >&2; exit 1; }
  mkdir -p "$ROOT/comorbidity4j_bin"
  # -f: fail on HTTP errors instead of saving an error page as the zip
  curl -fsSL -o "$ROOT/comorbidity4j_bin/comorbidity4j-3.5-bin.zip" \
    https://github.com/fra82/comorbidity4j/releases/download/3.5/comorbidity4j-3.5-bin.zip
  unzip -q -o "$ROOT/comorbidity4j_bin/comorbidity4j-3.5-bin.zip" -d "$ROOT/comorbidity4j_bin"
fi
mkdir -p "$ROOT/comorbidity4j_results"

# --- pick a Java (see header) ---------------------------------------------------------------
JAVA="${C4J_JAVA:-}"
if [[ -z "$JAVA" && -x /usr/libexec/java_home ]] && J8=$(/usr/libexec/java_home -v 1.8 2>/dev/null); then
  JAVA="$J8/bin/java"
fi
[[ -z "$JAVA" && -n "${JAVA_HOME:-}" && -x "$JAVA_HOME/bin/java" ]] && JAVA="$JAVA_HOME/bin/java"
[[ -z "$JAVA" ]] && JAVA="$(command -v java || true)"
[[ -n "$JAVA" && -x "$JAVA" ]] || { echo "No Java found. Install Java 8+, or set C4J_JAVA in .env." >&2; exit 1; }

# Java 8 reports its version as "1.8.x" and must NOT get --add-opens (it doesn't know the flag).
# Java 9+ needs it so Spring 5.0 can reflect into java.base.
if "$JAVA" -version 2>&1 | grep -q 'version "1\.8'; then
  OPENS=()
else
  OPENS=(--add-opens java.base/java.lang=ALL-UNNAMED --add-opens java.base/java.util=ALL-UNNAMED)
fi
echo "Comorbidity4j on http://localhost:$PORT/comorbidity4web/  (java: $JAVA)"

exec "$JAVA" "${OPENS[@]}" -cp "$B/comorbidity4j-3.5.jar:$B/lib/*" es.imim.ibi.comorbidity4j.server.StartComorbidity4j \
  --server.port="$PORT" --spring.servlet.multipart.location="$ROOT/comorbidity4j_results/"
