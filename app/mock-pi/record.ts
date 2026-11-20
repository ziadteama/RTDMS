/**
 * Record a real Pi's /status at 5 Hz into JSON lines, for `server.ts --replay`.
 *
 *   node mock-pi/record.ts http://10.42.0.1:8080 drive.jsonl 300   # 300 s
 */
import { appendFileSync } from 'node:fs';

const [base = 'http://10.42.0.1:8080', out = 'drive.jsonl', seconds = '120'] = process.argv.slice(2);
const end = Date.now() + Number(seconds) * 1000;
let n = 0;
while (Date.now() < end) {
  const t = Date.now();
  try {
    const r = await fetch(`${base}/status`, { signal: AbortSignal.timeout(1000) });
    appendFileSync(out, JSON.stringify(await r.json()) + '\n');
    n++;
  } catch (e) {
    console.error(`[record] ${String(e)}`);
  }
  await new Promise((r) => setTimeout(r, Math.max(0, 200 - (Date.now() - t))));
}
console.log(`[record] ${n} lines -> ${out}`);
