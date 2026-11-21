// Counts component re-renders on the Live tab while the app polls the Pi at 5 Hz (web build).
//   node scripts/render-count.mjs [seconds]     (mock Pi on :8080, `expo start --web` on :8081)
// A minimal React DevTools hook is installed before the app loads; on each commit it walks the
// fiber tree and counts components React actually re-ran (PerformedWork flag on an updated fiber).
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)('playwright');
const seconds = Number(process.argv[2] ?? 10);
const WATCH = ['Live', 'Banners', 'State', 'StateIndicator', 'Video', 'LiveView', 'Eyes', 'Heart', 'Phone', 'Speed', 'Sos', 'HoldButton', 'Metric'];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
await page.addInitScript((watch) => {
  performance.setResourceTimingBufferSize(100000);
  const counts = Object.fromEntries(watch.map((w) => [w, 0]));
  let commits = 0;
  let on = false;
  const PERFORMED_WORK = 1;
  // A bailed-out subtree is not cloned, so its fibers keep stale flags from their last render.
  // A fiber counts as re-rendered only if its props or hook state object changed since we last
  // saw that fiber object (both the current and alternate copies are recorded).
  const seen = new WeakMap();
  const nameOf = (f) => {
    const t = f.type;
    return t && (t.displayName || t.name || (t.type && (t.type.displayName || t.type.name)));
  };
  const walk = (fiber, count) => {
    const stack = [fiber];
    while (stack.length) {
      const f = stack.pop();
      if (!f) continue;
      const name = nameOf(f);
      if (name && name in counts) {
        const prev = seen.get(f);
        if (count && prev && f.flags & PERFORMED_WORK && (prev.p !== f.memoizedProps || prev.s !== f.memoizedState)) counts[name]++;
        seen.set(f, { p: f.memoizedProps, s: f.memoizedState });
        if (f.alternate) seen.set(f.alternate, { p: f.alternate.memoizedProps, s: f.alternate.memoizedState });
      }
      if (f.sibling) stack.push(f.sibling);
      if (f.child) stack.push(f.child);
    }
  };
  let lastRoot = null;
  window.__renderStats = { start: () => { if (lastRoot) walk(lastRoot.current, false); on = true; for (const k in counts) counts[k] = 0; commits = 0; }, read: () => ({ commits, counts }) };
  window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
    supportsFiber: true,
    renderers: new Map(),
    inject(r) { const id = this.renderers.size + 1; this.renderers.set(id, r); return id; },
    onCommitFiberRoot(_id, root) { lastRoot = root; if (on) commits++; walk(root.current, on); },
    onCommitFiberUnmount() {},
    onPostCommitFiberRoot() {},
    checkDCE() {},
  };
}, WATCH);
await page.goto('http://localhost:8081/');
await page.evaluate(() => {
  localStorage.setItem('sahi.settings', JSON.stringify({ version: 1, state: { consentedAt: 1, onboarded: true, theme: 'dark', units: 'kmh', baseUrl: 'http://localhost:8080', demo: false, paused: false, sound: false, volume: 1, vibration: 'strong', crashDetection: true, callTarget: 'ambulance', ambulanceNumber: '123' } }));
});
await page.goto('http://localhost:8081/live');
await page.waitForTimeout(5000);
const polls0 = await page.evaluate(() => performance.getEntriesByType('resource').filter((e) => e.name.endsWith('/status')).length);
await page.evaluate(() => window.__renderStats.start());
await page.waitForTimeout(seconds * 1000);
const stats = await page.evaluate(() => window.__renderStats.read());
const polls = (await page.evaluate(() => performance.getEntriesByType('resource').filter((e) => e.name.endsWith('/status')).length)) - polls0;
console.log(JSON.stringify({ seconds, statusPolls: polls, commits: stats.commits, renders: stats.counts }, null, 1));
await browser.close();
