#!/usr/bin/env bash
# Install the relay as a systemd USER service (restarts on crash, starts at boot with linger).
# Run on the machine that holds ~/RTDMS-coord/relay-data/relay.env. Safe to re-run.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
unit="$HOME/.config/systemd/user/rtdms-relay.service"
env_file="$HOME/RTDMS-coord/relay-data/relay.env"

[ -f "$env_file" ] || { echo "missing $env_file (RELAY_API_KEY, RELAY_AUTH_DIR, ...)" >&2; exit 1; }
[ -d "$here/../node_modules" ] || { echo "run 'npm ci' in relay/ first" >&2; exit 1; }

mkdir -p "$(dirname "$unit")"
install -m 0644 "$here/rtdms-relay.service" "$unit"
systemctl --user daemon-reload
systemctl --user enable rtdms-relay >/dev/null

# Two relays on one WhatsApp session fight each other: stop a hand-started one first.
old="$(ss -ltnp 2>/dev/null | awk '/:8088 /{print}' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2 || true)"
if [ -n "${old:-}" ] && ! systemctl --user is-active --quiet rtdms-relay; then
  echo "stopping the hand-started relay (pid $old)"
  kill "$old"
  for _ in $(seq 1 20); do kill -0 "$old" 2>/dev/null || break; sleep 0.5; done
fi
systemctl --user restart rtdms-relay

if [ "$(loginctl show-user "$USER" -p Linger --value)" != yes ]; then
  echo "NOTE: starts at boot only after:  sudo loginctl enable-linger $USER"
fi
systemctl --user --no-pager status rtdms-relay | head -6
