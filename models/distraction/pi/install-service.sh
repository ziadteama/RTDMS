#!/usr/bin/env bash
# Run once on the Pi as the normal user (not root). Makes the camera server start at every boot
# and restart itself if it crashes. Undo: systemctl --user disable --now rtdms-camera
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.config/systemd/user"
cp "$HERE/rtdms-camera.service" "$HOME/.config/systemd/user/rtdms-camera.service"
chmod +x "$HOME/rtdms/start_stream.sh" 2>/dev/null || true
# stop a hand-started copy so the service owns port 8080 (bracket keeps this grep from matching itself)
pkill -f "[s]cripts/stream.py" 2>/dev/null || true
sleep 1
systemctl --user daemon-reload
systemctl --user enable --now rtdms-camera.service
# user services run at boot without a login only with lingering on
sudo loginctl enable-linger "$USER"
# the Tailscale link the app uses must also come up on boot
sudo systemctl enable --now tailscaled
sleep 5
systemctl --user --no-pager status rtdms-camera.service | head -n 8
curl -s -m 5 -o /dev/null -w "status endpoint: HTTP %{http_code}\n" http://localhost:8080/status
