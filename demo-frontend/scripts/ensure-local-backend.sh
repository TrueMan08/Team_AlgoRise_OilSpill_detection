#!/usr/bin/env bash
# Inspect port 8000 and start OilTrace FastAPI from a sibling backend repo
# when it is not already healthy. Does not kill unrelated listeners unless
# REPLACE_PORT_8000=1.

set -euo pipefail

PORT="${OILTRACE_BACKEND_PORT:-8000}"
HEALTH="http://127.0.0.1:${PORT}/api/v1/health"

listen_pids() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -nP -iTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true
    return
  fi
  ss -lptn "sport = :${PORT}" 2>/dev/null | sed -n 's/.*pid=\([0-9]*\).*/\1/p' || true
}

print_listener() {
  local pid="$1"
  echo "PID ${pid}"
  ps -p "${pid}" -o pid=,user=,args= 2>/dev/null || true
  if [[ -r "/proc/${pid}/cwd" ]]; then
    echo "cwd $(readlink -f "/proc/${pid}/cwd" 2>/dev/null || true)"
  fi
}

if curl -sf --max-time 3 "${HEALTH}" >/tmp/oiltrace-health.json; then
  echo "Port ${PORT} already serves a healthy /api/v1/health — leaving it running."
  cat /tmp/oiltrace-health.json
  echo
  listen_pids | while read -r pid; do
    [[ -n "${pid}" ]] && print_listener "${pid}"
  done
  exit 0
fi

PIDS="$(listen_pids | tr '\n' ' ')"
if [[ -n "${PIDS// }" ]]; then
  echo "Port ${PORT} is occupied but health is not OK."
  for pid in ${PIDS}; do
    print_listener "${pid}"
    CMD="$(ps -p "${pid}" -o args= 2>/dev/null || true)"
    CWD="$(readlink -f "/proc/${pid}/cwd" 2>/dev/null || true)"
    if echo "${CMD}" | grep -Eq "uvicorn|app.main:app" && [[ -f "${CWD}/app/main.py" ]]; then
      echo "Listener looks like OilTrace uvicorn from ${CWD}, but /health failed. Not killing it."
      exit 1
    fi
  done
  if [[ "${REPLACE_PORT_8000:-}" == "1" ]]; then
    echo "REPLACE_PORT_8000=1 — stopping non-OilTrace listener(s)."
    for pid in ${PIDS}; do
      kill "${pid}" 2>/dev/null || true
    done
    sleep 1
  else
    echo "Not killing unrelated process(es). Re-run with REPLACE_PORT_8000=1 if this port should host OilTrace."
    exit 1
  fi
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CANDIDATES=(
  "${OILTRACE_BACKEND:-}"
  "${ROOT}/../oiltrace-backend"
  "${ROOT}/../oil-trace-backend"
  "${ROOT}/../OilTrace"
  "${ROOT}/../oiltrace"
  "${ROOT}/backend"
)

BACKEND=""
for dir in "${CANDIDATES[@]}"; do
  [[ -z "${dir}" ]] && continue
  if [[ -f "${dir}/app/main.py" ]]; then
    BACKEND="$(cd "${dir}" && pwd)"
    break
  fi
done

if [[ -z "${BACKEND}" ]]; then
  echo "No OilTrace FastAPI repo found (looked for app/main.py next to this frontend)."
  echo "This frontend workspace cannot start uvicorn by itself."
  echo "From the backend repo run:"
  echo "  python3 -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --reload"
  exit 2
fi

echo "Starting OilTrace backend from ${BACKEND}"
cd "${BACKEND}"
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --reload
