#!/usr/bin/env node
// ddr motion's browser half: open the page headless at one viewport and run tools/motion-probe.js on it.
//
//   node tools/motion.mjs --url https://example.com | --file page.html [--viewport mac-1512x820] [--scroll]
//        [--idle 3000] [--max-scroll 12000] [--storage-state state.json] [--json-out report.json]
//
// Writes {ok, exit, tool: 'motion', target, viewport, result} to --json-out (or stdout). Exit 0 when it measured,
// 2 when it could not (no browser, no page, or the instrument degraded). The probe races every wait against a
// timer, and this side races the whole probe against one more, so neither can hang.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { VIEWPORTS } from './viewports.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 && args[i + 1] !== undefined ? args[i + 1] : d; };
const flag = (n) => args.includes(`--${n}`);
const jsonOut = opt('json-out', null);
const storage = opt('storage-state', null);

function emit(rep) {
  const text = JSON.stringify(rep);
  if (jsonOut) { fs.mkdirSync(path.dirname(path.resolve(jsonOut)), { recursive: true }); fs.writeFileSync(jsonOut, text); }
  else process.stdout.write(text + '\n');
  process.exit(rep.exit);
}
const cannot = (message, extra = {}) => emit({ ok: false, exit: 2, tool: 'motion', summary: message,
  findings: [{ severity: 'error', rule: 'tool.could-not-run', message }], ...extra });

const url = opt('url', null), file = opt('file', null);
if (!url && !file) cannot('usage: motion.mjs --url <url> | --file <page.html> [--viewport mac-1512x820] [--scroll] [--json-out file]');
if (url && !/^https?:\/\//.test(url)) cannot(`--url needs http:// or https://, got ${url}`);
if (file && !fs.existsSync(file)) cannot(`no such file: ${file}`);
if (storage && !fs.existsSync(storage)) cannot(`no such storage state: ${storage}`);
const vpName = opt('viewport', 'mac-1512x820');
const vp = VIEWPORTS[vpName];
if (!vp) cannot(`unknown viewport ${vpName}. Choose from: ${Object.keys(VIEWPORTS).join(', ')}`);
const idleMs = Math.max(200, parseInt(opt('idle', '3000'), 10) || 3000);
const maxScrollMs = Math.max(500, parseInt(opt('max-scroll', '12000'), 10) || 12000);
const target = url || pathToFileURL(path.resolve(file)).href;

let chromium;
try { ({ chromium } = await import('playwright')); } catch {
  cannot('Playwright is not installed. Run in the design-director repo: npm install && npx playwright install chromium');
}
const PROBE = fs.readFileSync(path.join(HERE, 'motion-probe.js'), 'utf8').replace(/^\s*\/\/.*$/gm, '').trim();

let browser;
try {
  browser = await chromium.launch(file ? { args: ['--allow-file-access-from-files'] } : {});
} catch (e) {
  cannot(`Chromium would not start: ${e.message.split('\n')[0]}. Run: npx playwright install chromium`);
}
const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, isMobile: vp.isMobile, hasTouch: vp.hasTouch,
  deviceScaleFactor: vp.isMobile ? 2 : 1, ...(storage ? { storageState: storage } : {}) });
const page = await ctx.newPage();
let status = null;
try {
  const res = await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 45000 });
  status = res && res.status();
  await page.waitForLoadState('load', { timeout: 15000 }).catch(() => {});
  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(500);
} catch (e) {
  await browser.close();
  cannot(`navigation: ${e.message.split('\n')[0]}`, { target, viewport: vpName });
}
const budget = idleMs + maxScrollMs * 2 + 15000;
let result;
try {
  result = await Promise.race([
    page.evaluate(`(${PROBE})(${JSON.stringify({ idleMs, scroll: flag('scroll'), maxScrollMs })})`),
    new Promise((_, no) => setTimeout(() => no(new Error(`the probe did not come back in ${Math.round(budget / 1000)}s`)), budget)),
  ]);
} catch (e) {
  await browser.close().catch(() => {});
  cannot(`motion probe: ${e.message.split('\n')[0]}`, { target, viewport: vpName });
}
const finalUrl = page.url();
await browser.close();
const degraded = result.verdict === 'INSTRUMENT DEGRADED';
emit({ ok: !degraded, exit: degraded ? 2 : 0, tool: 'motion', target, viewport: vpName, status, finalUrl, result,
  summary: degraded ? result.why : `${result.verdict}: scroll p95 ${result.phases.scroll.p95 ?? '-'}ms, worst ${result.phases.scroll.worst ?? result.phases.idle.worst}ms, ${result.longTasks.count} long tasks` });
