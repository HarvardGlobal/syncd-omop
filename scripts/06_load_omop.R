# Step 6 - Load the Synthea CSVs into PostgreSQL and convert them to OMOP CDM 5.4
# with OHDSI ETLSyntheaBuilder.
#
# Usage (from the project root):
#   Rscript scripts/06_load_omop.R staging  [csv_dir]
#       -> creates empty OMOP CDM 5.4 tables in `cdm`, Synthea staging tables in `synthea`,
#          and bulk-loads the Synthea CSVs into `synthea`
#   Rscript scripts/06_load_omop.R vocab_etl <athena_vocab_dir>
#       -> loads Athena vocabularies into `cdm` (in R; needs lots of RAM), then runs the ETL
#   scripts/06a_load_vocab.sh <athena_vocab_dir> && Rscript scripts/06_load_omop.R etl
#       -> same result, vocabularies streamed by PostgreSQL COPY (used for this project)
#
# Connection: read from .env at the repo root (OMOP_DB_HOST, OMOP_DB_PORT, OMOP_DB_NAME,
# OMOP_DB_USER, OMOP_DB_PASSWORD) by scripts/lib/env.R. See .env.example.
suppressPackageStartupMessages({
  library(DatabaseConnector)
  library(ETLSyntheaBuilder)
})
source(file.path("scripts", "lib", "env.R"))

args <- commandArgs(trailingOnly = TRUE)
stage <- if (length(args) >= 1) args[1] else stop("stage required: staging | vocab_etl")
root <- normalizePath(".")
driver_dir <- file.path(root, "omop_load", "jdbc")
dir.create(driver_dir, recursive = TRUE, showWarnings = FALSE)
if (length(list.files(driver_dir, pattern = "postgresql.*\\.jar$")) == 0) {
  downloadJdbcDrivers(dbms = "postgresql", pathToDriver = driver_dir)
}
configure_psql_path()                     # psql \copy for bulk loads; found on PATH, not hardcoded
cd <- omop_connection_details(driver_dir)  # all connection settings come from .env

CDM_SCHEMA <- "cdm"
SYNTHEA_SCHEMA <- "synthea"
CDM_VERSION <- "5.4"
SYNTHEA_VERSION <- "3.3.0"
t0 <- Sys.time()
step <- function(msg) cat(sprintf("[%s] %s\n", format(Sys.time(), "%H:%M:%S"), msg))

if (stage == "staging") {
  csv_dir <- if (length(args) >= 2) normalizePath(args[2]) else
    file.path(root, "output", "expansion_10000", "csv")
  step(paste("Synthea CSV folder:", csv_dir))
  step("Creating OMOP CDM 5.4 tables in schema cdm")
  CreateCDMTables(connectionDetails = cd, cdmSchema = CDM_SCHEMA, cdmVersion = CDM_VERSION)
  step("Creating Synthea 3.3.0 staging tables in schema synthea")
  CreateSyntheaTables(connectionDetails = cd, syntheaSchema = SYNTHEA_SCHEMA,
                      syntheaVersion = SYNTHEA_VERSION)
  step("Loading Synthea CSVs")
  LoadSyntheaTables(connectionDetails = cd, syntheaSchema = SYNTHEA_SCHEMA,
                    syntheaFileLoc = csv_dir, bulkLoad = TRUE)
} else if (stage %in% c("vocab_etl", "etl")) {
  if (stage == "vocab_etl") {
    # In-R loader (memory heavy). On machines with < ~16 GB free, use
    # scripts/06a_load_vocab.sh <athena_dir> and then the "etl" stage instead.
    if (length(args) < 2) stop("vocab_etl needs the unzipped Athena vocabulary folder")
    vocab_dir <- normalizePath(args[2])
    step(paste("Loading Athena vocabularies from", vocab_dir))
    LoadVocabFromCsv(connectionDetails = cd, cdmSchema = CDM_SCHEMA, vocabFileLoc = vocab_dir,
                     bulkLoad = TRUE)
  }
  step("Creating source-to-standard vocabulary map tables")
  CreateVocabMapTables(connectionDetails = cd, cdmSchema = CDM_SCHEMA, cdmVersion = CDM_VERSION)
  desc <- paste("Synthetic adults (Synthea 3.3.0) calibrated to NSDUH 2024 joint prevalence of",
                "any mental illness and DSM-5 substance use disorder by age group and sex.",
                "Clinical timelines, MH diagnosis mapping and treatment content are documented",
                "simulation assumptions. Not for treatment-effect estimation.")
  step("Building visit/claim rollup tables")
  CreateMapAndRollupTables(connectionDetails = cd, cdmSchema = CDM_SCHEMA,
                           syntheaSchema = SYNTHEA_SCHEMA, cdmVersion = CDM_VERSION,
                           syntheaVersion = SYNTHEA_VERSION)
  step("Creating extra indices on staging tables")
  CreateExtraIndices(connectionDetails = cd, cdmSchema = CDM_SCHEMA,
                     syntheaSchema = SYNTHEA_SCHEMA, syntheaVersion = SYNTHEA_VERSION)
  step("Loading OMOP event tables")
  LoadEventTables(connectionDetails = cd, cdmSchema = CDM_SCHEMA, syntheaSchema = SYNTHEA_SCHEMA,
                  cdmVersion = CDM_VERSION, syntheaVersion = SYNTHEA_VERSION,
                  cdmSourceName = "Synthetic concurrent disorders",
                  cdmSourceAbbreviation = "SYNCD",
                  cdmHolder = "Synthetic data (no real patients)",
                  cdmSourceDescription = desc)
  step("Creating CDM indices")
  CreateCDMIndices(connectionDetails = cd, cdmSchema = CDM_SCHEMA, cdmVersion = CDM_VERSION)
} else {
  stop("unknown stage: ", stage)
}
step(sprintf("Done in %.1f min", as.numeric(difftime(Sys.time(), t0, units = "mins"))))
