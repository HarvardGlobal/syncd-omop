#!/usr/bin/env bash
# Export OMOP CDM tables into Comorbidity4j's tab-separated input format.
# Diagnoses = standard Condition-domain concepts from cdm.condition_occurrence (whole history),
# keyed by concept_id; one "visit" per condition_occurrence visit (or per person-date when the
# record has no visit).
#
# Usage: omop_tools/scripts/c4j_export.sh [out_dir=comorbidity4j_input]
#   out_dir is relative to omop_tools/.
# Connection settings come from .env via scripts/lib/env.sh (see .env.example);
# override the database for one run with  OMOP_DB_NAME=other_db omop_tools/scripts/c4j_export.sh
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=../../scripts/lib/env.sh
source "$(dirname "$0")/../../scripts/lib/env.sh"

OUT="$PROJECT_ROOT/omop_tools/${1:-comorbidity4j_input}"
mkdir -p "$OUT"

# OMOP_DB_* -> PG*, so psql connects to the same database as every other script.
omop_pg_env
PSQL="$(find_psql) -v ON_ERROR_STOP=1 -q"
check_db "$PSQL"
echo "Exporting from $PGDATABASE at $PGHOST:$PGPORT to $OUT"

CP="WITH (FORMAT csv, DELIMITER E'\t', HEADER true)"
$PSQL -c "\copy (SELECT p.person_id AS patient_id,
  to_char(make_date(p.year_of_birth, coalesce(p.month_of_birth,1), coalesce(p.day_of_birth,1)), 'YYYY/MM/DD') AS patient_dateBirth,
  CASE p.gender_concept_id WHEN 8532 THEN 'F' WHEN 8507 THEN 'M' ELSE 'U' END AS patient_gender,
  coalesce(nullif(p.race_source_value,''),'unknown') AS race
  FROM cdm.person p ORDER BY 1) TO '$OUT/patients.txt' $CP"
# visit id: the OMOP visit, or a synthetic id (negative) for records without one
# one row per visit id; a visit's date is its earliest condition start date
$PSQL -c "\copy (SELECT person_id AS patient_id,
  coalesce(visit_occurrence_id, -(person_id * 100000 + (condition_start_date - DATE '1900-01-01'))) AS visit_id,
  to_char(min(condition_start_date), 'YYYY/MM/DD') AS visit_date
  FROM cdm.condition_occurrence WHERE condition_concept_id <> 0 GROUP BY 1, 2 ORDER BY 1, 3) TO '$OUT/visits.txt' $CP"
$PSQL -c "\copy (SELECT DISTINCT person_id AS patient_id,
  coalesce(visit_occurrence_id, -(person_id * 100000 + (condition_start_date - DATE '1900-01-01'))) AS visit_id,
  condition_concept_id AS diagnosis_code
  FROM cdm.condition_occurrence WHERE condition_concept_id <> 0 ORDER BY 1, 2) TO '$OUT/diagnoses.txt' $CP"
$PSQL -c "\copy (SELECT DISTINCT c.concept_id AS diagnosis_code, replace(c.concept_name, E'\t', ' ') AS diagnosis_description
  FROM cdm.concept c JOIN cdm.condition_occurrence co ON co.condition_concept_id = c.concept_id ORDER BY 1) TO '$OUT/diagnosis_descriptions.txt' $CP"
wc -l "$OUT"/*.txt
