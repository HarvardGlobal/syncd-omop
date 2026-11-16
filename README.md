# Synthetic concurrent disorders dataset (Synthea → OMOP-ready CSV)

Synthetic clinical histories of U.S. adults in which **past-year mental illness (MH)** and
**substance use disorder (SUD)** co-occur at the rates estimated from the **2024 NSDUH public
use file**. The output is Synthea 3.3.0 CSV, which is what OHDSI `ETLSyntheaBuilder` reads
to load OMOP CDM 5.4. The 10,000-patient run has been loaded into PostgreSQL as OMOP CDM 5.4
and can be browsed in OHDSI ARES (see below).

Intended use: software testing, cohort development, teaching, and preliminary methods
evaluation. **Not** for estimating treatment effects or clinical outcomes.

**Start here:** [`figures/SYNCD_setup_guide.pdf`](figures/SYNCD_setup_guide.pdf) gives step-by-step
instructions to rebuild everything from scratch.

## Getting the data

Large files are kept out of git (see `.gitignore`):

| File | Where to get it | Put it in |
|---|---|---|
| 10,000-patient Synthea CSVs (1.8 GB) | `syncd_expansion_10000_csv.zip` on this repo's **Releases** page | `output/expansion_10000/csv/` |
| NSDUH 2024 public use file, tab-delimited (NSDUH-2024-DS0001) | SAMHSA, https://www.samhsa.gov/data/ | `source_data/nsduh_2024/NSDUH_2024_Tab.txt` |
| Synthea 3.3.0 jar | https://github.com/synthetichealth/synthea/releases/tag/v3.3.0 | `tools/synthea-with-dependencies.jar` |
| OMOP vocabularies | https://athena.ohdsi.org (free account; licensed per user) | `source_data/athena_vocab/` |

The NSDUH file and the Synthea jar are only needed to regenerate the data. The finished ARES
viewer, with this database's results, is included: run `scripts/08_view_ares.sh` to browse it
without building the database.

```bash
gh release download v1.0 -p syncd_expansion_10000_csv.zip && unzip syncd_expansion_10000_csv.zip -d output/expansion_10000/
```

## Datasets

| Run | Patients | Seed | CSV folder | Validation |
|---|---|---|---|---|
| Pilot | 1,000 | 12345 | `output/pilot_1000/csv/` | `output/pilot_1000/validation/validation_report.md` |
| Expansion | 10,000 | 12345 | `output/expansion_10000/csv/` | `output/expansion_10000/validation/validation_report.md` |

Each run folder also contains `run_manifest.json`, which records provenance: Synthea jar
SHA-256, Java version, seeds, dates, NSDUH file hash, module hashes, and row counts.

**Design:**
- **Population:** adults 18–85 at 2025-12-31, all alive at the end, Massachusetts demography.
- **Observation window:** 24 months, 2024-01-01 to 2025-12-31 (`years_of_history=2`).
- **Comparison groups:** neither, MH only, SUD only, both. All four are retained. To make
  a cohort restricted to concurrent disorders, select persons with both an MH and an SUD
  diagnosis (`validation/person_ground_truth.csv` already does this).

Curation overview figure: `figures/dataset_curation.png` (simple, 5 steps) and
`figures/dataset_curation_detailed.png` (full detail). SVG versions sit alongside. Regenerate with
`python3 scripts/05_make_figure.py . figures/dataset_curation.svg` (or `05b_make_detailed_figure.py`).
Every number on them is read from the pipeline outputs.

## Pipeline (all reproducible)

```
scripts/01_estimate_nsduh.py   NSDUH PUF -> calibration/*.csv, calibration.json  (survey-weighted, linearized SEs)
scripts/02_build_modules.py    calibration.json -> modules/*.json                 (Synthea GMF modules)
scripts/03_generate.sh N SEED RUN   Synthea 3.3.0 run -> output/RUN/csv + run_manifest.json
scripts/04_validate.py RUN_DIR calibration/calibration.json -> output/RUN/validation/
```

