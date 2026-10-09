#!/usr/bin/env python3
"""
Face subsystem, served to a browser -- run.py for a headless Pi.

    python stream.py                         # LiteRT backend, http://0.0.0.0:8000
    python stream.py --host 100.x.y.z        # bind to one interface (e.g. Tailscale)
    python stream.py --calibrate             # force driver calibration at start

The page shows the same HUD as run.py plus a live panel (state, PERCLOS,
blinks, head pose, gaze) and the per-stage cost of every frame, CPU, RSS,
SoC temperature and throttle flags, so the Pi budget is visible while you test.

Calibration works as in run.py (10 s eyes open, 3 s closed) and is started
automatically when the profile does not exist yet, or from the page.

Frames are only drawn and JPEG-encoded while a browser is watching: with no
viewer the loop costs the pipeline alone, which is what a deployment pays.
Alerts are shown, not sounded -- the buzzer belongs to fusion.
"""

import os

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse  # noqa: E402
import json  # noqa: E402
import resource  # noqa: E402
import socketserver  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from http import server  # noqa: E402

import cv2  # noqa: E402

from dms_face.calibration import CalibrationCollector, DriverProfile, build_profile  # noqa: E402
from dms_face.camera import open_source  # noqa: E402
from dms_face.config import Config  # noqa: E402
from dms_face.hud import Hud  # noqa: E402
from dms_face.pipeline import FacePipeline  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description="Face DMS over HTTP (MJPEG + JSON)")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--profile", default="default", help="driver profile name")
    p.add_argument("--calibrate", action="store_true", help="force recalibration at start")
    p.add_argument("--backend", choices=["litert", "mediapipe"], default="litert")
    p.add_argument("--threads", type=int, default=1, help="inference threads (litert)")
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--ir", action="store_true", help="IR mode: apply CLAHE to luminance")
    p.add_argument("--no-flip", action="store_true", help="disable the mirror view")
    p.add_argument("--camera-calib", help="camera_calibration.json from calibrate_camera.py")
    p.add_argument("--config", help="config JSON to load")
    p.add_argument("--jpeg-quality", type=int, default=70)
    return p.parse_args()


def build_config(args):
    cfg = Config.from_json(args.config) if args.config else Config()
    cfg.camera.width, cfg.camera.height, cfg.camera.fps = args.width, args.height, args.fps
    cfg.camera.ir_mode = args.ir
    cfg.camera.flip_horizontal = not args.no_flip
    cfg.landmarker.backend = args.backend
    cfg.landmarker.num_threads = args.threads
    return cfg


# --------------------------------------------------------------------------
class WebCalibration:
    """run.py's two-phase calibration, as a per-frame state machine so the
    stream keeps flowing (and shows the prompts) while it runs."""

    COUNTDOWN_S = 3.0

    def __init__(self, cfg, profile_name):
        c = cfg.calibration
        self.cfg = c
        self.profile_name = profile_name
        self.phases = [
            ("open", c.open_phase_s, "Look straight ahead. Blink normally."),
            ("closed", c.closed_phase_s, "Now CLOSE your eyes and keep them closed."),
        ]
        self.index = 0
        self.counting_down = True
        self.t_phase = time.monotonic()
        self.collector = None
        self.results = {}

    def update(self, res):
        """Feed one processed frame. Returns (banner_lines, finished)."""
        key, duration, prompt = self.phases[self.index]
        now = time.monotonic()
        if self.counting_down:
            # Started from a browser, the driver is often not in frame yet;
            # hold the countdown until a face is, instead of failing later.
            if not res.face_present:
                self.t_phase = now
                return [prompt, "waiting for your face in view..."], False
            remaining = self.COUNTDOWN_S - (now - self.t_phase)
            if remaining > 0:
                return [prompt, f"starting in {int(remaining) + 1}..."], False
            self.counting_down = False
            self.collector = CalibrationCollector(self.cfg.settle_s).start()

        col = self.collector
        if res.face_present and res.ear_raw is not None:
            col.push(
                ear=res.ear_raw, h=res.gaze_h, v=res.gaze_v,
                yaw=res.angles[0] if res.angles else None,
                pitch=res.angles[1] if res.angles else None,
                roll=res.angles[2] if res.angles else None,
            )
        total = duration + self.cfg.settle_s
        if col.elapsed < total:
            remain = max(0.0, total - col.elapsed)
            status = "settle..." if col.settling else f"{remain:0.1f}s left"
            face = "" if res.face_present else "   NO FACE"
            return [prompt, f"{status}   samples={len(col.ear)}{face}"], False

        self.results[key] = col.result()
        self.index += 1
        if self.index < len(self.phases):
            self.counting_down, self.t_phase = True, now
            return [self.phases[self.index][2], "get ready..."], False
        return [], True

    def build(self):
        """Profile from the two phases; raises ValueError like build_profile."""
        profile = build_profile(self.profile_name, self.results["open"], self.results["closed"])
        profile.save()
        return profile


