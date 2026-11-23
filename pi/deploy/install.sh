#!/usr/bin/env bash
# Idempotent installer, run ON the Pi as the normal user (deploy.sh --install does it for you).
# Safe to re-run: it only changes what differs, and restarts the runtime only if its unit changed.
#   install.sh [--open | --secure] [--no-system] [--dry-run] [--uninstall]
#   --open       DEV: drop-in RTDMS_BLE_OPEN=1 (no BLE token, anyone in range can connect)
#   --secure     (default) token mode; removes the open drop-in
#   --no-system  skip the steps that need sudo (BLE controller config, journald, linger)
#   --uninstall  remove the units and drop-ins (leaves venv, code and system config alone)
# sudo: uses SUDO_ASKPASS if set, else plain sudo. Never touches eth0, tailscale0 or Wi-Fi.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
CONF_DIR="$HOME/.config/rtdms"
VENV="$HOME/rtdms/.venv"
STAMP="$(date +%Y%m%d-%H%M%S)"
MODE=secure SYSTEM=1 DRY=0 UNINSTALL=0 CHANGED=0
for a in "$@"; do
  case "$a" in
    --open) MODE=open ;;
    --secure) MODE=secure ;;
    --no-system) SYSTEM=0 ;;
    --dry-run) DRY=1 ;;
    --uninstall) UNINSTALL=1 ;;
    *) echo "usage: $0 [--open|--secure] [--no-system] [--dry-run] [--uninstall]" >&2; exit 2 ;;
  esac
done
say() { echo "install: $*"; }
run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else "$@"; fi; }
SUDO=(sudo); [ -n "${SUDO_ASKPASS:-}" ] && SUDO=(sudo -A)
as_root() { run "${SUDO[@]}" "$@"; }
# put SRC DEST [sudo]: copy only when different; sets CHANGED
put() {
  local src="$1" dest="$2" root="${3:-}"
  if [ -f "$dest" ] && cmp -s "$src" "$dest"; then return 0; fi
  say "update $dest"; CHANGED=1
  if [ "$root" = sudo ]; then as_root install -D -m 644 "$src" "$dest"
  else run install -D -m 644 "$src" "$dest"; fi
}

if [ "$UNINSTALL" = 1 ]; then
  run systemctl --user disable --now rtdms-ready.service rtdms-pi-user.service || true
  run rm -f "$UNIT_DIR/rtdms-ready.service" "$UNIT_DIR/rtdms-pi-user.service"
  run rm -rf "$UNIT_DIR/rtdms-pi-user.service.d"
  run systemctl --user daemon-reload
  say "units removed (code, venv, BLE and journald config left in place)"
  exit 0
fi

# 1. prerequisites -----------------------------------------------------------------------------
[ -x "$VENV/bin/python" ] || { echo "install: $VENV missing: run ~/rtdms/install.sh (vision stack, offline wheels) first" >&2; exit 1; }
for d in pi fusion models/physiology contracts; do
  [ -d "$HOME/rtdms-pi/$d" ] || { echo "install: ~/rtdms-pi/$d missing: run deploy.sh first" >&2; exit 1; }
done

# 2. python packages (only when an import fails) ------------------------------------------------
if ! "$VENV/bin/python" -c 'import bless, bleak, dbus_fast, scipy, qrcode, rtdms_pi, dms_fusion, dms_physiology' 2>/dev/null; then
  say "installing runtime packages into $VENV"
  grep -vE '^\s*(#|$)' "$HERE/pi-extras.txt" | run xargs "$VENV/bin/pip" install --no-deps -q
  for p in fusion models/physiology pi; do run "$VENV/bin/pip" install --no-deps -q -e "$HOME/rtdms-pi/$p"; done
fi

# 3. vision sources are reached through the repo layout ------------------------------------------
if [ ! -e "$HOME/rtdms-pi/models/distraction" ]; then
  say "symlink models/distraction -> ~/rtdms/distraction"
  run ln -s "$HOME/rtdms/distraction" "$HOME/rtdms-pi/models/distraction"
fi

