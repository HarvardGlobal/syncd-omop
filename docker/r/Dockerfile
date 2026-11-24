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

WORKDIR /work