# Pi test-session tools

Used on 23 Nov 2026 to turn guesses into measured causes (see `Subsystems/Demo Prep 2026-11-23.md`).
The recordings contain camera frames of people: keep them in `/tmp` on the Pi or a scratch folder,
never in git, and delete them after the analysis.

| Script | Runs on | Does |
|---|---|---|
| `session_log.py <out dir>` | Pi (`python3`, stdlib) | every 0.5 s: one camera frame + camera `/status` (:8080) + runtime `/alert` (:8090) into `<out dir>/log.jsonl` and `fNNNNN.jpg`; stops after 10 min or when `<out dir>/STOP` exists |
| `analyse.py <session dir> [n]` | dev machine | `timeline.png` (eye ratio / openness / PERCLOS / state / classifier / alerts / fps) and frame sheets labelled with time, state, openness, classifier |
| `live_watch.py <out dir> <seconds>` | Pi | prints the drinking score and the dashboard's drinking decision; saves up to 6 frames while drinking is shown |

Start a recording detached, so a Tailscale drop does not stop it:

```bash
cat demo/tools/session_log.py | ssh khalifa@<pi> 'cat > /tmp/session_log.py; rm -rf /tmp/s1; nohup python3 -u /tmp/session_log.py /tmp/s1 > /tmp/s1.log 2>&1 &'
ssh khalifa@<pi> 'touch /tmp/s1/STOP'            # stop
ssh khalifa@<pi> 'tar c -C /tmp s1' | tar x -C <scratch>
python demo/tools/analyse.py <scratch>/s1
```

Do not `pkill -f session_log.py` inside an ssh command line that itself contains that text: it
kills its own shell.
