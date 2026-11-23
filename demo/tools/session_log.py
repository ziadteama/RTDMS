"""Record a test session on the Pi: one camera frame + camera /status + runtime /alert every
PERIOD s, until STOP exists in the output dir or MAX_S passes. Stdlib only."""
import json
import os
import sys
import threading
import time
import urllib.request

OUT = sys.argv[1]
PERIOD, MAX_S = 0.5, 600
os.makedirs(OUT, exist_ok=True)
latest = {"jpg": None}


def reader():
    r = urllib.request.urlopen("http://localhost:8080/stream.mjpg", timeout=10)
    buf = b""
    while True:
        chunk = r.read1(65536)
        if not chunk:
            return
        buf += chunk
        e = buf.rfind(b"\xff\xd9")
        if e < 0:
            continue
        s = buf.rfind(b"\xff\xd8", 0, e)
        if s >= 0:
            latest["jpg"] = buf[s:e + 2]
        buf = buf[e + 2:]


def get(url):
    try:
        return json.load(urllib.request.urlopen(url, timeout=1))
    except Exception as ex:  # noqa: BLE001
        return {"error": str(ex)}


threading.Thread(target=reader, daemon=True).start()
t0 = time.time()
i = 0
with open(os.path.join(OUT, "log.jsonl"), "a") as log:
    while time.time() - t0 < MAX_S and not os.path.exists(os.path.join(OUT, "STOP")):
        tick = time.time()
        st, al = get("http://localhost:8080/status"), get("http://localhost:8090/alert")
        jpg = latest["jpg"]
        name = None
        if jpg:
            name = f"f{i:05d}.jpg"
            with open(os.path.join(OUT, name), "wb") as f:
                f.write(jpg)
        log.write(json.dumps({"i": i, "t": round(tick - t0, 2), "clock": time.strftime("%T"),
                              "frame": name, "status": st, "alert": al}) + "\n")
        log.flush()
        if i % 20 == 0:
            d = st.get("drowsiness") or {}
            print(f"{time.strftime('%T')} {i} face={st.get('face')} state={d.get('state')} "
                  f"open={d.get('openness')} ear={d.get('ear')} alert={al.get('pattern')}",
                  flush=True)
        i += 1
        time.sleep(max(0.0, PERIOD - (time.time() - tick)))
print("stopped after", i, "samples", flush=True)
