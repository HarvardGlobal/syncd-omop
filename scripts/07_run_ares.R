# Step 7 - Characterise the OMOP CDM and build the OHDSI ARES viewer.
#   1. Achilles: descriptive statistics for every CDM domain -> results schema
#   2. Achilles::exportToAres: JSON/CSV files for ARES
#   3. DataQualityDashboard: ~3,500 data quality checks -> dq-result.json
#   4. Achilles temporal characterisation + AresIndexer network indices
# The ARES web app (omop_viz/ares_app/site) then reads omop_viz/ares_app/site/data.
#
# Usage (from the project root):  Rscript scripts/07_run_ares.R [all|achilles|dqd|index]
#
# Connection: read from .env at the repo root by scripts/lib/env.R (see .env.example).
suppressPackageStartupMessages({
  library(DatabaseConnector)
})
source(file.path("scripts", "lib", "env.R"))
args <- commandArgs(trailingOnly = TRUE)
stage <- if (length(args) >= 1) args[1] else "all"
root <- normalizePath(".")
driver_dir <- file.path(root, "omop_load", "jdbc")
Sys.setenv(DATABASECONNECTOR_JAR_FOLDER = driver_dir)

# Same database as 06_load_omop.R, because both read OMOP_DB_NAME from .env.
cd <- omop_connection_details(driver_dir)
CDM <- "cdm"; RESULTS <- "results"; VOCAB <- "cdm"; CDM_VERSION <- "5.4"
THREADS <- 4
ares_data <- file.path(root, "omop_viz", "ares_app", "site", "data")
dir.create(ares_data, recursive = TRUE, showWarnings = FALSE)
step <- function(msg) cat(sprintf("[%s] %s\n", format(Sys.time(), "%H:%M:%S"), msg))
t0 <- Sys.time()

# exportToAres writes <data>/<source>/<release date>/; the release key is "<source>/<date>"
release_key <- AresIndexer::getSourceReleaseKey(cd, CDM)
release_dir <- file.path(ares_data, release_key)
step(sprintf("Release %s -> %s", release_key, release_dir))

if (stage %in% c("all", "achilles")) {
  step("Achilles: characterising all CDM tables")
  Achilles::achilles(cd, cdmDatabaseSchema = CDM, resultsDatabaseSchema = RESULTS,
                     vocabDatabaseSchema = VOCAB, cdmVersion = CDM_VERSION,
                     numThreads = THREADS, createTable = TRUE, createIndices = FALSE,
                     smallCellCount = 0,   # synthetic data: no small-cell suppression needed
                     outputFolder = file.path(root, "omop_viz", "achilles_logs"))
  step("Exporting Achilles results for ARES")
  Achilles::exportToAres(cd, cdmDatabaseSchema = CDM, resultsDatabaseSchema = RESULTS,
                         vocabDatabaseSchema = VOCAB, outputPath = ares_data)
}

if (stage %in% c("all", "dqd")) {
  step("Data Quality Dashboard: running checks")
  dir.create(release_dir, recursive = TRUE, showWarnings = FALSE)
  # DQD 2.9.1 + DatabaseConnector 6.4 can throw on the final disconnect after the results file
  # is written; treat that as success when dq-result.json exists.
  # Checks on COHORT / COHORT_DEFINITION error because those tables are not in the cdm schema.
  tryCatch(DataQualityDashboard::executeDqChecks(
    connectionDetails = cd, cdmDatabaseSchema = CDM, resultsDatabaseSchema = RESULTS,
    vocabDatabaseSchema = VOCAB, cdmSourceName = "Synthetic concurrent disorders",
    numThreads = THREADS, outputFolder = release_dir, outputFile = "dq-result.json",
    verboseMode = FALSE, writeToTable = FALSE, cdmVersion = CDM_VERSION),
    error = function(e) {
      if (!file.exists(file.path(release_dir, "dq-result.json"))) stop(e)
      step(paste("DQD finished; ignoring error on disconnect:", conditionMessage(e)))
    })
}

if (stage %in% c("all", "dqd", "temporal")) {
  step("Achilles temporal characterisation")
  Achilles::performTemporalCharacterization(
    connectionDetails = cd, cdmDatabaseSchema = CDM, resultsDatabaseSchema = RESULTS,
    outputFile = file.path(release_dir, "temporal-characterization.csv"))
}

if (stage %in% c("all", "index")) {
  step("Building ARES indices")
  # Compatibility shim: AresIndexer 0.2.0 selects lower-case columns (analysis_id, category)
  # from Achilles::getAnalysisDetails(), which Achilles 1.7 returns in upper case.
  local({
    orig <- Achilles::getAnalysisDetails
    shim <- function() { x <- orig(); names(x) <- tolower(names(x)); x }
    utils::assignInNamespace("getAnalysisDetails", shim, ns = "Achilles")
  })
  sources <- list.dirs(ares_data, recursive = FALSE)
  # Function names follow AresIndexer 0.2.0 (the ARES docs list newer names).
  AresIndexer::augmentConceptFiles(releaseFolder = release_dir)
  AresIndexer::buildExportQueryIndex(ares_data)
  for (s in sources) {
    AresIndexer::buildDataSourceHistoryIndex(s)
    AresIndexer::buildDataQualityHistoryIndex(s)
  }
  # Optional query-timing index; AresIndexer 0.2.0 expects lower-case columns that
  # Achilles 1.7 no longer returns, so a failure here is reported and skipped.
  tryCatch(AresIndexer::buildNetworkPerformanceIndex(ares_data),
           error = function(e) step(paste("Skipped performance index:", conditionMessage(e))))
  AresIndexer::buildNetworkIndex(sources, outputFolder = ares_data)
  AresIndexer::buildDataQualityIndex(sources, outputFolder = ares_data)
  AresIndexer::buildNetworkUnmappedSourceCodeIndex(sources, outputFolder = ares_data)
}
step(sprintf("Done in %.1f min", as.numeric(difftime(Sys.time(), t0, units = "mins"))))
