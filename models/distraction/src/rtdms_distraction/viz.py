"""Debug overlay: driver view with boxes, zones and key landmarks, plus a state panel."""

from __future__ import annotations

import cv2
import numpy as np

from .pipeline import FrameResult
from .types import Box

# BGR
CLS_COLOUR = {"phone": (60, 60, 235), "drink": (235, 170, 40), "food": (40, 200, 240),
              "hand": (200, 120, 230)}
LEVEL_COLOUR = {"none": (150, 150, 150), "warning": (0, 200, 255), "alert": (40, 40, 240)}
ZONE_COLOUR = {"phone_right_ear": (120, 220, 120), "phone_left_ear": (220, 220, 120),
               "mouth": (120, 180, 255)}
PANEL_W = 400
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _rect(img, b: Box, colour, thick=1):
    cv2.rectangle(img, (int(b.x1), int(b.y1)), (int(b.x2), int(b.y2)), colour, thick, cv2.LINE_AA)


def _text(img, s, x, y, colour=(235, 235, 235), scale=0.48, thick=1):
    cv2.putText(img, s, (x, y), FONT, scale, colour, thick, cv2.LINE_AA)


def render(res: FrameResult, fps: float | None = None, holder_zones=None, *, debug: bool = True,
           info: list[str] | None = None, classifier: dict[str, float] | None = None,
           banner: str | None = None) -> np.ndarray:
    """debug: draw mesh, zones, boxes and timings (off = clean view + state panel).
    info: extra panel lines (live mode: model, threshold, gray / flip).
    classifier: crop-classifier probabilities, drawn when a classifier exists.
    banner: a prompt bar across the bottom of the view (guided mode)."""
    view = res.view.copy() if res.view.ndim == 3 else cv2.cvtColor(res.view, cv2.COLOR_GRAY2BGR)
    h, w = view.shape[:2]

    if debug:
        if res.face is not None:
            for x, y in res.face.landmarks[::3]:  # every 3rd mesh point keeps it readable
                cv2.circle(view, (int(x), int(y)), 1, (90, 160, 90), -1)
        for name, z in res.evidence.zones.items():
            _rect(view, z, ZONE_COLOUR.get(name, (200, 200, 200)))
        for x, y, zw, zh in holder_zones or []:
            _rect(view, Box(x * w, y * h, (x + zw) * w, (y + zh) * h), (90, 90, 90))
        for x, y in res.evidence.wrists:  # pose wrists (hand-at-ear evidence)
            cv2.circle(view, (int(x), int(y)), 7, (0, 140, 255), 2, cv2.LINE_AA)
    for d in res.detections:
        c = CLS_COLOUR.get(d.cls, (255, 255, 255))
        _rect(view, d.box, c, 2)
        _text(view, f"{d.cls} {d.conf:.2f}", int(d.box.x1), max(12, int(d.box.y1) - 4), c, 0.45)
    if res.face is not None:
        lm = res.face.landmarks
        for i, c in ((234, (120, 220, 120)), (454, (220, 220, 120))):
            cv2.circle(view, tuple(int(v) for v in lm[i]), 4, c, -1, cv2.LINE_AA)
        if debug:
            for i in (13, 14, 61, 291, 152):
                cv2.circle(view, tuple(int(v) for v in lm[i]), 2, (120, 180, 255), -1, cv2.LINE_AA)
    if banner:
        cv2.rectangle(view, (0, h - 34), (w, h), (0, 0, 0), -1)
        _text(view, banner, 10, h - 11, (255, 255, 255), 0.6, 2)

    panel = np.full((max(h, 560), PANEL_W, 3), (28, 24, 22), np.uint8)
    y = 26
    _text(panel, f"OVERALL: {res.level.upper()}", 12, y, LEVEL_COLOUR[res.level], 0.7, 2)
    y += 30
    for name, st in res.behaviours.items():
        col = LEVEL_COLOUR[st["level"]]
        raw = {True: "+", False: "-", None: "?"}[st["raw"]]
        _text(panel, f"{name:<16} {st['level']:<7} r={st['ratio']:.2f} {raw}", 12, y, col)
        y += 18
        if debug and st["why"]:
            _text(panel, f"   {st['why'][:46]}", 12, y, (160, 160, 160), 0.4)
            y += 16
    y += 8
    bl = res.baseline
    _text(panel, "baseline: " + ("ready" if bl["ready"] else f"calibrating {bl['progress']:.0%}"),
          12, y, (200, 200, 200))
    y += 20
    f = res.face
    if f is None:
        stale = res.evidence.stale_face
        msg = "face: none (zones from last face)" if stale else "face: none (holding state)"
        _text(panel, msg, 12, y, (40, 40, 240))
        y += 20
    elif debug:
        dp = (f.pitch_deg - bl["pitch"]) if bl["ready"] and f.pitch_deg is not None else None
        _text(panel, f"pitch {_f(f.pitch_deg)}  d {_f(dp)}  yaw {_f(f.yaw_deg)}", 12, y)
        y += 18
        _text(panel, f"gaze_down {_f(f.gaze_down, 2)} ({f.gaze_source})  "
                     f"head_down {res.evidence.head_down_s:.1f}s", 12, y)
        y += 18
        _text(panel, f"jaw {_f(f.jaw_open, 3)} ({f.jaw_source})  lips {f.lip_ratio:.2f}", 12, y)
        y += 18
    ch = res.evidence.chewing
    if debug and ch is not None:
        _text(panel, f"chew {'YES' if ch.chewing else 'no'} {ch.dominant_hz:.1f}Hz "
                     f"band {ch.band_fraction:.2f} amp {ch.amplitude:.3f}", 12, y)
        y += 18
    if classifier:
        y += 4
        _text(panel, "crop classifier:", 12, y, (200, 200, 200))
        y += 18
        for k, v in sorted(classifier.items(), key=lambda kv: -kv[1])[:5]:
            _text(panel, f"   {k:<14} {v:.2f}", 12, y)
            y += 16
    y += 8
    tm = res.timings_ms
    if debug:
        _text(panel, "  ".join(f"{k[:4]} {v:.1f}" for k, v in tm.items()), 12, y,
              (180, 180, 180), 0.4)
        y += 18
    if fps is not None:
        _text(panel, f"{fps:.1f} FPS  ({sum(tm.values()):.1f} ms/frame)", 12, y, (180, 180, 180))
        y += 20
    for line in info or []:
        _text(panel, line[:52], 12, y, (120, 200, 255), 0.45)
        y += 17

    if panel.shape[0] > h:
        view = cv2.copyMakeBorder(view, 0, panel.shape[0] - h, 0, 0, cv2.BORDER_CONSTANT)
    return np.hstack([view, panel[: view.shape[0]]])


def _f(v, n=1):
    return "--" if v is None else f"{v:.{n}f}"
