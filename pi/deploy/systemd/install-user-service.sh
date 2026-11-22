#!/usr/bin/env bash
# Run once on the Pi as the normal user (NOT root, no sudo).
#   install-user-service.sh [--dry-run] [--uninstall] [--open]
#   --open  DEV ONLY: drop-in with RTDMS_BLE_OPEN=1 (no BLE token; anyone in range can connect).
#           Without --open any existing drop-in is removed (token mode, the default).
# Env: RTDMS_UNIT_DIR overrides the unit directory (default ~/.config/systemd/user).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
UNIT=rtdms-pi-user.service
UNIT_DIR="${RTDMS_UNIT_DIR:-$HOME/.config/systemd/user}"
DROPIN_DIR="$UNIT_DIR/$UNIT.d"
DRY=0
UNINSTALL=0
OPEN=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --open) OPEN=1 ;;
    *) echo "usage: $0 [--dry-run] [--uninstall] [--open]" >&2; exit 2 ;;
  esac
done

run() {
  if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else "$@"; fi
}

if [ "$UNINSTALL" = 1 ]; then
  run systemctl --user disable --now "$UNIT" || true
  run rm -f "$UNIT_DIR/$UNIT"
  run rm -rf "$DROPIN_DIR"
  run systemctl --user daemon-reload
  exit 0
fi

run mkdir -p "$UNIT_DIR"
run cp "$HERE/$UNIT" "$UNIT_DIR/$UNIT"
if [ "$OPEN" = 1 ]; then
  run mkdir -p "$DROPIN_DIR"
  if [ "$DRY" = 1 ]; then
    echo "[dry-run] write $DROPIN_DIR/open.conf"
  else
    printf '[Service]\nEnvironment=RTDMS_BLE_OPEN=1\n' > "$DROPIN_DIR/open.conf"
  fi
  echo "WARNING: BLE open mode (dev only): no token required, anyone in Bluetooth range can connect"
else
  run rm -rf "$DROPIN_DIR"
fi
run systemctl --user daemon-reload
run systemctl --user enable --now "$UNIT"
# a restart is needed when the unit was already running and only the drop-in changed
run systemctl --user restart "$UNIT"

# user services start at boot without a login only with lingering on; hint only, never enable it
if command -v loginctl >/dev/null 2>&1; then
  if ! loginctl show-user "${USER:-$(id -un)}" -p Linger 2>/dev/null | grep -q 'Linger=yes'; then
    echo "hint: linger is off; to start at boot without a login run: sudo loginctl enable-linger \$USER"
  fi
fi

if [ "$DRY" = 0 ]; then
  sleep 2
  systemctl --user --no-pager status "$UNIT" | head -n 8 || true
  ss -ltn 2>/dev/null | grep ':8090' || echo "port 8090 not listening yet"
fi
