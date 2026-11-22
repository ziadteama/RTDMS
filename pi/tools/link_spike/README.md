# Phone-Pi Link Bench Spike (P1)

Tooling and test methodology for evaluating concurrent BLE + Wi-Fi performance on Raspberry Pi 5.
Reference specification: `Subsystems/Phone-Pi Link.md` ("Bench spike").

## Test Matrix

| Run | Configuration | Min Duration | Focus |
|---|---|---|---|
| **A** | Watch only (baseline) | 10 min (600 s) | Baseline Garmin packet loss and radio stability |
| **B** | Watch + BLE laptop client | 10 min (600 s) | Two centrals on single BLE peripheral |
| **C** | Run B + 5 GHz hotspot + 1 MJPEG viewer | 10 min (600 s) | Wi-Fi / Bluetooth CYW43455 coexistence |
| **D** | Run C + full vision pipeline (`start_stream.sh`) | 30 min (1800 s) | Full concurrent load soak test |

## Tools Overview

- `run_matrix.sh`: Runs locally on the Raspberry Pi. Samples every 5 seconds:
  - `vcgencmd get_throttled`
  - `vcgencmd measure_temp`
  - Host CPU utilization (`/proc/stat` delta)
  - `dmesg` tail filtered for `brcmfmac` / `bluetooth` kernel errors
  - Vision pipeline FPS via `curl -s localhost:8080/status`
  Outputs time series into `./spike_results/<run>/metrics.csv`.

- `ble_rtt.py`: Bleak laptop client acting as phone central:
  - Connects to peripheral `RTDMS-Pi` and authenticates using `$RTDMS_TOKEN`.
  - Measures write-with-response round-trip time (`command` -> `result`) p50 and p95.
  - Measures notification packet loss on the 1 Hz `alert` stream over 60 seconds.
  - Measures reconnect latency across 5 disconnect/reconnect cycles.

- `garmin_loss.py`: Reads Garmin packet counter statistics:
  - The Garmin receiver reports `[garmin] received N, lost M` in service logs at shutdown.
  - Parses journald output (`journalctl -u rtdms-pi | python garmin_loss.py`).

## Go / No-Go Criteria

All criteria must pass during Run D (30-minute soak):
1. **Garmin loss**: Packet loss in runs B, C, and D must be no worse than baseline run A.
2. **BLE latency**: Write-with-response command RTT p95 under 100 ms.
3. **BLE reconnection**: Reconnect time under 5 seconds across 5 consecutive cycles.
4. **Radio stability**: Zero Bluetooth / `brcmfmac` kernel crashes or firmware resets in `dmesg`.
5. **Vision throughput**: `stream.py` FPS decreases by no more than 10% under hotspot + MJPEG load.

## nRF Connect Android Verification

On a physical Android smartphone with the nRF Connect app:
1. **MTU negotiation**: Connect and verify that ATT MTU 247 is negotiated and granted.
2. **Screen-off notifications**: Subscribe to `alert` (UUID `1375193a-7edb-4a34-b3f2-181302390001`), lock phone screen, verify notifications continue without delay.
3. **Auto-reconnect**: Walk out of BLE range, wait 10 seconds, return in range, verify immediate automatic reconnect by remembered MAC.
4. **Network coexistence**: Verify phone cellular data remains functional while joined to `RTDMS-Pi` AP, and check behavior with "Smart Network Switch" / "Adaptive Connectivity" enabled vs disabled.

## Contract v1.2 bench

On the laptop, install `bleak`, export `RTDMS_TOKEN` securely, then run:

```sh
python3 pi/tools/link_spike/bench_link.py --name RTDMS-Pi --notify-seconds 30 \
  --samples 100 --cycles 5 --out results.json
```

Uses BlueZ adapter `hci0`. The token is read only from the environment; payloads and
backend exception text are never printed or stored. Results include service properties,
pre-auth access checks, notification arrival times/sizes, command RTT and reconnect timing.
The idle expectations are alert at 1 Hz, status keep-alive every 5 seconds (plus changes),
and one initial physio notification. Notification rates are measured only during the idle
observation window, before the RTT commands. Maximum gaps include the observation edges.
Reconnect timings include disconnect, scanning, the auth-reset probe, auth and clock write.

`test_alert` currently only plays the buzzer, so alert-change latency is **not measurable**.
The report explicitly records this limitation. Exit 0 requires every step to PASS, so this
version exits 1 even when every measurable check passes. Hardware BLE checks cannot run in
the Docker verification gate.

On the Pi (stdlib only):

```sh
python3 pi/tools/link_spike/proc_sample.py --pid 1234 --seconds 60 --interval 1 --out proc.json
python3 pi/tools/link_spike/proc_sample.py --pid-by-name rtdms-pi --seconds 60 \
  --interval 1 --load 4 --out proc-load.json
```

Name matching uses exact `/proc/PID/comm` or executable basename and rejects ambiguous names.
CPU percentages use one core as 100% (multithreaded processes can exceed 100%); the average
is weighted by elapsed time. RSS is reported in MiB. Context-switch counters are those of
the process leader, as exposed by `/proc/PID/status`; CPU time covers the process threads.
Thread counts and interval measurements are retained in JSON. Synthetic load children are
killed and reaped on completion, errors, Ctrl-C and SIGTERM. SIGKILL cannot be handled.
