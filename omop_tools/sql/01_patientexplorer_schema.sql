-- PatientExploreR compatibility schema.
-- PatientExploreR (2018) queries unqualified OMOP CDM 5.3 table names and loads the whole
-- CONCEPT table into R memory. This schema gives it:
--   * views over cdm.* tables, with the two CDM 5.4 renamed visit columns aliased back to 5.3 names;
--   * a CONCEPT table trimmed to the concepts this database uses (plus their ancestors and the
--     small reference domains), so the app loads ~10k concepts instead of 3 million.
-- The app connects with search_path = pexr (set by run_patientexplorer.R).
-- Usage: scripts/psql.sh -f omop_tools/sql/01_patientexplorer_schema.sql   (database from OMOP_DB_NAME in .env)
BEGIN;
DROP SCHEMA IF EXISTS pexr CASCADE;
CREATE SCHEMA pexr;

CREATE VIEW pexr.person               AS SELECT * FROM cdm.person;
CREATE VIEW pexr.death                AS SELECT * FROM cdm.death;
CREATE VIEW pexr.condition_occurrence AS SELECT * FROM cdm.condition_occurrence;
CREATE VIEW pexr.drug_exposure        AS SELECT * FROM cdm.drug_exposure;
CREATE VIEW pexr.procedure_occurrence AS SELECT * FROM cdm.procedure_occurrence;
CREATE VIEW pexr.measurement          AS SELECT * FROM cdm.measurement;
CREATE VIEW pexr.observation          AS SELECT * FROM cdm.observation;
CREATE VIEW pexr.device_exposure      AS SELECT * FROM cdm.device_exposure;
CREATE VIEW pexr.concept_relationship AS SELECT * FROM cdm.concept_relationship;
CREATE VIEW pexr.concept_ancestor     AS SELECT * FROM cdm.concept_ancestor;
CREATE VIEW pexr.visit_occurrence AS
  SELECT v.*, v.admitted_from_concept_id AS admitting_source_concept_id,
         v.discharged_to_concept_id AS discharge_to_concept_id
  FROM cdm.visit_occurrence v;

CREATE TABLE pexr.concept AS
WITH used AS (
  SELECT condition_concept_id AS c FROM cdm.condition_occurrence UNION
  SELECT condition_source_concept_id FROM cdm.condition_occurrence UNION
  SELECT drug_concept_id FROM cdm.drug_exposure UNION
  SELECT drug_source_concept_id FROM cdm.drug_exposure UNION
  SELECT procedure_concept_id FROM cdm.procedure_occurrence UNION
  SELECT procedure_source_concept_id FROM cdm.procedure_occurrence UNION
  SELECT measurement_concept_id FROM cdm.measurement UNION
  SELECT measurement_source_concept_id FROM cdm.measurement UNION
  SELECT observation_concept_id FROM cdm.observation UNION
  SELECT observation_source_concept_id FROM cdm.observation UNION
  SELECT device_concept_id FROM cdm.device_exposure UNION
  SELECT visit_concept_id FROM cdm.visit_occurrence
), keep AS (
  SELECT c FROM used
  UNION SELECT a.ancestor_concept_id FROM cdm.concept_ancestor a JOIN used ON a.descendant_concept_id = used.c
  UNION SELECT concept_id FROM cdm.concept
        WHERE domain_id IN ('Gender', 'Race', 'Ethnicity', 'Type Concept', 'Visit', 'Unit', 'Route')
)
SELECT c.* FROM cdm.concept c JOIN keep ON keep.c = c.concept_id;
CREATE UNIQUE INDEX ON pexr.concept (concept_id);

SELECT count(*) AS concepts_for_patientexplorer FROM pexr.concept;
COMMIT;
