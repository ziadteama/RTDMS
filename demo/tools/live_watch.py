"""Watch the live dashboard: print drinking scores, save frames while drinking is shown."""
import json
import os
import sys
import threading
import time
import urllib.request

OUT, SECS = sys.argv[1], float(sys.argv[2])
os.makedirs(OUT, exist_ok=True)
latest = {"jpg": None}


def reader():
    r = urllib.request.urlopen("http://localhost:8080/stream.mjpg", timeout=10)
    buf = b""
    while True:
        c = r.read1(65536)
        if not c:
            return
        buf += c
        e = buf.rfind(b"\xff\xd9")
        if e < 0:
            continue
        s = buf.rfind(b"\xff\xd8", 0, e)
        if s >= 0:
            latest["jpg"] = buf[s:e + 2]
        buf = buf[e + 2:]


def get(url):
    return json.load(urllib.request.urlopen(url, timeout=1))


threading.Thread(target=reader, daemon=True).start()
t0, n, saved = time.time(), 0, 0
while time.time() - t0 < SECS:
    try:
        st, cam = get("http://localhost:8000/state"), get("http://localhost:8080/status")
    except Exception:
        time.sleep(0.25)
        continue
    h, d = cam.get("hybrid") or {}, st.get("drinking") or {}
    shown = d.get("detected")
    line = (f"{time.time() - t0:5.1f}s top={h.get('action')} p={h.get('p')} "
            f"p_drink={h.get('p_drinking')} avg={d.get('p')} shown={shown}")
    if n % 4 == 0 or shown:
        print(line, flush=True)
    if shown and latest["jpg"] and saved < 6 and n % 2 == 0:
        with open(os.path.join(OUT, f"drink_{saved}_{time.time() - t0:.0f}s.jpg"), "wb") as f:
            f.write(latest["jpg"])
        saved += 1
    n += 1
    time.sleep(0.25)
print("saved", saved, "frames")
