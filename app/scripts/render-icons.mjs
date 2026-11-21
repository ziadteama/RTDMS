// Renders the app icon, Android adaptive icon layers, splash and favicon from assets/images/icon-mark.svg.
//   node scripts/render-icons.mjs        (uses the Playwright Chromium already on the machine)
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

// Playwright is not an app dependency: use the copy installed on the machine (NODE_PATH).
const { chromium } = createRequire(import.meta.url)('playwright');

const dir = join(dirname(fileURLToPath(import.meta.url)), '../assets/images');
const mark = readFileSync(join(dir, 'icon-mark.svg'), 'utf8').replace(/<!--.*?-->\s*/s, '');
const BG = '#0B0D0F';

// name, size, background, mark scale (fraction of the canvas), line, pupil
const outputs = [
  ['icon.png', 1024, BG, 0.62, '#F1F3F5', '#3FB97A'],
  ['android-icon-foreground.png', 1024, 'transparent', 0.46, '#F1F3F5', '#3FB97A'], // inside the 66% safe zone
  ['android-icon-monochrome.png', 1024, 'transparent', 0.46, '#FFFFFF', '#FFFFFF'],
  ['splash-icon.png', 512, 'transparent', 0.9, '#F1F3F5', '#3FB97A'],
  ['favicon.png', 48, BG, 0.8, '#F1F3F5', '#3FB97A'],
];

const browser = await chromium.launch();
const page = await browser.newPage();
for (const [name, size, bg, scale, line, pupil] of outputs) {
  await page.setViewportSize({ width: size, height: size });
  const m = size * scale;
  await page.setContent(
    `<html><body style="margin:0;width:${size}px;height:${size}px;background:${bg};display:flex;align-items:center;justify-content:center">` +
      `<div style="width:${m}px;height:${m}px;--line:${line};--pupil:${pupil}">${mark.replace('<svg ', `<svg width="${m}" height="${m}" `)}</div></body></html>`,
  );
  await page.screenshot({ path: join(dir, name), omitBackground: bg === 'transparent' });
  console.log('wrote', name);
}
await browser.close();
