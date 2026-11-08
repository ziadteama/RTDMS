#!/usr/bin/env python3
"""The distraction pipeline served to a browser: run.py for a headless Pi.

    python scripts/stream.py                          # Pi camera -> http://<pi>:8080
    python scripts/stream.py --no-rectify --roi full  # no fisheye calibration yet: whole frame
    python scripts/stream.py --video clip.mp4 --no-rectify --roi full   # test on a PC
    python scripts/stream.py --drowsiness --no-texting  # + PERCLOS drowsiness, no pose model
    python scripts/stream.py --drowsiness --hybrid --no-detect --mesh
        # v2 phone alerts (action classifier + phone checks, hybrid.py), no box detector,
        # face mesh drawn on the view

Open http://<pi address>:8080 on any computer on the same network: the camera view with the
detector's boxes and the alert state, plus /status (JSON: fps, per-stage ms, CPU temperature,
behaviour levels). With --drowsiness the face subsystem (models/face: eye closure, blinks,
PERCLOS) runs on the same frames; the page has a Calibrate button (10 s eyes open, 3 s closed,
saved per driver in profiles/). Frames are only drawn and JPEG-encoded while a browser is
watching, so with no viewer the loop costs what a deployment pays. Events are logged like run.py
(logs/drive_*.jsonl).
"""

from __future__ import annotations

import os

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402
from pathlib import Path  # noqa: E402

import cv2  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run import apply_overrides  # noqa: E402

