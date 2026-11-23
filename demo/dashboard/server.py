"""Live demo dashboard for the RTDMS Pi: one full-screen page for the audience.

It reads what the Pi already serves and merges it into one JSON for the page:
  camera server  :8080  /status (face mesh drowsiness, v2 phone classifier, fps, ms, temp)
                        /stream.mjpg (loaded by the browser directly, never proxied)
  Pi runtime     :8090  /alert (fusion decision), /physio (Garmin watch), /health (5 s)
Standard library only. Nothing is written to disk. A source that does not answer is shown as
offline, never guessed.

  python3 server.py                     # on the Pi, open http://<pi>:8000
  python3 server.py --pi-host <pi-ip>   # on the laptop, reading the Pi over the network
  python3 server.py --mock              # scripted data, page shows SIMULATED
"""

from __future__ import annotations

import argparse
import json
import math
import threading
import time
from collections import deque
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
COMMANDS = ("/calibrate", "/reset")  # POSTs relayed to the camera server
FAST_S = 0.25  # camera status, alert, physio
HEALTH_S = 5.0  # /health runs vcgencmd on the Pi: keep it slow
TIMEOUT_S = 0.5
STALE_S = {"camera": 1.5, "alert": 2.0, "physio": 2.0, "health": 15.0}

# Drinking: the classifier judges each frame alone and, mid-sip from a frontal camera, scores
# drinking and "other" about equally, so the top label flickers. The camera now reports the
# drinking score every frame (hybrid p_drinking); its mean over 1.5 s (hybrid_alerts.py's
# drinking window) >= 0.4 shows drinking. Display only: fusion ignores drinking (decision D28).
DRINK_WIN_S = 1.5
DRINK_MEAN_P = 0.4
DRINK_MIN_SAMPLES = 3

Json = dict[str, Any]


class Source:
    """Latest JSON from one URL, with the monotonic time it arrived."""

    def __init__(self, url: str | None, clock: Callable[[], float]) -> None:
        self.url, self.clock = url, clock
        self.data: Json | None = None
        self.t: float | None = None

    def poll(self) -> bool:
        if self.url is None:
            return False
        try:
            with urlopen(self.url, timeout=TIMEOUT_S) as r:
                data = json.load(r)
        except (OSError, ValueError):
            return False
        if not isinstance(data, dict):
            return False
        self.data, self.t = data, self.clock()
        return True

    def set(self, data: Json) -> None:
        self.data, self.t = data, self.clock()

    def fresh(self, now: float, stale_s: float) -> Json | None:
        if self.data is None or self.t is None or now - self.t > stale_s:
            return None
        return self.data

    def age(self, now: float) -> float | None:
        return None if self.t is None else round(now - self.t, 1)


class DrinkDebounce:
    """Mean drinking score over the last DRINK_WIN_S; drinking when it is >= DRINK_MEAN_P."""

    def __init__(self) -> None:
        self.samples: deque[tuple[float, float]] = deque()
        self.mean: float | None = None

    def reset(self) -> None:
        self.samples.clear()
        self.mean = None

    def update(self, t: float, action: Any, p: Any, p_drinking: Any = None) -> bool:
        if num(p_drinking) is not None:  # the score itself, even when another class wins
            score = float(p_drinking)
        else:  # older camera script: only the top class and its probability
            score = float(p) if action == "drinking" and num(p) is not None else 0.0
        self.samples.append((t, score))
        while self.samples and t - self.samples[0][0] > DRINK_WIN_S:
            self.samples.popleft()
        n = len(self.samples)
        self.mean = sum(s for _, s in self.samples) / n
        return n >= DRINK_MIN_SAMPLES and self.mean >= DRINK_MEAN_P


def num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def merge(cam: Json | None, alert: Json | None, physio: Json | None, health: Json | None,
          drinking: bool, drink_score: float | None = None) -> Json:
    """One view for the page. A part is None when its source is offline or stale."""
    out: Json = {"eyes": None, "phone": None, "drinking": None, "heart": None, "alert": None}
    perf: Json = {}
    if cam is not None:
        d = cam.get("drowsiness") or {}
        h = cam.get("hybrid") or {}
        out["eyes"] = {
            "face": bool(cam.get("face")),
            "state": d.get("state"),
            "openness": num(d.get("openness")),
            "perclos": num(d.get("perclos")),
            "perclos_valid": bool(d.get("perclos_valid")),
            "blink_rate": num(d.get("blink_rate")),
            "closure_ms": num(d.get("closure_ms")),
            "calibrated": bool(d.get("calibrated")),
            "calibration_step": d.get("calibration_step"),
            "calibration_left_s": num(d.get("calibration_left_s")),
        }
        out["phone"] = {k: h.get(k) for k in ("face", "call", "action", "p", "ear")}
        out["drinking"] = {"face": h.get("face"), "detected": drinking,
                           "p": None if drink_score is None else round(drink_score, 2)}
        ms = {k: v for k, v in (cam.get("ms") or {}).items() if num(v) is not None}
        perf.update(fps=num(cam.get("fps")), stages_ms=ms,
                    processing_ms=round(sum(ms.values()), 1) if ms else None,
                    temp_c=num(cam.get("temp_c")))
    if alert is not None:
        out["alert"] = {"pattern": alert.get("pattern", "none"),
                        "reasons": alert.get("reasons") or [],
                        "episode": alert.get("episode"), "emergency": alert.get("emergency")}
    if physio is not None:
        out["heart"] = {
            "watch_connected": bool(physio.get("watch_connected")),
            "hr_bpm": num(physio.get("hr_bpm")),
            "baseline_bpm": num(physio.get("hr_baseline_bpm")),
            "delta_bpm": num(physio.get("hr_delta_bpm")),
            "worn": physio.get("worn"),
            "quality": physio.get("quality"),
        }
    if health is not None:
        diag = health.get("physio_diag") or {}
        perf.update(cpu_pct=num(health.get("cpu_pct")), throttled=health.get("throttled"),
                    volts_5v=num(health.get("volts_5v")),
                    watch_rtt_p50_ms=num(diag.get("watch_alert_rtt_p50_ms")),
                    watch_rtt_p95_ms=num(diag.get("watch_alert_rtt_p95_ms")),
                    camera=health.get("camera"))
        if perf.get("temp_c") is None:
            perf["temp_c"] = num(health.get("temp_c"))
    out["perf"] = perf
    return out