Re-run everything from scratch with these commands:

```bash
python3 scripts/01_estimate_nsduh.py source_data/nsduh_2024/NSDUH_2024_Tab.txt calibration
```

```bash
scripts/03_generate.sh 1000 12345 my_run
```

```bash
python3 scripts/04_validate.py output/my_run calibration/calibration.json
```

`03_generate.sh` rebuilds the modules first and refuses to overwrite an existing run folder.

## Source data and definitions

- **Source:** SAMHSA NSDUH 2024 PUF, NSDUH-2024-DS0001, tab-delimited release, plus the
  codebook. Both are in `source_data/nsduh_2024/`.
- **Sample:** 47,299 adult respondents, representing a weighted 262.3 M adults.
- **MH:** `AMIPY == 1`, any mental illness in the past year.
- **SUD:** `UD5ILALANY == 1`, a DSM-5 illicit drug or alcohol use disorder in the past year.
  My recode of "both" matches SAMHSA's own `AMISUD5ANY` for every respondent.
- **Design:** weights `ANALWT2_C`, strata `VESTR_C`, PSUs `VEREP`. Standard errors use
  Taylor linearization.
- **Missing values:** blank (aged 12–17, not applicable) is recoded to missing. Adults are
  never missing on `AMIPY` or `UD5ILALANY`, because both are imputation-revised.
  `AMDEYR` (past-year MDE) is unknown for some adults with AMI. Those adults are excluded
  from P(MDE | AMI), which assumes the data are missing at random.
- **Joint distribution:** estimated within 10 strata (age groups 18–25, 26–34, 35–49, 50–64,
  65+, by sex). The four cells are estimated together, never as a product of marginals.
  All 40 cells have at least 30 respondents (`calibration/joint_mh_sud_by_stratum.csv`).

| NSDUH 2024, adults | Estimate (SE) |
|---|---|
| Any mental illness | 23.6% (0.4) |
| SUD | 17.7% (0.3) |
| Both | 8.1% (0.2), versus 4.2% if the two were independent |
| P(SUD \| AMI) / P(AMI \| SUD) | 34.3% / 45.6% |
| Odds ratio | 3.6 |

**Population coverage:** NSDUH represents the civilian, noninstitutionalized population. It
does not represent inpatient psychiatric, residential treatment, incarcerated, or homeless
(non-shelter) populations.

## How survey categories become clinical records

All rules are in `scripts/02_build_modules.py` (the `ASSUMPTIONS` dict) and
`calibration/simulation_assumptions.json`. These rules, and only these, are not taken from
NSDUH.

| Element | Source | Rule |
|---|---|---|
| MH/SUD group | NSDUH | P(group \| age group, sex) |
| MH diagnosis | NSDUH and an assumption | AMI with past-year MDE becomes **Major depressive disorder** (SNOMED 370143000). AMI without MDE becomes **Anxiety disorder** (197480006). The anxiety mapping is an assumption: AMI is a survey construct, not a diagnosis. P(MDE \| AMI) is conditioned on SUD status. |
| MH severity | NSDUH | Mild, moderate, or serious from `MICATPY`, conditioned on SUD status. Drives PHQ-9 and GAD-7 score ranges. |
| SUD diagnoses | NSDUH | Joint substance pattern from `IRPYUD5ALC`, `IRPYUD5MRJ`, `UD5OPIANY2`, `IRPYUD5COC`, `IRPYUD5MTH`, plus "other drug", conditioned on MH status. Patterns with fewer than 30 respondents are collapsed. Codes: SNOMED "Harmful pattern of use of" alcohol 15167005, cannabis 37344009, opioid 5602001, cocaine 78267003, methamphetamine 699449003; other drug 2403008. |
| Treatment receipt | NSDUH | P(MH treatment) and P(SUD treatment) by group, from `MHTRTPY2` and `SUTRTPY2`. Only the disorder that is present is treated. |
| Treatment content | Assumption | MH: SSRI only 40%, psychotherapy only 35%, both 25% (sertraline RxNorm 312938; CBT 228557008). SUD: counseling 313071005. OUD: buprenorphine/naloxone 351266. AUD: naltrexone 1483744 for 50%. Treated patients get 3 follow-up visits 4–13 weeks apart, with repeat PHQ-9 and GAD-7. |
| Timing | Assumption | The index diagnosis date is uniform over the first 12 months of the window. In the "both" group the second disorder is diagnosed 7–90 days later (observed median 50 days, maximum 116, because Synthea moves in 7-day time steps); which comes first is 50/50. Disorders stay active (no end date) through the window, so concurrence means overlapping active diagnoses. |
| Detection | Assumption | Every sampled disorder is clinically recorded (`detection_probability_untreated = 1.0`). Set it below 1 to simulate under-diagnosis. |
| Screening | Assumption | Wellness-visit PHQ-2/9, GAD-7, AUDIT-C, and DAST-10 scores follow the patient's profile. They never create diagnoses. |