from rtdms_distraction.capture import open_source  # noqa: E402
from rtdms_distraction.config import (  # noqa: E402
    load_pipeline_config,
    load_rules_config,
    resolve_path,
)
from rtdms_distraction.eventlog import EventLog  # noqa: E402
from rtdms_distraction.pipeline import DistractionPipeline  # noqa: E402
from rtdms_distraction.viz import render  # noqa: E402

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>RTDMS driver monitor</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{margin:0;background:#111;color:#ddd;font:15px system-ui,sans-serif}
main{display:flex;flex-wrap:wrap;gap:16px;padding:16px}img{max-width:100%;border:1px solid #333}
#s{min-width:260px}.alert{color:#ff5a4f;font-weight:700}.warning{color:#f5b300;font-weight:700}
td{padding:2px 10px 2px 0}h1{font-size:18px;margin:0 0 8px}</style></head><body><main>
<img src="/stream.mjpg" alt="camera"><div id="s"><h1>RTDMS distraction</h1>
<button onclick="fetch('/calibrate',{method:'POST'})">
Calibrate drowsiness (10 s open, 3 s closed)</button>
<table id="t"></table></div>
</main><script>
async function tick(){try{const r=await fetch('/status');const s=await r.json();
let h=`<tr><td>fps</td><td>${s.fps}</td></tr><tr><td>face</td><td>${s.face?'yes':'NO'}</td></tr>`+
`<tr><td>baseline</td><td>${Math.round(s.baseline*100)}%</td></tr>`;
for(const [b,l] of Object.entries(s.levels))h+=`<tr><td>${b}</td><td class="${l}">${l}</td></tr>`;
const y=s.hybrid;if(y){for(const k of ['call','texting'])h+=`<tr><td>${k==='call'?'PHONE CALL':'TEXTING'}</td>`+
`<td class="${y[k]?'alert':''}">${y[k]?'ALERT':'none'}</td></tr>`;
h+=`<tr><td>action</td><td>${y.action ?? '-'} ${y.p ?? ''}</td></tr>`+
`<tr><td>phone at ear / lap</td><td>${y.ear ?? '-'} / ${y.lap ?? '-'}</td></tr>`;}
const d=s.drowsiness;if(d){const c=d.state==='drowsy'?'alert':(d.state==='warning'?'warning':'');
h+=`<tr><td>DROWSINESS</td><td class="${c}">${d.state.toUpperCase()}</td></tr>`+
`<tr><td>PERCLOS</td><td>${d.perclos==null?'-':Math.round(d.perclos*100)+'%'}`+
`${d.perclos_valid?'':' (warming up)'}</td></tr>`+
`<tr><td>eye openness</td><td>${d.openness ?? '-'}</td></tr>`+
`<tr><td>blinks / min</td><td>${d.blink_rate ?? '-'}</td></tr>`+
`<tr><td>calibration</td><td>${d.message || (d.calibrated?'done':'no')}</td></tr>`;}
h+=`<tr><td>CPU temp</td><td>${s.temp_c ?? '-'} &deg;C</td></tr>`;
for(const [k,v] of Object.entries(s.ms))h+=`<tr><td>${k} ms</td><td>${v}</td></tr>`;
document.getElementById('t').innerHTML=h}catch(e){}}setInterval(tick,500);tick();</script>
</body></html>"""


def cpu_temp() -> float | None:
    try:
        return round(int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000, 1)
    except (OSError, ValueError):
        return None


class Shared:
    """Latest result and JPEG, shared between the pipeline thread and the HTTP handlers."""

    def __init__(self) -> None:
        self.cond = threading.Condition()
        self.jpeg: bytes | None = None
        self.seq = 0
        self.viewers = 0
        self.status: dict = {"fps": 0, "face": False, "baseline": 0, "levels": {}, "ms": {}}
        self.running = True
        self.calibrate = False  # set by POST /calibrate, consumed by the pipeline thread


ROTATE = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


class NullDetector:
    """--no-detect: the phone / drink / food box detector is not run at all."""

    def detect(self, view):
        return []


def draw_mesh(frame, lm) -> None:
    """Every face-mesh point as a small dot (the view sits at the frame's top-left)."""
    for x, y in lm:
        cv2.circle(frame, (int(x), int(y)), 1, (80, 220, 120), -1)


def pipeline_loop(args, shared: Shared) -> None:
    pcfg = load_pipeline_config(args.config)
    rcfg = load_rules_config(args.rules)
    apply_overrides(pcfg, args)
    if args.no_texting:  # no head-down texting rule -> no pose model
        rcfg.simple.texting = False
    c = pcfg.capture
    src = open_source(c.width, c.height, c.fps, video=args.video, flip=c.flip_horizontal,
                      realtime=args.video is not None)
    src.start()
    size = src.size[::-1] if args.rotate in (90, 270) else src.size
    pipe = DistractionPipeline(pcfg, rcfg, size,
                               detector=NullDetector() if args.no_detect else None)
    log = EventLog(resolve_path(pcfg.eventlog.dir), pcfg.eventlog.per_frame)
    log.session(source=src.describe(), driver_side=pcfg.driver_side,
                rectified=pipe.roi.rectified, roi=pipe.roi.rect,
                detector=f"{pcfg.detector.backend}:{pcfg.detector.weights}",
                facemesh=pcfg.facemesh.backend, hands=pcfg.hands.source)
    drowsy = None
    if args.drowsiness:
        from drowsiness import Drowsiness

        drowsy = Drowsiness(pipe.roi.out_w, pipe.roi.out_h,
                            str(resolve_path(pcfg.facemesh.model_path)), args.face_backend,
                            args.face_profile, str(resolve_path("profiles")))
    hybrid = None
    if args.hybrid:
        from hybrid import Hybrid

        hybrid = Hybrid(resolve_path(args.hybrid_models))
    det_name = "off" if args.no_detect else pcfg.detector.weights
    print(f"[stream] {src.describe()} -> view {pipe.roi.out_w}x{pipe.roi.out_h}; "
          f"detector {det_name}; v2 phone {'on' if hybrid else 'off'}; "
          f"drowsiness {'on' if drowsy else 'off'}; "
          f"texting rule {'on' if rcfg.simple.texting else 'off'}; log {log.path}", flush=True)
    n, fps, t0, last_enc = 0, 0.0, time.perf_counter(), 0.0
    try:
        while shared.running:
            gray, t = src.read()
            if gray is None:
                if args.video and args.loop:
                    src.stop()
                    src = open_source(c.width, c.height, c.fps, video=args.video, realtime=True)
                    src.start()
                    continue
                break
            if args.rotate:
                gray = cv2.rotate(gray, ROTATE[args.rotate])
            res = pipe.process(gray, t)
            n += 1
            dz = None
            if drowsy is not None:
                if shared.calibrate:
                    shared.calibrate = False
                    drowsy.start_calibration()
                dz = drowsy.feed(t, res.face.landmarks if res.face is not None else None)
            hy = None
            if hybrid is not None:
                v = res.view if res.view.ndim == 2 else cv2.cvtColor(res.view, cv2.COLOR_BGR2GRAY)
                hy = hybrid.feed(t, v, res.face.landmarks if res.face is not None else None)
                for a in hy.get("onsets", []):
                    print(f"[event] t={t:.2f} v2 {a} ALERT", flush=True)
            if n % 15 == 0:
                now = time.perf_counter()
                fps, t0 = 15 / (now - t0), now
            for e in log.update(t, res.behaviours):
                print(f"[event] t={e['t']:.2f} {e['event']} {e['behaviour']} "
                      f"{e.get('level', e.get('peak_level', ''))}", flush=True)
            status = {"fps": round(fps, 1), "face": res.face is not None,
                      "baseline": res.baseline["progress"],
                      "levels": {b: s["level"] for b, s in res.behaviours.items()},
                      "ms": {k: round(v, 1) for k, v in res.timings_ms.items()},
                      "temp_c": cpu_temp() if n % 30 == 0 else shared.status.get("temp_c")}
            if dz is not None:
                status["drowsiness"] = dz
                status["ms"]["drowsiness"] = dz["ms"]
            if args.no_detect:  # the release box rules have no input: hide them
                status["levels"] = {}
                res.behaviours = {}
                res.level = "alert" if hy is not None and (hy["call"] or hy["texting"]) else "none"
                status["ms"].pop("detect", None)
            if hy is not None:
                status["hybrid"] = {k: v for k, v in hy.items() if k not in ("onsets", "ms")}
                status["ms"]["v2_phone"] = hy["ms"]
            jpeg = None
            now = time.perf_counter()
            if shared.viewers and now - last_enc >= 1.0 / args.stream_fps:
                last_enc = now
                info, banner = [], None
                if dz is not None:
                    pct = "-" if dz["perclos"] is None else f"{dz['perclos'] * 100:.0f}%"
                    eyes = "-" if dz["openness"] is None else dz["openness"]
                    rate = "-" if dz["blink_rate"] is None else dz["blink_rate"]
                    info = [f"DROWSINESS: {dz['state'].upper()}  PERCLOS {pct}",
                            f"eyes {eyes}  blinks/min {rate}"]
                    if drowsy.banner:
                        banner = "  |  ".join(drowsy.banner)
                    elif not dz["calibrated"]:
                        info.append("drowsiness not calibrated")
                if hy is not None:
                    alerts = [n for k, n in (("call", "PHONE CALL"), ("texting", "TEXTING"))
                              if hy[k]]
                    info.append("PHONE: " + (" + ".join(alerts) + " ALERT" if alerts else "none"))
                    info.append(f"action {hy['action'] or '-'} {hy['p'] or ''}  "
                                f"ear {hy['ear'] if hy['ear'] is not None else '-'}  "
                                f"lap {hy['lap'] if hy['lap'] is not None else '-'}")
                    if alerts:
                        banner = (banner + "  |  " if banner else "") +                             " + ".join(alerts) + " ALERT"
                frame = render(res, fps, rcfg.phone_in_hand.holder_zones, debug=args.debug,
                               info=info, banner=banner)
                if args.mesh and res.face is not None:
                    draw_mesh(frame, res.face.landmarks)
                if hybrid is not None:
                    hybrid.draw(frame)
                if frame.shape[1] > args.max_width:
                    s = args.max_width / frame.shape[1]
                    frame = cv2.resize(frame, (args.max_width, round(frame.shape[0] * s)),
                                       interpolation=cv2.INTER_AREA)
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, args.jpeg_quality])
                jpeg = buf.tobytes() if ok else None
            with shared.cond:
                shared.status = status
                if jpeg is not None:
                    shared.jpeg, shared.seq = jpeg, shared.seq + 1
                    shared.cond.notify_all()
    finally:
        shared.running = False
        src.stop()
        with shared.cond:
            shared.cond.notify_all()
        print(f"[stream] stopped after {n} frames; events in {log.path}", flush=True)


def make_handler(shared: Shared):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the console for events
            pass

        def _send(self, body: bytes, ctype: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802 (http.server API)
            if self.path.startswith("/calibrate"):
                shared.calibrate = True
                self._send(b'{"ok": true}', "application/json")
            else:
                self.send_error(404)

        def do_GET(self):  # noqa: N802 (http.server API)
            if self.path in ("/", "/index.html"):
                self._send(PAGE.encode(), "text/html; charset=utf-8")
            elif self.path.startswith("/status"):
                with shared.cond:
                    body = json.dumps(shared.status).encode()
                self._send(body, "application/json")
            elif self.path.startswith("/stream.mjpg"):
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with shared.cond:
                    shared.viewers += 1
                seq = -1
                try:
                    while shared.running:
                        with shared.cond:
                            shared.cond.wait_for(
                                lambda last=seq: shared.seq != last or not shared.running,
                                timeout=2.0)
                            jpeg, seq = shared.jpeg, shared.seq
                        if jpeg is None:
                            continue
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
                finally:
                    with shared.cond:
                        shared.viewers -= 1
            else:
                self.send_error(404)

    return Handler


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--host", default="::", help="address to listen on (:: = every IPv4 + IPv6)")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--config", help="pipeline.yaml (default configs/pipeline.yaml)")
    p.add_argument("--rules", help="rules.yaml (default configs/rules.yaml)")
    p.add_argument("--video", help="video file instead of the camera (testing)")
    p.add_argument("--loop", action="store_true", help="restart the video at its end")
    p.add_argument("--no-rectify", action="store_true", help="no fisheye calibration: plain crop")
    p.add_argument("--roi", help="x,y,w,h in raw pixels, or 'full'")
    p.add_argument("--driver-side", choices=["right", "left"])
    p.add_argument("--weights", help="override detector.weights (e.g. the INT8 model)")
    p.add_argument("--detect-every", type=int, help="run the detector every Nth frame")
    p.add_argument("--debug", action="store_true", help="draw face mesh, zones and timings")
    p.add_argument("--stream-fps", type=float, default=10.0, help="max frames sent per second")
    p.add_argument("--max-width", type=int, default=640, help="downscale the stream to this")
    p.add_argument("--jpeg-quality", type=int, default=70)
    p.add_argument("--log-dir", help="override eventlog.dir")
    p.add_argument("--drowsiness", action="store_true",
                   help="also run the face subsystem's drowsiness / PERCLOS on the same frames")
    p.add_argument("--face-backend", choices=["litert", "mediapipe"], default="litert",
                   help="landmarker for --drowsiness (litert on the Pi)")
    p.add_argument("--face-profile", default="default", help="drowsiness calibration profile name")
    p.add_argument("--no-texting", action="store_true",
                   help="drop the head-down texting rule (and with it the pose model)")
    p.add_argument("--hybrid", action="store_true",
                   help="v2 phone alerts: action classifier + ear / lap phone checks (hybrid.py)")
    p.add_argument("--hybrid-models", default="models/action_v2",
                   help="folder with the three INT8 NCNN classifiers for --hybrid")
    p.add_argument("--no-detect", action="store_true",
                   help="do not run the phone / drink / food box detector at all")
    p.add_argument("--mesh", action="store_true", help="draw every face-mesh point on the view")
    p.add_argument("--rotate", type=int, choices=[0, 90, 180, 270], default=0,
                   help="rotate camera frames clockwise first (camera mounted upside down: 180)")
    a = p.parse_args(argv)
    # fields apply_overrides (run.py) expects
    a.detector_backend = a.hands = None
    a.per_frame_log = False
    return a


class DualStackServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        import socket

        if ":" in self.server_address[0]:
            self.address_family = socket.AF_INET6
            self.socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


def main(argv=None) -> int:
    args = parse_args(argv)
    shared = Shared()
    worker = threading.Thread(target=pipeline_loop, args=(args, shared), daemon=True)
    worker.start()
    srv = DualStackServer((args.host, args.port), make_handler(shared))
    print(f"[stream] open http://<this machine>:{args.port}  (Ctrl-C to stop)", flush=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        while worker.is_alive():
            worker.join(0.5)
    except KeyboardInterrupt:
        pass
    shared.running = False
    srv.shutdown()
    worker.join(5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
