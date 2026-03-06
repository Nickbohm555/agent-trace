#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-9223}"
APP_URL="${1:-${APP_URL:-http://localhost:5174}}"
TARGET="${2:-${TARGET:-chrome}}"
ENDPOINT="http://127.0.0.1:${PORT}/json/list"

if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port ${PORT} is already in use. Stop the current listener first (for example: docker compose stop chrome)."
  exit 1
fi

launch_chrome() {
  local profile_dir="${CHROME_PROFILE_DIR:-$HOME/.chrome-devtools-codex}"
  mkdir -p "$profile_dir"

  if [ -x "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary" ]; then
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary" \
      --remote-debugging-port="${PORT}" \
      --user-data-dir="$profile_dir" \
      "$APP_URL" >/dev/null 2>&1 &
    return
  fi

  if [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
      --remote-debugging-port="${PORT}" \
      --user-data-dir="$profile_dir" \
      "$APP_URL" >/dev/null 2>&1 &
    return
  fi

  echo "Chrome binary not found. Install Chrome/Canary or set up Electron mode."
  exit 1
}

launch_electron() {
  local electron_bin="${ELECTRON_BIN:-}"
  local electron_app="${ELECTRON_APP:-}"

  if [ -z "$electron_bin" ] && command -v electron >/dev/null 2>&1; then
    electron_bin="$(command -v electron)"
  fi

  if [ -z "$electron_bin" ] || [ -z "$electron_app" ]; then
    echo "Electron mode requires ELECTRON_APP and (optionally) ELECTRON_BIN."
    echo "Example: ELECTRON_APP=./desktop ELECTRON_BIN=./node_modules/.bin/electron ./launch-devtools.sh http://localhost:5174 electron"
    exit 1
  fi

  "$electron_bin" --remote-debugging-port="${PORT}" "$electron_app" "$APP_URL" >/dev/null 2>&1 &
}

case "$TARGET" in
  chrome)
    launch_chrome
    ;;
  electron)
    launch_electron
    ;;
  *)
    echo "Unknown target '$TARGET'. Use 'chrome' or 'electron'."
    exit 1
    ;;
esac

wait_for_endpoint() {
  local attempts="${1:-10}"
  local delay="${2:-1}"
  local i
  for i in $(seq 1 "${attempts}"); do
    if curl -fsS "$ENDPOINT" >/dev/null 2>&1; then
      return 0
    fi
    sleep "${delay}"
  done
  return 1
}

wait_for_endpoint 10 1 || true

echo "App URL: ${APP_URL}"
echo "DevTools endpoint: ${ENDPOINT}"

if command -v curl >/dev/null 2>&1; then
  echo "\nCurrent targets:"
  if ! curl -fsS "$ENDPOINT"; then
    echo "Unable to reach DevTools endpoint yet: ${ENDPOINT}"
  fi
fi
