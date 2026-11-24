# Running the SYNCD R pipeline in Docker

The R-based steps of this pipeline (OMOP load, Ares/Achilles/DQD, TreatmentPatterns, CohortContrast and related tools) need R, a Java JDK, a Fortran toolchain and a long list of OHDSI packages. Installing those directly on a workstation adds about 400 MB of system packages and compiler tooling.

Instead, this repo includes a small container image that holds the whole R toolchain. Your scripts, data and outputs stay on your machine. The container just runs them.

> **Summary:** nothing about the pipeline itself changed. The same scripts run in the same order from the repo root; you prefix each command with `docker compose run --rm r`.

---

## What was added

```
.
├── compose.yml            # defines the "r" service (how the container runs)
├── docker/
│   └── r/
│       ├── Dockerfile     # the image: R + JDK + psql client
│       └── install.R      # installs every R package the scripts use
└── .env                   # database credentials (NOT committed)
```

| File | Purpose |
|---|---|
| `docker/r/Dockerfile` | Starts from `rocker/r-ver` (a slim Ubuntu with R that installs packages as prebuilt binaries), then adds a headless JDK (for JDBC/rJava) and `postgresql-client` (for `psql \copy` bulk loads). |
| `docker/r/install.R` | Installs the package list, trying CRAN first and falling back to GitHub. The build fails loudly if anything is missing. |
| `compose.yml` | Runs the container as your user, mounts the repo at `/work`, shares the host network, and loads `.env`. |
| `.env` | Database user and password for both R (`OMOP_DB_*`) and `psql` (`PG*`). |

### Why the Dockerfile lives in `docker/r/`

`docker build` first sends the entire build context to Docker. With the repo root as the context, that would include `source_data/athena_vocab`, which is several GB, on every build. Keeping the context to `docker/r/` means a build only sends two small files. Data is **mounted** at runtime, never copied into the image.

---

## Prerequisites

- Docker Engine with the Compose plugin (`docker compose version` should work)
- The OMOP Postgres container running and reachable at `localhost:5432`, with the `syncd_omop` database
- **Linux host.** The setup uses `network_mode: host`, which Docker Desktop on macOS and Windows doesn't support the same way. See *Notes* below.

The host does **not** need R, Java or Fortran. Installing `psql` on the host is optional; it's only for poking at the database by hand.

---

## Setup

### 1. Create `.env` at the repo root

Start from the template, then fill in your own values:

```bash
cp .env.example .env
chmod 600 .env
```

The required settings are:

```dotenv
OMOP_DB_HOST=localhost
OMOP_DB_PORT=5432
OMOP_DB_NAME=syncd_omop      # which dataset; see "Switching datasets" below
OMOP_DB_USER=postgres
OMOP_DB_PASSWORD=change-me
```

`.env` is the only place these live. The R scripts read them through `scripts/lib/env.R`, and the bash scripts read them through `scripts/lib/env.sh`, which also maps them onto `psql`'s `PG*` variables. So you write the password once. If a required setting is missing, the script stops and names it, rather than guessing a database.

**Switching datasets.** Several OMOP databases can share one Postgres server. Change `OMOP_DB_NAME` in `.env`, or override it for one run (a variable already set in your shell wins over `.env`):

```bash
docker compose run --rm -e OMOP_DB_NAME=synthetic_concurrent r Rscript scripts/07_run_ares.R
```

Make sure `.gitignore` contains:

```gitignore
.env
omop_load/jdbc/
```

### 2. Build the image

```bash
docker compose build r
```

The first build takes roughly 10–20 minutes, because the OHDSI packages and duckdb have a lot of dependencies. Later builds use the cache and are near-instant unless `install.R` changes.

### 3. Verify

Check that the packages load:

```bash
docker compose run --rm r Rscript -e 'for (p in c("ETLSyntheaBuilder","Achilles","AresIndexer","DataQualityDashboard","TreatmentPatterns","CohortContrast","CDMConnector","RPostgres")) { suppressPackageStartupMessages(library(p, character.only = TRUE)); cat("ok ", p, "\n") }'
```

Check that the database is reachable:

```bash
docker compose run --rm r psql -c 'SELECT current_database(), current_user;'
```

---

## Running the pipeline

Run every command from the **repo root**. The scripts build paths from `normalizePath(".")`, and the repo is mounted at `/work`, which is also the container's working directory.

```bash
# Load vocabulary CSVs (bash + psql)
docker compose run --rm r bash scripts/06a_load_vocab.sh source_data/athena_vocab

# OMOP ETL
docker compose run --rm r Rscript scripts/06_load_omop.R staging
docker compose run --rm r Rscript scripts/06_load_omop.R vocab_etl

# Achilles / DQD / Ares export
docker compose run --rm r Rscript scripts/07_run_ares.R

# Analysis tools
docker compose run --rm r Rscript omop_tools/scripts/run_treatmentpatterns.R
docker compose run --rm r Rscript omop_tools/scripts/run_cohortcontrast.R
docker compose run --rm r Rscript omop_tools/scripts/run_patientexplorer.R
```

