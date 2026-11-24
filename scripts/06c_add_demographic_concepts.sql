-- Step 6c - Add the OMOP Gender, Race and Ethnicity vocabularies.
-- The Athena bundle used here (v5.0 29-AUG-26) has no Gender, Race or Ethnicity vocabulary,
-- so cdm.person.gender_concept_id (8507/8532), race_concept_id and ethnicity_concept_id point
-- at concepts that are missing from cdm.concept. Achilles/ARES then show no gender, race or
-- age-by-gender data, and foreign-key DQD checks fail.
-- These are the fixed OHDSI standard concepts. Selecting Gender, Race and Ethnicity in a fresh
-- Athena download would give the same rows; this script is a no-op where they already exist.
-- Usage: scripts/psql.sh -f scripts/06c_add_demographic_concepts.sql   (database from OMOP_DB_NAME in .env)
BEGIN;

INSERT INTO cdm.vocabulary (vocabulary_id, vocabulary_name, vocabulary_reference, vocabulary_version, vocabulary_concept_id)
SELECT v.* FROM (VALUES
  ('Gender',    'OMOP Gender',                        'OMOP generated', NULL::varchar, 44819108),
  ('Race',      'Race and Ethnicity Code Set (USBC)', 'OMOP generated', NULL::varchar, 44819109),
  ('Ethnicity', 'OMOP Ethnicity',                     'OMOP generated', NULL::varchar, 44819134)
) AS v(vocabulary_id, vocabulary_name, vocabulary_reference, vocabulary_version, vocabulary_concept_id)
WHERE NOT EXISTS (SELECT 1 FROM cdm.vocabulary x WHERE x.vocabulary_id = v.vocabulary_id);

INSERT INTO cdm.concept (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
                         standard_concept, concept_code, valid_start_date, valid_end_date, invalid_reason)
SELECT c.id, c.name, c.voc, c.voc, c.voc, 'S', c.code, DATE '1970-01-01', DATE '2099-12-31', NULL
FROM (VALUES
  (8507,     'MALE',                                      'Gender',    'M'),
  (8532,     'FEMALE',                                    'Gender',    'F'),
  (8657,     'American Indian or Alaska Native',          'Race',      '1'),
  (8515,     'Asian',                                     'Race',      '2'),
  (8516,     'Black or African American',                 'Race',      '3'),
  (8557,     'Native Hawaiian or Other Pacific Islander', 'Race',      '4'),
  (8527,     'White',                                     'Race',      '5'),
  (38003563, 'Hispanic or Latino',                        'Ethnicity', 'Hispanic'),
  (38003564, 'Not Hispanic or Latino',                    'Ethnicity', 'Not Hispanic')
) AS c(id, name, voc, code)
WHERE NOT EXISTS (SELECT 1 FROM cdm.concept x WHERE x.concept_id = c.id);

SELECT vocabulary_id, count(*) FROM cdm.concept
WHERE vocabulary_id IN ('Gender', 'Race', 'Ethnicity') GROUP BY 1 ORDER BY 1;

COMMIT;
