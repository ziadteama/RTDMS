#!/usr/bin/env bash
# Every 2 s: time, input voltage (5V rail), throttling flags, temperature -> power.log (synced to SD)
while true; do
  v=$(vcgencmd pmic_read_adc EXT5V_V 2>/dev/null | sed 's/.*=//')
  echo "$(date +%T) 5V=$v $(vcgencmd get_throttled) $(vcgencmd measure_temp)" >> ~/rtdms/power.log
  sync ~/rtdms/power.log 2>/dev/null
  sleep 2
done
