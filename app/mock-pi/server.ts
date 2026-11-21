/**
 * Mock Pi for Sahi. Serves the real stream.py endpoints (/status, /stream.mjpg, POST /calibrate)
 * in their exact shape, plus every proposed endpoint from app/docs/API.md.
 *
 *   node mock-pi/server.ts                         # synthetic two-minute drive, port 8080
 *   node mock-pi/server.ts --port 8090 --host 0.0.0.0
 *   node mock-pi/server.ts --replay drive.jsonl     # replay /status lines recorded from a real Pi
 *                                                   # (mock-pi/record.ts writes them)
 *   node mock-pi/server.ts --freeze 92              # hold the scenario at 92 s (drowsy): screenshots
 *
 * Node >= 22.18 (type stripping on by default). No dependencies.
 */
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

import {
  SCENARIO_LENGTH_S,
  alertAt,
  healthAt,
  incidentFrames,
  physioAt,
  statusAt,
} from '../src/demo/scenario.ts';
import type {
  AlertPattern,
  IncidentFrame,
  IncidentRequest,
  PiIncident,
  PiSettings,
  PiStatus,
} from '../src/pi/types.ts';
import { ALERT_PATTERNS } from '../src/pi/types.ts';

const { values: args } = parseArgs({
  options: {
    port: { type: 'string', default: '8080' },
    host: { type: 'string', default: '0.0.0.0' },
    replay: { type: 'string' },
    freeze: { type: 'string' },
  },
});

const here = dirname(fileURLToPath(import.meta.url));
const frames = Array.from({ length: 10 }, (_, i) => readFileSync(join(here, 'assets', `frame${i}.jpg`)));
const clip = readFileSync(join(here, 'assets', 'clip.mp4'));
const started = Date.now();
const frozen = args.freeze !== undefined ? Number(args.freeze) : null;
const now = () => frozen ?? (Date.now() - started) / 1000;

const replay: PiStatus[] | null = args.replay
  ? readFileSync(args.replay, 'utf8')
      .split('\n')
      .filter(Boolean)
      .map((l) => JSON.parse(l) as PiStatus)
  : null;

let calibration: { until: number } | null = null;
let calibrated = true;
let testAlert: { pattern: AlertPattern; until: number } | null = null;
const settings: PiSettings = {
  profile: 'default',
  profiles: ['default', 'driver-2'],
  sensitivity: 'normal',
  eye_closure_s: 2.0,
  offroad_gaze_s: 2.0,
  phone_s: 1.0,
  detectors: { drowsiness: true, distraction: true, phone: true, physiology: true },
};
const incidents: (PiIncident & { frames: IncidentFrame[] })[] = [];

function status(): PiStatus {
  const t = now();
  if (replay && replay.length) return replay[Math.floor(t * 5) % replay.length]!; // recorded at 5 Hz
  let cal = { message: calibrated ? 'calibrated' : 'not calibrated: press Calibrate', calibrated };
  if (calibration) {
    if (t < calibration.until) cal = { message: 'calibrating', calibrated };
    else {
      calibration = null;
      calibrated = true;
      cal = { message: 'calibrated', calibrated: true };
    }
  }
  return statusAt(t, cal);
}

function json(res: ServerResponse, body: unknown, code = 200) {
  const b = Buffer.from(JSON.stringify(body));
  res.writeHead(code, {
    'Content-Type': 'application/json',
    'Content-Length': b.length,
    'Cache-Control': 'no-store',
  });
  res.end(b);
}

async function body(req: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  for await (const c of req) chunks.push(c as Buffer);
  const s = Buffer.concat(chunks).toString('utf8');
  return s ? JSON.parse(s) : {};
}

function stream(req: IncomingMessage, res: ServerResponse) {
  res.writeHead(200, {
    'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
    'Cache-Control': 'no-store',
  });
  let i = 0;
  const timer = setInterval(() => {
    const jpeg = frames[i++ % frames.length]!;
    res.write(`--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${jpeg.length}\r\n\r\n`);
    res.write(jpeg);
    res.write('\r\n');
  }, 100); // stream.py default --stream-fps 10
  req.on('close', () => clearInterval(timer));
}