To save typing, add this alias to your shell config:

```bash
alias omop-r='docker compose run --rm r'
# omop-r Rscript scripts/06_load_omop.R staging
```

### Still runs on the host (no R needed)

- `scripts/08_view_ares.sh`: only serves static files
- `omop_tools/journey_app`: Python
- Python steps `01`–`05`

---

## Script changes made for this setup

| Where | Change | Why |
|---|---|---|
| `scripts/lib/env.R`, `scripts/lib/env.sh` (new) | Shared loaders. They read `.env` as data (never executed), let real environment variables win, and stop with a list of any missing settings. | One place for settings; nothing person- or machine-specific in committed code. |
| `06_load_omop.R`, `07_run_ares.R` | Connection built by `omop_connection_details()` from `OMOP_DB_*`. No default database name or user. | Previously 06 and 07 had different hardcoded defaults and could silently read different databases. |
| `06_load_omop.R` | `POSTGRES_PATH` comes from the environment, then `PSQL_BIN`, then `psql` on `PATH` (Homebrew path removed). | DatabaseConnector bulk loads need the **directory** that contains `psql`. |
| `06a_load_vocab.sh` | `PG*` variables derived from `OMOP_DB_*`; `psql` found on `PATH` or `PSQL_BIN`. A `SELECT 1` check fails fast if the database is down. | Same database as the R scripts, no password on the command line, any OS. |
| `08_view_ares.sh` | Opens the browser with `xdg-open`, `open` or `wslview`, whichever exists; port from `ARES_PORT`. | macOS `open` was the only option before. |

---

## Notes and gotchas

**Host networking.** With `network_mode: host`, `localhost:5432` inside the container is the same address you use from your terminal, so no script needed a hostname change. On macOS or Windows, drop that line and set `OMOP_DB_HOST` to `host.docker.internal`, adding `extra_hosts: ["host.docker.internal:host-gateway"]` if needed.

**Why `\copy` works.** `\copy` reads files from wherever the `psql` *client* runs. Both `psql` and the mounted repo are inside the same container, so the CSV paths resolve. Running `psql` inside the *database* container with `docker exec` would **not** work, because that container can't see your files.

**Relative paths only.** Inside the container the repo is `/work`. Paths such as `./source_data/...` work; `/home/<you>/...` does not exist in there.

**File ownership.** The container runs as your UID/GID, so generated files (the JDBC jar, results, Ares exports) are owned by you, not root.

**CohortContrast DESCRIPTION patch.** The upstream `HealthInformaticsUT/CohortContrast` `DESCRIPTION` declares a dependency with a bare `=` operator, which `remotes` rejects (`Invalid comparison operator in dependency: =`). When that exact error occurs, `install.R` falls back to downloading the source, rewriting `(= ` to `(>= `, and installing the local copy. The build log prints the patched line (`>> Patched DESCRIPTION lines: ...`). If CohortContrast behaves oddly, that loosened version pin is the first suspect. Remove the workaround once upstream fixes it.

**Namespace warnings.** The AresIndexer `replacing previous import 'data.table::...' by 'dplyr::...'` messages during the build are harmless.

**GitHub rate limits.** Several `install_github` calls can exceed the unauthenticated limit of 60 requests per hour, which shows up as HTTP 403. To fix it, pass a no-scope token **at build time only**: add `args: [GITHUB_PAT]` under `build:` in `compose.yml` and `ARG GITHUB_PAT` before the install step in the Dockerfile, then run:

```bash
GITHUB_PAT=ghp_xxx docker compose build r
```

Never put the token in the Dockerfile itself.

**Reproducibility.** Pin the base image (e.g. `rocker/r-ver:4.4.2`) once a combination is known to work, so a future rebuild produces the same environment.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `could not connect to server` | The Postgres container isn't running, or `PG*` / `OMOP_DB_*` in `.env` are wrong |
| `password authentication failed` | The user or password doesn't match `POSTGRES_USER` / `POSTGRES_PASSWORD` in the database's compose file |
| `No such file or directory` on a CSV | An absolute host path was used; switch to a repo-relative path |
| `Permission denied` writing output | `UID`/`GID` in `.env` don't match `id -u` / `id -g` |
| HTTP 403 during build | GitHub rate limit; see the `GITHUB_PAT` note above |

---

## Cleanup

```bash
docker image rm syncd-omop-r     # remove the image
docker builder prune             # optionally reclaim build cache
```

Nothing was installed on the host, so there's nothing else to uninstall.
