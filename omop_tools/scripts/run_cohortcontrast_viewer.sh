#!/usr/bin/env bash
# Launch the CohortContrast viewer (Python Dash app shipped inside the R package) on the studies in
# omop_tools/cohortcontrast_results, at http://localhost:8050 (or the port given).
# This starts app.py directly instead of CohortContrast::runCohortContrastViewer(): on Apple-silicon
# Macs where R runs as Intel (Rosetta), R would start Python as Intel and fail to load the arm64
# wheels in the viewer's virtualenv.
#
# Python env: a venv with the package's python/requirements.txt plus "pyarrow>=14,<19"
# (newer pyarrow needs NumPy 2, the viewer pins NumPy < 2). See omop_tools/README.md.
#
# Usage (from anywhere): omop_tools/scripts/run_cohortcontrast_viewer.sh [port]
#
# Settings (optional, in .env):
#   CC_PYTHON       python inside the viewer's venv
#                   (default ~/.virtualenvs/r-cohortcontrast-viewer/bin/python)
#   CC_VIEWER_PORT  port when none is given on the command line (default 8050)
#   CC_APP_DIR      folder holding the viewer's app.py, if CohortContrast isn't in
#                   omop_tools/r_lib_cohortcontrast (e.g. installed in the system R library)
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=../../scripts/lib/env.sh
source "$(dirname "$0")/../../scripts/lib/env.sh"

ROOT="$PROJECT_ROOT/omop_tools"
PY="${CC_PYTHON:-$HOME/.virtualenvs/r-cohortcontrast-viewer/bin/python}"
APP_DIR="${CC_APP_DIR:-$ROOT/r_lib_cohortcontrast/CohortContrast/python}"
PORT="${1:-${CC_VIEWER_PORT:-8050}}"

[[ -x "$PY" ]] || { echo "No Python at $PY. Create the venv (omop_tools/README.md) or set CC_PYTHON in .env." >&2; exit 1; }
[[ -f "$APP_DIR/app.py" ]] || { echo "Viewer not found at $APP_DIR/app.py. Set CC_APP_DIR in .env." >&2; exit 1; }

# Apple-silicon Macs only: force the native arm64 Python (see header). On Linux and Intel
# Macs ARCH stays empty, so Python runs as-is.
ARCH=()
if [[ "$(uname -s)" == "Darwin" && "$(sysctl -n hw.optional.arm64 2>/dev/null)" == "1" ]]; then
  ARCH=(arch -arm64)
fi

cd "$APP_DIR"
export CONTRAST_VIEWER_PORT="$PORT" CONTRAST_VIEWER_DATA_DIR="$ROOT/cohortcontrast_results" \
       CONTRAST_VIEWER_MODE=simple CONTRAST_VIEWER_ALLOW_EXPORTS=1 CONTRAST_VIEWER_DEBUG=0
echo "CohortContrast viewer on http://localhost:$PORT  (Ctrl+C to stop)"
exec "${ARCH[@]}" "$PY" app.py
