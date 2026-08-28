# Lightweight Physiological DMS Architecture

## Purpose

This subsystem turns raw wrist PPG samples from a MAX30102 bracelet into quality-gated heart-rate (HR), pulse-rate variability (PRV), and a fatigue probability for the Driver Monitoring System (DMS). It is designed for a Raspberry Pi 5 that is already running face/eye and phone-detection models.

PPG-derived variability is called PRV in this project. It must not be presented as equivalent to ECG-derived HRV, particularly during motion or poor optical contact. The DMS fusion layer owns the final driver-alert decision.

## Runtime Constraints

- Python 3.11.
- Runtime dependencies: NumPy, SciPy, Bleak, and the standard library.
- Training-only dependency: scikit-learn.
- No pandas, plotting libraries, deep-learning frameworks, databases, web servers, or internal worker processes in the runtime path.
- One asyncio event loop and one BLAS/OpenMP thread.
- Target average load: below 1% of one Pi core and 120 MB RSS during a 100 Hz replay while the two CV models run.
- Hard gate: below 2% of one Pi core, 150 MB RSS, P95 feature update below 100 ms, and no unbounded queue growth.

## Data Flow

```text
ESP32-C3 + MAX30102
  acquisition, FIFO draining, BLE only
              |
              v
Bleak SampleSource -> packet validation -> raw ring buffer (120 s)
              |
              v
stateful 0.5-5 Hz SOS filter -> incremental PPG peak detector
              |
              v
IBI generation -> artifact rejection -> quality assessment
              |                         |
              v                         +-> BAD: suppress fatigue prediction
HR and PRV features -> exported logistic model -> OutputSink -> DMS fusion
```

The processor is incremental. It must process a BLE batch once, retain filter state across batches, and never rescan a full 60-second window for every notification.

## Component Contracts

The following contracts are the target public surface for the first implementation. They are intentionally small so acquisition, replay, signal processing, and fusion can be tested independently.

```python
class SampleSource(Protocol):
    def frames(self) -> AsyncIterator[PpgFrame]: ...


class OutputSink(Protocol):
    async def publish(self, output: PhysiologyOutput) -> None: ...
```

### `PpgFrame`

Required fields:

- `packet: PpgPacket`, containing the packet sequence, sample index, channel mask, status, and packed samples.
- `sample_rate_hz: int`, initially fixed at `100`.
- `received_at_seconds: float`, used for transport diagnostics only.

The Pi derives sample time from `first_sample_index` and `sample_rate_hz`, not notification arrival time. Arrival timestamps are transport diagnostics only.

### `QualityReport`

Required fields:

- `state: QualityState`, one of `GOOD`, `DEGRADED`, or `BAD`.
- `score: float`, normalized to `[0.0, 1.0]`.
- `reasons: QualityReason` bit flags.
- Transport, clipping, peak-consistency, and interval-artifact measurements.

`BAD` quality must set the fatigue probability to `None`. It may retain HR only when the HR-specific quality condition is satisfied.

### `PhysiologyOutput`

Required fields:

- Schema version, model version, monotonic output time, and window-ending sample index.
- State: `WARMUP`, `VALID`, `DEGRADED`, or `STALE`.
- Nullable HR, PRV features, and fatigue probability.
- `QualityReport` and BLE/session health data.

Version 1 uses a Unix-domain datagram `OutputSink` with JSON payloads. An in-memory sink is required for deterministic tests. The binary format and socket path must be configurable, but no HTTP API is required.

## Signal Processing Defaults

| Item | Default | Rationale |
|---|---:|---|
| Sampling | 100 Hz | Native MAX30102 option with adequate within-subject PRV resolution and low BLE volume. |
| Raw history | 120 s | Two analysis windows with minimal memory use. |
| Detector history | 20 s | Supports adaptive peak thresholds without repeated full-window work. |
| PRV history | 300 s | Supports baseline features and optional five-minute analysis. |
| HR update | 1 s | Responsive display and fusion data. |
| PRV/model update | 5 s | Low redundant work with timely DMS updates. |
| Primary feature window | 60 s | Suitable for responsive HR and short-window RMSSD, subject to quality gating. |
| Filter | 2nd-order Butterworth SOS, 0.5-5 Hz | Removes drift and high-frequency noise with retained causal state. |
| Peaks | Elgendi-style adaptive detector | Linear-time block detection with 300 ms refractory period. |
| Valid IBI | 300-2,000 ms | Rejects implausible pulse intervals. |

Required features are mean HR, HR slope, median IBI, RMSSD, SDNN, pNN50, CVNN, valid-beat count, and rolling HR/RMSSD deviation from a 300-second baseline. Do not interpolate rejected intervals for the primary RMSSD or SDNN calculation. Optional LF/HF features require a clean five-minute window and are not version-1 classifier inputs.

## BLE and Hardware Boundary

The ESP32-C3 configures the MAX30102, services the FIFO, assigns sample indices, and sends raw data. It does not calculate HR, PRV, signal quality, or fatigue.

Each BLE payload must carry protocol version, status flags, packet sequence, first sample index, sample count, channel mask, and packed 18-bit samples. The protocol reserves an optional accelerometer field but version 1 has no IMU requirement.

Packet loss, reordering, sequence wraparound, MCU reset, FIFO overflow, and sensor saturation are normal operating conditions. The service must detect and surface them. It must not silently bridge a sample-index gap with fabricated samples.

## State and Failure Policy

| Condition | Required behavior |
|---|---|
| Startup | Emit `WARMUP`; do not emit PRV until 60 seconds of valid data. |
| BLE disconnect | Emit `STALE` after the configured timeout, reconnect with bounded backoff, preserve diagnostics, and begin a new session on MCU reset. |
| Packet/sample gap | Record loss, reset only affected detector state when needed, and degrade or reject the affected window. |
| FIFO overflow/reset | Mark the affected window bad and restart processing at the next valid sample boundary. |
| Bad signal quality | Emit quality and null fatigue probability. Do not emit an alert-like value. |
| Invalid model artifact | Fail closed at service startup with a clear health error; keep raw acquisition diagnostics available. |
| Fusion sink unavailable | Bound the output queue, count dropped outputs, and continue acquisition and processing. |

## Model Artifact

The training pipeline uses `StandardScaler` plus `LogisticRegression`. The runtime model is a JSON artifact, not a pickled scikit-learn object.

It must contain:

- Artifact schema version and model version.
- Ordered feature names.
- Feature means and positive scales.
- Coefficients, intercept, decision threshold, and calibration metadata.
- Training dataset fingerprint and creation metadata.

Runtime validation must reject duplicate feature names, unknown or reordered features, non-finite values, zero or negative scales, dimension mismatches, unsupported schemas, and non-finite coefficients. Inference standardizes in the exported feature order, calculates a stable sigmoid, and returns a continuous probability. Fusion owns thresholding and alert policy.

## Deployment Shape

Run the physiology subsystem as a separate systemd service with a memory limit and lower scheduling priority than the two CV workloads. The service must expose health through its own output state and logs; it does not need an HTTP server.

Before production deployment, run the Pi benchmark with the actual CV models active. A standalone physiology benchmark is only a component measurement and cannot establish DMS readiness.

## Current Implementation Status

The initial replay implementation now includes the package scaffold, versioned BLE packet codec, deterministic synthetic source, bounded streaming signal path, JSON logistic-model loader, Docker Python 3.11 verification environment, and unit tests. Dataset adapters, trained artifacts, Pi concurrent-CV measurements, and hardware integration remain explicit release gates. See [VALIDATION.md](VALIDATION.md) for the required evidence.
