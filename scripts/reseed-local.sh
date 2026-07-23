#!/usr/bin/env bash
# Stage P2 Track F [DEVIATED - see DEVIATIONS.md #DEV-065]: the ONLY sanctioned way to re-seed
# entities/relationships/variant_claims/myths/entity_aliases from V10-V17 (e.g. after a
# reversed-edge fix at the candidate-JSON layer, docs/TODO-phase2-stage-p2.md Track I) without
# dropping `narrative_chunks` — its pgvector embeddings cost real OpenAI API calls to regenerate.
# NEVER use `docker compose down -v` for this: it drops the whole volume, chunks included.
#
# Shared-environment guard (the Flyway checksum trap, §8 / cross-referenced from the P3
# ingredient/audit README): regenerating an *already-applied* V10-V12 changes those migrations'
# checksums and breaks `flyway validate` for anyone else pointed at the same database. This
# script refuses to run unless it's told this is a local-only DB.
#
# Usage (mirrors scripts/run-local.sh's repo-root/.env bootstrap style):
#   scripts/reseed-local.sh --check              # print the SQL/steps without touching anything
#   scripts/reseed-local.sh --local-only          # actually reseed
#   ALLOW_RESEED=1 scripts/reseed-local.sh        # same, via env var instead of a flag
#
# What it does: drop+truncate the V10-V14 seed tables (never narrative_chunks) -> delete
# V10-V17 from flyway_schema_history -> start core-api so Flyway re-applies V10-V17 (+ anything
# newer) and the afterMigrate callback re-grants zeus_app -> print a row-count sanity check.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CHECK_ONLY=false
ALLOW=false
for arg in "$@"; do
  case "$arg" in
    --check|--dry-run) CHECK_ONLY=true ;;
    --local-only) ALLOW=true ;;
    -h|--help)
      echo "Usage: $0 [--check|--dry-run] [--local-only]"
      echo "  --check|--dry-run  print the SQL/steps without executing anything"
      echo "  --local-only       confirm this is a local-only DB (or set ALLOW_RESEED=1)"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg (see --help)" >&2
      exit 1
      ;;
  esac
done
if [ "${ALLOW_RESEED:-0}" = "1" ]; then
  ALLOW=true
fi

# --- F2-F4: the reset SQL, defined once so --check and the real run share one source of truth ---
# relation_aliases (V17, Track F/ADR-019/DEV-072) joined the drop/clear lists here: without it,
# clearing 10-16's history while 17 stays applied leaves Flyway seeing an out-of-order state
# (a higher version already applied while lower versions are pending) and it refuses to migrate
# (`Detected resolved migration not applied to database: 10` etc.) -- discovered live during the
# Track I first pass landing relation_aliases (see docs/DEVIATIONS.md).
DROP_ALIASES_SQL="DROP TABLE IF EXISTS entity_aliases; DROP TABLE IF EXISTS relation_aliases;"
TRUNCATE_SQL="TRUNCATE myth_participants, variant_claims, relationships, myths, entities CASCADE;"
CLEAR_HISTORY_SQL="DELETE FROM flyway_schema_history WHERE version IN ('10','11','12','13','14','15','16','17');"

if [ "$CHECK_ONLY" = true ]; then
  echo "==> --check: printing the reset steps, nothing will be executed"
  echo
  echo "1) As the Flyway superuser (POSTGRES_USER, not zeus_app), against the Postgres container:"
  echo "     $DROP_ALIASES_SQL"
  echo "     $TRUNCATE_SQL"
  echo "     $CLEAR_HISTORY_SQL"
  echo "   narrative_chunks is NOT touched (no entity FK; embeddings preserved)."
  echo "2) Start core-api -- Flyway re-applies V10-V17 (+ anything newer); afterMigrate re-grants zeus_app."
  echo "3) Print row counts for entities, relationships, variant_claims, narrative_chunks."
  exit 0
fi

# --- F6: shared-environment guard ---
if [ "$ALLOW" != true ]; then
  cat >&2 <<'EOF'
ERROR: refusing to reseed without explicit local-only confirmation.

Regenerating an already-applied V10-V12 changes those migrations' checksums -- if this
Postgres is shared (a demo/staging DB, not your own local docker-compose instance), this
breaks `flyway validate` for everyone else pointed at it. See docs/TODO-phase2-stage-p2.md
Track F6 and ingestion/audit/README.md.

