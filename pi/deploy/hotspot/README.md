# RTDMS Wi-Fi Hotspot

## Usage
- Bring up: `sudo pi/deploy/hotspot/rtdms-ap-up.sh [--dry-run]`
- Tear down: `sudo pi/deploy/hotspot/rtdms-ap-down.sh [--dry-run]`

## Non-DFS Channel Reason
DFS channels (52-144) require radar detection (CAC) causing startup delays or drops.
A fixed non-DFS 5 GHz channel (default 36) guarantees immediate AP availability.

## Hardware Status
This hotspot configuration is not verified on hardware.

## 2.4 GHz Fallback
Fallback to 2.4 GHz channel 6 only if a test phone will not join 5 GHz (env override).
