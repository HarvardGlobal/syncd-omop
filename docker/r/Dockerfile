FROM rocker/r-ver:4.4

# default-jdk-headless: rJava / JDBC for DatabaseConnector
# postgresql-client:    psql for \copy bulk loads + 06a_load_vocab.sh
# libpq-dev:            in case RPostgres has to compile from source
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
       default-jdk-headless postgresql-client libpq-dev \
  && rm -rf /var/lib/apt/lists/* \
  && R CMD javareconf

# Copied in on its own, so the slow install layer only rebuilds
# when the package list actually changes.
COPY install.R /tmp/install.R
RUN Rscript /tmp/install.R

# Viewer apps (PatientExploreR's shiny add-ons). A separate, later layer: changing
# this list rebuilds in a minute or two instead of redoing the OHDSI install above.
COPY install-viewers.R /tmp/install-viewers.R
RUN Rscript /tmp/install-viewers.R

# curl: Comorbidity4j's first-run download and its form driver
# (omop_tools/scripts/c4j_start_server.sh, c4j_run_analysis.sh).
# Added as a late layer on purpose: putting it in the first apt-get line would
# invalidate every layer below it and force the full OHDSI reinstall.
RUN apt-get update \
  && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /work