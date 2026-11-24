#' Install the R packages the SYNCD pipeline needs.
#'
#' Strategy: try CRAN first (on rocker these come down as prebuilt
#' Linux binaries, so they're fast), and fall back to GitHub for anything
#' CRAN doesn't carry. Anything that fails either way stops the build loudly,
#' rather than leaving you to find out halfway through an ETL run.
#'
#' @see https://rocker-project.org/images/versioned/r-ver.html

#' Install a GitHub package whose DESCRIPTION has a malformed version operator.
#'
#' Some packages declare deps like `pkg (= 1.2.3)`. R wants `==` or `>=`,
#' and remotes refuses to parse a bare `=`. This downloads the repo tarball,
#' rewrites `(= ` to `(>= ` in DESCRIPTION, and installs from the patched copy.
#'
#' `>=` rather than `==` on purpose: an exact pin can clash with a newer
#' version another package already pulled in. If CohortContrast misbehaves
#' at runtime, that's the first place to look.
#'
#' @param repo  "owner/repo" on GitHub
#' @return      invisible(NULL); errors if the install fails
install_github_patched <- function(repo) {
  tmp <- tempfile("pkg_")
  dir.create(tmp)
  tarball <- file.path(tmp, "src.tar.gz")

  # HEAD tarball: the same commit install_github would have used.
  utils::download.file(
    sprintf("https://github.com/%s/archive/HEAD.tar.gz", repo),
    tarball, quiet = TRUE
  )
  utils::untar(tarball, exdir = tmp)

  # GitHub tarballs unpack to a single "<repo>-<sha>/" folder.
  src <- list.dirs(tmp, recursive = FALSE)[1]
  desc_path <- file.path(src, "DESCRIPTION")

  desc <- readLines(desc_path)
  fixed <- gsub("\\(\\s*=\\s*", "(>= ", desc)
  changed <- which(desc != fixed)
  if (length(changed)) {
    message(">> Patched DESCRIPTION lines: ", paste(trimws(fixed[changed]), collapse = " | "))
  }
  writeLines(fixed, desc_path)

  remotes::install_local(src, upgrade = "never")
  invisible(NULL)
}

# Packages that only live on GitHub, or whose GitHub repo name
# differs from the package name. Format: package = "owner/repo".
github_sources <- c(
  ETLSyntheaBuilder    = "OHDSI/ETL-Synthea",
  AresIndexer          = "OHDSI/AresIndexer",
  Achilles             = "OHDSI/Achilles",
  DataQualityDashboard = "OHDSI/DataQualityDashboard",
  CohortContrast       = "HealthInformaticsUT/CohortContrast",
  TreatmentPatterns    = "darwin-eu/TreatmentPatterns",
  CDMConnector         = "darwin-eu/CDMConnector"
)

# Everything the scripts load (from the grep), minus base R's methods/utils.
wanted <- c(
  # DB connectivity
  "DatabaseConnector", "SqlRender", "DBI", "RPostgres", "bit64",
  # data wrangling / storage
  "dplyr", "Andromeda",
  # OHDSI / DARWIN analytics
  "CDMConnector", "Achilles", "DataQualityDashboard", "AresIndexer",
  "TreatmentPatterns", "CohortContrast", "ETLSyntheaBuilder",
  # viewers
  "shiny", "htmlwidgets"
)

install.packages("remotes")

# Pass 1: CRAN. Packages it doesn't have are skipped with a warning, not an error.
available <- rownames(available.packages())
from_cran <- intersect(wanted, available)
install.packages(from_cran)

# Pass 2: GitHub, for whatever still isn't installed.
missing <- setdiff(wanted, rownames(installed.packages()))
for (pkg in missing) {
  repo <- github_sources[[pkg]]
  if (is.null(repo)) stop("No CRAN or GitHub source known for: ", pkg)
  message(">> ", pkg, " not on CRAN; installing from github.com/", repo)
  tryCatch(
    remotes::install_github(repo, upgrade = "never"),
    error = function(e) {
      # Only take the patch route for this specific parse error;
      # any other failure should still stop the build.
      if (!grepl("Invalid comparison operator", conditionMessage(e))) stop(e)
      message(">> ", pkg, ": malformed DESCRIPTION, retrying with patched copy")
      install_github_patched(repo)
    }
  )
}

# Final check: fail the image build if anything is still missing.
still_missing <- setdiff(wanted, rownames(installed.packages()))
if (length(still_missing)) stop("Failed to install: ", paste(still_missing, collapse = ", "))
message(">> All ", length(wanted), " packages installed.")