NSDUH is cross-sectional, so every trajectory feature (onset dates, ordering, follow-up)
is a simulation assumption. None of it is an empirical estimate.

**Built-in Synthea modules that were disabled or replaced** (via `-d modules/`), because
they would add MH/SUD diagnoses outside the calibration:
- **Disabled:** `opioid_addiction`, `prescribing_opioids_for_chronic_pain_and_treatment_of_oud`,
  `self_harm`, `veteran_self_harm`, `veteran_mdd`, `veteran_ptsd`,
  `veteran_substance_abuse_conditions`, `veteran_substance_abuse_treatment`.
- **Replaced:** `encounter/depression_screening`, `encounter/anxiety_screening`, and
  `encounter/substance_use_screening`. The originals created random findings such as
  "Severe anxiety", "Misuses drugs", and "Unhealthy alcohol drinking".
- **Side effect:** there are no opioid prescriptions for chronic pain and no self-harm events.

## Validation summary

`04_validate.py` checks:
- joint and stratum frequencies against NSDUH, with exact binomial 95% CIs;
- conditional probabilities and the odds ratio;
- diagnosis mix;
- treatment rates;
- chronology;
- absence of foreign MH/SUD codes;
- screening-score separation.

**Pilot (n = 1,000).**
- **Marginals:** close to target (MH 22.6% vs 23.6%; SUD 16.5% vs 17.7%).
- **Strata:** 38 of 40 stratum cells have the target inside the 95% CI.
- **"Both":** low by chance at 5.2%, against 7.8% expected for this age/sex mix.
- **Sampling check:** two independent 3,000-person runs gave 7.5% and 8.0%. The sampling
  logic is unbiased. At n = 1,000 the "both" cell has an SE of about 0.85 points, and seed
  12345 happened to draw low. I did **not** pick seeds to improve the fit.
- **Recommendation:** use the 10,000-patient expansion for any statement about concurrence
  rates.

**Expansion (n = 10,000).** Full report: `output/expansion_10000/validation/validation_report.md`.
- **"Both" (concurrent disorders):** 7.69% (95% CI 7.18–8.23) vs 7.81% expected.
- **Other groups:** SUD only 9.8% vs 9.4%; neither 68.3% vs 67.5%.
- **MH only:** 14.3% vs 15.2% expected, slightly low and outside the CI.
- **Co-occurrence:** odds ratio 3.76 vs 3.62. P(SUD | MH) 0.350 vs 0.343; P(MH | SUD) 0.440 vs 0.456.
- **Strata:** 37 of 40 stratum cells have the target inside the 95% CI.
- **Substance mix and treatment rates:** within about 3 points of NSDUH.
- **MDD share among MH patients:** slightly low, 0.381 vs 0.422 with SUD and 0.277 vs 0.308
  without. Pooled over four independent runs (n ≈ 3,800 MH patients), the gap is about
  2 points (z ≈ −1.8). The assignment probabilities in the module are exact, so this is
  consistent with sampling noise.
