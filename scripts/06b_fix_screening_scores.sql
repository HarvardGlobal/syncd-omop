-- Step 6b - Restore numeric screening scores in cdm.observation.
-- ETL-Synthea 2.1 sends LOINC codes in the Observation domain to cdm.observation but drops
-- their numeric VALUE, so PHQ-2/PHQ-9/GAD-7/AUDIT-C/DAST-10 totals arrive empty.
-- This copies each score from synthea.observations, matched on person, date and code.
-- Rows are paired by order on the rare days with two results for the same code.
-- Usage: scripts/psql.sh -f scripts/06b_fix_screening_scores.sql   (database from OMOP_DB_NAME in .env)
BEGIN;

WITH src AS (
  SELECT p.person_id, o.date::date AS d, o.code, o.value::numeric AS v, o.units,
         row_number() OVER (PARTITION BY p.person_id, o.date::date, o.code ORDER BY o.date, o.value) AS rn
  FROM synthea.observations o
  JOIN cdm.person p ON p.person_source_value = o.patient
  WHERE o.code IN ('44261-6', '70274-6', '75626-2', '82667-7', '55758-7')
    AND o.type = 'numeric'
),
tgt AS (
  SELECT observation_id, person_id, observation_date AS d, observation_source_value AS code,
         row_number() OVER (PARTITION BY person_id, observation_date, observation_source_value
                            ORDER BY observation_id) AS rn
  FROM cdm.observation
  WHERE observation_source_value IN ('44261-6', '70274-6', '75626-2', '82667-7', '55758-7')
)
UPDATE cdm.observation ob
SET value_as_number = src.v,
    value_source_value = src.v::text,
    unit_source_value = src.units
FROM tgt JOIN src USING (person_id, d, code, rn)
WHERE ob.observation_id = tgt.observation_id;

SELECT observation_source_value AS loinc, count(*) AS rows, count(value_as_number) AS with_score
FROM cdm.observation
WHERE observation_source_value IN ('44261-6', '70274-6', '75626-2', '82667-7', '55758-7')
GROUP BY 1 ORDER BY 1;

COMMIT;
