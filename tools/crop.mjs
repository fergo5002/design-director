#!/usr/bin/env node
// Before and after, the same region of each, side by side and scaled up so type and fine
// geometry can be judged at the pixel. A full-page screenshot hides a 1px misalignment; a
// 2x crop of the same box from both renders does not.
//
//   node tools/crop.mjs before.png after.png --box L,T,W,H [--scale 2] [--labels "Before,After"] --out pair.png
//
// The box is in image pixels. Scaling is nearest-neighbour, so what you see is the real pixels.
// Rendering is Chromium through playwright; images are embedded as data URIs.
// Exit: 0 written, 2 could not run (bad arguments, a missing image, a box outside an image,
// no playwright).
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const VALUED = ['--box', '--scale', '--labels', '--out'];
const imgs = args.filter((a, i) => !a.startsWith('--') && !VALUED.includes(args[i - 1]));
const fail = (m) => { console.error(m); process.exit(2); };

if (imgs.length !== 2) fail('usage: node tools/crop.mjs <before.png> <after.png> --box L,T,W,H [--scale 2] [--labels "Before,After"] --out pair.png');
const missing = imgs.filter((f) => !fs.existsSync(f));
if (missing.length) fail(`not found: ${missing.join(', ')}`);
const box = (opt('box', '') || '').split(',').map((v) => Number(v.trim()));
if (box.length !== 4 || box.some((v) => !Number.isFinite(v) || v < 0 || !Number.isInteger(v)) || box[2] < 1 || box[3] < 1) {
  fail('--box must be four whole numbers in image pixels: left,top,width,height (for example 0,0,400,300)');
}
const [L, T, W, H] = box;
const scale = Number(opt('scale', '2'));
if (!(scale >= 1 && scale <= 8)) fail('--scale must be between 1 and 8');
const out = path.resolve(opt('out', 'crop-pair.png'));
const labels = (opt('labels', 'Before,After') || '').split(',').map((s) => s.trim());
let chromium;
try { ({ chromium } = await import('playwright')); } catch {
  fail('Playwright is not installed. Run in the design-director repo: npm install && npx playwright install chromium');
}
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const mime = (f) => (/\.jpe?g$/i.test(f) ? 'image/jpeg' : /\.webp$/i.test(f) ? 'image/webp' : 'image/png');
const cw = Math.round(W * scale), ch = Math.round(H * scale);
const cells = imgs.map((f, i) => `<figure><div class="frame"><img id="i${i}" src="data:${mime(f)};base64,${fs.readFileSync(f).toString('base64')}"></div>`
  + `<figcaption>${esc(labels[i] || path.basename(f))}</figcaption></figure>`).join('');
const html = `<!doctype html><meta charset="utf-8"><style>
body{margin:0;padding:20px;background:#e9e7e2;font:13px/1.3 -apple-system,system-ui,sans-serif;color:#222}
#pair{display:inline-flex;gap:20px;align-items:flex-start}
figure{margin:0}.frame{width:${cw}px;height:${ch}px;overflow:hidden;position:relative;background:#fff;box-shadow:0 0 0 1px #0003}
img{position:absolute;image-rendering:pixelated;transform-origin:0 0;left:${-L * scale}px;top:${-T * scale}px}
figcaption{margin-top:8px;font-weight:600}
</style><div id="pair">${cells}</div>`;
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: cw * 2 + 80, height: ch + 80 }, deviceScaleFactor: 1 });
  await page.setContent(html, { waitUntil: 'load' });
  const sizes = await page.evaluate(async (scale) => {
    const out = [];
    for (const img of document.images) {
      await img.decode().catch(() => {});
      img.style.width = `${img.naturalWidth * scale}px`;
      img.style.height = `${img.naturalHeight * scale}px`;
      out.push([img.naturalWidth, img.naturalHeight]);
    }
    return out;
  }, scale);
  for (let i = 0; i < 2; i++) {
    const [w, h] = sizes[i];
    if (!w || !h) fail(`${imgs[i]} would not decode as an image`);
    if (L + W > w || T + H > h) fail(`the box ${L},${T},${W},${H} falls outside ${imgs[i]} (${w}x${h})`);
  }
  if (sizes[0][0] !== sizes[1][0] || sizes[0][1] !== sizes[1][1]) {
    console.log(`note: the images differ in size (${sizes[0].join('x')} and ${sizes[1].join('x')}), so the same box may not show the same content`);
  }
  fs.mkdirSync(path.dirname(out), { recursive: true });
  await page.locator('#pair').screenshot({ path: out });
} finally {
  await browser.close();
}
console.log(`crop: ${out} (box ${L},${T},${W},${H} at ${scale}x). Open it and compare before you judge.`);
