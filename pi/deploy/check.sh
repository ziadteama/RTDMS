#!/usr/bin/env bash
# RTDMS readiness check: green/red for everything the product needs. Read-only.
#   check.sh [--wait SECONDS] [--boot] [--ssh user@host] [--quiet]
#   --wait N   keep retrying until no FAIL (or N seconds pass); WARN does not block
#   --boot     also log "RTDMS READY ..." to the journal and write ~/.local/state/rtdms/ready
#   --ssh H    run this script on host H (key auth) instead of locally
# Exit 0 = ready (OK/WARN only), 1 = at least one FAIL.
set -u
WAIT=0 BOOT=0 QUIET=0 SSH_HOST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --wait) WAIT="${2:?seconds}"; shift ;;
    --boot) BOOT=1 ;;
    --quiet) QUIET=1 ;;
    --ssh) SSH_HOST="${2:?host}"; shift ;;
    *) echo "usage: $0 [--wait N] [--boot] [--quiet] [--ssh host]" >&2; exit 2 ;;
  esac
  shift
done
if [ -n "$SSH_HOST" ]; then
  args=(--wait "$WAIT")
  [ "$BOOT" = 1 ] && args+=(--boot)
  [ "$QUIET" = 1 ] && args+=(--quiet)
  exec ssh -o BatchMode=yes "$SSH_HOST" bash -s -- "${args[@]}" <"$0"
fi

