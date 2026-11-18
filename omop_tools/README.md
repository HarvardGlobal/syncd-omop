# Patient journey tools on the SYNCD OMOP database

Four open-source tools from the "OMOP longitudinal tools" shortlist, run against the local
`synthetic_concurrent` PostgreSQL database (OMOP CDM 5.4). Run every command from the project root.

| Tool | Question it answers | Run | View |
|---|---|---|---|
| PatientExploreR | What happened to *this* patient, in order? | `Rscript omop_tools/scripts/run_patientexplorer.R` | http://localhost:8090 |
| TreatmentPatterns | In what order do patients receive treatments? | `Rscript omop_tools/scripts/run_treatmentpatterns.R` | `treatmentpatterns_results/sunburst_*.html`, `sankey_*.html` |
| CohortContrast | What is over-represented in the concurrent group, and when? | `Rscript omop_tools/scripts/run_cohortcontrast.R` | `omop_tools/scripts/run_cohortcontrast_viewer.sh` -> http://localhost:8050 |
| Comorbidity4j | Which diagnoses co-occur more than chance? | `omop_tools/scripts/c4j_start_server.sh`, then `c4j_export.sh` and `c4j_run_analysis.sh` | http://localhost:8181/comorbidity4web/ (results page) |

The HTML result pages load their JavaScript from `lib/`, so serve the folder rather than opening
files directly: `python3 -m http.server 8086 --directory omop_tools`.

## Shared setup

```bash
psql -d synthetic_concurrent -f omop_tools/sql/02_study_cohorts.sql   # cohorts in results.cohort
psql -d synthetic_concurrent -f omop_tools/sql/01_patientexplorer_schema.sql   # PatientExploreR only
```

`02_study_cohorts.sql` builds the cohorts every tool uses (counts match the ground truth exactly):

| ID | Cohort | People |
|---|---|---|
| 1 | Concurrent MH and SUD (index = date both diagnoses are present) | 769 |
| 2 | MH only | 1,426 |
| 3 | SUD only | 979 |
| 4 | Any MH or SUD | 3,174 |
| 11-15 | Treatment events: sertraline, CBT, SUD counselling, buprenorphine-naloxone, naltrexone | |

CBT and counselling are single-day procedures; each session is given a 30-day episode so
TreatmentPatterns does not drop it as a too-short era.

## Installing the tools (R 4.3, macOS)

```bash
# TreatmentPatterns + CDMConnector: CRAN binaries built for R 4.3
Rscript -e 'install.packages(c("TreatmentPatterns","CDMConnector","duckdb","RPostgres","shiny","shinyWidgets","shinyjs","shinythemes","plotly","DT","timevis","shinyalert","shinycssloaders"), type="binary")'
# CohortContrast 1.0.0 needs newer dplyr/dbplyr/omopgenerics than the R 4.3 binaries, so it gets its own library
Rscript -e 'install.packages(c("dplyr","dbplyr","omopgenerics","PatientProfiles","CodelistGenerator","CohortConstructor","CohortContrast"), lib="omop_tools/r_lib_cohortcontrast", type="source")'
# CohortContrast viewer (Python Dash app); pin pyarrow because the viewer pins NumPy < 2
python3 -m venv ~/.virtualenvs/r-cohortcontrast-viewer
~/.virtualenvs/r-cohortcontrast-viewer/bin/pip install -r omop_tools/r_lib_cohortcontrast/CohortContrast/python/requirements.txt "pyarrow>=14,<19"
# PatientExploreR (2018) and its PostgreSQL patch
git clone https://github.com/BenGlicksberg/PatientExploreR omop_tools/PatientExploreR
git -C omop_tools/PatientExploreR apply ../patches/patientexplorer_postgres.patch
# Comorbidity4j 3.5 is downloaded by omop_tools/scripts/c4j_start_server.sh on first run
```

## Compatibility fixes (all in this folder)

- **PatientExploreR** (`patches/patientexplorer_postgres.patch` + `sql/01_patientexplorer_schema.sql`):
  - its DBI path now uses RPostgres; choose "PostgreSQL (DBI, SYNCD patch)" in the login form;
  - query results are converted to the text dates and numeric ids the app expects;
  - `DBI::fetch()` and `shiny:::%AND%` (both removed upstream) are replaced;
  - the `pexr` schema maps CDM 5.4 visit columns back to 5.3 names and trims CONCEPT to 13k rows;
  - the encounter timeline keeps visits with no admitted-from / discharged-to value (ETL-Synthea
    never fills them). In the timeline tab, pick the visit types to show.
- **TreatmentPatterns 3.1.0**: run once per target cohort; `export(nonePaths = TRUE)` fails when one
  run has several targets.
- **CohortContrast 1.0.0**: matched controls are clipped to their own observation periods; the viewer
  is started from native Python (R runs as Intel under Rosetta and cannot load the arm64 wheels).
- **Comorbidity4j 3.5**: needs Java 8 (or `--add-opens` on newer Java). It has only a web form, so
  `c4j_run_analysis.sh` drives the form with curl. Use the default non-directional mode for
  comorbidity strength; `C4J_DIRECTIONAL=enabled` counts only pairs where A precedes B, which splits
  every pair in two.
