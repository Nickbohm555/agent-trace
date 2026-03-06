#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

APP_URL="${1:-http://localhost:5174}"

echo "Starting agent-trace services (db, backend, frontend)..."
docker compose up -d db backend frontend

echo "Waiting for backend docs at http://localhost:8001/docs ..."
for _ in $(seq 1 30); do
  if curl -fsS "http://localhost:8001/docs" >/dev/null 2>&1; then
    echo "Backend is reachable."
    break
  fi
  sleep 1
done

if docker compose ps --services --filter status=running | grep -qx chrome; then
  echo "Stopping docker chrome service to free port 9223..."
  docker compose stop chrome >/dev/null
fi

echo "Launching local Chrome DevTools on ${APP_URL} ..."
./launch-devtools.sh "${APP_URL}"
