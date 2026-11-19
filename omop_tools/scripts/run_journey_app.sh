#!/usr/bin/env bash
# Start the SYNCD Journey Explorer: one local app with all patient-journey modules and ARES.
# Usage (from the project root): omop_tools/scripts/run_journey_app.sh [port]   (default 8070)
# Python: set JOURNEY_PYTHON, else the CohortContrast viewer virtualenv, else python3.
# Packages: pip install -r omop_tools/journey_app/requirements.txt
set -euo pipefail
cd "$(dirname "$0")/../.."
export JOURNEY_APP_PORT="${1:-${JOURNEY_APP_PORT:-8070}}"
PY="${JOURNEY_PYTHON:-$HOME/.virtualenvs/r-cohortcontrast-viewer/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
# On Apple silicon run natively (the shell may be running under Rosetta)
if [ "$(uname -s)" = "Darwin" ] && sysctl -n hw.optional.arm64 2>/dev/null | grep -q 1; then
  exec arch -arm64 "$PY" omop_tools/journey_app/app.py
fi
exec "$PY" omop_tools/journey_app/app.py
