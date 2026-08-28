# Physiological DMS Validation Plan

## Objective

Validate the simulator, model artifact, service behavior, and Raspberry Pi resource use before hardware integration. The first validation phase must be deterministic and replayable without a bracelet.

This plan assumes the architecture in [ARCHITECTURE.md](ARCHITECTURE.md). It separates signal correctness from fatigue-model performance. A good fatigue score cannot compensate for invalid peaks, corrupted transport, or poor PPG quality.

## Initial Simulator

### Required Inputs

The simulator must generate a `PpgFrame` stream at 100 Hz with a deterministic seed. It must support both a known-beat synthetic waveform and replayed public PPG samples.

Required controls:

- HR profile and exact ground-truth beat indices.
- Baseline drift, white noise, amplitude modulation, and pulse-width variation.
- Motion-burst intervals with documented start/end samples.
- Clipping, saturation, contact loss, and flatline intervals.
- Packet loss, duplication, reordering, sequence wraparound, sample-index gaps, and reconnects.
- FIFO overflow and MCU reset status events.
- Batch-size variation, including peaks split across two frames.

### Simulator Acceptance Tests

| Scenario | Expected evidence |
|---|---|
| Clean constant 60 bpm | Peak count equals ground truth, HR is 60 bpm within tolerance, no artifacts. |
| HR ramp from 50 to 120 bpm | HR trend follows ground truth; no doubled or skipped beats at changing spacing. |
| Peak at frame boundary | Exactly one peak is emitted, independent of frame partitioning. |
| Baseline drift and moderate noise | Filtered HR and IBI remain within clean-signal tolerance. |
| Motion burst | Quality becomes `DEGRADED` or `BAD`; invalid intervals do not enter RMSSD/SDNN. |
| Clipping or flatline | Quality is `BAD`; fatigue probability is null. |
| Lost/reordered packets | Loss is counted; no fabricated timestamps or false consecutive intervals span the gap. |
| Sequence wraparound | No false packet-loss event at `65535 -> 0`. |
| Reset or FIFO overflow | New session/affected window is marked invalid; valid output recovers after warm-up. |
| Same seed and input | Output payload sequence is byte-for-byte identical except explicitly injected monotonic clock fields. |

The simulator must allow virtual time. Tests must not use real sleeps, wall-clock deadlines, or BLE hardware.

## Signal Validation Gates

Validate the peak and interval pipeline against ECG-referenced datasets before training a fatigue model.

| Dataset | Use | Required reporting |
|---|---|---|
| BIDMC PPG | Controlled peak and IBI comparison | Peak precision, recall, F1, HR MAE, IBI MAE. |
| PPG-DaLiA | Motion-heavy wrist PPG comparison | Same metrics, stratified by activity and quality state. |
| BUT PPG | Signal-quality validation | Quality discrimination and rate-estimation metrics by quality label. |

Initial clean-window targets are peak F1 at least 0.98, HR MAE at most 3 bpm, and IBI MAE at most 20 ms. Report all metrics by quality state. Do not hide degraded or rejected windows in a single aggregate score.

PRV validation must compare RMSSD and SDNN against ECG-derived references using bias, MAE, correlation, and Bland-Altman limits. The documentation and UI must continue to call the output PRV even when the numerical agreement is good.

## Model Artifact Tests

The runtime must load a small JSON artifact and never unpickle a model.

| Test | Expected behavior |
|---|---|
| Valid artifact and feature vector | Produces finite probability in `[0, 1]`. |
| Repeated load | Produces identical prediction and model metadata. |
| Reordered feature vector | Rejected before inference. |
| Duplicate/unknown feature name | Rejected at artifact validation. |
| Wrong coefficient length | Rejected at startup. |
| Zero, negative, NaN, or infinity scale | Rejected at startup. |
| NaN/Infinity input feature | Suppress prediction and report a model-input quality reason. |
| Extreme linear score | Stable sigmoid returns finite value without overflow. |
| Unsupported schema | Fail closed with an actionable error. |
| Quality is `BAD` | Model is not invoked and probability is null. |

Training validation uses subject-grouped, leave-one-subject-out splits only. For UL-DD, use KSS 1-5 as alert and KSS 7-9 as drowsy; exclude KSS 6 from primary binary training. Report AUROC, macro-F1, balanced accuracy, sensitivity, specificity, Brier score, expected calibration error, and per-subject results.

Retain Logistic Regression unless another candidate improves leave-one-subject-out macro-F1 by at least 0.05 and AUROC by at least 0.03 while passing the same calibration and Pi resource gates.

## Service Tests

### Unit and Integration Coverage

