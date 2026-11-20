// Screenshots of every screen, dark + light, English + Arabic, from the web build.
//
//   npm run mock -- --freeze 92          # terminal 1: mock Pi held in the "drowsy" phase
//   npx expo start --web --port 8081     # terminal 2
//   node scripts/screenshots.mjs         # → docs/screenshots/<theme>-<lang>/<screen>.png
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

const settings = (theme, language, extra = {}) => ({
  version: 1,
  state: {
    consentedAt: 1, onboarded: true, language, theme, units: 'kmh', baseUrl: PI, demo: false, paused: false,
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
  ['04-emergency-contacts', '/emergency-contacts', { onboarded: false }],
  ['05-live', '/live', {}],
  ['06-live-driving-lock', '/live', { demo: true }, async (p) => p.waitForTimeout(23_000)], // demo speed > 10 km/h after 20 s
  ['07-trips', '/trips', { demo: true }],
  ['08-trip', '/trips', { demo: true }, async (p) => { await p.getByRole('button').filter({ hasText: /\d+ min|د/ }).nth(1).click(); await p.waitForTimeout(2500); }],
  ['09-health', '/health', {}],
  ['10-settings', '/settings', {}],
  ['11-calibrate', '/calibrate', {}],
  ['12-contacts', '/contacts', {}],
  ['13-privacy', '/privacy', {}],
  ['14-sos', '/settings', { demo: true }, async (p, t) => { await p.getByText(t.fake).click(); await p.waitForTimeout(3500); }],
  ['15-incident', '/settings', { demo: true }, async (p, t) => {
    await p.getByText(t.fake).click();
    await p.waitForTimeout(1500);
    await p.getByText(t.ok).click();
    await p.waitForTimeout(1000);
    await p.getByText(t.trips, { exact: true }).last().click(); // in-app: a reload wipes the web in-memory DB
    await p.waitForTimeout(2000);
    await p.getByText(t.crash).first().click();
    await p.waitForTimeout(3000);
  }],
];

const TEXT = {
  en: { fake: 'Simulate a crash', ok: "I'm OK", trips: 'Trips', crash: /Crash detected/ },
  ar: { fake: 'محاكاة حادث', ok: 'أنا بخير', trips: 'الرحلات', crash: /تم رصد حادث/ },
};

const only = process.argv[2];
const browser = await chromium.launch();
for (const theme of ['dark', 'light'])
  for (const lang of ['en', 'ar']) {
    const dir = join(OUT, `${theme}-${lang}`);
    mkdirSync(dir, { recursive: true });
    for (const [name, route, extra, steps] of SHOTS) {
      if (only && !name.includes(only)) continue;
      const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
      await page.goto(WEB + '/');
      await page.evaluate(([s, c]) => {
        localStorage.clear();
        localStorage.setItem('sahi.settings', JSON.stringify(s));
        localStorage.setItem('sahi.contacts', JSON.stringify(c));
      }, [settings(theme, lang, extra), contacts]);
      await page.goto(WEB + route);
      await page.waitForTimeout(5000);
      if (steps) await steps(page, TEXT[lang]);
      await page.screenshot({ path: join(dir, `${name}.png`) });
      await page.close();
      console.log(`${theme}-${lang}/${name}.png`);
    }
  }
await browser.close();
