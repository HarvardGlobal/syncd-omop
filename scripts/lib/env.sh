# shellcheck shell=bash
# =============================================================================
# scripts/lib/env.sh - shared settings loader for the SYNCD bash scripts
# =============================================================================
#
# The bash counterpart of scripts/lib/env.R. Source it near the top of a script:
#
#   source "$(dirname "$0")/lib/env.sh"
#
# It loads `.env` from the repo root (git-ignored; see .env.example) and provides
# small helpers so scripts don't hardcode database names, users, or macOS-only
# paths and commands.
#
# Precedence, highest first:
#   1. Variables already in the environment (docker compose `env_file`, or a
#      one-off `VAR=value scripts/...` on the command line)
#   2. Values in `.env`
#   3. Generic defaults (host `localhost`, port `5432` only)
#
# @see scripts/lib/env.R
# @see .env.example
# =============================================================================

# Repo root, resolved from this file's location so callers can run from anywhere.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PROJECT_ROOT

##
# Load KEY=value pairs from a .env file into the environment.
#
# The file is parsed as data, never `source`d, so nothing in it can run as a
# command. (Sourcing would also die on `UID=1000`, because UID is readonly in
# bash; here it's simply skipped, as it's already set.) Same rules as load_dotenv() in env.R: comments and blank lines are
# skipped, a leading `export ` is ignored, surrounding quotes are removed, and a
# trailing ` # comment` on an unquoted value is dropped. Variables that are
# already set are left alone.
#
# @param $1 Path to the .env file (default: $PROJECT_ROOT/.env)
# @return 0 always; a missing file is fine (Docker passes values via env_file)
##
load_dotenv() {
  local file="${1:-$PROJECT_ROOT/.env}" line key val
  [[ -f "$file" ]] || return 0

  # `|| [[ -n $line ]]` keeps the last line even if the file has no final newline.
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"                                   # Windows line endings
    line="${line#"${line%%[![:space:]]*}"}"                # trim leading space
    [[ -z "$line" || "$line" == \#* ]] && continue
    line="${line#export }"
    [[ "$line" == *=* ]] || continue

    key="${line%%=*}"; key="${key%"${key##*[![:space:]]}"}"
    val="${line#*=}";  val="${val#"${val%%[![:space:]]*}"}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue

    if [[ "$val" =~ ^\"(.*)\"$ || "$val" =~ ^\'(.*)\'$ ]]; then
      val="${BASH_REMATCH[1]}"                              # quoted: take literally
    else
      val="${val%%[[:space:]]#*}"                           # unquoted: drop comment
      val="${val%"${val##*[![:space:]]}"}"                  # trim trailing space
    fi

    # ${!key+x} is non-empty when the variable exists (even if empty): env wins.
    [[ -n "${!key+x}" ]] || export "$key=$val"
  done < "$file"
}

##
# Exit with one message listing every required variable that is unset.
#
# @param $@ Variable names that must be set (an empty value counts as set)
##
require_env() {
  local missing=() k
  for k in "$@"; do [[ -n "${!k+x}" ]] || missing+=("$k"); done
  if (( ${#missing[@]} )); then
    echo "Missing setting(s): ${missing[*]}" >&2
    echo "Add them to .env at the repo root (copy .env.example to start)." >&2
    exit 1
  fi
}

##
# Map the project's OMOP_DB_* settings onto libpq's PG* variables, so psql
# connects to the same database the R scripts use without the password being
# stored twice. Any PG* value already set is kept, as an explicit override.
#
# @see https://www.postgresql.org/docs/16/libpq-envars.html
##
omop_pg_env() {
  require_env OMOP_DB_NAME OMOP_DB_USER OMOP_DB_PASSWORD
  export PGHOST="${PGHOST:-${OMOP_DB_HOST:-localhost}}"
  export PGPORT="${PGPORT:-${OMOP_DB_PORT:-5432}}"
  export PGDATABASE="${PGDATABASE:-$OMOP_DB_NAME}"
  export PGUSER="${PGUSER:-$OMOP_DB_USER}"
  export PGPASSWORD="${PGPASSWORD:-$OMOP_DB_PASSWORD}"
}

##
# Print the path to psql: PSQL_BIN from .env if set, otherwise whatever is on
# PATH. Works with Linux packages, Homebrew, Postgres.app and the Docker image.
#
# @return 0 and the path on stdout, or exits 1 with a hint if psql is missing
##
find_psql() {
  local bin="${PSQL_BIN:-$(command -v psql || true)}"
  if [[ -z "$bin" || ! -x "$bin" ]]; then
    echo "psql not found. Install the PostgreSQL client, or set PSQL_BIN in .env." >&2
    exit 1
  fi
  printf '%s\n' "$bin"
}

##
# Fail fast, with a clear message, if the database can't be reached.
# Call after omop_pg_env, so psql already knows where to connect.
#
# @param $1 The psql command to test with (default: psql found by find_psql)
##
check_db() {
  local psql="${1:-$(find_psql)}"
  $psql -v ON_ERROR_STOP=1 -Atqc 'SELECT 1' >/dev/null 2>&1 || {
    echo "Can't reach database '$PGDATABASE' at $PGHOST:$PGPORT as $PGUSER." >&2
    echo "Is Postgres running, and are the OMOP_DB_* values in .env right?" >&2
    exit 1
  }
}

##
# Open a URL in the user's browser, on whichever platform this is.
# Degrades gracefully: on a headless machine or over SSH it does nothing, and
# the calling script's printed URL is still there to copy.
#
# @param $1 URL to open
##
open_url() {
  local url="$1" cmd
  for cmd in xdg-open open wslview; do                    # Linux, macOS, WSL
    if command -v "$cmd" >/dev/null 2>&1; then
      "$cmd" "$url" >/dev/null 2>&1 &
      return 0
    fi
  done
  return 0
}

# Load .env as soon as this file is sourced (path passed explicitly so the
# caller's own $1 is never mistaken for a .env path).
load_dotenv "$PROJECT_ROOT/.env"
