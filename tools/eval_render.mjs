#!/usr/bin/env node
// Chromium work for the eval harness (tools/evals.py). Three verbs, each prints one JSON
// object on stdout and exits 0 when it could look, 2 when it could not:
//
//   node tools/eval_render.mjs count --file page.html --selector "main > section"
//   node tools/eval_render.mjs probe --file page.html --expr "innerWidth === 390" [--viewport 390x844] [--motion reduce]
//   node tools/eval_render.mjs sheet --out sheet.png [--title "case"] --item "arm::/abs/page.html" ...
//
// Pages load from file URLs with reduced motion by default, so a probe sees the finished
// state rather than a frame of an entrance animation. Needs `npm install` in this repo.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [verb, ...args] = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const all = (n) => args.flatMap((a, i) => (a === `--${n}` ? [args[i + 1]] : []));
const out = (o, code) => { process.stdout.write(JSON.stringify(o) + '\n'); process.exit(code); };
const fail = (error) => out({ ok: false, error }, 2);

if (!['count', 'probe', 'sheet'].includes(verb)) fail('usage: eval_render.mjs count|probe|sheet ...');
let chromium;
try { ({ chromium } = await import('playwright')); } catch {
  fail('playwright is not installed: run `npm install && npx playwright install chromium` in the design-director repo');
}

const size = (s) => {
  const m = /^(\d+)x(\d+)$/.exec(s || '');
  if (!m) fail(`viewport must look like 1440x900, got ${s}`);
  return { width: +m[1], height: +m[2] };
};

async function open(browser, file, vp, motion) {
  const mobile = vp.width < 700;
  const ctx = await browser.newContext({ viewport: vp, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1,
    reducedMotion: motion, colorScheme: 'light' });
  const page = await ctx.newPage();
  await page.goto(pathToFileURL(path.resolve(file)).href, { waitUntil: 'load', timeout: 30000 });
  await page.waitForTimeout(motion === 'reduce' ? 200 : 1200);
  return { ctx, page };
}

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  fail(`chromium would not start: ${e.message.split('\n')[0]}`);
}

try {
  if (verb === 'count' || verb === 'probe') {
    const file = opt('file');
    if (!file || !fs.existsSync(file)) fail(`no such file: ${file}`);
    const { page } = await open(browser, file, size(opt('viewport', '1440x900')), opt('motion', 'reduce'));
    if (verb === 'count') {
      const sel = opt('selector', '');
      const n = await page.evaluate((s) => document.querySelectorAll(s).length, sel);
      await browser.close();
      out({ ok: true, count: n }, 0);
    }
    const value = await page.evaluate(opt('expr', 'false'));
    await browser.close();
    out({ ok: true, value: value === undefined ? null : value }, 0);
  }

  // sheet: every item at a desktop and a phone fold, one row per item, same scale throughout
  const items = all('item').map((s) => { const i = s.indexOf('::'); return { label: s.slice(0, i), file: s.slice(i + 2) }; });
  if (!items.length) fail('sheet needs at least one --item "label::/path/page.html"');
  const dest = path.resolve(opt('out', 'sheet.png'));
  const views = [['desktop 1440x900', { width: 1440, height: 900 }], ['phone 390x844', { width: 390, height: 844 }]];
  const rows = [];
  for (const it of items) {
    const cells = [];
    for (const [name, vp] of views) {
      if (!it.file || !fs.existsSync(it.file)) { cells.push({ name, missing: true, vp }); continue; }
      try {
        const { ctx, page } = await open(browser, it.file, vp, 'reduce');
        const png = await page.screenshot();
        await ctx.close();
        cells.push({ name, vp, src: `data:image/png;base64,${png.toString('base64')}` });
      } catch (e) { cells.push({ name, vp, missing: true, why: e.message.split('\n')[0] }); }
    }
    rows.push({ ...it, cells });
  }
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const scale = 0.5;
  const cell = (c) => `<figure style="width:${c.vp.width * scale}px"><div class="frame" style="height:${c.vp.height * scale}px">`
    + (c.missing ? `<p class="none">no page${c.why ? ': ' + esc(c.why) : ''}</p>` : `<img src="${c.src}">`)
    + `</div><figcaption>${esc(c.name)}</figcaption></figure>`;
  const html = `<!doctype html><meta charset="utf-8"><style>
body{margin:0;padding:24px;background:#e9e7e2;font:13px/1.3 -apple-system,system-ui,sans-serif;color:#222}
h1{font-size:16px;margin:0 0 16px}.row{display:flex;gap:20px;align-items:flex-start;margin-bottom:28px}
.label{width:140px;font-weight:600;word-break:break-word}figure{margin:0}
.frame{background:#fff;box-shadow:0 0 0 1px #0002;overflow:hidden}img{display:block;width:100%;height:auto}
.none{padding:12px;color:#933}figcaption{margin-top:6px;color:#555}
</style><h1>${esc(opt('title', ''))}</h1>${rows.map((r) => `<div class="row"><div class="label">${esc(r.label)}<br><small>${esc(path.basename(r.file || ''))}</small></div>${r.cells.map(cell).join('')}</div>`).join('')}`;
  const page = await browser.newPage({ viewport: { width: 140 + 20 + 720 + 20 + 195 + 48 + 20, height: 400 } });
  await page.setContent(html, { waitUntil: 'load' });
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  await page.screenshot({ path: dest, fullPage: true });
  await browser.close();
  out({ ok: true, out: dest, rows: rows.length }, 0);
} catch (e) {
  try { await browser.close(); } catch { /* already closed */ }
  fail(e.message.split('\n')[0]);
}
