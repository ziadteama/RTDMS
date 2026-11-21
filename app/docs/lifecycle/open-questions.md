# Lifecycle open questions

Part of [Sahi lifecycle](../LIFECYCLE.md).

## 5. Open Questions

1. BLE GATT Peripheral Multi-Central Concurrency: Can BlueZ 5.82 and `bless` 0.2.6 reliably sustain concurrent connections from both the Garmin smartwatch (sending 1 Hz RR intervals on service `0xFFF0`) and the Android phone central without increasing packet loss on the Garmin stream?
2. Android 16 BLE Connection Interval and Background Latency (realme GT 6T): What connection interval and MTU will Android 16 (SDK 36) on the realme GT 6T (Qualcomm Snapdragon 7+ Gen 3) grant in practice for GATT characteristic `0x01` (`alert` at 5 Hz)? Does notify delivery maintain < 100 ms latency with the screen turned off under ColorOS aggressive background limits? *(unverified, test on device; compare with baseline on Huawei EMUI / Helio G80).*
3. Wi-Fi AP 5 GHz Coexistence on BCM43455: Does operating the Pi 5 Wi-Fi access point on non-DFS 5 GHz channels (channels 36–48) completely eliminate radio packet drop on the 2.4 GHz Bluetooth receiver during concurrent live MJPEG video streaming?
4. ColorOS and EMUI Background Exemption Durability: On the realme GT 6T (ColorOS, Android 16), does enabling 'Allow background activity' and 'Allow auto-launch' permanently prevent process reclamation during multi-hour drives, or does Android 16 impose new foreground service runtime limits (e.g. timeout quotas)? *(unverified, test on device).* Secondary: On Huawei FRL-L22, does setting EMUI App Launch to 'Manual' remain durable without periodic user re-confirmation?
5. IMU Accelerometer Dynamic Range: Can the smartphone's internal MEMS accelerometer (on realme GT 6T and reference devices) reliably record peak impact accelerations up to 8 g without sensor saturation?
6. Pi Incident Ring-Buffer Flush Latency: When the phone writes an incident request to characteristic `0x07` over BLE, how long does the Pi 5 take to lock its 20 s ring buffer and produce `clip.mp4` via software x264 while the vision pipelines are running?
