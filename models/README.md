# Models

The detection models described in the Project 1 report (§3.1 System Architecture), plus the
fusion layer that will combine them.

| Model | Directory | Detects | Approach | Status |
|---|---|---|---|---|
| Physiology | `physiology/` | Fatigue/stress from HR + PRV | Wrist PPG → filter → peaks → features → logistic regression | **Implemented** (replay pipeline) |
| Face (drowsiness + gaze) | `face/` | Eye closure, PERCLOS, blink, gaze, head pose | MediaPipe Face Landmarker → arithmetic channels → `StateReport` | **Implemented** (core + demo runner) |
| Vision — phone / eating | `phone/` | Phone + eating distraction | YOLOv8n-cls ONNX (Safe-Drive-TN) @ ~5 Hz → `PhoneOutput` | **ONNX wired** (open weights) |
| Decision fusion | `../fusion/` | Combines models → alert pattern | Consumes scores + quality; owns alerts | **Stub** (`decide()`) |

Decision fusion consumes model outputs and owns the alert decision. No individual model owns
production cabin alerts — see each subsystem's architecture doc. Face's `run.py` may buzz for
demos; that path is explicitly non-production.

## Naming note

`physiology/models/` and `face/models/` (nested) hold **trained / vendor model artifacts**, not
subsystems. The outer `models/` directory here holds the subsystems.

## Ownership — parallel work

Path ownership alone is not enough — **branching is mandatory**. Agents and humans follow
trunk-based, zone-scoped short-lived branches defined in `.cursor/rules/git-branching.mdc`
(always applied in Cursor; also summarised in `Agent Guide.md`).

| Zone | Owner | Path | Branch prefix |
|---|---|---|---|
| Face vision | Youssef | `models/face/` | `face/` |
| Physiology | Ziad | `models/physiology/` | `physio/` |
| Phone / eating | TBD | `models/phone/` | `phone/` |
| Fusion + production alerts | Joint | `fusion/` | `fusion/` |
| Shared status docs | Anyone, **tiny PRs only** | `models/README.md`, root `README.md`, `CLAUDE.md`, `Subsystems/Models Index.md` | `docs/` |

Rules that keep merges clean:

1. **One subsystem tree per PR.** Do not mix `face/` and `physiology/` edits.
2. **Never commit model code on `main`** — branch first (`face/<topic>`, `physio/<topic>`, …).
3. **Shared-doc bumps are separate** `docs/` PRs after the code PR merges.
4. **New shared contracts** (JSON schemas, socket paths) are proposed under `Subsystems/` before
   both sides implement.
5. **Artifacts stay local to the package** (`face/models/*.task`, `physiology/models/*.json`).
6. Rebase/sync onto `origin/main` before opening or updating a PR.

## Adding a new model

Follow the shape `physiology/` and `face/` already establish:

```
models/<name>/
├─ pyproject.toml       pinned runtime + dev extras
├─ Dockerfile           multi-stage: base → development → runtime
├─ compose.yaml         `verify` (test + lint) is mandatory
├─ configs/             tunable defaults, not hardcoded constants
├─ docs/
│  ├─ ARCHITECTURE.md   contracts, data flow, failure policy
│  ├─ VALIDATION.md     what evidence gates a release
│  └─ EVIDENCE.md       what has actually been measured
├─ src/<package>/
├─ tests/
└─ tools/               training, benchmarking, hardware scripts (optional)
```

Key conventions:

- **Runtime deps stay minimal.** Training-only dependencies must not enter the runtime path.
- **Quality gating is not optional.** Bad input → null / `UNAVAILABLE`, not a confident wrong number.
- **Fusion owns thresholds and alerts.** Models emit continuous scores and quality state.
- **Docker is the canonical verify environment** where practical.
- **Resource budgets are explicit** and eventually validated on the Pi with other models running.
