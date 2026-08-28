---
name: faithful-brief
description: Write a delegation brief that provably drops nothing from the source plan, and verify the result against the PLAN rather than the brief. Use whenever writing a brief for codex-delegate, agy-delegate, or a subagent implementation task, and whenever marking a delegated phase complete. Triggers on "delegate", "write a brief", "dispatch to Codex", "hand this to agy", "phase N", "implement the plan".
---

# Faithful Brief

A delegation brief is a **lossy re-encoding of a plan**. Every item that fails to survive the
re-encoding is silently lost forever, because from that point on the brief becomes the thing you
verify against, and the plan is never opened again.

## The failure this exists to prevent (real, 2026-07-27)

An approved 5-phase architecture plan was delegated phase by phase. Each phase's diff was reviewed
against **the brief written for that phase**, never against the plan. The briefs had quietly dropped
items. Result: six plan requirements shipped as "complete" while missing:

- `engagementRate` — listed in the plan's `ResearchSubject` interface, never added
- `businessCategory` / `categories` — same
- CENSUS unioning website-SERP leads — plan said "unions **both** website-first sources", only Maps shipped
- research resumability / snapshot dedup — plan said "make it resumable by skipping subjects already
  snapshotted in the current sweep, which also kills the duplicate-snapshot problem"
- the synthetic historical sweep backfill
- `mode` on the campaign-creation form

Every phase passed its gates. Typecheck was green, tests were green, diffs were reviewed line by
line. **None of that catches a requirement that was never asked for.** Worse, one dropped item got
written into a commit message as a deliberate design decision ("deliberately no dedup/resume logic")
because the implementer framed its omission as a choice and the reviewer had no plan-side checklist
to contradict it.

Green gates prove the brief was satisfied. They say nothing about whether the brief was faithful.

## Procedure

### 1. Extract the coverage ledger BEFORE writing any brief prose

Open the source plan. Walk it top to bottom and extract **every** normative statement into a flat
numbered list — anything phrased as must/should/add/wire/fix/populate/ensure, plus every field name,
file path, and constant it names. Include items that look trivial; triviality is why they get
dropped.

Write the ledger to a scratchpad file. Do not write it from memory, and do not write it after
drafting the brief — the whole point is that the ledger is derived from the plan independently of
what you were already planning to say.

### 2. Map every ledger item to a disposition

Each item gets exactly one, and dispositions 2–4 need a stated reason:

| Disposition | Meaning |
|---|---|
| **IN** | covered by this brief — note where |
| **DEFERRED** | intentionally later — say which phase/task, and it must land in a tracked list |
| **DROPPED** | deliberately not doing — needs a real reason and, if it changes agreed scope, the user's sign-off |
| **ALREADY DONE** | verify in code first; "I think it shipped" is not a disposition |

An item you cannot confidently place is IN. Defaulting to IN is cheap; defaulting to silence is what
caused the incident above.

### 3. Put the ledger in the brief

The brief itself carries the checklist of IN items, phrased as acceptance criteria. This gives the
implementer something to self-check against, and gives you something to verify against later that
isn't just your own prose. Require the implementer to report per-item status in its structured
output contract — an implementer that silently skips item 7 of 9 should be visible in the report.

### 4. Verify against the PLAN, not the brief

When the work returns, re-open the **plan** (or the ledger, which is the plan's normative content)
and check each item against the actual code. Grep for the field names. Read the functions. Do not
re-read your brief and conclude the brief was satisfied — that is the exact loop that failed.

For anything the implementer reports as "deliberately not done" or "kept consistent with existing
behavior": check the ledger. If the plan required it, the implementer does not get to reclassify it
as a design decision, and neither do you when writing the commit message.

### 5. Carry unfinished items forward

DEFERRED and DROPPED items go somewhere durable (the vault's decisions/TODO notes, or the plan file
itself), with the reason. An item that exists only in a scratchpad ledger from three sessions ago is
functionally dropped.

## Rules

- **No brief without a ledger.** Even a small one. Small briefs drop small items, and small items are
  exactly what nobody notices.
- **The ledger is derived from the plan, not from the conversation.** Re-read the source document.
  Your recollection of it is already lossy — that is the failure mode.
- **"Green gates" is never evidence of completeness.** It is evidence of consistency with the brief.
- **When an implementer's report reframes a requirement as a choice, check the ledger before you
  believe it** — and never launder that reframing into a commit message.
- Applies to Haiku/Sonnet subagent briefs too, not just Codex/Antigravity relays. A subagent drops
  details exactly as easily.

## Scope

This governs faithfulness of a brief to its source, not brief style. Combine with `ponytail` (how
much to build) and the `improve-codebase-architecture` vocabulary (how it should be shaped) — those
constrain the solution; this one constrains the requirements.

When there is no written plan — an ad-hoc request — the "plan" is the user's own message. Extract the
ledger from that instead. Multi-part requests in chat are dropped as easily as plan items, usually
the clause after the last "and".
