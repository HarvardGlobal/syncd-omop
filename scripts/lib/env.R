# =============================================================================
# scripts/lib/env.R - shared settings loader for the SYNCD R scripts
# =============================================================================
#
# Every R script in the pipeline sources this file instead of hardcoding database
# names, users, or platform-specific paths (the original scripts assumed a Homebrew
# PostgreSQL on macOS). All machine- and person-specific settings live in `.env` at
# the repo root, which is git-ignored. See `.env.example` for the full list.
#
# Usage (scripts are always run from the project root):
#
#   source(file.path("scripts", "lib", "env.R"))
#   cd <- omop_connection_details(driver_dir)
#
# Precedence, highest first:
#   1. Variables already in the environment (e.g. passed in by `docker compose`
#      via `env_file: .env`, or set on the command line for a one-off run)
#   2. Values in `.env`
#   3. Built-in generic defaults (host `localhost`, port `5432` only; nothing
#      project- or person-specific has a default)
#
# @see .env.example
# @see README-docker.md
# =============================================================================

#' Load KEY=value pairs from a .env file into the R session environment.
#'
#' A deliberately small parser, written so the file is read as *data* and never
#' executed (unlike `source()`-ing it from a shell). It understands the subset of
#' the dotenv format that `docker compose` also understands:
#'   - blank lines and lines starting with `#` are skipped
#'   - an optional leading `export ` is ignored
#'   - values may be wrapped in single or double quotes (quotes are removed)
#'   - on an unquoted value, ` # comment` at the end is stripped
#'
#' Variables that are already set in the environment are NOT overwritten, so a
#' value from `docker compose` or the command line always wins.
#'
#' @param path Path to the .env file. Defaults to `.env` in the working directory
#'   (the project root).
#' @return Invisibly, TRUE if a file was read, FALSE if none was found. A missing
#'   file is not an error: inside Docker the variables arrive via `env_file`.
load_dotenv <- function(path = file.path(normalizePath("."), ".env")) {
  if (!file.exists(path)) return(invisible(FALSE))

  for (raw in readLines(path, warn = FALSE)) {
    line <- trimws(sub("\r$", "", raw))                # tolerate Windows line endings
    if (line == "" || startsWith(line, "#")) next
    line <- sub("^export[[:space:]]+", "", line)

    eq <- regexpr("=", line, fixed = TRUE)
    if (eq < 2) next                                    # no key, or no '=' at all
    key <- trimws(substr(line, 1, eq - 1))
    val <- trimws(substr(line, eq + 1, nchar(line)))

    # Only accept shell-style variable names; anything else is a typo, not config.
    if (!grepl("^[A-Za-z_][A-Za-z0-9_]*$", key)) next

    if (grepl('^".*"$', val) || grepl("^'.*'$", val)) {
      val <- substr(val, 2, nchar(val) - 1)             # quoted: take literally
    } else {
      val <- sub("[[:space:]]+#.*$", "", val)           # unquoted: drop trailing comment
    }

    # The real environment wins (see precedence notes at the top of this file).
    if (!is.na(Sys.getenv(key, unset = NA))) next
    do.call(Sys.setenv, stats::setNames(list(val), key))
  }
  invisible(TRUE)
}

#' Stop with one readable message listing every required variable that is unset.
#'
#' Checking all keys at once (rather than failing on the first) saves a round
#' trip of "fix one, rerun, find the next".
#'
#' @param keys Character vector of variable names that must be set.
#'   An empty string counts as set, so passwordless local setups still work.
#' @return Invisibly, TRUE when all keys are present.
require_env <- function(keys) {
  missing <- keys[is.na(Sys.getenv(keys, unset = NA))]
  if (length(missing) > 0) {
    stop(
      "Missing setting(s): ", paste(missing, collapse = ", "), "\n",
      "Add them to .env at the repo root (copy .env.example to start).",
      call. = FALSE
    )
  }
  invisible(TRUE)
}

#' Build DatabaseConnector connection details for the OMOP database from .env.
#'
#' DatabaseConnector's PostgreSQL `server` argument is "host/database", so it is
#' assembled here from OMOP_DB_HOST and OMOP_DB_NAME rather than stored twice.
#'
#' @param driver_dir Folder holding (or receiving) the PostgreSQL JDBC driver.
#' @return A DatabaseConnector `ConnectionDetails` object.
#' @see https://ohdsi.github.io/DatabaseConnector/reference/createConnectionDetails.html
omop_connection_details <- function(driver_dir) {
  require_env(c("OMOP_DB_NAME", "OMOP_DB_USER", "OMOP_DB_PASSWORD"))

  host <- Sys.getenv("OMOP_DB_HOST", "localhost")
  port <- suppressWarnings(as.integer(Sys.getenv("OMOP_DB_PORT", "5432")))
  if (is.na(port)) stop("OMOP_DB_PORT must be a number.", call. = FALSE)

  DatabaseConnector::createConnectionDetails(
    dbms = "postgresql",
    server = paste0(host, "/", Sys.getenv("OMOP_DB_NAME")),
    port = port,
    user = Sys.getenv("OMOP_DB_USER"),
    password = Sys.getenv("OMOP_DB_PASSWORD"),
    pathToDriver = driver_dir
  )
}

