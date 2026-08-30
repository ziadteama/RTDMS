---
title: "Agent Guide — how to work in this repo"
tags:
  - meta
  - process
  - agent-guide
aliases:
  - agent guide
  - onboarding
---

# Agent Guide — how to work in this repo

↑ [[Home]]

For any agent (Claude Code, Codex, Antigravity/agy, a subagent, or a human) about to dev, explore
options, or delegate work in RTDMS. Read this **before** writing code, running a benchmark, or
handing work to another agent. It is process, not project facts — for project facts, see
[[../CLAUDE.md|CLAUDE.md]] (auto-loaded context) and `README.md` (repo map).

This note exists because this project has already paid for most of the lessons in it — a stale
evidence doc that silently lagged three commits behind main, an agent's self-reported "82 passed"
that turned out to mean the gate had never actually run, a merge conflict resolution that quietly
deleted 32 lines. Read it as "how to not re-pay for those," not as bureaucracy.

## 1. Gather context in this order, before touching anything

1. **`git log --oneline -20` and `git status`, always, even mid-conversation.** Don't trust a
   conversation summary's account of "current state" — branches get merged, reverted, and merged
   again inside a single session. The git log is ground truth; everything else is a claim about it.
2. **`README.md`** for the monorepo map, then **[[../CLAUDE.md|CLAUDE.md]]** for project framing
   (objectives, hardware, the phase-two scope).
