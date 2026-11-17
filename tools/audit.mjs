#!/usr/bin/env node
// ddr audit's browser half: open a page at each viewport, walk it one scroll stop at a time, and measure what is
// wrong on screen with tools/audit-probe.js. Contrast is read off pixels: a second screenshot with every glyph made
// transparent shows what is really behind each text run (a photograph, a gradient, a token that lies).
//
//   node tools/audit.mjs --url https://example.com | --file page.html [--viewports mac-1512x820,phone-390x844]
//        [--json-out report.json] [--max-items 5] [--max-stops 12] [--storage-state state.json] [--deadline 240]
//
// --deadline (seconds) stops the walk where it is and keeps what was measured (stoppedAtDeadline); the first stop of
// the first viewport is always looked at. A page that scrolls inside a container (html and body hidden, #app
// scrolling) is walked through its largest scroller.
// Writes one JSON object {ok, exit, tool: 'audit', target, viewports: [...], total, summary} to --json-out (or
// stdout). Exit 0 when it could look (findings or not), 2 when it could not. ddr audit (tools/audit.py) decides
// the rest. Needs `npm install` and `npx playwright install chromium` in this repo.
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { VIEWPORTS } from './viewports.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 && args[i + 1] !== undefined ? args[i + 1] : d; };
export const DEFAULT_VIEWPORTS = 'mac-1512x820,mac-1440x780,phone-390x844';
const jsonOut = opt('json-out', null);
const maxItems = Math.max(0, parseInt(opt('max-items', '5'), 10) || 0);
const maxStops = Math.max(1, parseInt(opt('max-stops', '12'), 10) || 12);
const storage = opt('storage-state', null);
const T0 = Date.now();
const deadlineMs = Math.max(0, parseFloat(opt('deadline', '240')) || 0) * 1000;
const left = () => deadlineMs - (Date.now() - T0);
// Every wait on the page is raced against a timer: a page that never answers must not hold the audit.
const within = (promise, ms, fallback) => Promise.race([promise, new Promise((r) => setTimeout(() => r(fallback), ms))]);

function emit(rep) {
  const text = JSON.stringify(rep);
  if (jsonOut) { fs.mkdirSync(path.dirname(path.resolve(jsonOut)), { recursive: true }); fs.writeFileSync(jsonOut, text); }
  else process.stdout.write(text + '\n');
  process.exit(rep.exit);
}
const cannot = (message) => emit({ ok: false, exit: 2, tool: 'audit', findings: [{ severity: 'error', rule: 'tool.could-not-run', message }], summary: message, viewports: [], total: 0 });

