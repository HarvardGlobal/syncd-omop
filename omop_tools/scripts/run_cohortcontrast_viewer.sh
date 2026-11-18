#!/usr/bin/env bash
# Launch the CohortContrast viewer (Python Dash app shipped inside the R package) on the studies in
# omop_tools/cohortcontrast_results, at http://localhost:8050 (or the port given).
# This starts app.py directly instead of CohortContrast::runCohortContrastViewer(): on Apple-silicon
# Macs where R runs as Intel (Rosetta), R would start Python as Intel and fail to load the arm64
# wheels in the viewer's virtualenv.
# Python env: ~/.virtualenvs/r-cohortcontrast-viewer with the package's python/requirements.txt plus
# "pyarrow>=14,<19" (newer pyarrow needs NumPy 2, the viewer pins NumPy < 2).
# Usage (from the project root): omop_tools/scripts/run_cohortcontrast_viewer.sh [port=8050]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${CC_PYTHON:-$HOME/.virtualenvs/r-cohortcontrast-viewer/bin/python}"
APP_DIR="$ROOT/r_lib_cohortcontrast/CohortContrast/python"
ARCH=(); [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ] && ARCH=(arch -arm64)
cd "$APP_DIR"
export CONTRAST_VIEWER_PORT="${1:-8050}" CONTRAST_VIEWER_DATA_DIR="$ROOT/cohortcontrast_results" \
       CONTRAST_VIEWER_MODE=simple CONTRAST_VIEWER_ALLOW_EXPORTS=1 CONTRAST_VIEWER_DEBUG=0
exec "${ARCH[@]}" "$PY" app.py