# 4. user units and drop-ins -----------------------------------------------------------------------
run mkdir -p "$CONF_DIR/backup" "$UNIT_DIR"
for u in rtdms-pi-user.service rtdms-ready.service; do put "$HERE/systemd/$u" "$UNIT_DIR/$u"; done
D="$UNIT_DIR/rtdms-pi-user.service.d"
# the hand-made camera.conf of 2026-11-23 is now part of the base unit
if [ -f "$D/camera.conf" ]; then
  say "retire hand-made camera.conf (saved in $CONF_DIR/backup)"; CHANGED=1
  run mv "$D/camera.conf" "$CONF_DIR/backup/camera.conf.$STAMP"
fi
if [ "$MODE" = open ]; then
  tmp="$(mktemp)"; printf '[Service]\nEnvironment=RTDMS_BLE_OPEN=1\n' >"$tmp"
  put "$tmp" "$D/open.conf"; rm -f "$tmp"
  say "WARNING: BLE OPEN mode (dev only): no token, anyone in Bluetooth range can connect"
elif [ -f "$D/open.conf" ]; then
  say "remove open.conf (token mode)"; CHANGED=1; run rm -f "$D/open.conf"
fi
if [ ! -f "$CONF_DIR/deploy.env" ]; then
  say "create $CONF_DIR/deploy.env (site settings, never overwritten)"
  if [ "$DRY" = 0 ]; then
    printf '# RTDMS site settings, read by rtdms-pi-user.service\nRTDMS_ROTATE=180\n# extra rtdms-pi flags, e.g. --buzzer gpio\nRTDMS_EXTRA_ARGS=\n' >"$CONF_DIR/deploy.env"
  fi
  CHANGED=1
fi
put "$HERE/system/90-rtdms-no-ble-midi.conf" "$HOME/.config/wireplumber/wireplumber.conf.d/90-rtdms-no-ble-midi.conf"

# 5. system settings (sudo) --------------------------------------------------------------------------
if [ "$SYSTEM" = 1 ]; then
  BT=/etc/bluetooth/main.conf
  if ! grep -q '^ControllerMode *= *le' "$BT" || ! grep -q '^MinAdvertisementInterval *= *160' "$BT" \
     || ! grep -q '^MaxAdvertisementInterval *= *240' "$BT"; then
    say "BLE controller config (LE only, 100-150 ms advertising); restarts bluetoothd (backup main.conf.rtdms-backup)"
    as_root cp -n "$BT" "$BT.rtdms-backup"
    as_root sed -i -e 's/^#\?ControllerMode *=.*/ControllerMode = le/' \
      -e 's/^#\?MinAdvertisementInterval *=.*/MinAdvertisementInterval=160/' \
      -e 's/^#\?MaxAdvertisementInterval *=.*/MaxAdvertisementInterval=240/' "$BT"
    as_root systemctl restart bluetooth
  fi
  J=/etc/systemd/journald.conf.d/rtdms.conf
  if [ ! -f "$J" ] || ! cmp -s "$HERE/system/journald-rtdms.conf" "$J"; then
    say "persistent journal"
    as_root install -D -m 644 "$HERE/system/journald-rtdms.conf" "$J"
    as_root mkdir -p /var/log/journal
    as_root systemctl restart systemd-journald
  fi
  if ! loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q 'Linger=yes'; then
    say "enable linger (user services start at boot without a login)"
    as_root loginctl enable-linger "$USER"
  fi
else
  say "skipping system steps (--no-system)"
fi

# 6. activate ----------------------------------------------------------------------------------------
run systemctl --user daemon-reload
# one process may own the camera: the old stand-alone camera service stays off
if systemctl --user is-enabled rtdms-camera.service >/dev/null 2>&1; then
  say "disable old rtdms-camera.service (it would fight for the camera)"
  run systemctl --user disable --now rtdms-camera.service
fi
run systemctl --user enable rtdms-pi-user.service rtdms-ready.service
if [ "$CHANGED" = 1 ] || ! systemctl --user is-active --quiet rtdms-pi-user.service; then
  say "restarting rtdms-pi-user"
  run systemctl --user restart rtdms-pi-user.service
else
  say "nothing changed: runtime left running"
fi
run systemctl --user restart rtdms-ready.service --no-block
say "done (mode: $MODE). Verify with: $HERE/check.sh --wait 60"