- Packet codec round trips, malformed length rejection, and 18-bit sample decoding.
- Ring-buffer wraparound and extraction across the physical array boundary.
- Streaming filter output equivalence for one large batch versus arbitrary smaller batches.
- Peak overlap deduplication and refractory handling.
- IBI bounds, local median/MAD rejection, and no interpolation in primary time-domain features.
- `WARMUP`, `VALID`, `DEGRADED`, `BAD`, and `STALE` transitions.
- Bounded reconnect backoff, disconnect recovery, and session changes after resets.
- Fusion-sink failure with bounded queue depth and retained acquisition health.
- No unhandled task exceptions when a source, model, or sink fails.

### Long Replay

Run a two-hour 100 Hz virtual-time replay containing clean periods, noise, motion, disconnects, packet loss, and a reset. Assert:

- No backlog or growing queue.
- Bounded ring-buffer sizes.
- No increase in process memory after warm-up beyond an agreed tolerance.
- Output cadence: HR every second when available, PRV/model output every five seconds after valid warm-up.
- No fatigue probability during bad quality, stale data, or invalid model input.

## Pi Benchmark Protocol

Run the benchmark on the target 64-bit Raspberry Pi 5 with the same camera inputs, frame rates, and face/eye plus phone-detection models intended for the DMS. Pinning or changing CV model settings is not permitted just to improve this subsystem's score.

### Measurements

- Physiology process RSS, CPU percentage, thread count, and context switches.
- Per-stage latency: packet decode, filtering, peak processing, features, model, and fusion publish.
- End-to-end output lag from simulated sample index to fusion payload.
- BLE/replay queue depth, dropped outputs, reconnect time, and error count.
- CV model FPS/latency before and during the physiology load.
- Pi temperature, clock throttling flags, and memory pressure.

### Test Matrix

| Run | Workload | Pass condition |
|---|---|---|
| Baseline | Both CV models only | Record reference FPS, latency, RSS, temperature. |
| Physiology alone | Two-hour replay | Meets component CPU, memory, and latency gates. |
| Concurrent clean | Both CV models plus clean replay | CV metrics stay within agreed tolerance; physiology meets hard gates. |
| Concurrent faulted | Both CV models plus replay with packet loss/reconnects | No crash, no queue growth, correct stale/bad outputs. |
| Thermal soak | At least 30 minutes concurrent workload | No thermal throttle that invalidates the measurements. |

Acceptance thresholds:

- Physiology average CPU below 1% of one core and below 2% at peak.
- Physiology RSS at most 120 MB target and 150 MB hard maximum.
- P95 feature update below 20 ms target and 100 ms hard maximum.
- End-to-end fusion lag below 250 ms after a five-second feature boundary.
- Zero unbounded-memory events, service crashes, or silently dropped acquisition samples.
- No material regression in either CV model's throughput or latency. Record the agreed tolerance before the first concurrent run.

## Risks Requiring Explicit Closure

| Risk | Why it matters | Closure evidence |
|---|---|---|
| Wrist motion without an IMU | Steering and road vibration may make optical PRV unusable. | At least 80% usable 60-second windows during representative steering, otherwise add IMU or revise the sensor choice. |
| Sensor-domain shift | Public BVP data may not match MAX30102 red/IR wrist signals. | Validate after hardware arrival against simultaneous ECG or a trusted chest strap. |
| Fatigue-label scarcity | Small driving datasets can overfit subjects and sessions. | LOSO results, calibration, confidence intervals, and an explicit experimental label until replicated. |
| BLE timing misuse | Notification timing is jittery and corrupts IBI calculations. | Tests prove sample-index timing is used end to end. |
| Quality leakage | A model can mistake motion artifacts for fatigue. | Quality metrics are gating outputs, not classifier features; ablation confirms this. |
| Resource contention | Physiology may cause CV deadline misses despite low standalone cost. | Concurrent Pi benchmark including thermal soak and CV metrics. |
| Unsafe fusion semantics | A numerical score can be misread as an alert decision. | Nullable probability, quality/state fields, and fusion-owned alert thresholds. |

## Current Gaps

The repository now has a deterministic synthetic simulator, replay source, packet tests, signal tests, service tests, and a Pi benchmark harness. Public dataset adapters, a trained model artifact, and concurrent Pi measurements remain incomplete release gates. Hardware integration and fatigue-model release remain later gates, not prerequisites for building the replay pipeline.

## Initial Real-Data Evidence

`tools/validate_bidmc.py` replays one downloaded BIDMC CSV record through the full streaming service and compares quality-gated HR outputs to the record's ECG-derived one-Hz HR reference. On `bidmc_01`, the first run processed 60,001 PPG samples (480 seconds) and produced 504 valid outputs with 0.50 bpm HR MAE and 1.65 bpm 95th-percentile absolute error.

This is an initial controlled clinical HR check only. It does not validate PRV agreement against ECG, wrist motion, MAX30102 sensor-domain transfer, fatigue labels, or Pi performance under the two CV workloads.