- **Known edge case:** 308 patients turned 18 during the window. Their profile is assigned
  late, and 14 of them had a scheduled diagnosis date after 2025-12-31, so their disorder
  shows only in screening scores. This slightly lowers the MH and SUD counts.

**Structural checks (both runs):**
- every MH/SUD diagnosis is dated inside the window;
- 100% of "both" patients have overlapping active diagnoses;
- medications start on or after the related diagnosis;
- there are no uncalibrated MH/SUD codes.

Passing these checks shows the records are structurally consistent. It does not show
clinical realism. Before any clinical claims, a clinician should review sample records.

## PostgreSQL / OMOP load status

**Complete (2026-11-12).** The 10,000-patient run is in OMOP CDM 5.4 in the PostgreSQL 16
database `synthetic_concurrent` (localhost:5432; schemas `synthea`, `cdm`, `results`).

Commands run (ETLSyntheaBuilder 2.1, DatabaseConnector 6.4.0; logs in `omop_load/`):

```bash
Rscript scripts/06_load_omop.R staging
scripts/06a_load_vocab.sh source_data/athena_vocab
Rscript scripts/06_load_omop.R etl
/opt/homebrew/opt/postgresql@16/bin/psql -d synthetic_concurrent -f scripts/06b_fix_screening_scores.sql
/opt/homebrew/opt/postgresql@16/bin/psql -d synthetic_concurrent -f scripts/06c_add_demographic_concepts.sql
```

The Athena vocabularies are v5.0 29-AUG-26. They were loaded with PostgreSQL COPY so the
1.7 GB CONCEPT_RELATIONSHIP file did not have to fit in R's memory. The ETL took about
165 minutes.

| CDM table | Rows |
|---|---:|
| person | 10,000 |
| observation_period | 10,000 |
| visit_occurrence | 218,130 |
| condition_occurrence | 87,580 |
| drug_exposure | 185,528 |
| procedure_occurrence | 170,604 |
| measurement | 1,487,880 |
| observation | 874,797 |
| device_exposure | 13,454 |
| payer_plan_period | 30,022 |
| cost | 363,178 |
| condition_era / drug_era | 87,124 / 49,696 |
| death | 0 (only living patients were generated) |

**Checks**
- **Concept IDs:** No event table has any rows with concept_id = 0.
- **Group counts:** Counting people by the 8 module diagnosis codes in
  `cdm.condition_occurrence` reproduces the ground truth exactly: both 769, MH only 1,426,
  SUD only 979, neither 6,826.
- **Synthea conditions:** Of the 184,692 rows, 87,690 map to the Condition domain and
  89,517 to Observation (SNOMED findings such as "medication review due"). The other 7,480
  rows have ICD-10 dental codes from Synthea's dental module, which this vocabulary set does
  not include, so the ETL drops them. No MH or SUD code is affected.
- **Screening scores:** ETL-Synthea puts the PHQ-2, PHQ-9, GAD-7, AUDIT-C and DAST-10
  records in `cdm.observation` but leaves `value_as_number` empty.
  `scripts/06b_fix_screening_scores.sql` copies the scores back from `synthea.observations`
  (95,673 rows, all filled). Run it again after any re-run of the ETL.
- **Study window:** Restrict analyses to 2024-01-01 to 2025-12-31. About half of the
  visits are older history, and `observation_period` starts as early as 1941.
- **Visual guide:** `figures/omop_database_guide.html`.
- **`cdm.cdm_source`:** Records the dataset as "Synthetic concurrent disorders" (SYNCD).

## Viewing the database: OHDSI ARES

ARES 0.6 is OHDSI's browser for an OMOP CDM. It shows population, domain and concept
reports, data density over time and data quality results. It runs locally as a static site,
with no Docker or WebAPI.

