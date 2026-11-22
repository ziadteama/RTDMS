#!/usr/bin/env bash
# Re-link the relay's WhatsApp number after "whatsapp_logged_out" (401).
#   relink-whatsapp.sh start   back up the old session (renamed, NOT deleted), restart the service,
#                              then keep the newest pairing QR in relay-data/qr.txt until connected
#   relink-whatsapp.sh show    draw the newest QR in the terminal (WhatsApp rotates it about every 20-60 s)
# Scan with the relay's phone: WhatsApp > Linked devices > Link a device.
set -euo pipefail
data="$HOME/RTDMS-coord/relay-data"
qrfile="$data/qr.txt"

draw() { python3 -c 'import qrcode,sys; q=qrcode.QRCode(border=2); q.add_data(sys.argv[1]); q.print_ascii(invert=True)' "$1"; }

case "${1:-}" in
  show)
    [ -s "$qrfile" ] || { echo "no QR yet: run '$0 start' first" >&2; exit 1; }
    age=$(( $(date +%s) - $(stat -c %Y "$qrfile") ))
    draw "$(cat "$qrfile")"
    echo "QR age: ${age}s (rotates about every 20-60 s; run 'show' again if it stops scanning)"
    ;;
  start)
    systemctl --user stop rtdms-relay
    if [ -d "$data/auth" ]; then
      mv "$data/auth" "$data/auth.logged-out-$(date +%Y%m%d-%H%M%S)"
    fi
    mkdir -m 0700 "$data/auth"
    rm -f "$qrfile"
    since="$(date '+%Y-%m-%d %H:%M:%S')"
    systemctl --user start rtdms-relay
    # journald lines: the raw QR follows the "WHATSAPP PAIRING QR CODE:" line.
    journalctl --user -u rtdms-relay --since "$since" -f -o cat | while IFS= read -r line; do
      if [ "${next:-0}" = 1 ]; then
        (umask 077; printf '%s' "$line" > "$qrfile"); next=0
      fi
      case "$line" in
        *"WHATSAPP PAIRING QR CODE:"*) next=1 ;;
        *whatsapp_connected*) rm -f "$qrfile"; echo "WhatsApp connected"; break ;;
        *whatsapp_logged_out*) echo "logged out again: $line" >&2; break ;;
      esac
    done
    ;;
  *) echo "usage: $0 start|show" >&2; exit 2 ;;
esac
