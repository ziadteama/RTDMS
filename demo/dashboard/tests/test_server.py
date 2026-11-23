import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402

CAM = {
    "fps": 14.2, "face": True, "temp_c": 63.0, "ms": {"facemesh": 18.0, "v2_phone": 25.0},
    "drowsiness": {"state": "drowsy", "openness": 0.05, "perclos": 0.4, "perclos_valid": True,
                   "blink_rate": 9, "closure_ms": 2100, "calibrated": True,
                   "calibration_step": None, "calibration_left_s": None},
    "hybrid": {"face": True, "call": False, "texting": False, "action": "drinking", "p": 0.9,
               "ear": 0.02, "lap": 0.01},
}
RUNTIME = {
    "/alert": {"pattern": "repeated", "reasons": ["face drowsy"], "t": 1, "t_src": "pi",
               "episode": 3},
    "/physio": {"watch_connected": True, "hr_bpm": 66, "hr_baseline_bpm": 70,
                "hr_delta_bpm": -4.0, "worn": True, "quality": "good", "t": 1, "t_src": "pi"},
    "/health": {"cpu_pct": 55, "temp_c": 60.0, "camera": "ok", "throttled": 0, "volts_5v": 5.1,
                "physio_diag": {"watch_alert_rtt_p50_ms": 60, "watch_alert_rtt_p95_ms": 90}},
}


def serve(routes):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = json.dumps(routes[self.path]).encode() if self.path in routes else b""
            self.send_response(200 if body else 404)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def pi():
    cam, rt = serve({"/status": CAM}), serve(RUNTIME)
    yield cam.server_address[1], rt.server_address[1]
    cam.shutdown()
    rt.shutdown()


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_merged_state_from_live_sources(pi):
    clock = Clock()
    d = server.Dashboard("127.0.0.1", pi[0], pi[1], mock=False, clock=clock)
    for _ in range(4):  # drinking needs a few samples
        d.tick()
        clock.t += 0.25
    s = d.state()
    assert s["mock"] is False
    assert s["stream"] is True
    assert all(s["links"][k]["ok"] for k in ("camera", "alert", "physio", "health", "watch"))
    assert s["eyes"]["state"] == "drowsy" and s["eyes"]["closure_ms"] == 2100
    assert s["alert"] == {"pattern": "repeated", "reasons": ["face drowsy"], "episode": 3,
                          "emergency": None}
    assert s["heart"]["hr_bpm"] == 66 and s["heart"]["baseline_bpm"] == 70
    assert s["drinking"] == {"face": True, "detected": True, "p": 0.9}
    assert s["phone"]["face"] is True
    assert s["perf"]["processing_ms"] == 43.0
    assert s["perf"]["temp_c"] == 63.0  # the camera's reading wins over /health
    assert s["perf"]["watch_rtt_p95_ms"] == 90 and s["perf"]["volts_5v"] == 5.1


def test_unreachable_pi_is_offline_not_guessed():
    d = server.Dashboard("127.0.0.1", 9, 9, mock=False)  # port 9: nothing listens
    d.tick()
    s = d.state()
    assert not any(v["ok"] for v in s["links"].values())
    for part in ("eyes", "phone", "drinking", "heart", "alert"):
        assert s[part] is None
    assert s["perf"] == {}


def test_stale_camera_goes_offline_and_clears_drinking(pi):
    clock = Clock()
    d = server.Dashboard("127.0.0.1", pi[0], pi[1], mock=False, clock=clock)
    for _ in range(4):
        d.tick()
        clock.t += 0.25
    assert d.state()["drinking"]["detected"]
    d.sources["camera"].url = "http://127.0.0.1:9/status"
    clock.t += server.STALE_S["camera"] + 0.1
    d.tick()
    s = d.state()
    assert s["eyes"] is None and s["drinking"] is None and not s["links"]["camera"]["ok"]
    assert s["alert"] is not None  # the runtime still answers
    assert d.drinking is False


def test_camera_lost_in_health_hides_camera(pi):
    d = server.Dashboard("127.0.0.1", pi[0], pi[1], mock=False)
    d.tick()
    d.sources["health"].data = dict(RUNTIME["/health"], camera="lost")
    assert d.state()["eyes"] is None


