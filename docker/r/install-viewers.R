#' Install the extra R packages the interactive viewer apps need.
#'
#' Kept separate from install.R on purpose: install.R builds the slow OHDSI
#' layer (10-20 minutes). This file is its own, later Docker layer, so adding a
#' package here rebuilds in a minute or two and leaves that layer cached.
#'
#' Current consumers:
#'   - PatientExploreR (omop_tools/scripts/run_patientexplorer.R): its app.R and
#'     global.R load every package below. shiny, DBI, RPostgres, dplyr, purrr,
#'     data.table, stringr, DatabaseConnector and SqlRender already come from
#'     install.R (directly or as dependencies), so they aren't repeated here.
#'
#' Same rule as install.R: anything that fails to install stops the build,
#' rather than surfacing later as "there is no package called ...".
#'
#' @see docker/r/install.R
#' @see omop_tools/PatientExploreR/install.R  upstream's own (devtools-based) list
#' @see https://rocker-project.org/images/versioned/r-ver.html

viewer_packages <- c(
  "shinyWidgets",     # pickers and switches in the login and filter panels
  "shinyjs",          # show/hide panels after login
  "shinythemes",      # Bootstrap theme
  "shinyalert",       # pop-up messages (connection errors, etc.)
  "shinycssloaders",  # loading spinners
  "plotly",           # interactive charts
  "DT",               # data tables
  "timevis"           # the patient timeline
)

# All on CRAN; rocker's repository serves prebuilt Linux binaries, so this is quick.
install.packages(viewer_packages)

still_missing <- setdiff(viewer_packages, rownames(installed.packages()))
if (length(still_missing)) stop("Failed to install: ", paste(still_missing, collapse = ", "))
message(">> All ", length(viewer_packages), " viewer packages installed.")