function makeIncident(r: IncidentRequest): PiIncident & { frames: IncidentFrame[] } {
  return {
    id: new Date().toISOString().replace(/[:.]/g, '-'),
    t_crash: r.t_crash,
    g_peak: r.g_peak,
    lat: r.lat,
    lon: r.lon,
    duration_s: 25,
    clip_ready: true,
    frames: incidentFrames(now(), r.t_crash),
  };
}

const server = createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*'); // the web build runs on another port
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS');
  const url = new URL(req.url ?? '/', 'http://mock');
  const path = url.pathname;
  try {
    if (req.method === 'OPTIONS') return void res.writeHead(204).end();
    if (req.method === 'GET') {
      if (path === '/status') return json(res, status());
      if (path === '/stream.mjpg') return stream(req, res);
      if (path === '/alert') {
        const t = now();
        if (testAlert && t < testAlert.until)
          return json(res, { pattern: testAlert.pattern, reasons: ['test alert'], t });
        return json(res, alertAt(t));
      }
      if (path === '/physio') return json(res, physioAt(now()));
      if (path === '/health') return json(res, healthAt(now(), now() + 3600));
      if (path === '/settings') return json(res, settings);
      if (path === '/incidents')
        return json(res, incidents.map(({ frames: _f, ...i }) => i));
      const m = path.match(/^\/incidents\/([^/]+)\/(clip\.mp4|data\.jsonl|meta\.json)$/);
      if (m) {
        const inc = incidents.find((i) => i.id === m[1]);
        if (!inc) return json(res, { error: 'no such incident' }, 404);
        if (m[2] === 'clip.mp4') {
          res.writeHead(200, { 'Content-Type': 'video/mp4', 'Content-Length': clip.length });
          return void res.end(clip);
        }
        if (m[2] === 'data.jsonl') {
          res.writeHead(200, { 'Content-Type': 'application/x-ndjson' });
          return void res.end(inc.frames.map((f) => JSON.stringify(f)).join('\n') + '\n');
        }
        const { frames: _f, ...meta } = inc;
        return json(res, meta);
      }
    }
    if (req.method === 'POST') {
      if (path === '/calibrate') {
        calibration = { until: now() + 13 }; // stream.py: 10 s eyes open + 3 s closed
        return json(res, { ok: true });
      }
      if (path === '/test_alert') {
        const b = (await body(req)) as { pattern?: string };
        const pattern = ALERT_PATTERNS.find((p) => p === b.pattern);
        if (!pattern) return json(res, { error: `pattern must be one of ${ALERT_PATTERNS.join(', ')}` }, 400);
        testAlert = { pattern, until: now() + 3 };
        return json(res, { ok: true });
      }
      if (path === '/incident') {
        const b = (await body(req)) as Partial<IncidentRequest>;
        if (typeof b.t_crash !== 'number' || typeof b.g_peak !== 'number')
          return json(res, { error: 't_crash and g_peak are required numbers' }, 400);
        const inc = makeIncident({ t_crash: b.t_crash, g_peak: b.g_peak, lat: b.lat ?? null, lon: b.lon ?? null });
        incidents.unshift(inc);
        return json(res, { id: inc.id });
      }
      if (path === '/system/restart' || path === '/system/shutdown') {
        console.log(`[mock-pi] ${path} requested (ignored by the mock)`);
        return json(res, { ok: true });
      }
    }
    if (req.method === 'PUT' && path === '/settings') {
      const b = (await body(req)) as Partial<PiSettings>;
      Object.assign(settings, b, { detectors: { ...settings.detectors, ...(b.detectors ?? {}) } });
      return json(res, settings);
    }
    json(res, { error: 'not found' }, 404);
  } catch (e) {
    json(res, { error: String(e) }, 400);
  }
});

server.listen(Number(args.port), args.host, () => {
  console.log(
    `[mock-pi] http://${args.host}:${args.port}  ${replay ? `replaying ${replay.length} recorded lines` : `synthetic ${SCENARIO_LENGTH_S} s drive, looping`}`,
  );
});