UNIT=rtdms-pi-user
STATE_DIR="${STATE_DIRECTORY:-$HOME/.local/state/rtdms}"
FAILS=0 WARNS=0 OUT=""
row() { # level label detail
  case "$1" in FAIL) FAILS=$((FAILS + 1)) ;; WARN) WARNS=$((WARNS + 1)) ;; esac
  OUT+="$(printf '[%-4s] %-18s %s' "$1" "$2" "$3")"$'\n'
}
# json_get <json> <python expression on d>; prints nothing on any error
json_get() { python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(eval(sys.argv[2]))' "$1" "$2" 2>/dev/null; }
num_lt() { awk -v a="$1" -v b="$2" 'BEGIN{exit !(a<b)}'; } # a < b, numeric

run_checks() {
  FAILS=0 WARNS=0 OUT=""
  local state; state="$(systemctl --user is-active $UNIT 2>/dev/null)"
  if [ "$state" = active ]; then
    local nr; nr="$(systemctl --user show $UNIT -p NRestarts --value 2>/dev/null)"
    row OK service "$UNIT active (restarts since start: ${nr:-?})"
  else
    row FAIL service "$UNIT is '${state:-unknown}'"
  fi
  if [ -e "$HOME/.config/systemd/user/$UNIT.service.d/open.conf" ]; then
    row WARN ble-auth "OPEN MODE: no BLE token (dev only; install.sh --secure removes it)"
  else
    row OK ble-auth "token mode"
  fi

  local h; h="$(curl -s -m 3 http://127.0.0.1:8090/health || true)"
  if [ -z "$h" ]; then
    row FAIL health ":8090 /health not answering"
  else
    local cam fps
    cam="$(json_get "$h" 'd.get("camera")')"; fps="$(json_get "$h" 'd.get("fps")')"
    if [ "$cam" = ok ]; then
      if [ -n "$fps" ] && num_lt "$fps" 15; then row WARN camera "ok but only $fps fps"
      else row OK camera "ok, ${fps:-?} fps"; fi
    else row FAIL camera "'${cam:-missing}' (ribbon / camera service)"; fi
    local m
    for m in fusion face distraction physiology; do
      local v; v="$(json_get "$h" "d['models'].get('$m')")"
      if [ "$v" = running ]; then row OK "model $m" running
      elif [ "$m" = physiology ]; then row WARN "model $m" "'${v:-missing}' (normal until the watch connects)"
      else row FAIL "model $m" "'${v:-missing}'"; fi
    done
    local mem memt cpu
    mem="$(json_get "$h" 'd.get("mem_used_mb")')"; memt="$(json_get "$h" 'd.get("mem_total_mb")')"
    cpu="$(json_get "$h" 'd.get("cpu_pct")')"
    row OK load "cpu ${cpu:-?} %, mem ${mem:-?}/${memt:-?} MB"
  fi

  local s; s="$(curl -s -m 3 http://127.0.0.1:8080/status || true)"
  if [ -n "$s" ] && [ "$(json_get "$s" 'd.get("fps") is not None')" = True ]; then
    row OK stream ":8080 /status fps $(json_get "$s" 'd.get("fps")'), calibrated $(json_get "$s" 'd.get("drowsiness",{}).get("calibrated")')"
  else row FAIL stream ":8080 /status not answering"; fi

  local bt; bt="$(bluetoothctl show 2>/dev/null || true)"
  if ! grep -q 'Powered: yes' <<<"$bt"; then row FAIL ble "adapter missing or not powered"
  elif ! grep -qE 'ActiveInstances: 0x0[1-9]' <<<"$bt"; then row FAIL ble "powered but not advertising"
  elif ! grep -q 'Alias: RTDMS-Pi' <<<"$bt"; then row WARN ble "advertising, alias is not RTDMS-Pi"
  else row OK ble "advertising as RTDMS-Pi"; fi

  local th t d
  th="$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)"
  if [ -z "$th" ]; then row WARN power "vcgencmd unavailable"
  elif [ $(( th & 0x5 )) -ne 0 ]; then row FAIL power "throttled=$th NOW (under-voltage or frequency cap): check the supply"
  elif [ "$th" != 0x0 ]; then row WARN power "throttled=$th (happened since boot, not now)"
  else row OK power "throttled=0x0"; fi
  t="$(vcgencmd measure_temp 2>/dev/null | sed "s/[^0-9.]//g")"
  if [ -z "$t" ]; then row WARN temp unavailable
  elif num_lt "$t" 70; then row OK temp "${t} C"
  elif num_lt "$t" 80; then row WARN temp "${t} C (hot)"
  else row FAIL temp "${t} C (throttling soon)"; fi
  d="$(df -m --output=avail / | tail -1 | tr -d ' ')"
  if [ "${d:-0}" -ge 2000 ]; then row OK disk "$((d / 1024)) GB free"
  elif [ "${d:-0}" -ge 500 ]; then row WARN disk "${d} MB free"
  else row FAIL disk "${d:-?} MB free"; fi

  local ifs="" i
  for i in eth0 tailscale0 wlan0; do
    [ -e "/sys/class/net/$i" ] && ifs+="$i=$(cat /sys/class/net/$i/operstate) "
  done
  row OK network "${ifs:-none} (read only)"
}

START=$SECONDS
while :; do
  run_checks
  [ "$FAILS" -eq 0 ] && break
  [ $((SECONDS - START)) -ge "$WAIT" ] && break
  sleep 3
done
[ "$QUIET" = 1 ] || printf '%s' "$OUT"
if [ "$FAILS" -eq 0 ]; then
  up="$(cut -d. -f1 /proc/uptime)"
  summary="READY: all checks pass (${WARNS} warning(s)), ${up}s since boot, waited $((SECONDS - START))s"
  echo "$summary"
  if [ "$BOOT" = 1 ]; then
    logger -t rtdms-ready "RTDMS READY ${up}s after boot ($((SECONDS - START))s waiting, ${WARNS} warnings)" || true
    mkdir -p "$STATE_DIR" && printf 'ready_epoch=%s\nboot_seconds=%s\n' "$(date +%s)" "$up" >"$STATE_DIR/ready"
  fi
  exit 0
fi
echo "NOT READY: ${FAILS} failure(s)"
if [ "$BOOT" = 1 ]; then
  logger -t rtdms-ready "RTDMS NOT READY: ${FAILS} failure(s) $(printf '%s' "$OUT" | grep FAIL | tr '\n' ';')" || true
fi
exit 1
