#!/usr/bin/env bash
# Hardware verification runner for Raspberry Pi runtime (pi/).
#
# Usage:
#   RTDMS_PI_HOST=192.168.100.181 RTDMS_PI_USER=khalifa RTDMS_PI_KEY=~/.ssh/id_ed25519 ./verify_on_pi.sh [host]
#
# Syncs repository to the Pi, sets up venv, runs verification gates (pytest, ruff, mypy),
# runs rtdms-pi daemon for 10s to exercise health and status endpoints, and checks thermals/throttling.
set -euo pipefail

HOST="${1:-${RTDMS_PI_HOST:-}}"
USER_NAME="${RTDMS_PI_USER:-}"
KEY="${RTDMS_PI_KEY:-$HOME/.ssh/id_ed25519}"

if [[ -z "$HOST" ]]; then
  echo "Error: Host must be provided as first argument or via RTDMS_PI_HOST environment variable." >&2
  exit 1
fi

if [[ -z "$USER_NAME" ]]; then
  echo "Error: RTDMS_PI_USER environment variable must be set (e.g. export RTDMS_PI_USER=khalifa)." >&2
  exit 1
fi

if [[ ! -f "$KEY" ]]; then
  echo "Error: SSH private key not found at '$KEY'. Set RTDMS_PI_KEY to valid key path." >&2
  exit 1
fi

REMOTE="${USER_NAME}@${HOST}"
SSH=(ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=20 -o PasswordAuthentication=no "$REMOTE")
RSYNC_SSH="ssh -i $KEY -o BatchMode=yes -o ConnectTimeout=20 -o PasswordAuthentication=no"

echo "== Reachability check =="
"${SSH[@]}" "echo ok" >/dev/null 2>&1 || {
  echo "UNREACHABLE: Cannot connect to $REMOTE via SSH key $KEY." >&2
  exit 1
}
echo "Connected successfully to $HOST"

echo "== Pre-run status =="
"${SSH[@]}" "hostname; uname -m; python3 --version; \
  echo -n 'temp: '; vcgencmd measure_temp 2>/dev/null || echo 'N/A'; \
  echo -n 'throttled: '; vcgencmd get_throttled 2>/dev/null || echo 'N/A'"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "== Rsync repository to Pi =="
rsync -avz --delete -e "$RSYNC_SSH" \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='logs' \
  --exclude='spike_results' \
  "$REPO_ROOT/" "$REMOTE:~/rtdms_verify/"

echo "== Environment setup on Pi =="
"${SSH[@]}" "python3 -m venv --system-site-packages ~/rtdms_verify/venv && \
  ~/rtdms_verify/venv/bin/pip install --upgrade pip && \
  ~/rtdms_verify/venv/bin/pip install -e ~/rtdms_verify/fusion -e ~/rtdms_verify/models/physiology -e '~/rtdms_verify/pi[pi,ble,dev]'"

echo "== Running test and lint gates =="
"${SSH[@]}" "cd ~/rtdms_verify/pi && \
  export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 && \
  ~/rtdms_verify/venv/bin/pytest -v && \
  ~/rtdms_verify/venv/bin/ruff check . && \
  ~/rtdms_verify/venv/bin/mypy src"

echo "== Running 10s smoke daemon =="
"${SSH[@]}" "bash -c '
  export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
  ~/rtdms_verify/venv/bin/rtdms-pi --no-camera --buzzer none --port 8080 >/tmp/rtdms_smoke.log 2>&1 &
  PID=\$!
  sleep 2
  echo \"--- /health endpoint ---\"
  curl -s http://localhost:8080/health || echo \"curl /health failed\"
  echo
  echo \"--- /status endpoint ---\"
  curl -s http://localhost:8080/status || echo \"curl /status failed\"
  echo
  sleep 8
  kill \$PID 2>/dev/null || true
  wait \$PID 2>/dev/null || true
'"

echo "== Post-run status =="
"${SSH[@]}" "echo -n 'temp: '; vcgencmd measure_temp 2>/dev/null || echo 'N/A'; \
  echo -n 'throttled: '; vcgencmd get_throttled 2>/dev/null || echo 'N/A'"

echo "== Hardware verification completed successfully =="
