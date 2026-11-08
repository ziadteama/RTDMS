#!/usr/bin/env bash
# One-time Pi Bluetooth setup so a Garmin watch can find the RR receiver (needs sudo):
#   - LE-only controller (ControllerMode = le): advertising Flags 0x06, the form Garmin scans report
#   - advertise every 100-150 ms instead of the 1.28 s kernel default
#     (main.conf units are 0.625 ms: 160 = 100 ms, 240 = 150 ms)
# Classic Bluetooth (speakers, headsets) is switched off; RTDMS does not use it.
# The original file is kept at /etc/bluetooth/main.conf.rtdms-backup; to undo:
#   sudo cp /etc/bluetooth/main.conf.rtdms-backup /etc/bluetooth/main.conf
#   sudo systemctl restart bluetooth
set -e
CONF=/etc/bluetooth/main.conf
sudo cp -n "$CONF" "$CONF.rtdms-backup"
sudo sed -i \
  -e 's/^#\?ControllerMode *=.*/ControllerMode = le/' \
  -e 's/^#\?MinAdvertisementInterval *=.*/MinAdvertisementInterval=160/' \
  -e 's/^#\?MaxAdvertisementInterval *=.*/MaxAdvertisementInterval=240/' \
  "$CONF"
echo "--- changed lines:"
grep -n -E '^(ControllerMode|MinAdvertisementInterval|MaxAdvertisementInterval)' "$CONF"
sudo systemctl restart bluetooth
sleep 3
bluetoothctl show | grep -E 'Powered|Roles' | head -3
