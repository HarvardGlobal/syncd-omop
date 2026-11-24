#!/usr/bin/env bash
# Step 6a - Load Athena vocabulary files into cdm.* with PostgreSQL COPY (streams the files,
# so the 1.7 GB CONCEPT_RELATIONSHIP never has to fit in R's memory).
#
# Usage: scripts/06a_load_vocab.sh <athena_vocab_dir> [database]
#   database defaults to OMOP_DB_NAME from .env; pass it only for a one-off override.
# Connection settings come from .env via scripts/lib/env.sh (see .env.example).

set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=lib/env.sh
source "$(dirname "$0")/lib/env.sh"

[[ $# -ge 1 ]] || { echo "Usage: $0 <athena_vocab_dir> [database]" >&2; exit 1; }

# Absolute path to the Athena CSV directory.
DIR="$(cd "$1" && pwd)"

# Map OMOP_DB_* onto libpq's PG* variables (host, port, user, password, database),
# so psql reaches the same database the R scripts use. No password on the command line.
omop_pg_env
DB="${2:-$PGDATABASE}"

# psql from PATH (or PSQL_BIN in .env): no OS-specific install path.
# ON_ERROR_STOP=1 makes psql exit non-zero on the first SQL error,
# so 'set -e' stops the script instead of carrying on with a half-loaded database.
PSQL="$(find_psql) -v ON_ERROR_STOP=1 -d $DB"

# Fail early with a clear message if the database isn't reachable.
PGDATABASE="$DB" check_db "$PSQL"

for T in vocabulary domain concept_class relationship concept concept_relationship \
         concept_synonym concept_ancestor drug_strength; do
  F="$DIR/$(echo "$T" | tr '[:lower:]' '[:upper:]').csv"
  [ -f "$F" ] || { echo "missing $F" >&2; exit 1; }
  COLS=$(head -1 "$F" | tr -d '\r' | tr '\t' ',' | tr '[:upper:]' '[:lower:]')
  START=$(date +%s)
  $PSQL -q -c "TRUNCATE cdm.$T;"
  # Athena files are tab-delimited and unquoted; QUOTE E'\b' disables quote handling.
  $PSQL -q -c "\copy cdm.$T($COLS) FROM '$F' WITH (FORMAT csv, DELIMITER E'\t', QUOTE E'\b', NULL '', HEADER true)"
  N=$($PSQL -tAc "SELECT count(*) FROM cdm.$T")
  echo "$T: $N rows ($(( $(date +%s) - START )) s)"
done
