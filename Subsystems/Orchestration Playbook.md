---
title: "Orchestration Playbook: how the agents work on this repo"
tags:
  - process
  - agents
  - orchestration
status: current
updated: 2026-11-22
---

# Orchestration Playbook

↑ [[Home]] | [[Agent Guide]] | [[Project Log 2026-11]] | Setup: [[Dev Environment and Test Devices]]

How the multi-agent work ran on 21–22 Nov, what rules hold it together, and what went wrong.

## Roles

| Role | Who | Does | Does not |
|---|---|---|---|
| **MAIN** (coordinator) | the interactive Claude session | owns `contracts/`, merges PRs after re-running the gates, relays user decisions, runs hardware and device steps | write large features |
| **PI orchestrator** | Sonnet agent in its own worktree | builds `pi/` (runtime, Bluetooth phone service, incidents, hotspot, health) | edit `models/`, `fusion/`, `contracts/` |
| **APP orchestrator** | Sonnet agent in its own worktree | builds `app/` (design docs, crash/SOS, relay client, restructure) | edit `contracts/` or `pi/` |
| **RELAY orchestrator** | Sonnet agent | built `relay/` (WhatsApp SOS server) | link a real WhatsApp account or send real messages |
| **Delegates** | Codex (`codex exec`) and agy (`agy -p`) | write the code from a faithful brief; agy also cross-reviews | decide scope |

Orchestrators are Sonnet on purpose: they plan, brief, re-run every gate and review; the typing is
delegated. Haiku does read-only lookups. **No Sonnet sub-subagents** (they share the session quota).

## The coordination board

Append-only file outside git (`~/RTDMS-coord/BOARD.md`), entries `date time [ROLE] text`, sections
Status / Contract CRs / Needs / Hardware queue. Agents re-read it at the start of each work package
and before each PR. A change to a shared contract is a **CR**: propose on the board, the other side
ACKs, MAIN merges into `contracts/` and bumps the version; nobody codes against an un-ACKed change.
The 21–22 Nov trail is archived in [[Coordination Board 2026-11]].

## Always-on rules (in `.cursor/rules/`)

- `git-branching.mdc`: one zone per branch (`face/ physio/ phone/ fusion/ app/ pi/ relay/ contracts/ docs/ meta/`).
- `code-structure.mdc`: reuse before writing, one source of truth per fact, code files ≤ 300 lines (tests 400), docs ≤ 400, no grab-bag modules, strategy / pure core + thin shell / state machines as data; every PR body says "Reused: … / New and why: …" and lists files over 300 lines.
- `end-user-product.mdc`: the audience is the driver; admin items go to hidden Diagnostics; vocabulary table; every UI PR carries an "Audience check" line.
- `pi-performance-pipeline.mdc`: Pi concurrent cost first.

## Per work package

1. Write a **coverage ledger** from the plan (skill `faithful-brief`) before the brief.
2. Dispatch to Codex or agy with the code-structure rule text in the brief; max two delegates at once, on disjoint directories.
3. **Cross-review** the diff with the other delegate.
4. **Re-run the gates yourself** (never trust "done"). MAIN re-runs them again before merging.
5. PR with attribution lines, "Reused / New and why", the longest-files check, and the Audience check for UI.
6. Merge in stack order and retarget stacked PRs to `main` (a PR merged into its stacked base never reaches `main`: PRs #13/#14 did this and needed a catch-up PR #19).
7. Docs on a separate `docs/` branch.

## Safety rules for hardware agents

Never touch `eth0` or `tailscale0` (our only ways into the Pi); the hotspot goes on `wlan0` only and
never together with a station connection (trixie's CYW43455 firmware crashes with both); every Pi
change is listed on the board first and reversible; check `vcgencmd get_throttled` before and after
timed runs; no passwords or keys in files; do not measure latency over Tailscale.

## What went wrong, and the lesson

| Problem | Lesson |
|---|---|
| The first design looked like generic AI output | Treat generated screens as rough input; keep the written design system as the source of truth; add anti-slop skills (`taste-design`, `impeccable`) and critique before shipping |
| The app grew admin features nobody asked for | Define the audience in a rule and audit against it (D9 in [[Project Log 2026-11]]) |
| Demo mode produced fake "delivered" results that looked real | Fabricated data must be labelled and must never trigger real side effects |
| A dry-run test passed while the real start crashed | Test the real path at least once before calling a component done |
| An agent said done while the work was unverified | Orchestrators and MAIN re-run gates; reports must separate "verified" from "not verified" |
| Codex quota ran out mid-campaign | Keep a second implementer (agy) ready; note quota reset times |
| A shell killed itself via `pkill -f` | Script file + bracket patterns for process control |
| Three research subagents were first launched on the expensive model | Use cheaper agents (Haiku or Sonnet) for exploration |

## Skills installed for this work

`codex-delegate`, `agy-delegate`, `faithful-brief` (delegation); `ui-ux-pro-max`, `wireframe-spec`,
`taste-design`, `impeccable` (design); `competitive-brief`, `competitor-analysis` (research);
`obsidian-markdown`, `obsidian-bases`, `obsidian-cli`, `obsidian-documentation` (vault). The
`impeccable` launcher downloads a checksum-verified binary from its GitHub releases on first run.
