# ruff: noqa: E501  (the PAGE string holds the HTML / JS page; its lines are not Python)
"""Live view of the Garmin stream on the Pi: the latest state as a thread-safe dict, plus a tiny
web page (standard library only) that shows it.

    LiveState      latest() -> one timestamped dict: link counters, last packet, recent beats,
                   latest HRV snapshot. Safe to read from any thread (the camera pipeline, a
                   web handler) while the receiver's event loop updates it.
    serve(state)   http://<pi>:8081/        page: HR, link, beats chart, HRV + quality
                   http://<pi>:8081/status  the same data as JSON (what RTDMS / fusion polls)

Times: `t_monotonic` values are the Pi's time.monotonic(), the same clock the camera frames use,
so HRV snapshots line up with video frames. `age_s` fields say how old each part is.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .garmin_hrv import HrvSnapshot
from .garmin_rr import RrFrame, SequenceTracker

RECENT_BEATS = 90  # beats kept for the page's chart (~1-1.5 min)


class LiveState:
    def __init__(self, tracker: SequenceTracker) -> None:
        self._lock = threading.Lock()
        self._tracker = tracker
        self._last_frame: dict[str, Any] | None = None
        self._last_rx: float | None = None
        self._beats: deque[tuple[float, int]] = deque(maxlen=RECENT_BEATS)  # (t, rr ms)
        self._hrv: dict[str, Any] | None = None
        self._started = time.monotonic()
        self.decode_errors = 0

    def on_frame(self, f: RrFrame) -> None:
        p = f.packet
        with self._lock:
            self._last_rx = f.rx_monotonic
            self._last_frame = {"seq": p.seq, "hr_bpm": p.hr_bpm, "rr_ms": list(p.rr_ms),
                                "t_monotonic": round(f.rx_monotonic, 3),
                                "t_wall": round(f.rx_wall, 3), "session": f.session}
            for rr in p.rr_ms:
                self._beats.append((round(f.rx_monotonic, 3), int(rr)))

    def on_hrv(self, snap: HrvSnapshot) -> None:
        with self._lock:
            self._hrv = snap.to_dict()

    def latest(self) -> dict[str, Any]:
        """A copy of everything, stamped now. The one call other subsystems need."""
        now = time.monotonic()
        with self._lock:
            t = self._tracker
            age = None if self._last_rx is None else round(now - self._last_rx, 1)
            return {
                "t_monotonic": round(now, 3), "t_wall": round(time.time(), 3),
                "uptime_s": round(now - self._started),
                "link": {"receiving": age is not None and age < 5.0, "last_packet_age_s": age,
                         "packets": t.received, "lost": t.lost, "duplicates": t.duplicates,
                         "late": t.late, "decode_errors": self.decode_errors,
                         "loss_fraction": round(t.loss_fraction(), 4), "sessions": t.session},
                "last_packet": dict(self._last_frame) if self._last_frame else None,
                "recent_rr_ms": [rr for _, rr in self._beats],
                "hrv": dict(self._hrv) if self._hrv else None,
            }


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>RTDMS heart</title>
<style>
:root{--bg:#111;--fg:#e8e8e8;--dim:#9a9a9a;--card:#1b1b1b;--line:#333;--ok:#3ccf6e;--warn:#f2b232;
--bad:#ff5a4f;--rr:#5aa9ff}
body{margin:0;background:var(--bg);color:var(--fg);font:15px system-ui,sans-serif}
main{max-width:860px;margin:auto;padding:16px;display:grid;gap:14px}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.k{color:var(--dim);font-size:13px}.v{font-size:28px;font-weight:650;margin-top:2px}
.big{font-size:56px;color:var(--bad)}h1{font-size:18px;margin:0}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
svg{width:100%;height:150px;display:block}table{width:100%;border-collapse:collapse}
td{padding:3px 0;border-bottom:1px solid var(--line)}td:last-child{text-align:right}
</style></head><body><main>
<h1>RTDMS &middot; Garmin heart data on the Pi <span id="link" class="k"></span></h1>
<div class="row">
 <div class="card"><div class="k">Heart rate (watch)</div><div class="v big" id="hr">--</div></div>
 <div class="card"><div class="k">Last packet</div><div class="v" id="age">--</div>
  <div class="k" id="seq"></div></div>
 <div class="card"><div class="k">Packets / lost / dup</div><div class="v" id="pk">--</div>
  <div class="k" id="loss"></div></div>
 <div class="card"><div class="k">Last RR (beat-to-beat)</div><div class="v" id="rr">--</div>
  <div class="k">ms between the last two beats</div></div>
</div>
<div class="card"><div class="k">RR intervals received (ms), newest on the right</div>
 <svg id="chart" viewBox="0 0 800 150" preserveAspectRatio="none"></svg></div>
<div class="row">
 <div class="card"><div class="k">HRV (60 s window, updated every 5 s)</div>
  <div class="v" id="state">--</div><table id="hrv"></table></div>
 <div class="card"><div class="k">Quality of the window</div><table id="qual"></table></div>
</div>
</main><script>
const $=id=>document.getElementById(id);
const cls=s=>({valid:'ok',good:'ok',degraded:'warn',warmup:'warn'}[s]||'bad');
function rows(el,pairs){el.innerHTML=pairs.map(([k,v])=>`<tr><td class=k>${k}</td><td>${v??'-'}</td></tr>`).join('')}
function chart(rr){const s=$('chart');if(rr.length<2){s.innerHTML='';return}
 const lo=Math.min(...rr)-30,hi=Math.max(...rr)+30,n=rr.length;
 const pts=rr.map((v,i)=>`${(i/(n-1)*800).toFixed(1)},${(150-(v-lo)/(hi-lo)*150).toFixed(1)}`).join(' ');
 s.innerHTML=`<polyline points="${pts}" fill="none" stroke="var(--rr)" stroke-width="2"/>`+
 `<text x="4" y="14" fill="var(--dim)" font-size="12">${Math.round(hi)} ms</text>`+
 `<text x="4" y="146" fill="var(--dim)" font-size="12">${Math.round(lo)} ms</text>`}
async function tick(){try{const s=await (await fetch('status')).json();const L=s.link,P=s.last_packet,H=s.hrv;
 $('link').textContent=L.receiving?'● receiving':'○ no data';$('link').className=L.receiving?'ok':'bad';
 $('hr').textContent=P&&P.hr_bpm?P.hr_bpm:'--';
 $('age').textContent=L.last_packet_age_s==null?'never':L.last_packet_age_s+' s ago';
 $('age').className='v '+(L.receiving?'ok':'bad');$('seq').textContent=P?`seq ${P.seq}, session ${P.session}`:'';
 $('pk').textContent=`${L.packets} / ${L.lost} / ${L.duplicates}`;
 $('loss').textContent=`loss ${(L.loss_fraction*100).toFixed(1)} %`;
 const rr=s.recent_rr_ms;$('rr').textContent=rr.length?rr[rr.length-1]:'--';chart(rr);
 if(H){$('state').textContent=H.state.toUpperCase();$('state').className='v '+cls(H.state);
  rows($('hrv'),[['Mean HR (bpm)',H.mean_hr_bpm],['RMSSD (ms)',H.rmssd_ms],['SDNN (ms)',H.sdnn_ms],
   ['pNN50',H.pnn50]]);
  rows($('qual'),[['Quality',`<span class=${cls(H.quality)}>${H.quality}</span>`],
   ['Beats in window',H.valid_beats],['Beat coverage',H.coverage],['Rejected beats',H.artifacts],
   ['Packet loss',H.packet_loss],['Breaks in the beat chain',H.gaps]])}
}catch(e){$('link').textContent='○ page cannot reach the Pi';$('link').className='bad'}}
setInterval(tick,1000);tick();
</script></body></html>"""


def serve(state: LiveState, port: int = 8081, host: str = "::") -> ThreadingHTTPServer:
    """Start the page + JSON server on a background thread and return it."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:  # keep the console for the receiver
            pass

        def _send(self, body: bytes, ctype: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            if self.path in ("/", "/index.html"):
                self._send(PAGE.encode(), "text/html; charset=utf-8")
            elif self.path.startswith("/status"):
                self._send(json.dumps(state.latest()).encode(), "application/json")
            else:
                self.send_error(404)

    class DualStack(ThreadingHTTPServer):
        daemon_threads = True

        def server_bind(self) -> None:
            import socket
            if ":" in str(self.server_address[0]):
                self.address_family = socket.AF_INET6
                self.socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            super().server_bind()

    server = DualStack((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="garmin-live").start()
    return server
