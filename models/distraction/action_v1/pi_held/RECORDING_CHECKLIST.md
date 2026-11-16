# Pi camera test set — recording checklist (held-object drinking + false-alarm cases)

The Pi IR frames are the number that counts. This set is **test only**: never train or tune on
it. Record with the real unit (Pi 5, 160° NoIR camera at the mirror, mounted as in the car,
upside down as `--rotate 180` expects), IR LEDs on, ideally a parked car or a car-like seat.

## What to record

| Label (`labels.csv`) | Clips | Each clip | Notes |
|---|---|---|---|
| `drinking` | 5 | 15–30 s, one sip | Mix: bottle, can, cup with handle, paper cup; 1 sip head tilted back, 1 short sip without tilt, 1 with the cup held low first |
| `yawning` | 5 | 10–20 s | Real or acted yawns, hand over the mouth in at least 2 |
| `smoking` or `hand_on_face` | 5 | 15–30 s | Cigarette (unlit is fine) or a pen at the lips; chin-on-hand; touching the mouth |
| `phone` | 5 | 20–30 s | 2 calls at the ear, 2 texting low, 1 phone raised near the mouth (speaker mode) |
| `rubbing_eyes` | 5 | 10–20 s | Both hands and one hand |
| `normal` | 1 (or several) | **10 min total** | Normal driving posture, talking, looking at mirrors, adjusting the seat belt |

Do it with **at least 2 different people** (3+ is better), with and without glasses, day and
night if possible. A person in more clips is fine; write the person's ID in `labels.csv`.

## How

1. Stop the live stream: `pkill -f stream.py` (the eval runs the same stack itself).
2. Record each clip with the Pi camera at the stream's resolution, e.g.
   `rpicam-vid -t 20000 --width 1280 --height 800 --framerate 30 --codec libav -o drinking_01.mp4`
   (one file per clip; start the action ~3 s after the recording starts, end ~3 s before).
3. Put all files in `~/rtdms_rec/` with `labels.csv`:

   ```
   file,label,person,notes
   drinking_01.mp4,drinking,p1,bottle tilt back
   yawning_01.mp4,yawning,p1,
   normal_01.mp4,normal,p2,10 min
   ```

4. Run `bash models/distraction/action_v1/pi_held/run_pi_eval.sh ~/rtdms_rec` and copy back
   `~/rtdms_held_eval/` (report.json + wrist_check.jpg) for the results table.

## Consent and privacy

Volunteers agree in writing; clips stay on the Pi / project drive, are not uploaded anywhere,
and are deleted when the project ends (CLAUDE.md "Ethics").