def test_drinking_debounce():
    db = server.DrinkDebounce()
    assert not db.update(0.0, "drinking", 0.9)  # too few samples
    assert not db.update(0.25, "drinking", 0.9)
    assert db.update(0.5, "drinking", 0.9)
    assert db.update(0.75, "normal", 0.9)  # 3 of 4 = 75 % still holds
    assert not db.update(1.0, "normal", 0.9)  # 3 of 5 = 60 %
    db.reset()
    for i in range(6):  # low confidence never counts
        assert not db.update(i * 0.25, "drinking", 0.6)
    db.reset()
    for i in range(6):
        db.update(i * 0.25, "drinking", 0.9)
    assert not db.update(5.0, "normal", 0.9)  # old samples expire
    assert len(db.samples) == 1


def test_watch_disconnected_link():
    s = server.merge(None, None, {"watch_connected": False}, None, False)
    assert s["heart"]["watch_connected"] is False and s["heart"]["hr_bpm"] is None


def test_mock_is_flagged_and_covers_every_phase():
    clock = Clock()
    d = server.Dashboard("127.0.0.1", 8080, 8090, mock=True, clock=clock)
    seen = set()
    for _ in range(int(server.MOCK_LOOP_S / 0.25)):
        d.tick()
        s = d.state()
        assert s["mock"] is True and s["stream"] is False
        seen.add(s["alert"]["pattern"])
        if s["drinking"]["detected"]:
            seen.add("drinking")
        if s["eyes"]["calibration_step"]:
            seen.add("calibrating")
        clock.t += 0.25
    assert {"none", "short_beep", "repeated", "continuous", "drinking", "calibrating"} <= seen


def test_stream_is_relayed_on_one_address():
    mjpg = b"--frame\r\nContent-Type: image/jpeg\r\n\r\nJPEGDATA\r\n"

    class Cam(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            self.wfile.write(mjpg * 3)

        def log_message(self, *a):
            pass

    cam = ThreadingHTTPServer(("127.0.0.1", 0), Cam)
    threading.Thread(target=cam.serve_forever, daemon=True).start()
    d = server.Dashboard("127.0.0.1", cam.server_address[1], 9, mock=False)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(d))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with urlopen(f"http://127.0.0.1:{srv.server_address[1]}/stream.mjpg?t=1") as r:
            assert r.headers["Content-Type"].startswith("multipart/x-mixed-replace")
            assert r.read() == mjpg * 3
    finally:
        srv.shutdown()
        cam.shutdown()


def test_stream_offline_is_502():
    d = server.Dashboard("127.0.0.1", 9, 9, mock=False)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(d))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pytest.raises(OSError, match="502"):
            urlopen(f"http://127.0.0.1:{srv.server_address[1]}/stream.mjpg")
    finally:
        srv.shutdown()


def post(url):
    from urllib.request import Request

    try:
        with urlopen(Request(url, data=b"", method="POST")) as r:
            return r.status, json.load(r)
    except OSError as e:  # HTTPError
        body = e.read()
        return e.code, json.loads(body) if body.startswith(b"{") else body


def test_commands_are_relayed_to_the_camera():
    got = []

    class Cam(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            got.append((self.path, self.headers.get("Content-Length")))
            ok = self.path == "/calibrate"
            self.send_response(200 if ok else 404)
            self.end_headers()
            self.wfile.write(b'{"ok": true}' if ok else b"")

        def log_message(self, *a):
            pass

    cam = ThreadingHTTPServer(("127.0.0.1", 0), Cam)
    threading.Thread(target=cam.serve_forever, daemon=True).start()
    d = server.Dashboard("127.0.0.1", cam.server_address[1], 9, mock=False)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(d))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert post(base + "/calibrate") == (200, {"ok": True})
        assert got == [("/calibrate", "0")]  # empty body = Pi-camera calibration
        assert post(base + "/reset") == (404, {"ok": False, "error": "not on this Pi yet"})
        assert post(base + "/shutdown")[0] == 404 and len(got) == 2  # not relayed
    finally:
        srv.shutdown()
        cam.shutdown()


def test_commands_without_camera_or_in_mock():
    for mock, code in ((False, 502), (True, 409)):
        d = server.Dashboard("127.0.0.1", 9, 9, mock=mock)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(d))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            status, body = post(f"http://127.0.0.1:{srv.server_address[1]}/calibrate")
            assert status == code and body["ok"] is False
        finally:
            srv.shutdown()


def test_http_routes():
    d = server.Dashboard("127.0.0.1", 8080, 8090, mock=True)
    d.tick()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(d))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with urlopen(base + "/") as r:
            assert b"RTDMS" in r.read()
        with urlopen(base + "/state?x=1") as r:
            assert json.load(r)["mock"] is True
    finally:
        srv.shutdown()