3. **If the task touches a specific model** (`models/<name>/`): read its `docs/ARCHITECTURE.md`
   (contracts, data flow, failure policy) and `docs/VALIDATION.md` or `docs/EVIDENCE.md` (what
   evidence gates a release, and what's actually been measured) before writing a line of code.
4. **Check the matching vault note** in [[Models Index|Subsystems/]] for that area — code docs say
   what's true now; the vault's narrative sections (milestones, corrections, "not closed by this
   campaign") carry the *why*, the open questions, and the dead ends already explored. Skipping this
   is how the same mistake gets made twice.
5. **Check whether the doc you're about to trust is stale.** `git log --oneline -- <path>` on an
   `EVIDENCE.md`/`ARCHITECTURE.md`-type file shows when it last actually changed — compare that
   against the surrounding commit history. This repo has shipped a real regression (a schema-vocab
   mismatch) that sat unnoticed on `main` for several commits because the validation doc wasn't
   re-run after a merge. A doc's last-updated commit lagging behind recent related commits is a
   signal to re-verify before citing it, not to assume it's still accurate.
6. **If using Claude Code's memory system**, check `MEMORY.md` and linked memory files — they carry
   standing instructions (e.g. "the report is not binding," Pi access method) that aren't restated
   in every message.

## 2. This repo's shape

- **It is two things at once**: a git monorepo *and* an Obsidian vault (`.obsidian/` at root).
  `Report/` is the Project-1 final report, transcribed verbatim, section by section. `Subsystems/`
  is living implementation notes, one per subsystem, updated as work happens — not a one-time dump.
  `bases/` holds Obsidian database views over the vault.
- **Documentation convention** (don't violate it by duplicating): code-level docs — architecture,
  contracts, validation plans, evidence — live in each component's own `docs/`. Project-level notes,
  cross-subsystem context, and anything narrative (why a decision was made, what was tried and
  rejected) live here in the vault, mainly under `Subsystems/`. A vault note should *link* to the
  code doc it's about, not restate its content. If you're about to write the same fact in two
  places, put it in one and link the other.
- **`models/<name>/` shape** — every model follows this, so a new one should too:
  ```
  models/<name>/
  ├─ pyproject.toml       pinned runtime + dev/train extras, kept separate
  ├─ Dockerfile           multi-stage: base → development → runtime
  ├─ compose.yaml         a `verify` service (test+lint+typecheck) is mandatory
  ├─ configs/             tunable defaults, not hardcoded constants
  ├─ docs/
  │  ├─ ARCHITECTURE.md   contracts, data flow, failure policy
  │  ├─ VALIDATION.md     what evidence gates a release
  │  └─ EVIDENCE.md       what has actually been measured, and on what environment
  ├─ src/<package>/
  ├─ tests/
  └─ tools/               training, benchmarking, dataset validation, hardware verification scripts
  ```

## 3. Invariants that must not be silently broken

These are cross-model architectural decisions, not one component's preference — check
[[Models Index]] before working around any of them:

- **The report is a starting point, not a spec.** Prefer the technically optimal option over what
  the report says — but *always* record the divergence and why, in the component's docs and/or here
  in the vault (see [[Pi Setup Plan]]'s "Divergences from the report" table for the pattern). Silent
  divergence is the failure mode, not divergence itself.
- **Models report; fusion decides.** A model emits a continuous score plus a quality state. No
  model raises its own alert or applies its own threshold — that boundary belongs to the fusion
  stage alone, even before fusion exists as code.
- **Bad input → null output, never a guess.** A model that can't trust its input says "I don't
  know," not a confident wrong number.
- **Quality gates outputs; it is never a model feature.** Don't let a quality signal leak into what
  a model is trained or scored on.
- **Training-only dependencies stay out of the runtime path.** Export trained artifacts as plain
  JSON (or another inert format) and load them at runtime — never unpickle, never import a training
  framework in the deployed path.
- **Resource budgets are validated with all models running concurrently, on the real target.** A
  standalone benchmark proves nothing about contention. (This is precisely the open question in
  [[Pi Setup Plan#Open question — does the AI HAT+ turn out to be optional|Pi Setup Plan]] about
  whether the AI HAT+ is load-bearing — it can't be answered until it's measured that way.)

## 4. Verification discipline

- **Prefer measuring on the real target over a substitute, whenever the target is reachable.**
  Docker (x86_64) is the canonical fallback when the Pi is offline, not the canonical result — every
  number produced only in Docker should carry an explicit caveat, and get promoted (or corrected)
  once hardware is reachable again.
- **Never trust a delegated agent's "done" / "N passed" self-report.** Re-run the actual gate
  yourself — `pytest`/`ruff`/`mypy`, plus any domain validator (e.g. `tools/validate_bidmc.py`) —
  before marking a work package complete. This project has caught false "all passing" claims this
  way more than once, including one where the underlying tool had genuinely never executed.
- **A single passing data point is not a fix.** If a defect depends on a parameter (packet-loss
  rate, MTU size, input duration), sweep it before declaring the defect closed. "It looked fixed at
  the one setting I tried" is the easiest way to close something that is still broken.
- **Record methodology corrections explicitly**, as a visible callout, rather than quietly
  replacing a wrong number with a right one. The wrong number and *why* it was wrong is the part
  worth keeping — it's what stops the next agent from making the same measurement mistake.
- **A gate that returns exit 0 is not automatically evidence.** Confirm the tool actually ran and
  actually checked what you think it checked (e.g. a `pytest -q | tail -3` can clip the real summary
  line without failing; a Docker command can silently no-op if the daemon isn't running). Read the
  actual output, not just the exit code.

## 5. Raspberry Pi hardware access

- Connect over the **LAN IP with SSH key auth**, not the Tailscale IP — Tailscale SSH on this
  tailnet runs in check mode and demands an interactive browser re-auth that breaks non-interactive
  use. Current IP/user/key path: [[Raspberry Pi 5 Target]].
- **Never write the Pi's password into any git-tracked file, commit, or persistent memory file.**
  This vault is a git repo that may be pushed to GitHub. Key auth only, always, in anything written
  down.
- `models/physiology/tools/verify_on_pi.sh [host]` is the reusable one-command hardware
  verification entrypoint: syncs the checkout, runs the test/lint/type gate, runs the domain
  validator, runs a CPU/RSS sweep, and checks thermal state before and after. **Reuse this pattern**
  for any new model rather than re-deriving a sync-and-verify flow from scratch each time the Pi
  comes back online.
- Check `vcgencmd get_throttled` before and after any timed run. A non-zero value invalidates every
  CPU/latency number from that run — say so explicitly if it happens, don't quietly drop the caveat.
- If the Pi goes unreachable mid-session: park unverified work on a clearly labeled branch rather
  than merging it to `main` unverified, and prefer a real reachability check
  (`Test-NetConnection -Port 22` in PowerShell, or a direct `ssh ... echo ok`) over `ping`, which has
  shown stale/cached results in this environment.

## 6. Delegating work to another agent

- Use the **`faithful-brief`** skill discipline: extract a numbered coverage ledger from the plan
  *before* writing the delegation brief, and verify the completed work against that ledger — not
  against the agent's own report of what it did.
- For a long campaign, route heavy implementation work to **codex** or **agy** (separate quotas from
  the orchestrating Claude Code session) rather than spawning many Sonnet subagents, which draw on
  the same quota as the session doing the orchestrating.
- Isolate concurrent agents' file edits with **git worktrees**, and isolate concurrent container
  builds with `docker compose -p <name>` — running several agents against one shared working tree or
  one shared compose project name is how their changes collide.
- **Watch for a conflict resolution silently deleting content.** `git checkout --theirs` or
  `--ours` during a merge/cherry-pick conflict can drop lines that only existed on the side you
  discarded. After resolving any conflict in a doc, `grep` for something you know should still be
  there before trusting the result.
- When a background job is genuinely long-running, launch it with the harness's own background
  mechanism (so its completion produces a real notification) rather than a bare `nohup ... &`, which
  detaches without one.

## 7. Quick index

| Looking for | Go to |
|---|---|
| Project overview, objectives, hardware BOM | [[../CLAUDE.md\|CLAUDE.md]] |
| Vault entry point | [[Home]] |
| Cross-model architectural principles | [[Models Index]] |
| Pi hardware facts + access | [[Raspberry Pi 5 Target]] |
| Researched Pi configuration + open questions | [[Pi Setup Plan]] |
| Physiology model contracts | `models/physiology/docs/ARCHITECTURE.md` |
| Physiology model evidence (what's actually measured) | `models/physiology/docs/EVIDENCE.md` |
| Physiology hardware-in-the-loop narrative log | [[HIL Test Campaign]] |
| New-model conventions | `models/README.md` |
| Adopted agent skills | `.claude/skills/` |
