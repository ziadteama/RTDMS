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
  - Measures notification packet loss on the 5 Hz `alert` stream over 60 seconds.
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
