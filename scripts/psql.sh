#!/usr/bin/env bash
# =============================================================================
# scripts/psql.sh - psql, pointed at the OMOP database configured in .env
# =============================================================================
#
# A thin wrapper so the SQL steps don't need a database name, user, or install
# path typed out (or written into docs). It loads .env through scripts/lib/env.sh,
# maps OMOP_DB_* onto libpq's PG* variables, and hands every argument to psql.
#
# Usage (from anywhere):
#   scripts/psql.sh                                          # interactive session
#   scripts/psql.sh -f scripts/06b_fix_screening_scores.sql  # run a file
#   scripts/psql.sh -c 'SELECT count(*) FROM cdm.person'     # one query
#   OMOP_DB_NAME=synthetic_concurrent scripts/psql.sh        # other dataset, one run
#
# Or inside the container (no psql needed on the host):
#   docker compose run --rm r scripts/psql.sh -f omop_tools/sql/02_study_cohorts.sql
#
# ON_ERROR_STOP=1 makes a failing statement in a -f file stop the run with a non-zero
# exit code, instead of carrying on and reporting success.
#
# @see scripts/lib/env.sh
# @see https://www.postgresql.org/docs/16/app-psql.html
# =============================================================================
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=lib/env.sh
source "$(dirname "$0")/lib/env.sh"

omop_pg_env
exec "$(find_psql)" -v ON_ERROR_STOP=1 "$@"