def draw_banner(bgr, lines):
    cv2.rectangle(bgr, (0, 0), (bgr.shape[1], 30 + 26 * len(lines)), (26, 20, 16), -1)
    cv2.putText(bgr, "CALIBRATING", (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (200, 170, 60), 2, cv2.LINE_AA)
    for i, line in enumerate(lines):
        cv2.putText(bgr, line, (12, 50 + 26 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (235, 235, 230), 1, cv2.LINE_AA)


# --------------------------------------------------------------------------
class SystemStats:
    """Process CPU, system CPU, RSS, SoC temperature, throttle flags."""

    def __init__(self):
        self._t = time.monotonic()
        self._cpu = time.process_time()
        self._sys = self._read_proc_stat()
        self._throttled = None
        self._throttle_t = 0.0
        self.values = {}

    @staticmethod
    def _read_proc_stat():
        try:
            with open("/proc/stat") as f:
                vals = [int(v) for v in f.readline().split()[1:]]
            idle = vals[3] + vals[4]
            return sum(vals), idle
        except OSError:
            return None

    def sample(self):
        now, cpu = time.monotonic(), time.process_time()
        dt = max(1e-6, now - self._t)
        proc_pct = (cpu - self._cpu) / dt * 100.0
        sys_pct = None
        cur = self._read_proc_stat()
        if cur and self._sys:
            dtot, didle = cur[0] - self._sys[0], cur[1] - self._sys[1]
            sys_pct = 100.0 * (1 - didle / dtot) if dtot > 0 else None
        self._t, self._cpu, self._sys = now, cpu, cur

        temp = None
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                temp = int(f.read()) / 1000.0
        except OSError:
            pass
        if now - self._throttle_t > 5.0:
            self._throttle_t = now
            try:
                out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True,
                                     text=True, timeout=2).stdout.strip()
                self._throttled = out.split("=")[-1] if out else None
            except (OSError, subprocess.SubprocessError):
                self._throttled = None

        self.values = {
            "proc_cpu_pct": round(proc_pct, 1),  # % of ONE core
            "sys_cpu_pct": None if sys_pct is None else round(sys_pct, 1),  # all cores
            "rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            "soc_temp_c": temp,
            "throttled": self._throttled,
        }
        return self.values


# --------------------------------------------------------------------------
class App:
    def __init__(self, args):
        self.args = args
        self.cfg = build_config(args)
        self.cond = threading.Condition()
        self.jpeg = None
        self.stats = {}
        self.viewers = 0
        self.requests = []  # actions from the page, run on the processing thread
        self.lock = threading.Lock()
        self.sysstats = SystemStats()

    def request(self, action):
        with self.lock:
            self.requests.append(action)

    def _pop_requests(self):
        with self.lock:
            out, self.requests = self.requests, []
        return out

    def _new_pipeline(self, profile, w, h):
        return FacePipeline(self.cfg, profile, width=w, height=h,
                            camera_calib=self.args.camera_calib)

    def run(self):
        args, cfg = self.args, self.cfg
        profile, loaded = DriverProfile.load_or_default(args.profile)
        print(f"[profile] {'loaded: ' + profile.describe() if loaded else 'none saved'}")
        source = open_source(cfg)
        print(f"[camera] {source.describe()}")
        with source:
            w, h = source.size
            pipeline = self._new_pipeline(profile, w, h)
            hud = Hud(w, h)
            calib = WebCalibration(cfg, args.profile) if (args.calibrate or not loaded) else None
            calib_msg = "calibrating" if calib else (
                f"profile '{profile.name}' ({profile.quality})" if loaded else "uncalibrated")
            last_ts, n_frames, t_last_sys = None, 0, 0.0

            while True:
                frame, ts = source.read()
                if frame is None or ts == last_ts:
                    time.sleep(0.002)
                    continue
                last_ts = ts

                for action in self._pop_requests():
                    if action == "calibrate":
                        calib, calib_msg = WebCalibration(cfg, args.profile), "calibrating"
                    elif action == "reset":
                        pipeline.perclos.reset()
                        pipeline.blink.reset()
                    elif action == "mesh":
                        hud.toggle_mesh()

                t0 = time.perf_counter()
                try:
                    res = pipeline.process(frame, ts)
                except Exception as exc:  # one bad frame must not end the session
                    print(f"[frame error] {type(exc).__name__}: {exc}")
                    continue
                t_pipe = (time.perf_counter() - t0) * 1000.0
                n_frames += 1

                banner = None
                if calib is not None:
                    banner, finished = calib.update(res)
                    if finished:
                        try:
                            profile = calib.build()
                            pipeline = self._new_pipeline(profile, w, h)
                            calib_msg = f"calibrated: {profile.describe()}"
                            advice = profile.quality_advice()
                            if advice:
                                calib_msg += f" -- {advice}"
                        except ValueError as exc:
                            calib_msg = f"calibration failed: {exc}"
                        print(f"[calibration] {calib_msg}")
                        calib, banner = None, None

                hud_ms = enc_ms = 0.0
                jpeg = None
                if self.viewers > 0:
                    t1 = time.perf_counter()
                    if banner is not None:
                        img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                        draw_banner(img, banner)
                    else:
                        img = hud.draw(frame, res, profile, cfg)
                    t2 = time.perf_counter()
                    ok, buf = cv2.imencode(".jpg", img,
                                           [cv2.IMWRITE_JPEG_QUALITY, args.jpeg_quality])
                    t3 = time.perf_counter()
                    hud_ms, enc_ms = (t2 - t1) * 1000.0, (t3 - t2) * 1000.0
                    jpeg = buf.tobytes() if ok else None

                now = time.monotonic()
                if now - t_last_sys >= 1.0:
                    self.sysstats.sample()
                    t_last_sys = now

                stats = self._stats(res, pipeline, profile, t_pipe, hud_ms, enc_ms,
                                    n_frames, calib is not None, calib_msg, banner)
                with self.cond:
                    if jpeg is not None:
                        self.jpeg = jpeg
                    self.stats = stats
                    self.cond.notify_all()

    def _stats(self, res, pipeline, profile, t_pipe, hud_ms, enc_ms, n_frames,
               calibrating, calib_msg, banner):
        rep = res.report
        lm = pipeline.landmarker
        angles = None
        if res.angles is not None:
            angles = [round(res.angles[0] - profile.yaw0, 1),
                      round(res.angles[1] - profile.pitch0, 1),
                      round(res.angles[2] - profile.roll0, 1)]

        def r(v, n=3):
            return None if v is None else round(float(v), n)

        out = {
            "state": rep.state.value if rep else "unavailable",
            "reasons": rep.reasons if rep else [],
            "should_alert": bool(rep and rep.should_alert),
            "perclos": r(rep.perclos if rep else None),
            "perclos_fast": r(rep.perclos_fast if rep else None),
            "perclos_valid": bool(rep and rep.perclos_valid),
            "perclos_warming": bool(rep and rep.perclos_warming),
            "perclos_span": r(rep.perclos_span if rep else None, 1),
            "perclos_window_s": self.cfg.perclos.primary_window_s,
            "perclos_min_window_s": self.cfg.perclos.min_window_s,
            "perclos_warn": self.cfg.perclos.warn_threshold,
            "perclos_drowsy": self.cfg.perclos.drowsy_threshold,
            "validity": r(rep.validity if rep else None),
            "closure_ms": r(rep.closure_ms if rep else None, 0),
            "blink_rate": r(rep.blink_rate if rep else None, 1),
            "mean_blink_ms": r(rep.mean_blink_ms if rep else None, 0),
            "blinks": len(pipeline.blink.events),
            "gaze_off_road_s": r(rep.gaze_off_road_s if rep else None, 2),
            "eye_channel_available": bool(rep.eye_channel_available) if rep else False,
            "face": res.face_present,
            "eye_state": res.eye_state.value,
            "eye_valid": res.eye_channel_valid,
            "openness": r(res.openness_smooth),
            "ear": r(res.ear_filtered, 4),
            "head_ypr": angles,
            "gaze_dev": r(res.gaze_dev),
            "perf": {
                "fps": round(res.fps, 1),
                "pipeline_ms": round(t_pipe, 2),
                "inference_ms": round(res.inference_ms, 2),
                "detector_ms": round(getattr(lm, "last_detector_ms", 0.0), 2),
                "mesh_ms": round(getattr(lm, "last_mesh_ms", res.inference_ms), 2),
                "post_ms": round(res.total_ms - res.inference_ms, 2),
                "hud_ms": round(hud_ms, 2),
                "jpeg_ms": round(enc_ms, 2),
                "detector_runs": getattr(lm, "detector_runs", None),
                "frames": n_frames,
                "face_rate": r(pipeline.frames_with_face / max(1, pipeline.frames_processed)),
                "backend": self.cfg.landmarker.backend,
                "threads": self.cfg.landmarker.num_threads,
                "resolution": f"{pipeline.width}x{pipeline.height}",
                "viewers": self.viewers,
                **self.sysstats.values,
            },
            "calibrating": calibrating,
            "calibration_prompt": banner,
            "calibration": calib_msg,
            "profile": profile.describe(),
            "camera_calibrated": pipeline.headpose.calibrated,
        }
        return out


app = None

PAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stream_page.html")


class Handler(server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(PAGE_PATH, "rb") as f:
                self._send(f.read(), "text/html; charset=utf-8")
        elif self.path == "/stats":
            with app.cond:
                body = json.dumps(app.stats).encode()
            self._send(body, "application/json")
        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            with app.cond:
                app.viewers += 1
            try:
                while True:
                    with app.cond:
                        app.cond.wait(timeout=2.0)
                        frame = app.jpeg
                    if frame is None:
                        continue
                    self.wfile.write(b"--FRAME\r\nContent-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame + b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with app.cond:
                    app.viewers -= 1
        else:
            self._send(b"not found", "text/plain", 404)

    def do_POST(self):
        action = self.path.strip("/")
        if action in ("calibrate", "reset", "mesh"):
            app.request(action)
            self._send(b'{"ok":true}', "application/json")
        else:
            self._send(b"not found", "text/plain", 404)


class Server(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    global app
    args = parse_args()
    app = App(args)
    worker = threading.Thread(target=app.run, daemon=True, name="pipeline")
    worker.start()
    print(f"[stream] http://{args.host}:{args.port}  backend={args.backend} "
          f"threads={args.threads}")
    srv = Server((args.host, args.port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        while worker.is_alive():
            worker.join(timeout=1.0)
    except KeyboardInterrupt:
        pass
    print("[stream] pipeline stopped")


if __name__ == "__main__":
    main()
