#!/usr/bin/env bash
# ExecStartPre of rtdms-pi-user: wait (default 60 s) until the Bluetooth adapter exists and is
# powered, then make it discoverable for the Garmin watch. Always exits 0: the runtime has its own
# retry, and a missing adapter must not stop the camera half of the product from starting.
# Only talks to bluez (bluetoothctl); never touches network interfaces.
LIMIT="${RTDMS_WAIT_BT_S:-60}"
log() { echo "wait-bluetooth: $*"; }

for ((i = 0; i < LIMIT; i++)); do
  if compgen -G '/sys/class/bluetooth/hci*' >/dev/null; then
    out="$(bluetoothctl show 2>/dev/null || true)"
    if grep -q 'Powered: yes' <<<"$out"; then
      # discoverable is cleared by a reboot; the watch scans for this unit
      bluetoothctl discoverable-timeout 0 >/dev/null 2>&1 || true
      bluetoothctl discoverable on >/dev/null 2>&1 || true
      bluetoothctl pairable on >/dev/null 2>&1 || true
      log "adapter powered after ${i}s"
      exit 0
    fi
    bluetoothctl power on >/dev/null 2>&1 || true
  fi
  sleep 1
done
log "WARNING: adapter not ready after ${LIMIT}s, starting anyway"
exit 0