class Dashboard:
    def __init__(self, pi_host: str, stream_port: int, runtime_port: int, mock: bool,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.clock, self.mock = clock, mock
        host = f"[{pi_host}]" if ":" in pi_host else pi_host
        cam = None if mock else f"http://{host}:{stream_port}/status"
        rt = None if mock else f"http://{host}:{runtime_port}"
        self.sources = {
            "camera": Source(cam, clock),
            "alert": Source(rt and rt + "/alert", clock),
            "physio": Source(rt and rt + "/physio", clock),
            "health": Source(rt and rt + "/health", clock),
        }
        # The camera MJPEG and its commands are relayed through this server: one address only.
        self.camera_base = None if mock else f"http://{host}:{stream_port}"
        self.stream_url = self.camera_base and self.camera_base + "/stream.mjpg"
        self.drink = DrinkDebounce()
        self.drinking = False
        self.lock = threading.Lock()
        self.t0 = clock()
        self._next_health = 0.0

    def tick(self) -> None:
        """One polling round (or one mock step)."""
        if self.mock:
            with self.lock:
                for name, data in mock_sources(self.clock() - self.t0).items():
                    self.sources[name].set(data)
        else:
            for name in ("camera", "alert", "physio"):
                self.sources[name].poll()
            if self.clock() >= self._next_health:
                self.sources["health"].poll()
                self._next_health = self.clock() + HEALTH_S
        now = self.clock()
        with self.lock:
            cam = self.sources["camera"].fresh(now, STALE_S["camera"])
            if cam is None:
                self.drink.reset()
                self.drinking = False
            else:
                h = cam.get("hybrid") or {}
                self.drinking = self.drink.update(now, h.get("action"), h.get("p"),
                                                  h.get("p_drinking"))

    def state(self) -> Json:
        now = self.clock()
        with self.lock:
            fresh = {n: s.fresh(now, STALE_S[n]) for n, s in self.sources.items()}
            health = fresh["health"]
            if health is not None and health.get("camera") == "lost":
                fresh["camera"] = None
            out = merge(fresh["camera"], fresh["alert"], fresh["physio"], health,
                        self.drinking, self.drink.mean)
            out["links"] = {n: {"ok": fresh[n] is not None, "age_s": s.age(now)}
                            for n, s in self.sources.items()}
        heart = out["heart"]
        out["links"]["watch"] = {"ok": bool(heart and heart["watch_connected"]
                                            and heart["hr_bpm"] is not None)}
        out["mock"] = self.mock
        out["stream"] = self.stream_url is not None
        return out

    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            start = self.clock()
            self.tick()
            stop.wait(max(0.0, FAST_S - (self.clock() - start)))


# Scripted demo for rehearsing the page without the Pi: (start s, phase).
MOCK_PHASES = [(0, "normal"), (6, "closing"), (9, "drowsy"), (15, "normal"), (19, "phone"),
               (25, "normal"), (28, "drinking"), (33, "lookaway"), (37, "calibrate")]
MOCK_LOOP_S = 48


def mock_sources(t: float) -> dict[str, Json]:
    t %= MOCK_LOOP_S
    phase = [p for start, p in MOCK_PHASES if t >= start][-1]
    since = t - max(start for start, _ in MOCK_PHASES if start <= t)
    wobble = math.sin(t * 2.1)
    openness, state, closure, reasons, pattern = 0.92 + 0.04 * wobble, "alert", 0, [], "none"
    call = drinking = False
    action, p = "normal", 0.9
    step, left = None, None
    if phase == "closing":
        openness, state, closure = max(0.1, 0.9 - since * 0.3), "warning", int(since * 400)
    elif phase == "drowsy":
        openness, state, closure = 0.04, "drowsy", int(1200 + since * 1000)
        pattern, reasons = "repeated", ["face drowsy"]
    elif phase == "phone":
        action, p = "call", 0.93
        call = since > 2
        if call:
            pattern, reasons = "continuous", ["phone call"]
    elif phase == "drinking":
        action, p, drinking = "drinking", 0.88, True
    elif phase == "lookaway":
        state, pattern, reasons = "distracted", "short_beep", ["face distracted"]
    elif phase == "calibrate":
        if since < 3:
            step, left = "countdown_open", round(3 - since, 1)
        elif since < 8:
            step, left = "open", round(8 - since, 1)
        else:
            step, left = "closed", round(11 - since, 1)
            openness = 0.05
    perclos = 0.06 if phase not in ("closing", "drowsy") else min(0.6, 0.2 + since * 0.05)
    hr = 72 + 3 * math.sin(t / 5) + (6 if phase == "phone" else 0)
    cam = {
        "fps": round(14.6 + 0.6 * wobble, 1), "face": True, "temp_c": 61.5 + wobble,
        "ms": {"facemesh": 18.2, "rules": 0.4, "drowsiness": 3.1, "v2_phone": 24.7},
        "drowsiness": {"state": state, "openness": round(openness, 2),
                       "perclos": round(perclos, 2), "perclos_valid": True,
                       "blink_rate": 14, "closure_ms": closure, "calibrated": True,
                       "calibration_step": step, "calibration_left_s": left},
        "hybrid": {"face": True, "call": call, "action": action, "p": p,
                   "p_drinking": 0.88 if drinking else 0.05,
                   "ear": 0.81 if phase == "phone" else 0.03},
    }
    if drinking:
        cam["hybrid"]["action"] = "drinking"
    alert: Json = {"pattern": pattern, "reasons": reasons}
    if pattern != "none":
        alert["episode"] = 1 + [name for _, name in MOCK_PHASES].index(phase)
    physio = {"watch_connected": True, "hr_bpm": round(hr), "hr_baseline_bpm": 72,
              "hr_delta_bpm": round(hr - 72, 1), "worn": True, "quality": "good"}
    health = {"cpu_pct": round(48 + 5 * wobble), "temp_c": 61.5, "camera": "ok",
              "throttled": 0, "volts_5v": 5.08,
              "physio_diag": {"watch_alert_rtt_p50_ms": 62, "watch_alert_rtt_p95_ms": 91}}
    return {"camera": cam, "alert": alert, "physio": physio, "health": health}


def make_handler(dash: Dashboard) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, "text/html; charset=utf-8", (HERE / "index.html").read_bytes())
            elif path == "/state":
                self._send(200, "application/json", json.dumps(dash.state()).encode())
            elif path == "/stream.mjpg" and dash.stream_url:
                self._relay(dash.stream_url)
            else:
                self._send(404, "text/plain", b"not found")

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path not in COMMANDS:
                self._send(404, "text/plain", b"not found")
            elif dash.camera_base is None:
                self._reply(409, "not available with simulated data")
            else:
                self._command(dash.camera_base + path)

        def _command(self, url: str) -> None:
            """POST with an empty body to the camera server (calibrate = Pi-camera calibration,
            reset = clear the drowsiness readings) and pass its answer back."""
            try:
                with urlopen(Request(url, data=b"", method="POST"), timeout=3) as r:
                    self._send(r.status, "application/json", r.read(4096) or b'{"ok": true}')
            except HTTPError as e:
                why = "not on this Pi yet" if e.code == 404 else f"camera said {e.code}"
                self._reply(e.code, why)
            except OSError:
                self._reply(502, "camera server not answering")

        def _reply(self, code: int, error: str) -> None:
            self._send(code, "application/json", json.dumps({"ok": False, "error": error}).encode())

        def _relay(self, url: str) -> None:
            """Copy the camera's MJPEG through; the camera only encodes while someone watches."""
            try:
                up = urlopen(url, timeout=5)
            except OSError:
                self._send(502, "text/plain", b"camera stream offline")
                return
            with up:
                self.send_response(200)
                self.send_header("Content-Type", up.headers.get("Content-Type", ""))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    while chunk := up.read1(65536):
                        self.wfile.write(chunk)
                except OSError:
                    pass  # viewer closed the page, or the camera stopped

        def _send(self, code: int, ctype: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass

    return Handler


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pi-host", default="127.0.0.1", help="where the Pi services run")
    ap.add_argument("--stream-port", type=int, default=8080)
    ap.add_argument("--runtime-port", type=int, default=8090)
    ap.add_argument("--host", default="0.0.0.0", help="address this page listens on")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--mock", action="store_true", help="scripted data, shown as SIMULATED")
    a = ap.parse_args(argv)
    dash = Dashboard(a.pi_host, a.stream_port, a.runtime_port, a.mock)
    stop = threading.Event()
    threading.Thread(target=dash.run, args=(stop,), daemon=True, name="poll").start()
    server = ThreadingHTTPServer((a.host, a.port), make_handler(dash))
    print(f"dashboard on http://{a.host}:{a.port}  ({'MOCK' if a.mock else a.pi_host})",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()


if __name__ == "__main__":
    main()
