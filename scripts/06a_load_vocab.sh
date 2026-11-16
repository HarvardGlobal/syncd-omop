#!/usr/bin/env bash
# Step 6a - Load Athena vocabulary files into cdm.* with PostgreSQL COPY (streams the files,
# so the 1.7 GB CONCEPT_RELATIONSHIP never has to fit in R's memory).
# Usage: scripts/06a_load_vocab.sh <athena_vocab_dir> [database=synthetic_concurrent]
set -euo pipefail
DIR="$(cd "$1" && pwd)"
DB="${2:-synthetic_concurrent}"
PSQL="/opt/homebrew/opt/postgresql@16/bin/psql -v ON_ERROR_STOP=1 -d $DB"

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