#' Open a DBI connection to the OMOP database with RPostgres, using .env.
#'
#' For tools built on DBI/CDMConnector rather than DatabaseConnector
#' (e.g. CohortContrast). Same settings as omop_connection_details().
#'
#' @return A DBI connection. The caller is responsible for DBI::dbDisconnect().
#' @see https://rpostgres.r-dbi.org/reference/postgres.html
omop_dbi_connect <- function() {
  require_env(c("OMOP_DB_NAME", "OMOP_DB_USER", "OMOP_DB_PASSWORD"))
  port <- suppressWarnings(as.integer(Sys.getenv("OMOP_DB_PORT", "5432")))
  if (is.na(port)) stop("OMOP_DB_PORT must be a number.", call. = FALSE)

  DBI::dbConnect(
    RPostgres::Postgres(),
    host = Sys.getenv("OMOP_DB_HOST", "localhost"),
    port = port,
    dbname = Sys.getenv("OMOP_DB_NAME"),
    user = Sys.getenv("OMOP_DB_USER"),
    password = Sys.getenv("OMOP_DB_PASSWORD")
  )
}

#' Copy the OMOP_DB_* settings onto libpq's PG* variables.
#'
#' Anything built on libpq (psql, RPostgres, apps that leave connection fields
#' blank) then reaches the same database without its own configuration.
#' Mirrors omop_pg_env() in scripts/lib/env.sh. Existing PG* values are kept,
#' as an explicit override.
#'
#' @return Invisibly, TRUE.
#' @see https://www.postgresql.org/docs/16/libpq-envars.html
omop_pg_env <- function() {
  require_env(c("OMOP_DB_NAME", "OMOP_DB_USER", "OMOP_DB_PASSWORD"))
  map <- c(
    PGHOST     = Sys.getenv("OMOP_DB_HOST", "localhost"),
    PGPORT     = Sys.getenv("OMOP_DB_PORT", "5432"),
    PGDATABASE = Sys.getenv("OMOP_DB_NAME"),
    PGUSER     = Sys.getenv("OMOP_DB_USER"),
    PGPASSWORD = Sys.getenv("OMOP_DB_PASSWORD")
  )
  for (key in names(map)) {
    if (is.na(Sys.getenv(key, unset = NA))) do.call(Sys.setenv, stats::setNames(list(map[[key]]), key))
  }
  invisible(TRUE)
}

#' Point DatabaseConnector's bulk loader at psql, wherever it is installed.
#'
#' DatabaseConnector bulk-loads PostgreSQL with `psql \copy`, and wants the
#' *directory* containing psql in POSTGRES_PATH. Lookup order:
#'   1. POSTGRES_PATH already set (compose.yml sets /usr/bin for the container)
#'   2. PSQL_BIN from .env (full path to the psql binary)
#'   3. psql on PATH (Linux packages, Homebrew, Postgres.app, Windows installers)
#'
#' Degrades gracefully: if psql can't be found, it warns and leaves POSTGRES_PATH
#' unset rather than stopping, so stages that don't bulk-load still run.
#'
#' @return Invisibly, the directory used, or NA if psql was not found.
configure_psql_path <- function() {
  existing <- Sys.getenv("POSTGRES_PATH", unset = "")
  if (nzchar(existing)) return(invisible(existing))

  bin <- Sys.getenv("PSQL_BIN", unset = "")
  if (!nzchar(bin)) bin <- unname(Sys.which("psql"))

  if (!nzchar(bin) || !file.exists(bin)) {
    warning("psql not found on PATH and PSQL_BIN is not set; bulk loads will fail. ",
            "Install the PostgreSQL client or set PSQL_BIN in .env.", call. = FALSE)
    return(invisible(NA_character_))
  }
  # dirname() of the path as found, NOT normalizePath(): on Debian/Ubuntu /usr/bin/psql
  # is a symlink to /usr/share/postgresql-common/pg_wrapper, and following it would
  # hand DatabaseConnector a folder with no `psql` in it.
  dir <- dirname(bin)
  Sys.setenv(POSTGRES_PATH = dir)
  invisible(dir)
}

# Load .env as soon as this file is sourced, so every script sees the same settings.
load_dotenv()
