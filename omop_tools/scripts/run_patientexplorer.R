# Launch PatientExploreR against the SYNCD OMOP database.
# PatientExploreR (2018) expects unqualified OMOP CDM 5.3 tables and connects through RMySQL or
# an old DatabaseConnector API. We patch it (omop_tools/patches/patientexplorer_postgres.patch) so
# its DBI code path uses RPostgres, and point it at the `pexr` compatibility schema
# (omop_tools/sql/01_patientexplorer_schema.sql) through libpq's PGOPTIONS search_path.
#
# Connection: the OMOP_DB_* settings in .env are copied onto libpq's PG* variables
# (scripts/lib/env.R, omop_pg_env()). RPostgres is built on libpq, so any field left blank
# in the app's login form is filled from them: choose "PostgreSQL (DBI, SYNCD patch)" and
# you can leave host, database, username and password empty. Anything typed into the form
# still wins.
#
# Usage (from the project root): Rscript omop_tools/scripts/run_patientexplorer.R [port]
#   port: first argument, else PEXR_PORT from .env, else 8090.
source(file.path("scripts", "lib", "env.R"))

args <- commandArgs(trailingOnly = TRUE)
port <- suppressWarnings(as.integer(if (length(args) >= 1) args[1] else Sys.getenv("PEXR_PORT", "8090")))
if (is.na(port)) stop("Port must be a number.", call. = FALSE)

omop_pg_env()                                    # OMOP_DB_* -> PGHOST, PGDATABASE, PGUSER, ...
Sys.setenv(PGOPTIONS = "-c search_path=pexr")    # the compatibility schema, not cdm

app_dir <- file.path("omop_tools", "PatientExploreR")
if (!dir.exists(app_dir)) {
  stop("PatientExploreR isn't installed at ", app_dir, ". See \"Installing the tools\" in ",
       "omop_tools/README.md (clone it, then apply patches/patientexplorer_postgres.patch).",
       call. = FALSE)
}
app_dir <- normalizePath(app_dir)
setwd(app_dir)
cat(sprintf("PatientExploreR on http://127.0.0.1:%d  (database: %s)\n", port, Sys.getenv("PGDATABASE")))
shiny::runApp(app_dir, port = port, launch.browser = FALSE, host = "127.0.0.1")
