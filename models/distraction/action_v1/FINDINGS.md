# Step 1 findings: "detect ms = 0" and "pose ms = 0"

**Neither model is broken. The page showed one frame's timings, and on most frames those stages are
skipped on purpose.**

1. **detect ms = 0.** The Pi runs `stream.py --detect-every 2`, so the detector runs on every 2nd
   frame and the other frame reuses its boxes (`pipeline.py` line 200: `ran = self._i % every_n == 0`).
   The timer around it (line 204) still records the skipped frames, as ~0 ms. `/status` sent the
   timings of the LAST frame only, so half of the snapshots read 0 ms. Real cost when it runs:
   ~45 ms (INT8 det_v2d on the Pi, measured earlier with every_n 1).
2. **pose ms = 0.** Two reasons:
   - with `--no-texting` (current Pi setup) the texting rule is off, and `pipeline.py` line 121 then
     disables pose entirely (`pcfg.pose.enabled = ... and rcfg.simple.texting`): pose never runs;
   - before that, pose ran on every 6th frame (`pose.every_n: 6`, line 290), so 5 of 6 snapshots
     showed 0 ms.

**Fix (in the copy, action_v1/src/distraction/scripts/stream.py):** `/status` now reports, per
stage, a rolling window of 60 frames: `avg` (mean ms per frame, what the frame rate pays),
`per_run` (mean ms on frames where the stage ran) and `ran_pct` (how often it ran). The original
code in the repo is unchanged.