const url = opt('url', null), file = opt('file', null);
if (!url && !file) cannot('usage: audit.mjs --url <url> | --file <page.html> [--viewports ...] [--json-out file]');
if (url && !/^https?:\/\//.test(url)) cannot(`--url needs http:// or https://, got ${url}`);
if (file && !fs.existsSync(file)) cannot(`no such file: ${file}`);
if (storage && !fs.existsSync(storage)) cannot(`no such storage state: ${storage}`);
const target = url || pathToFileURL(path.resolve(file)).href;
const asked = opt('viewports', DEFAULT_VIEWPORTS).split(',').map((v) => v.trim()).filter(Boolean);
const unknown = asked.filter((v) => !VIEWPORTS[v]);
if (unknown.length || !asked.length) cannot(`unknown viewport(s): ${unknown.join(', ') || '(none)'}. Choose from: ${Object.keys(VIEWPORTS).join(', ')}`);

let chromium;
try { ({ chromium } = await import('playwright')); } catch {
  cannot('Playwright is not installed. Run in the design-director repo: npm install && npx playwright install chromium');
}
const PROBE = fs.readFileSync(path.join(HERE, 'audit-probe.js'), 'utf8').replace(/^\s*\/\/.*$/gm, '').trim();

// ---------------------------------------------------------------- pixels

// A PNG decoder for what Chromium writes (8-bit RGB or RGBA, not interlaced): enough to read a screenshot's pixels
// without a dependency.
function decodePng(buf) {
  let pos = 8, width = 0, height = 0, type = 0, depth = 0, interlace = 0;
  const idat = [];
  while (pos < buf.length) {
    const len = buf.readUInt32BE(pos), kind = buf.toString('ascii', pos + 4, pos + 8), data = buf.subarray(pos + 8, pos + 8 + len);
    if (kind === 'IHDR') { width = data.readUInt32BE(0); height = data.readUInt32BE(4); depth = data[8]; type = data[9]; interlace = data[12]; }
    else if (kind === 'IDAT') idat.push(data);
    else if (kind === 'IEND') break;
    pos += 12 + len;
  }
  if (depth !== 8 || ![2, 6].includes(type) || interlace) throw new Error(`unsupported PNG (depth ${depth}, type ${type}, interlace ${interlace})`);
  const bpp = type === 6 ? 4 : 3, stride = width * bpp;
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const px = Buffer.alloc(height * stride);
  for (let y = 0; y < height; y++) {
    const f = raw[y * (stride + 1)], src = y * (stride + 1) + 1, row = y * stride, prev = row - stride;
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? px[row + x - bpp] : 0, b = y ? px[prev + x] : 0, c = x >= bpp && y ? px[prev + x - bpp] : 0;
      let v = raw[src + x];
      if (f === 1) v += a; else if (f === 2) v += b; else if (f === 3) v += (a + b) >> 1;
      else if (f === 4) { const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c); v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c; }
      px[row + x] = v & 255;
    }
  }
  return { width, height, at: (x, y) => { const i = y * stride + x * bpp; return [px[i], px[i + 1], px[i + 2]]; } };
}
const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
const ratio = (x, y) => { const a = lum(x), b = lum(y); return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); };
const hex = (c) => '#' + c.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');
const HIDE_TEXT = `*, *::before, *::after { color: transparent !important; -webkit-text-fill-color: transparent !important;
  text-shadow: none !important; text-decoration-color: transparent !important; caret-color: transparent !important; }
  *::placeholder { color: transparent !important; }`;

// WCAG AA: 4.5:1, or 3:1 for large text (24px, or 18.66px bold). The run's colour composited over each sampled
// pixel behind it; the 10th percentile is reported, so a pale patch under part of a line still counts.
function contrastItems(runs, img) {
  const items = [];
  let unmeasured = 0;
  for (const r of runs) {
    const [fr, fg, fb, fa] = r.fg;
    const alpha = fa * r.opacity;
    if (r.clipText || alpha < 0.05 || !r.rects.length) { unmeasured++; continue; }
    const samples = [], bgs = [];
    for (const [l, t, rr, b] of r.rects) {
      const w = Math.floor(rr) - Math.ceil(l), h = Math.floor(b) - Math.ceil(t);
      if (w < 1 || h < 1) continue;
      const step = Math.max(1, Math.floor(Math.sqrt((w * h) / 200)));
      for (let y = Math.ceil(t); y < Math.floor(b) && y < img.height; y += step) {
        for (let x = Math.ceil(l); x < Math.floor(rr) && x < img.width; x += step) {
          const bg = img.at(x, y);
          const fgc = [fr * alpha + bg[0] * (1 - alpha), fg * alpha + bg[1] * (1 - alpha), fb * alpha + bg[2] * (1 - alpha)];
          samples.push(ratio(fgc, bg)); bgs.push(bg);
        }
      }
    }
    if (!samples.length) { unmeasured++; continue; }
    const sorted = samples.slice().sort((a, b) => a - b);
    const p10 = sorted[Math.floor(sorted.length * 0.1)], med = sorted[Math.floor(sorted.length / 2)];
    const needs = r.px >= 24 || (r.px >= 18.66 && r.weight >= 700) ? 3 : 4.5;
    if (p10 < needs) {
      const mid = bgs.map((c) => [lum(c), c]).sort((a, b) => a[0] - b[0])[Math.floor(bgs.length / 2)][1];
      items.push({ selector: r.selector, text: r.text, rect: r.rect, ratio: +p10.toFixed(2), median: +med.toFixed(2), needs,
        fg: hex([fr, fg, fb]), bg: hex(mid), score: needs - p10,
        detail: `${p10.toFixed(2)}:1 on the pixels behind it (needs ${needs}:1), ${hex([fr, fg, fb])} over about ${hex(mid)}` });
    }
  }
  return { items, unmeasured };
}

