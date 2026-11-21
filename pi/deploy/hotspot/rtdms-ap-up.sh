#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run)
            DRY_RUN=1
            ;;
        -h|--help)
            echo "Usage: $0 [--dry-run]"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

COUNTRY="${RTDMS_WIFI_COUNTRY:-EG}"
CHANNEL="${RTDMS_WIFI_CHANNEL:-36}"
SSID="${RTDMS_SSID:-RTDMS-Pi}"
CON_NAME="rtdms-ap"

if ! [[ "$CHANNEL" =~ ^[0-9]+$ ]]; then
    echo "Error: RTDMS_WIFI_CHANNEL must be an integer, got: $CHANNEL" >&2
    exit 1
fi

if [[ "$CHANNEL" -ge 52 && "$CHANNEL" -le 144 ]]; then
    echo "Error: DFS channels 52-144 are not permitted, requested channel: $CHANNEL" >&2
    exit 1
fi

if [[ -n "${RTDMS_WIFI_BAND:-}" ]]; then
    BAND="$RTDMS_WIFI_BAND"
elif [[ "$CHANNEL" -le 14 ]]; then
    BAND="bg"
else
    BAND="a"
fi

PSK_FILE="${RTDMS_PSK_FILE:-/var/lib/rtdms/wifi_psk}"
if [[ ! -f "$PSK_FILE" ]]; then
    PSK_DIR="$(dirname "$PSK_FILE")"
    if ! mkdir -p "$PSK_DIR" 2>/dev/null; then
        if [[ "$DRY_RUN" -eq 1 ]]; then
            PSK="mock-psk-dry-run"
        else
            echo "Error: cannot create directory $PSK_DIR" >&2
            exit 1
        fi
    else
        NEW_PSK="$(openssl rand -base64 18 | tr -d '/+=')"
        (umask 077 && printf '%s\n' "$NEW_PSK" > "$PSK_FILE")
        chmod 600 "$PSK_FILE" 2>/dev/null || true
        PSK="$NEW_PSK"
    fi
else
    PSK="$(tr -d '\r\n' < "$PSK_FILE")"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "nmcli connection add type wifi ifname '*' con-name $CON_NAME ssid $SSID 802-11-wireless.mode ap 802-11-wireless.band $BAND 802-11-wireless.channel $CHANNEL wifi.powersave 2 ipv4.method shared ipv4.addresses 10.42.0.1/24 wifi-sec.key-mgmt wpa-psk connection.autoconnect no"
    echo "printf '%s\\n' '<psk from file>' | nmcli --ask connection modify $CON_NAME wifi-sec.psk"
    echo "nmcli radio wifi on"
    echo "nmcli con up $CON_NAME"
    exit 0
fi

if command -v iw >/dev/null 2>&1; then
    iw reg set "$COUNTRY" || true
fi

if nmcli connection show "$CON_NAME" >/dev/null 2>&1; then
    nmcli connection modify "$CON_NAME" \
        ssid "$SSID" \
        802-11-wireless.mode ap \
        802-11-wireless.band "$BAND" \
        802-11-wireless.channel "$CHANNEL" \
        wifi.powersave 2 \
        ipv4.method shared \
        ipv4.addresses 10.42.0.1/24 \
        wifi-sec.key-mgmt wpa-psk \
        connection.autoconnect no
else
    nmcli connection add type wifi ifname '*' con-name "$CON_NAME" \
        ssid "$SSID" \
        802-11-wireless.mode ap \
        802-11-wireless.band "$BAND" \
        802-11-wireless.channel "$CHANNEL" \
        wifi.powersave 2 \
        ipv4.method shared \
        ipv4.addresses 10.42.0.1/24 \
        wifi-sec.key-mgmt wpa-psk \
        connection.autoconnect no
fi

printf '%s\n' "$PSK" | nmcli --ask connection modify "$CON_NAME" wifi-sec.psk
nmcli radio wifi on
nmcli con up "$CON_NAME"
