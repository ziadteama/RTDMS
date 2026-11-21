#!/usr/bin/env bash
# Runs on the Raspberry Pi: executes matrix spike runs A-D.
# Samples every 5s: throttled, temp, CPU, dmesg errors, status FPS.
# Writes results to ./spike_results/<run>/metrics.csv
set -euo pipefail

RUN_NAME="${1:-A}"
DURATION="${2:-}"

if [[ -z "$DURATION" ]]; then
  if [[ "$RUN_NAME" =~ ^[Dd]$ ]]; then
    DURATION=1800
  else
    DURATION=600
  fi
fi

OUT_DIR="./spike_results/${RUN_NAME}"
mkdir -p "$OUT_DIR"
CSV_FILE="${OUT_DIR}/metrics.csv"

echo "== Link Spike Matrix Run: $RUN_NAME ($DURATION s) =="
echo "Output: $CSV_FILE"

echo "timestamp,uptime_s,throttled,temp_c,cpu_pct,fps,dmesg_errors" > "$CSV_FILE"

read_cpu() {
  grep '^cpu ' /proc/stat 2>/dev/null || echo "cpu 0 0 0 0 0 0 0"
}

prev_cpu=$(read_cpu)
start_time=$(date +%s)
end_time=$((start_time + DURATION))

while true; do
  now=$(date +%s)
  if [[ $now -ge $end_time ]]; then
    break
  fi

  uptime_s=$(awk '{print int($1)}' /proc/uptime 2>/dev/null || echo 0)
  throttled_out=$(vcgencmd get_throttled 2>/dev/null || echo "throttled=0x0")
  throttled=$(echo "$throttled_out" | sed 's/.*=//')

  temp_out=$(vcgencmd measure_temp 2>/dev/null || echo "temp=0.0'C")
  temp_c=$(echo "$temp_out" | grep -o -E '[0-9]+\.[0-9]+' || echo 0.0)

  curr_cpu=$(read_cpu)
  read -r -a prev_parts <<< "$prev_cpu"
  read -r -a curr_parts <<< "$curr_cpu"
  prev_cpu="$curr_cpu"

  prev_idle=$(( ${prev_parts[4]:-0} + ${prev_parts[5]:-0} ))
  curr_idle=$(( ${curr_parts[4]:-0} + ${curr_parts[5]:-0} ))

  prev_total=0
  for val in "${prev_parts[@]:1}"; do prev_total=$((prev_total + val)); done
  curr_total=0
  for val in "${curr_parts[@]:1}"; do curr_total=$((curr_total + val)); done

  delta_total=$((curr_total - prev_total))
  delta_idle=$((curr_idle - prev_idle))

  if [[ $delta_total -gt 0 ]]; then
    cpu_pct=$(awk -v dt="$delta_total" -v di="$delta_idle" 'BEGIN { printf "%.1f", 100.0 * (dt - di) / dt }')
  else
    cpu_pct="0.0"
  fi

  fps=$(curl -s --max-time 2 http://localhost:8080/status 2>/dev/null | grep -o '"fps":[^,}]*' | sed 's/"fps"://' || echo "0.0")
  if [[ -z "$fps" ]]; then fps="0.0"; fi

  dmesg_errors=$(dmesg 2>/dev/null | tail -n 20 | grep -iE 'brcmfmac|bluetooth' | wc -l || echo 0)

  echo "${now},${uptime_s},${throttled},${temp_c},${cpu_pct},${fps},${dmesg_errors}" >> "$CSV_FILE"
  echo "[$(date +%T)] temp=${temp_c}C cpu=${cpu_pct}% throttled=${throttled} fps=${fps} dmesg_err=${dmesg_errors}"

  sleep 5
done

echo "Matrix run $RUN_NAME complete. Results saved in $CSV_FILE"
