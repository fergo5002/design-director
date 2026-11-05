#!/usr/bin/env node
// A contact sheet: several screenshots side by side, scaled to the same width, labelled,
// in one image. Judging your own work against the category's best only works when they
// sit next to each other at the same size; from memory, everything you made looks fine.
//
//   node tools/sheet.mjs a.png b.png c.png [--labels "Yours,Best,Runner-up"] [--cols 3]
//                        [--width 480] [--crop 900] [--out sheet.png]
//   node tools/sheet.mjs --images a.png b.png [--labels "a,b"] [--cols 3] [--out sheet.png]
//
// --crop keeps only the top N pixels of each (scaled) image, so full-page captures can sit
// beside folds. Images are embedded as data, so nothing is fetched. Exit 2 when an image is
// missing or playwright is not installed.
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const VALUED = ['--labels', '--cols', '--width', '--crop', '--out', '--title'];
// --images takes every path up to the next flag; bare paths anywhere also count.
const imgs = args.filter((a, i) => !a.startsWith('--') && !VALUED.includes(args[i - 1]));
if (!imgs.length) {
  console.error('usage: node tools/sheet.mjs [--images] <png...> [--labels "A,B"] [--cols 3] [--width 480] [--crop 900] [--out sheet.png]');
  process.exit(2);
}
const missing = imgs.filter((f) => !fs.existsSync(f));
if (missing.length) { console.error(`not found: ${missing.join(', ')}`); process.exit(2); }
let chromium;
try { ({ chromium } = await import('playwright')); } catch {
  console.error('Playwright is not installed. Run in the design-director repo: npm install && npx playwright install chromium');
  process.exit(2);
}
const labels = (opt('labels', '') || '').split(',').map((s) => s.trim());
const cols = Math.max(1, parseInt(opt('cols', String(Math.min(imgs.length, 3))), 10));
const width = Math.max(160, parseInt(opt('width', '480'), 10));
const crop = parseInt(opt('crop', '0'), 10) || 0;
const out = path.resolve(opt('out', 'sheet.png'));
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const mime = (f) => (/\.jpe?g$/i.test(f) ? 'image/jpeg' : /\.webp$/i.test(f) ? 'image/webp' : 'image/png');
const cells = imgs.map((f, i) => `<figure><div class="frame"><img src="data:${mime(f)};base64,${fs.readFileSync(f).toString('base64')}"></div>`
  + `<figcaption>${esc(labels[i] || path.basename(path.dirname(f)) + '/' + path.basename(f))}</figcaption></figure>`).join('');
const html = `<!doctype html><meta charset="utf-8"><style>
body{margin:0;padding:24px;background:#e9e7e2;font:13px/1.3 -apple-system,system-ui,sans-serif;color:#222}
.grid{display:grid;grid-template-columns:repeat(${cols},${width}px);gap:24px 20px}
figure{margin:0}.frame{width:${width}px;${crop ? `max-height:${crop}px;overflow:hidden;` : ''}background:#fff;box-shadow:0 0 0 1px #0002}
img{display:block;width:100%;height:auto}figcaption{margin-top:8px;font-weight:600}
</style><div class="grid">${cells}</div>`;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: cols * width + (cols - 1) * 20 + 48, height: 600 } });
await page.setContent(html, { waitUntil: 'load' });
fs.mkdirSync(path.dirname(out), { recursive: true });
await page.screenshot({ path: out, fullPage: true });
await browser.close();
console.log(`sheet: ${out} (${imgs.length} images, ${cols} across at ${width}px). Open it and compare before you judge.`);
