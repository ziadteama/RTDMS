"""Timeline + frame sheets from a session_log.py recording (dev machine; needs numpy, opencv,
matplotlib). Usage: python analyse.py <session dir> [every Nth sample on the sheets, default 4]
Writes timeline.png and sheet_<k>.jpg next to the session dir."""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import cv2  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

D = Path(sys.argv[1])
rows = [json.loads(x) for x in (D / "log.jsonl").read_text().splitlines()]
t = np.array([r["t"] for r in rows])


def g(r, *keys):
    v = r["status"]
    for k in keys:
        v = (v or {}).get(k) if isinstance(v, dict) else None
    return v


def f(v):
    return np.nan if v is None else float(v)


ear = np.array([f(g(r, "drowsiness", "ear")) for r in rows])
ear_open = np.array([f(g(r, "drowsiness", "ear_open")) for r in rows])
ear_closed = np.array([f(g(r, "drowsiness", "ear_closed")) for r in rows])
openness = np.array([f(g(r, "drowsiness", "openness")) for r in rows])
perclos = np.array([f(g(r, "drowsiness", "perclos")) for r in rows])
face = np.array([1.0 if g(r, "face") else 0.0 for r in rows])
occl = np.array([1.0 if g(r, "drowsiness", "occluded") else 0.0 for r in rows])
states = [g(r, "drowsiness", "state") or "-" for r in rows]
actions = [g(r, "hybrid", "action") or "-" for r in rows]
pact = np.array([f(g(r, "hybrid", "p")) for r in rows])
call = np.array([1.0 if g(r, "hybrid", "call") else 0.0 for r in rows])
text = np.array([1.0 if g(r, "hybrid", "texting") else 0.0 for r in rows])
alerts = [(r["alert"] or {}).get("pattern", "-") for r in rows]
fps = np.array([f(g(r, "fps")) for r in rows])

SC = {"alert": 0, "warning": 1, "distracted": 1.5, "drowsy": 2, "unavailable": -1, "starting": -1}
AC = ["normal", "call", "texting", "drinking", "eating", "hand_on_face", "other"]
PA = {"none": 0, "short_beep": 1, "repeated": 2, "continuous": 3, "max": 4}

fig, ax = plt.subplots(6, 1, figsize=(18, 16), sharex=True)
ax[0].plot(t, ear, ".", ms=3, label="EAR (filtered)")
ax[0].plot(t, ear_open, "-", label="ear_open (adapted)")
ax[0].plot(t, ear_closed, "-", label="ear_closed")
ax[0].set_ylabel("eye ratio")
ax[0].legend(loc="upper right")
ax[1].plot(t, openness, ".", ms=3, label="openness")
ax[1].axhline(0.2, color="r", lw=.8)
ax[1].plot(t, perclos, "-", label="PERCLOS")
ax[1].legend(loc="upper right")
ax[1].set_ylim(-.05, 1.1)
ax[2].plot(t, [SC.get(s, -2) for s in states], ".", ms=4)
ax[2].set_yticks([-1, 0, 1, 1.5, 2])
ax[2].set_yticklabels(["unavail", "alert", "warning", "distracted", "drowsy"])
ax[2].fill_between(t, -1.5, -1.5 + 0.5 * (1 - face), color="k", alpha=.3, step="mid",
                   label="no face")
ax[2].fill_between(t, 2.3, 2.3 + 0.4 * occl, color="orange", alpha=.6, step="mid",
                   label="eyes occluded")
ax[2].legend(loc="upper right")
ax[3].scatter(t, [AC.index(a) if a in AC else -1 for a in actions], c=pact, cmap="viridis", s=8,
              vmin=0, vmax=1)
ax[3].set_yticks(range(-1, 7))
ax[3].set_yticklabels(["-"] + AC)
ax[3].set_ylabel("classifier (colour=p)")
ax[4].step(t, call, label="call alert")
ax[4].step(t, text + 0.05, label="texting alert")
ax[4].step(t, [PA.get(a, -1) / 4 for a in alerts], label="fusion pattern /4")
ax[4].legend(loc="upper right")
ax[5].plot(t, fps, "-")
ax[5].set_ylabel("fps")
ax[5].set_xlabel("seconds since start")
for a in ax:
    a.grid(alpha=.3)
    a.set_xticks(np.arange(0, t[-1] + 1, 10))
fig.tight_layout()
fig.savefig(D.parent / "timeline.png", dpi=70)

# contact sheet: every 4th sample (2 s), left camera part only, label t / state / openness / action
step = int(sys.argv[2]) if len(sys.argv) > 2 else 4
tiles = []
for r, s, o, a, p in zip(rows, states, openness, actions, pact, strict=True):
    if r["i"] % step or not r["frame"]:
        continue
    img = cv2.imread(str(D / r["frame"]))
    if img is None:
        continue
    img = img[:, : int(img.shape[1] * 0.62)]
    img = cv2.resize(img, (240, int(240 * img.shape[0] / img.shape[1])))
    lab = f"{r['t']:.0f}s {s} o={'-' if np.isnan(o) else f'{o:.2f}'}"
    lab2 = f"{a} {'' if np.isnan(p) else f'{p:.2f}'} {(r['alert'] or {}).get('pattern', '')}"
    cv2.rectangle(img, (0, 0), (240, 30), (0, 0, 0), -1)
    cv2.putText(img, lab, (3, 12), cv2.FONT_HERSHEY_SIMPLEX, .38, (255, 255, 255), 1)
    cv2.putText(img, lab2, (3, 26), cv2.FONT_HERSHEY_SIMPLEX, .38, (0, 255, 255), 1)
    tiles.append(img)
cols = 8
h = max(x.shape[0] for x in tiles)
tiles = [cv2.copyMakeBorder(x, 0, h - x.shape[0], 0, 0, cv2.BORDER_CONSTANT) for x in tiles]
while len(tiles) % cols:
    tiles.append(np.zeros_like(tiles[0]))
sheet_rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
for k in range(0, len(sheet_rows), 8):
    cv2.imwrite(str(D.parent / f"sheet_{k // 8}.jpg"), np.vstack(sheet_rows[k:k + 8]))
print("samples", len(rows), "duration", t[-1], "sheets", (len(sheet_rows) + 7) // 8)
