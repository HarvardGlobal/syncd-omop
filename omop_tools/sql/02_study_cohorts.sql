-- Study cohorts for TreatmentPatterns and CohortContrast, written to results.cohort
-- (standard OHDSI cohort table: cohort_definition_id, subject_id, cohort_start_date, cohort_end_date).
--
-- Diagnosis cohorts (one row per person; end = end of the person's observation period):
--   1  Concurrent MH + SUD   start = date both are present (the later of first MH and first SUD diagnosis)
--   2  MH only               start = first MH diagnosis;  person never has an SUD diagnosis
--   3  SUD only              start = first SUD diagnosis; person never has an MH diagnosis
--   4  Any MH or SUD         start = first MH or SUD diagnosis
-- Treatment event cohorts (one row per exposure; used as TreatmentPatterns "event" cohorts):
--   11 Sertraline                      drugs containing ingredient 739138
--   12 Cognitive behavioural therapy   procedure 4043071
--   13 SUD counselling                 procedure 4210149
--   14 Buprenorphine/naloxone          drugs containing ingredient 1133201
--   15 Naltrexone                      drugs containing ingredient 1714319
-- CBT and counselling are single-day procedures; each session is given a 30-day episode so it
-- survives TreatmentPatterns' minimum era durations and can combine with drug eras.
-- Only records from the study window (2024-01-01 to 2025-12-31) are used.
-- Usage: scripts/psql.sh -f omop_tools/sql/02_study_cohorts.sql   (database from OMOP_DB_NAME in .env)
BEGIN;

CREATE TABLE IF NOT EXISTS results.cohort (
  cohort_definition_id integer NOT NULL,
  subject_id bigint NOT NULL,
  cohort_start_date date NOT NULL,
  cohort_end_date date NOT NULL
);
CREATE TABLE IF NOT EXISTS results.cohort_definition_names (
  cohort_definition_id integer PRIMARY KEY,
  cohort_name text NOT NULL,
  cohort_type text NOT NULL
);
DELETE FROM results.cohort WHERE cohort_definition_id IN (1, 2, 3, 4, 11, 12, 13, 14, 15);
DELETE FROM results.cohort_definition_names WHERE cohort_definition_id IN (1, 2, 3, 4, 11, 12, 13, 14, 15);

INSERT INTO results.cohort_definition_names VALUES
  (1, 'Concurrent MH and SUD', 'target'), (2, 'MH only', 'target'), (3, 'SUD only', 'target'),
  (4, 'Any MH or SUD', 'target'),
  (11, 'Sertraline', 'event'), (12, 'CBT', 'event'), (13, 'SUD counselling', 'event'),
  (14, 'Buprenorphine-naloxone', 'event'), (15, 'Naltrexone', 'event');

CREATE TEMP TABLE dx AS
SELECT co.person_id,
       min(co.condition_start_date) FILTER (WHERE co.condition_concept_id IN (4152280, 442077)) AS first_mh,
       min(co.condition_start_date) FILTER (WHERE co.condition_concept_id IN
            (433753, 434327, 438130, 432303, 44783367, 4080762)) AS first_sud
FROM cdm.condition_occurrence co
WHERE co.condition_start_date BETWEEN DATE '2024-01-01' AND DATE '2025-12-31'
  AND co.condition_concept_id IN (4152280, 442077, 433753, 434327, 438130, 432303, 44783367, 4080762)
GROUP BY co.person_id;

INSERT INTO results.cohort
SELECT g.id, d.person_id, g.start_date, op.observation_period_end_date
FROM dx d
JOIN cdm.observation_period op ON op.person_id = d.person_id
CROSS JOIN LATERAL (VALUES
  (1, CASE WHEN d.first_mh IS NOT NULL AND d.first_sud IS NOT NULL THEN greatest(d.first_mh, d.first_sud) END),
  (2, CASE WHEN d.first_sud IS NULL THEN d.first_mh END),
  (3, CASE WHEN d.first_mh IS NULL THEN d.first_sud END),
  (4, least(d.first_mh, d.first_sud))
) AS g(id, start_date)
WHERE g.start_date IS NOT NULL
  AND g.start_date BETWEEN op.observation_period_start_date AND op.observation_period_end_date;

INSERT INTO results.cohort
SELECT e.id, de.person_id, de.drug_exposure_start_date,
       greatest(de.drug_exposure_start_date,
                coalesce(de.drug_exposure_end_date, de.drug_exposure_start_date + coalesce(de.days_supply, 1)))
FROM cdm.drug_exposure de
JOIN cdm.concept_ancestor ca ON ca.descendant_concept_id = de.drug_concept_id
JOIN (VALUES (11, 739138), (14, 1133201), (15, 1714319)) AS e(id, ingredient) ON e.ingredient = ca.ancestor_concept_id
WHERE de.drug_exposure_start_date BETWEEN DATE '2024-01-01' AND DATE '2025-12-31';

INSERT INTO results.cohort
SELECT e.id, po.person_id, po.procedure_date, po.procedure_date + 29   -- a session stands for a 30-day course
FROM cdm.procedure_occurrence po
JOIN (VALUES (12, 4043071), (13, 4210149)) AS e(id, concept) ON e.concept = po.procedure_concept_id
WHERE po.procedure_date BETWEEN DATE '2024-01-01' AND DATE '2025-12-31';

SELECT n.cohort_definition_id AS id, n.cohort_name, n.cohort_type,
       count(c.subject_id) AS records, count(DISTINCT c.subject_id) AS persons
FROM results.cohort_definition_names n
LEFT JOIN results.cohort c USING (cohort_definition_id)
GROUP BY 1, 2, 3 ORDER BY 1;
COMMIT;
