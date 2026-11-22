// Screenshots of every screen, dark + light, English only, from the web build.
//
//   npm run mock -- --freeze 92          # terminal 1: mock Pi held in the "drowsy" phase
//   npx expo start --web --port 8081     # terminal 2
//   node scripts/screenshots.mjs         # → docs/screenshots/<theme>-en/<screen>.png
//
// Bluetooth shots (03c, 14): the web build runs the in-memory FakeBleLink, never real radio. Shots
// with `bleName` in their overrides also get a pairing token. 14-diagnostics-link shows "Bluetooth"
// only if the fake link comes up online by itself (autoplay in src/pi/ble); otherwise the link
// stays offline and the row shows the Wi-Fi fallback served by mock-pi. Both are valid evidence.
//
// The web build is a stand-in for the Android dev build (no emulator in CI): the native tab bar,
// @expo/ui controls and fonts are web renderings. See docs/EVIDENCE.md.
import { mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const { chromium } = createRequire(import.meta.url)('playwright');
const OUT = join(dirname(fileURLToPath(import.meta.url)), '../docs/screenshots');
const WEB = process.env.WEB ?? 'http://localhost:8081';
const PI = process.env.PI ?? 'http://localhost:8080';

const settings = (theme, extra = {}) => ({
  version: 1,
  state: {
    consentedAt: 1, onboarded: true, theme, units: 'kmh', baseUrl: PI, demo: false, paused: false,
    sound: false, volume: 1, vibration: 'strong', crashDetection: true, callTarget: 'ambulance', ambulanceNumber: '123',
    ...extra,
  },
});
const contacts = [{ id: '1', name: 'Mona Hassan', phone: '+20 100 123 4567' }, { id: '2', name: 'Karim', phone: '+20 122 555 0101' }];

/** [file, route, settings overrides, steps after load] */
const SHOTS = [
  ['01-consent', '/consent', { onboarded: false, consentedAt: null }],
  ['02-permissions', '/permissions', { onboarded: false }],
  ['03-pair', '/connect', { onboarded: false }],
  ['03b-onboarding-eye-calibration', '/eye-calibration', { onboarded: false }],
  ['03c-pair-ble-manual', '/connect', { onboarded: false }, async (p) => { await p.getByRole('button', { name: 'Pair with a code instead' }).click(); await p.waitForTimeout(500); }],
  ['04-emergency-contacts', '/emergency-contacts', { onboarded: false }],
  ['05-drive', '/live', {}],
  ['06-drive-driving-lock', '/live', { demo: true }, async (p) => p.waitForTimeout(23_000)], // demo speed > 10 km/h after 20 s
  ['07-trips', '/trips', { demo: true }],
  ['08-trip', '/trips', { demo: true }, async (p) => { await p.getByRole('button').filter({ hasText: /\d+ min/ }).nth(1).click(); await p.waitForTimeout(2500); }],
  ['09-settings', '/settings', {}],
  ['10-calibrate', '/calibrate', {}],
  ['10b-eye-cal-intro', '/eye-calibration?cal=intro', {}],
  ['10c-eye-cal-framing', '/eye-calibration?cal=framing', {}],
  ['10d-eye-cal-open', '/eye-calibration?cal=open', {}],
  ['10e-eye-cal-closed', '/eye-calibration?cal=closed', {}],
  ['10f-eye-cal-result-good', '/eye-calibration?cal=good', {}],
  ['10g-eye-cal-result-poor', '/eye-calibration?cal=poor', {}],
  ['10h-eye-cal-failure', '/eye-calibration?cal=failure', {}],
  ['11-contacts', '/contacts', {}],
  ['12-privacy', '/privacy', {}],
  ['14-diagnostics-link', '/diagnostics', { bleName: 'RTDMS-Pi' }, async (p) => { await p.getByText('Signal').first().scrollIntoViewIfNeeded(); await p.waitForTimeout(2500); }],
  ['13-sos', '/sos?incident=1', { demo: true }, async (p) => p.waitForTimeout(3000)],
];

const TEXT = { version: '0.1.0', fake: 'Simulate crash', ok: "I'm OK", trips: 'Trips', crash: /Crash detected/ };

const only = process.argv[2];
const browser = await chromium.launch();
for (const theme of ['dark', 'light']) {
  const dir = join(OUT, `${theme}-en`);
  mkdirSync(dir, { recursive: true });
  for (const [name, route, extra, steps] of SHOTS) {
    if (only && !name.includes(only)) continue;
    const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
    await page.goto(WEB + '/');
    await page.evaluate(([s, c]) => {
      localStorage.clear();
      if (s.state.bleName) localStorage.setItem('sahi.pi_token', JSON.stringify('k3Jx9mQ2pL7vN4wR8tY1'));
      localStorage.setItem('sahi.settings', JSON.stringify(s));
      localStorage.setItem('sahi.contacts', JSON.stringify(c));
    }, [settings(theme, extra), contacts]);
    await page.goto(WEB + route);
    await page.waitForTimeout(5000);
    if (steps) await steps(page, TEXT).catch((e) => console.warn(`  step failed for ${name}: ${String(e).split('\n')[0]}`));
    await page.screenshot({ path: join(dir, `${name}.png`) });
    await page.close();
    console.log(`${theme}-en/${name}.png`);
  }
}
await browser.close();
