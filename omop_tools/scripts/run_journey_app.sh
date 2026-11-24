#!/usr/bin/env bash
#
# run_journey_app.sh — launch the SYNCD Journey Explorer (omop_tools/journey_app/app.py).
#
# Usage (from anywhere; paths resolve relative to this script):
#   omop_tools/scripts/run_journey_app.sh
#   JOURNEY_APP_PORT=8071 omop_tools/scripts/run_journey_app.sh
#
# Database settings come from the repo-root .env (the same file the R container
# uses). Variables already exported in your shell win over .env, so a one-off
# override like  OMOP_DB_NAME=other_db omop_tools/scripts/run_journey_app.sh
# still works.
#
# Python, first match wins:
#   1. $JOURNEY_PYTHON                                  (explicit override)
#   2. omop_tools/journey_app/.venv/bin/python          (the app's own venv)
#   3. ~/.virtualenvs/r-cohortcontrast-viewer/bin/python (legacy shared venv)
#   4. python3 on PATH
#
# Packages: pip install -r omop_tools/journey_app/requirements.txt
#
# @see omop_tools/journey_app/app.py  for the OMOP_DB_* variables it reads
# @see README-docker.md               for the shared .env layout

set -euo pipefail

# --------------------------------------------------------------------------- paths
# Everything is relative to this file, so the script works from any directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"          # omop_tools/
REPO_ROOT="$(cd "$TOOLS_DIR/.." && pwd)"           # project root
APP_DIR="$TOOLS_DIR/journey_app"
ENV_FILE="$REPO_ROOT/.env"

# --------------------------------------------------------------------------- environment
#
# Load .env with the shared loader every other script uses (scripts/lib/env.sh).
# It parses the file as data rather than sourcing it: safer for a file holding a
# password, and it doesn't die on compose's UID/GID lines (readonly in bash).
# Anything already set in the shell wins, so one-off overrides still work.
#
# @see scripts/lib/env.sh  load_dotenv()
[[ -f "$ENV_FILE" ]] || echo "note: no .env at $ENV_FILE, using shell environment only" >&2
# shellcheck source-path=SCRIPTDIR source=../../scripts/lib/env.sh
source "$REPO_ROOT/scripts/lib/env.sh"

# Fall back to the libpq PG* variables (used by psql and the bash loaders) for
# anything OMOP_DB_* doesn't set, so one set of credentials covers every tool.
export OMOP_DB_HOST="${OMOP_DB_HOST:-${PGHOST:-localhost}}"
export OMOP_DB_PORT="${OMOP_DB_PORT:-${PGPORT:-5432}}"
export OMOP_DB_NAME="${OMOP_DB_NAME:-${PGDATABASE:-syncd_omop}}"
export OMOP_DB_USER="${OMOP_DB_USER:-${PGUSER:-}}"
export OMOP_DB_PASSWORD="${OMOP_DB_PASSWORD:-${PGPASSWORD:-}}"
export JOURNEY_APP_PORT="${JOURNEY_APP_PORT:-8070}"

# --------------------------------------------------------------------------- python
#
# Pick the first usable interpreter from the list in the header.
# "Usable" means it exists and is executable; package checks come next.
PY="${JOURNEY_PYTHON:-}"
for cand in \
  "$APP_DIR/.venv/bin/python" \
  "$HOME/.virtualenvs/r-cohortcontrast-viewer/bin/python"; do
  [[ -n "$PY" ]] && break
  [[ -x "$cand" ]] && PY="$cand"
done
if [[ -z "$PY" ]]; then
  # Nothing preferred was found: say where we looked before falling back,
  # so a missing venv is obvious instead of silently using the system Python.
  echo "note: no venv found (checked JOURNEY_PYTHON, $APP_DIR/.venv," >&2
  echo "      ~/.virtualenvs/r-cohortcontrast-viewer); falling back to python3 on PATH" >&2
  PY="$(command -v python3 || true)"
fi

if [[ -z "$PY" || ! -x "$PY" ]]; then
  echo "error: no Python found. Set JOURNEY_PYTHON or create $APP_DIR/.venv" >&2
  exit 1
fi

# --------------------------------------------------------------------------- preflight
#
# Fail fast with a clear message instead of a mid-session traceback.
# Includes the lazily-imported packages (pyarrow, sklearn) that otherwise only
# break when you open the Cohort contrast tab.
if ! "$PY" -c 'import dash, plotly, flask, pandas, numpy, psycopg2, pyarrow, sklearn' 2>/dev/null; then
  echo "error: $PY is missing packages the app needs." >&2
  echo "       fix:  \"$PY\" -m pip install -r \"$APP_DIR/requirements.txt\"" >&2
  echo "       (check requirements.txt lists psycopg2-binary, pyarrow and scikit-learn)" >&2
  echo "       or point at an existing venv:  JOURNEY_PYTHON=/path/to/venv/bin/python in .env" >&2
  exit 1
fi

# Summary of what's about to run. The password is never printed.
cat <<EOF
SYNCD Journey Explorer
  python   : $PY
  database : ${OMOP_DB_USER:-<default user>}@${OMOP_DB_HOST}:${OMOP_DB_PORT}/${OMOP_DB_NAME}
  password : $([[ -n "$OMOP_DB_PASSWORD" ]] && echo set || echo "<unset>")
  url      : http://localhost:${JOURNEY_APP_PORT}
EOF

# --------------------------------------------------------------------------- run
# 'exec' replaces this shell with Python, so Ctrl-C stops the app directly.
cd "$REPO_ROOT"
exec "$PY" "$APP_DIR/app.py" "$@"