```bash
scripts/08_view_ares.sh        # serves omop_viz/ares_app/site at http://localhost:8085
```

| Where to look | What it shows |
|---|---|
| Data Network > Overview | 1 source, 10,000 people, data quality issue count |
| Data Source Release > Person | Age, sex, race and ethnicity |
| Data Source Release > Condition (and Drug, Procedure, Observation, Measurement) | Every concept, prevalence and records per person; click one, e.g. Major depressive disorder, for age at first diagnosis and monthly trends |
| Data Source Release > Data Quality | DataQualityDashboard results |

**Rebuild:** `Rscript scripts/07_run_ares.R all` takes about 3 minutes. It runs:
1. Achilles 1.7.2, which writes statistics to `results.achilles_*`, exported for ARES.
2. DataQualityDashboard 2.9.1.
3. Achilles temporal characterisation.
4. AresIndexer 0.2.0.

**Data quality:** 2,384 checks, 99.16% passed.
- **46 checks error:** they target COHORT / COHORT_DEFINITION, which are not in the `cdm`
  schema.
- **20 checks fail.** All are known ETL-Synthea artefacts:
  - Fields left unset: unit, admitted-from / discharged-to, condition status, cost currency
    and provider specialty concepts.
  - Implausible values: drug days_supply and quantity.
  - 163 observation periods start before 1950.
  - None involve the MH or SUD diagnosis, drug, procedure or screening concepts.

**Fixes made while setting this up:**
- **Missing vocabularies.** The Athena bundle had no Gender, Race or Ethnicity vocabulary, so
  sex, race and ethnicity charts were empty. `scripts/06c_add_demographic_concepts.sql` adds
  the 9 standard OMOP concepts (MALE/FEMALE, 5 races, 2 ethnicities).
- **Unmapped race.** 288 people whose Synthea race is native, hawaiian or other keep
  race_concept_id 0, as ETL-Synthea maps only white, black and asian.
- **Package version mismatches.** `07_run_ares.R` works around three mismatches, each
  commented in the script:
  - DQD's error on disconnect.
  - AresIndexer 0.2.0 function names.
  - Upper-case Achilles columns.

The ARES sample dataset that ships in the zip was moved to `omop_viz/sample_data_removed/`.

## Loading into OMOP (reference steps)

1. Create the database `synthetic_concurrent` with schemas `synthea`, `cdm`, and `results`.
2. From Athena, download SNOMED, RxNorm, LOINC, and the default vocabularies. Every code
   above is a standard SNOMED, RxNorm, or LOINC code, so Usagi mapping should not be needed.
3. In R, using `ETLSyntheaBuilder`, call these functions in order:
   1. `CreateCDMTables(cdmVersion = "5.4")`
   2. `CreateSyntheaTables(syntheaVersion = "3.3.0")`
   3. `LoadSyntheaTables(syntheaFileLoc = "<abs path>/output/expansion_10000/csv")`
   4. `LoadVocabFromCsv`
   5. `CreateMapAndRollupTables`
   6. `LoadEventTables(cdmSourceName = "Synthetic concurrent disorders", cdmSourceAbbreviation = "SYNCD")`
   7. `CreateCDMIndices`
4. Run the Data Quality Dashboard.
5. Compare `person_ground_truth.csv` with cohort definitions run against `cdm.condition_occurrence`.

FHIR export is off. Turn it on in `03_generate.sh` if you need it.

## Folder layout

```
source_data/nsduh_2024/   NSDUH 2024 PUF (tab) + codebook  (public data)
calibration/              survey-weighted estimates + calibration.json + simulation_assumptions.json
modules/                  generated Synthea modules (pass with -d)
scripts/                  01-04 pipeline
tools/                    synthea-with-dependencies.jar (v3.3.0)
output/<run>/csv          Synthea CSV  -> ETL-Synthea input
output/<run>/validation   validation report, tables, person_ground_truth.csv
```
