#!/usr/bin/env bash
# Bootstraps core-api for local development: starts Postgres, loads .env, and runs bootRun.
# Mirrors README.md "Running Locally" steps 1 + 3 (step 2, ingestion, is a separate one-time
# job — this script does not run it, it only warns if the DB looks unseeded).
#
# Usage: scripts/run-local.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Starting Postgres (docker-compose up -d)"
docker-compose up -d

echo "==> Waiting for Postgres to be healthy"
until [ "$(docker inspect -f '{{.State.Health.Status}}' blame-zeus-postgres-1 2>/dev/null)" = "healthy" ]; do
  sleep 1
  printf '.'
done
echo " ready"

if [ ! -f .env ]; then
  echo "ERROR: .env not found at repo root." >&2
  echo "Run: cp .env.example .env   then fill in LLM_API_KEY / OPENAI_API_KEY / LLM_CHAT_MODEL." >&2
  exit 1
fi

echo "==> Loading .env"
set -a
# shellcheck disable=SC1091
source .env
set +a

missing=()
for var in LLM_API_KEY OPENAI_API_KEY LLM_CHAT_MODEL; do
  if [ -z "${!var:-}" ]; then
    missing+=("$var")
  fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "ERROR: .env is missing required value(s): ${missing[*]}" >&2
  exit 1
fi

echo "==> Checking whether the DB is seeded"
chunk_count="$(docker exec blame-zeus-postgres-1 psql -U "${POSTGRES_USER:-zeus}" -d "${POSTGRES_DB:-blamezeus}" -tAc \
  "SELECT count(*) FROM narrative_chunks" 2>/dev/null || echo 0)"
if [ "$chunk_count" -eq 0 ] 2>/dev/null; then
  echo "WARNING: narrative_chunks is empty — RAG/MIXED questions will return no results."
  echo "         Run ingestion first: cd ingestion && python main.py"
else
  echo "    $chunk_count narrative_chunks rows found."
fi

echo "==> Starting core-api (./gradlew :core-api:bootRun)"
echo "    Web UI:  http://localhost:8080/"
echo "    Swagger: http://localhost:8080/swagger-ui.html"
exec ./gradlew :core-api:bootRun
