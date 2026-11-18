#!/usr/bin/env bash
# Start the Comorbidity4j 3.5 web server locally (http://localhost:8181/comorbidity4web/).
# Downloads the release on first use. Spring 5.0 inside it needs Java 8, or --add-opens on newer Java.
# Usage: omop_tools/scripts/c4j_start_server.sh      (Ctrl+C to stop)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
B="$ROOT/comorbidity4j_bin/comorbidity4j-3.5"
if [ ! -f "$B/comorbidity4j-3.5.jar" ]; then
  mkdir -p "$ROOT/comorbidity4j_bin"
  curl -sL -o "$ROOT/comorbidity4j_bin/comorbidity4j-3.5-bin.zip" \
    https://github.com/fra82/comorbidity4j/releases/download/3.5/comorbidity4j-3.5-bin.zip
  unzip -q -o "$ROOT/comorbidity4j_bin/comorbidity4j-3.5-bin.zip" -d "$ROOT/comorbidity4j_bin"
fi
mkdir -p "$ROOT/comorbidity4j_results"
JAVA=java; OPENS=(--add-opens java.base/java.lang=ALL-UNNAMED --add-opens java.base/java.util=ALL-UNNAMED)
if J8=$(/usr/libexec/java_home -v 1.8 2>/dev/null); then JAVA="$J8/bin/java"; OPENS=(); fi
exec "$JAVA" "${OPENS[@]}" -cp "$B/comorbidity4j-3.5.jar:$B/lib/*" es.imim.ibi.comorbidity4j.server.StartComorbidity4j \
  --server.port=8181 --spring.servlet.multipart.location="$ROOT/comorbidity4j_results/"
