# TreatmentPatterns (OHDSI HADES) on the SYNCD OMOP database.
# Needs the cohorts from omop_tools/sql/02_study_cohorts.sql in results.cohort.
#   Targets: 1 Concurrent MH and SUD, 2 MH only, 3 SUD only
#   Events : 11 Sertraline, 12 CBT, 13 SUD counselling, 14 Buprenorphine-naloxone, 15 Naltrexone
# Writes CSVs per target, and interactive sunburst + Sankey pages per target to
# omop_tools/treatmentpatterns_results/.
# Usage (from the project root): Rscript omop_tools/scripts/run_treatmentpatterns.R
# Connection settings come from .env via scripts/lib/env.R (see .env.example).
suppressPackageStartupMessages({
  library(DatabaseConnector)
  library(TreatmentPatterns)
  library(dplyr)
})
source(file.path("scripts", "lib", "env.R"))
root <- normalizePath(".")
driver_dir <- file.path(root, "omop_load", "jdbc")
out_dir <- file.path(root, "omop_tools", "treatmentpatterns_results")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

# Same database as the pipeline scripts: OMOP_DB_* from .env, no built-in default.
cd <- omop_connection_details(driver_dir)

targets <- data.frame(cohortId = c(1, 2, 3),
                      cohortName = c("Concurrent MH and SUD", "MH only", "SUD only"))
events <- data.frame(
  cohortId   = c(11, 12, 13, 14, 15),
  cohortName = c("Sertraline", "CBT", "SUD counselling", "Buprenorphine-naloxone", "Naltrexone"),
  type       = "event"
)

# One run per target: TreatmentPatterns 3.1.0 fails in export(nonePaths = TRUE) when a run has
# several targets (getFilteredSubjects compares cohortId with `==` against a vector).
all_paths <- list()
for (i in seq_len(nrow(targets))) {
  tgt <- targets[i, ]
  slug <- gsub("[^a-z0-9]+", "_", tolower(tgt$cohortName))
  cat("\n==== Target:", tgt$cohortName, "====\n")
  cohorts <- rbind(data.frame(cohortId = tgt$cohortId, cohortName = tgt$cohortName, type = "target"),
                   events)
  andromeda <- computePathways(
    cohorts = cohorts,
    cohortTableName = "cohort",
    connectionDetails = cd,
    cdmSchema = "cdm",
    resultSchema = "results",
    analysisId = tgt$cohortId,
    description = tgt$cohortName,
    # Look for treatment from 365 days before the index diagnosis to the end of observation, so
    # treatment for the first disorder is kept in the concurrent-disorder journey.
    startAnchor = "startDate", windowStart = -365,
    endAnchor = "endDate", windowEnd = 0,
    minEraDuration = 0,
    eraCollapseSize = 95,            # follow-up visits are 4-13 weeks apart: gaps <= 95 days stay one era
    combinationWindow = 7,           # overlap >= 7 days counts as a combination (e.g. CBT+Sertraline)
    minPostCombinationDuration = 7,  # drop leftover fragments shorter than a week
    filterTreatments = "Changes",    # keep a treatment again only when it follows a different one
    maxPathLength = 5
  )
  tdir <- file.path(out_dir, slug)
  dir.create(tdir, showWarnings = FALSE)
  # nonePaths = TRUE keeps untreated patients as the pathway "None"
  results <- export(andromeda, outputPath = tdir, minCellCount = 5, censorType = "minCellCount",
                    ageWindow = c(18, 35, 50, 65, 150), nonePaths = TRUE)
  Andromeda::close(andromeda)
  tp <- results$treatment_pathways %>% filter(age == "all", sex == "all", index_year == "all")
  all_paths[[tgt$cohortName]] <- tp
  htmlwidgets::saveWidget(createSunburstPlot(tp, groupCombinations = FALSE),
                          file.path(out_dir, paste0("sunburst_", slug, ".html")), selfcontained = FALSE, libdir = "lib")  # no pandoc needed
  htmlwidgets::saveWidget(createSankeyDiagram(tp, groupCombinations = FALSE),
                          file.path(out_dir, paste0("sankey_", slug, ".html")), selfcontained = FALSE, libdir = "lib")  # no pandoc needed
}

cat("\nTop pathways by target (all ages, both sexes, all index years):\n")
top <- bind_rows(all_paths) %>%
  group_by(target_cohort_name) %>%
  mutate(share = round(100 * freq / sum(freq), 1)) %>%
  slice_max(freq, n = 8, with_ties = FALSE) %>%
  ungroup() %>%
  select(target_cohort_name, pathway, freq, share)
print(as.data.frame(top), row.names = FALSE)
write.csv(bind_rows(all_paths), file.path(out_dir, "pathways_all_targets.csv"), row.names = FALSE)
cat("\nResults written to", out_dir, "\n")
