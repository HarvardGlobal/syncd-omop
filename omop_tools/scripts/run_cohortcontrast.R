# CohortContrast on the SYNCD OMOP database: which concepts (diagnoses, drugs, procedures,
# screening scores, visits) are enriched in the concurrent MH + SUD cohort, and when they occur.
# Needs the cohorts from omop_tools/sql/02_study_cohorts.sql in results.cohort.
#
# Two studies are written to omop_tools/cohortcontrast_results/:
#   concurrent_vs_mh_only   target = cohort 1 (concurrent MH and SUD), control = cohort 2 (MH only)
#   concurrent_vs_matched   target = cohort 1, control = 4 age- and sex-matched people per patient
#                           from the rest of the database (CohortContrast::createControlCohortMatching)
#
# CohortContrast 1.0.0 needs newer packages than the R 4.3 binaries; they are installed in
# omop_tools/r_lib_cohortcontrast (see omop_tools/README.md).
# Usage (from the project root): Rscript omop_tools/scripts/run_cohortcontrast.R
#   CC_STUDIES=concurrent_vs_mh_only  runs just one of the two studies.
# Connection settings come from .env via scripts/lib/env.R (see .env.example).
# The private library is added only if it exists; in the Docker image the packages are
# already on the default library path (see docker/r/install.R).
cc_lib <- file.path("omop_tools", "r_lib_cohortcontrast")
if (dir.exists(cc_lib)) .libPaths(c(normalizePath(cc_lib), .libPaths()))
suppressPackageStartupMessages({
  library(CohortContrast)
  library(CDMConnector)
  library(DBI)
  library(dplyr)
})
source(file.path("scripts", "lib", "env.R"))
out_dir <- normalizePath(file.path("omop_tools", "cohortcontrast_results"), mustWork = FALSE)
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

# RPostgres connection built from OMOP_DB_* in .env; no built-in database or user.
db <- omop_dbi_connect()
on.exit(DBI::dbDisconnect(db), add = TRUE)

cdm <- CDMConnector::cdmFromCon(
  con = db, cdmSchema = "cdm", achillesSchema = "results",
  writeSchema = c(schema = "results", prefix = "cc_"), cdmName = "SYNCD"
)

target <- cohortFromCohortTable(cdm, db, tableName = "cohort", schemaName = "results", cohortId = 1)
mh_only <- cohortFromCohortTable(cdm, db, tableName = "cohort", schemaName = "results", cohortId = 2)
set.seed(2026)
matched <- createControlCohortMatching(cdm, targetTable = target, ratio = 4)
# Matched controls inherit the target's dates; keep only the part inside each control's own
# observation period (CohortContrast rejects rows outside it).
op <- DBI::dbGetQuery(db, "SELECT person_id AS subject_id, observation_period_start_date AS op_start,
                                  observation_period_end_date AS op_end FROM cdm.observation_period")
# keep subject_id in the same type as the target table (integer64 from RPostgres)
op$subject_id <- if (inherits(matched$subject_id, "integer64")) bit64::as.integer64(op$subject_id) else
  methods::as(op$subject_id, class(matched$subject_id)[1])
matched <- matched %>%
  inner_join(op, by = "subject_id") %>%
  mutate(cohort_start_date = pmax(as.Date(cohort_start_date), op_start),
         cohort_end_date = pmin(as.Date(cohort_end_date), op_end)) %>%
  filter(cohort_start_date <= cohort_end_date) %>%
  select(-op_start, -op_end)
cat(sprintf("Target %d people; MH-only control %d; matched control %d\n",
            n_distinct(target$subject_id), n_distinct(mh_only$subject_id),
            n_distinct(matched$subject_id)))

run_study <- function(control, name) {
  cat("\n==== CohortContrast:", name, "====\n")
  CohortContrast(
    cdm,
    targetTable = target,
    controlTable = control,
    pathToResults = out_dir,
    domainsIncluded = c("Drug", "Condition", "Measurement", "Observation", "Procedure", "Visit"),
    prevalenceCutOff = 1.5,   # keep concepts at least 1.5x as prevalent in target as in control
    presenceFilter = 0.05,    # ... and present in at least 5% of target patients
    topK = FALSE,
    runChi2YTests = TRUE,
    runLogitTests = FALSE,
    createOutputFiles = TRUE,
    complName = name,
    numCores = 4
  )
}
studies <- strsplit(Sys.getenv("CC_STUDIES", "concurrent_vs_mh_only,concurrent_vs_matched"), ",")[[1]]
if ("concurrent_vs_mh_only" %in% studies) res_mh <- run_study(mh_only, "concurrent_vs_mh_only")
if ("concurrent_vs_matched" %in% studies) res_matched <- run_study(matched, "concurrent_vs_matched")

top_separating <- function(study, name) {
  out <- getTopSeparatingConcepts(file.path(out_dir, study), n = 15)
  cat("\nTop separating concepts -", name, ":\n")
  print(as.data.frame(out), row.names = FALSE)
}
try(top_separating("concurrent_vs_mh_only", "concurrent vs MH only"))
try(top_separating("concurrent_vs_matched", "concurrent vs matched population"))
cat("\nStudies written to", out_dir, "\n")
