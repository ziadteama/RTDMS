# RTDMS — Real-Time Driver Monitoring System

Graduation project monorepo. B.Sc. Computer Engineering, AASTMT. See [Home.md](Home.md) for the
Obsidian vault entry point and [CLAUDE.md](CLAUDE.md) for full project context.

This repo is **both** a code monorepo and an Obsidian vault — documentation lives beside the code
it describes.

## Layout

```
RTDMS/
├─ Home.md                  Obsidian entry point (vault map)
├─ CLAUDE.md                Project context for AI agents
├─ Report/                  Project 1 final report, transcribed section-by-section
├─ Subsystems/              Implementation notes, one per subsystem
├─ bases/                   Obsidian .base database views
├─ models/                  The three DMS detection models
│  └─ physiology/           HR/HRV fatigue inference from wrist PPG  [IMPLEMENTED]
└─ .claude/skills/          Agent skills adopted into this workspace
```

## Components

| Component | Path | Status |
|---|---|---|
| Physiology (HR/PRV, fatigue) | `models/physiology/` | Replay pipeline implemented; hardware + trained artifact pending |
| Vision — drowsiness (PERCLOS/EAR) | `models/` *(not yet created)* | Planned — Phase 2 |
| Vision — distraction (gaze, phone) | `models/` *(not yet created)* | Planned — Phase 2 |
| Decision fusion | *(not yet created)* | Planned — Phase 4 |
| Alert subsystem (buzzer/vibration) | *(not yet created)* | Planned — Phase 4 |
| Wearable firmware (ESP32-C3) | *(not yet created)* | Planned — Phase 1 |
| Application / dashboard | *(deferred)* | Scope not yet decided |

New components follow the same shape as `models/physiology/`: a self-contained project with its own
`pyproject.toml` (or equivalent), `src/`, `tests/`, `docs/`, and Docker-based verification, so each
can be developed and tested independently before integration.

## Quickstart — physiology

Requires Docker (canonical environment; guarantees the Python 3.11 runtime the package pins):

```bash
cd models/physiology
docker compose run --rm verify     # pytest + ruff + mypy
docker compose run --rm simulate   # 70s synthetic PPG replay
```

See [models/physiology/README.md](models/physiology/README.md) and its
[docs/ARCHITECTURE.md](models/physiology/docs/ARCHITECTURE.md).

## Documentation convention

Code-level docs (architecture, validation plans, API contracts) live in each component's `docs/`.
Project-level notes, cross-subsystem context, and the report transcription live in the Obsidian
vault (`Report/`, `Subsystems/`). Subsystem notes link to the code docs rather than duplicating
them, so there is one source of truth per fact.