Re-run with --local-only, or set ALLOW_RESEED=1, once you've confirmed this is your own
local DB.
EOF
  exit 1
fi

# --- F1: preconditions ---
echo "==> Checking preconditions"

if lsof -i :8080 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ERROR: something is already listening on :8080 -- stop core-api before reseeding" >&2
  echo "       (Flyway DDL and a live app querying the same tables don't mix)." >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo "ERROR: .env not found at repo root." >&2
  echo "Run: cp .env.example .env   then fill in credentials." >&2
  exit 1
fi

echo "==> Loading .env"
set -a
# shellcheck disable=SC1091
source .env
set +a

missing=()
for var in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB LLM_API_KEY OPENAI_API_KEY LLM_CHAT_MODEL; do
  if [ -z "${!var:-}" ]; then
    missing+=("$var")
  fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "ERROR: .env is missing required value(s): ${missing[*]}" >&2
  exit 1
fi

if [ "$POSTGRES_USER" = "zeus_app" ]; then
  echo "ERROR: POSTGRES_USER resolves to the read-only runtime user (zeus_app)." >&2
  echo "       Flyway DDL needs the superuser (zeus/olympus) -- check .env." >&2
  exit 1
fi

if ! docker inspect -f '{{.State.Health.Status}}' blame-zeus-postgres-1 2>/dev/null | grep -q healthy; then
  echo "ERROR: blame-zeus-postgres-1 isn't up/healthy -- run 'docker-compose up -d' first." >&2
  exit 1
fi

PSQL=(docker exec -i blame-zeus-postgres-1 psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB")

# --- F2-F4: the actual reset, as the Flyway superuser ---
echo "==> Resetting V10-V14 seed tables (narrative_chunks left untouched)"
echo "    $DROP_ALIASES_SQL"
echo "    $TRUNCATE_SQL"
echo "    $CLEAR_HISTORY_SQL"
"${PSQL[@]}" -c "$DROP_ALIASES_SQL" -c "$TRUNCATE_SQL" -c "$CLEAR_HISTORY_SQL"

# --- F5: restart the app so Flyway re-applies V10-V17 ---
BOOT_LOG="$REPO_ROOT/core-api/build/reseed-bootrun.log"
mkdir -p "$(dirname "$BOOT_LOG")"
: > "$BOOT_LOG"

echo "==> Starting core-api (./gradlew :core-api:bootRun) to re-apply V10-V17"
nohup ./gradlew :core-api:bootRun >"$BOOT_LOG" 2>&1 &
BOOT_PID=$!

echo "==> Waiting for Flyway migration + app startup (log: $BOOT_LOG)"
attempts=0
until grep -qE "Started CoreApiApplication|APPLICATION FAILED TO START|BUILD FAILED" "$BOOT_LOG" 2>/dev/null; do
  if ! kill -0 "$BOOT_PID" 2>/dev/null; then
    echo "ERROR: core-api process exited before starting up -- see $BOOT_LOG" >&2
    exit 1
  fi
  attempts=$((attempts + 1))
  if [ "$attempts" -gt 120 ]; then
    echo "ERROR: timed out waiting for core-api to start -- see $BOOT_LOG" >&2
    exit 1
  fi
  sleep 1
done

if ! grep -q "Started CoreApiApplication" "$BOOT_LOG"; then
  echo "ERROR: core-api failed to start -- see $BOOT_LOG" >&2
  tail -n 40 "$BOOT_LOG" >&2
  exit 1
fi

echo "==> core-api is up (pid $BOOT_PID)"

# --- F5: row-count sanity print ---
echo "==> Row-count sanity check"
"${PSQL[@]}" -tAc "
  SELECT 'entities: ' || count(*) FROM entities
  UNION ALL SELECT 'relationships: ' || count(*) FROM relationships
  UNION ALL SELECT 'variant_claims: ' || count(*) FROM variant_claims
  UNION ALL SELECT 'narrative_chunks: ' || count(*) FROM narrative_chunks;
"

echo
echo "==> reseed complete — embeddings preserved"
echo "    core-api is running in the background (pid $BOOT_PID); logs: $BOOT_LOG"
echo "    Stop it with: kill $BOOT_PID"
