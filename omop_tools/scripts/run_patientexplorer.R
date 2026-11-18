# Launch PatientExploreR against the SYNCD OMOP database.
# PatientExploreR (2018) expects unqualified OMOP CDM 5.3 tables and connects through RMySQL or
# an old DatabaseConnector API. We patch it (omop_tools/patches/patientexplorer_postgres.patch) so
# its DBI code path uses RPostgres, and point it at the `pexr` compatibility schema
# (omop_tools/sql/01_patientexplorer_schema.sql) through libpq's PGOPTIONS search_path.
# In the app choose "PostgreSQL (DBI, SYNCD patch)"; the other fields are pre-filled from
# omop_tools/PatientExploreR/.Renviron. Leave username blank to connect as your OS user.
# Usage (from the project root): Rscript omop_tools/scripts/run_patientexplorer.R [port=8090]
args <- commandArgs(trailingOnly = TRUE)
port <- if (length(args) >= 1) as.integer(args[1]) else 8090L
Sys.setenv(PGOPTIONS = "-c search_path=pexr")
app_dir <- normalizePath(file.path("omop_tools", "PatientExploreR"))
setwd(app_dir)
shiny::runApp(app_dir, port = port, launch.browser = FALSE, host = "127.0.0.1")
