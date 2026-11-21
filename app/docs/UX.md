# Sahi UX Redesign Specification

## 1. Overview & System Principles

Sahi is an Android driver-monitoring companion app for your Sahi unit mounted in the vehicle. The app acts as a calm, distraction-free instrument panel: it displays real-time driver state from the camera and sensors on your Sahi unit, records trip history, provides configurable alert feedback, and executes a two-stage crash detection and emergency SOS workflow.

### Audience & Product Principles
- **Driver-First Product**: The sole audience is the driver of a personal car (see `.cursor/rules/end-user-product.mdc` and `Subsystems/Mobile App End-User Scope.md`). Fleet managers, OEM engineers, and the team are not the audience of the main app.
- **Three Tabs**: **Drive**, **Trips**, **Settings**. Driving lock hides secondary details while moving.
- **Hidden Diagnostics**: Engineering diagnostics (hardware health, CPU/throttle/memory/disk, per-model switches, numeric thresholds, address entry, demo mode, relay override, raw sensor metrics) live in a hidden Diagnostics screen opened by tapping the app version 7 times in Settings > About.
- **No In-Drive Video**: Live camera video is strictly confined to setup and calibration, never on the Drive tab while driving.
- **Defaults Over Settings**: Sensible defaults, followed by simple 3-way choices (Low / Normal / High sensitivity), then Diagnostics. No numeric thresholds in Settings.
- **No Metric Without Meaning**: Plain state words and sentences; raw numbers (EAR, PERCLOS, RR, fps, FOV) never appear in the driver-facing UI.

### Target Environment & Test Device
- **Hardware Reference**: realme GT 6T (Qualcomm Snapdragon 7+ Gen 3).
- **Operating System**: Android 16 (ColorOS 15), Google Play Services present.
- **Platform Constraints**: Android 12+ (API 31+) permissions (`BLUETOOTH_SCAN`, `BLUETOOTH_CONNECT`), Android 13+ (API 33+) notification gating (`POST_NOTIFICATIONS`), foreground-service type requirements (`location`, `connectedDevice`), and ColorOS aggressive power-saving restrictions (auto-launch and background activity gating).
- **Legacy & Ecosystem Support**: Android 10+ background location gating; Huawei EMUI/HarmonyOS non-GMS paths.
- **Language Scope**: English only. No Arabic text, no RTL mirroring, no multi-language switcher.

### Core Visual & Interaction Tenets (DESIGN.md Alignment)
- **Instrument-Panel Aesthetic**: High contrast, dark-theme first (`#0B0D0F`), designed for arm's length reading on a dashboard mount under direct sunlight or night driving.
- **Zero Decorative Slop**: No decorative gradients, no ambient glows, no generic card grids, no emoji, no stock icons, no over-rounded pills everywhere, and no centered hero blocks.
- **Strict Hierarchy**: Layouts use grouped lists (`Section` and `Row` on `surface` with hairline `separator`), structured data metrics (`Metric` with tabular numbers), and high-visibility status indicators.
- **Token Strictness**: Every wireframe and component uses existing tokens defined in `app/docs/DESIGN.md` and `src/theme/`. Zero new hex codes or arbitrary sizes.

---

## 2. Redesigned Flows (see Contents below)

---

## Contents

- [Flow 1: permission checklist](ux/flow-1-permissions.md)
- [Flow 2: monitoring status](ux/flow-2-status.md)
- [Flows 3 and 4: wrong-alert feedback and per-alert why](ux/flow-3-4-feedback-why.md)
- [Flow 5: SOS](ux/flow-5-sos.md)
- [Flows 6 and 7: calibration warning, score and streaks](ux/flow-6-7-calibration-score.md)
- [Flow 8, state matrix and accessibility](ux/flow-8-clip-matrix-a11y.md)