// ---------------------------------------------------------------- the walk

const settle = (page, ms) => page.evaluate((ms) => new Promise((done) => {
  // two frames, or the timer: a hidden or throttled page never runs requestAnimationFrame, so never wait on it alone
  let over = false;
  const end = () => { if (!over) { over = true; done(); } };
  requestAnimationFrame(() => requestAnimationFrame(end));
  setTimeout(end, ms);
}), ms).catch(() => {});

const CHECKS = ['clip.text', 'clip.box', 'offscreen', 'page.sideways', 'overlap', 'tap.small', 'tap.close', 'contrast', 'line.length', 'text.small'];

let browser;
try {
  browser = await chromium.launch(file ? { args: ['--allow-file-access-from-files'] } : {});
} catch (e) {
  cannot(`Chromium would not start: ${e.message.split('\n')[0]}. Run: npx playwright install chromium`);
}
const results = [];
let looked = 0;
const errors = [];
for (const name of asked) {
  const vp = VIEWPORTS[name];
  if (results.length > 0 && left() <= 0) {
    results.push({ viewport: name, width: vp.width, height: vp.height, stops: 0, checks: {}, stoppedAtDeadline: true,
      error: `not looked at: the ${deadlineMs / 1000}s deadline ran out` });
    continue;
  }
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, isMobile: vp.isMobile, hasTouch: vp.hasTouch,
    deviceScaleFactor: vp.isMobile ? 2 : 1, colorScheme: 'light', ...(storage ? { storageState: storage } : {}) });
  const page = await ctx.newPage();
  const entry = { viewport: name, width: vp.width, height: vp.height, stops: 0, stopsCapped: false, checks: {} };
  try {
    const res = await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 45000 });
    entry.status = res && res.status();
    entry.finalUrl = page.url();
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    await page.evaluate(() => Promise.race([document.fonts ? document.fonts.ready : null,
      new Promise((r) => setTimeout(r, 5000))])).catch(() => {});
    await page.waitForTimeout(800);
    // What scrolls: the window, or else the largest element that scrolls (an app shell with html and body hidden)
    const dims = await page.evaluate(() => {
      const doc = document.documentElement;
      scrollTo(0, 1e7);
      const windowScrolls = scrollY > 0;
      scrollTo(0, 0);
      if (windowScrolls) return { h: doc.scrollHeight, vh: doc.clientHeight || innerHeight, inner: null };
      let best = null, area = 0;
      for (const el of document.querySelectorAll('body *')) {
        const s = getComputedStyle(el);
        if (!/auto|scroll|overlay/.test(s.overflowY) || el.scrollHeight <= el.clientHeight + 1) continue;
        const a = el.clientWidth * el.clientHeight;
        if (a > area) { area = a; best = el; }
      }
      if (!best) return { h: doc.scrollHeight, vh: doc.clientHeight || innerHeight, inner: null };
      document.querySelectorAll('[data-ddr-scroller]').forEach((n) => n.removeAttribute('data-ddr-scroller'));
      best.setAttribute('data-ddr-scroller', '');
      return { h: best.scrollHeight, vh: best.clientHeight, inner: best.id ? `#${best.id}` : best.tagName.toLowerCase() };
    });
    entry.scroller = dims.inner || 'window';
    const last = Math.max(0, dims.h - dims.vh), step = Math.max(1, Math.floor(dims.vh * 0.85));
    let ys = [];
    for (let y = 0; y < last; y += step) ys.push(y);
    ys.push(last);
    ys = [...new Set(ys)];
    if (ys.length > maxStops) {
      entry.stopsCapped = true;
      entry.stopsWanted = ys.length;
      ys = Array.from({ length: maxStops }, (_, i) => Math.round((last * i) / (maxStops - 1)));
    }
    const found = Object.fromEntries(CHECKS.map((c) => [c, new Map()]));
    let unmeasured = 0;
    entry.stopsWanted = entry.stopsWanted || ys.length;
    let walked = 0;
    for (const [i, y] of ys.entries()) {
      if ((i > 0 || results.length > 0) && left() <= 0) { entry.stoppedAtDeadline = true; break; }
      const offsetY = await page.evaluate((y) => {
        const el = document.querySelector('[data-ddr-scroller]');
        if (el) { el.scrollTop = y; return el.scrollTop; }
        window.scrollTo(0, y);
        return 0;
      }, y);
      await settle(page, 300);
      await page.waitForTimeout(i ? 250 : 0);
      const m = await within(page.evaluate(`(${PROBE})(${JSON.stringify({ touch: vp.hasTouch, fold: i === 0, offsetY })})`), 30000, null);
      if (!m) { entry.stoppedAtDeadline = true; entry.why = 'the page did not answer the probe in 30s'; break; }
      walked += 1;
      const stop = m.scrollY;
      if (i === 0) { entry.fold = m.fold; entry.sideways = m.sideways; }
      for (const [check, list] of Object.entries(m.checks)) {
        for (const it of list) {
          const key = `${it.selector}|${it.text}|${it.other ? it.other.selector : ''}`;
          if (!found[check].has(key)) found[check].set(key, { ...it, stop });
        }
      }
      // contrast on the pixels: the same screen with every glyph transparent
      const handle = await page.addStyleTag({ content: HIDE_TEXT });
      const png = await page.screenshot({ scale: 'css', animations: 'disabled', timeout: 10000 }).catch(() => null);
      await handle.evaluate((n) => n.remove()).catch(() => {});
      const c = png ? contrastItems(m.runs, decodePng(png)) : { items: [], unmeasured: m.runs.length };
      unmeasured += c.unmeasured;
      for (const it of c.items) {
        const key = `${it.selector}|${it.text}|`;
        if (!found.contrast.has(key)) found.contrast.set(key, { ...it, stop });
      }
    }
    if (entry.sideways) {
      const widest = await page.evaluate((vw) => [...document.querySelectorAll('body *')].map((el) => [el, el.getBoundingClientRect().right])
        .filter(([, r]) => r > vw + 1).sort((a, b) => b[1] - a[1]).slice(0, 3)
        .map(([el, r]) => `${el.tagName.toLowerCase()}${typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/)[0] : ''} to ${Math.round(r)}px`), vp.width);
      found['page.sideways'].set('page', { selector: 'html', text: '', rect: [0, 0, vp.width + entry.sideways, vp.height], px: entry.sideways,
        widest, score: entry.sideways, stop: 0, detail: `the page scrolls sideways by ${entry.sideways}px (${widest.join(', ')})` });
    }
    entry.stops = walked;
    entry.contrastUnmeasured = unmeasured;
    for (const check of CHECKS) {
      const all = [...found[check].values()].sort((a, b) => (b.score || 0) - (a.score || 0));
      entry.checks[check] = { count: all.length, cut: Math.max(0, all.length - maxItems), items: all.slice(0, maxItems) };
    }
    looked += 1;
  } catch (e) {
    entry.error = e.message.split('\n')[0];
    errors.push(`${name}: ${entry.error}`);
  }
  results.push(entry);
  await ctx.close();
}
await browser.close();
const total = results.reduce((n, v) => n + Object.values(v.checks).reduce((m, c) => m + c.count, 0), 0);
const exit = looked ? 0 : 2;
const stoppedAtDeadline = results.some((v) => v.stoppedAtDeadline);
emit({ ok: exit === 0, exit, tool: 'audit', target, viewports: results, total, errors, stoppedAtDeadline,
  summary: looked ? `${total} measured problems over ${looked} viewports` : `could not look: ${errors.join('; ')}` });
