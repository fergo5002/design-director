#!/usr/bin/env node
// The look gate. Renders a page the way people will actually see it and measures what
// eyeballing misses. Screenshots are for a human (or a vision model) to judge; the numbers
// are for catching regressions. Neither one says the design is good.
//
//   node tools/shots.mjs https://example.com [more urls] [--file page.html ...] [--out .design/shots]
//                        [--flat] [--full] [--viewports mac-1512x820,phone-390x844] [--no-axe] [--dark]
//                        [--json-out report.json]
//
// --flat writes into --out itself instead of a timestamped folder inside it. --json-out writes
// one JSON object {ok, exit, tool, findings, summary, outDir, viewports, results}. Each result
// carries the rendered text (innerText of body, for copy fidelity) and the load numbers.
//
// Fonts: a browser never fails on a missing font, it falls back, and document.fonts.check()
// answers true for any family no @font-face declares. So for each family the page names, a
// sample node is asked through CDP (CSS.getPlatformFontsForNode) which platform font actually
// painted it. The approach follows html2png.mjs and toolchain.mjs in LangChain's open-source
// design agent (Apache 2.0).
//
// Tap targets: under 24px is an error everywhere (WCAG 2.5.8); under 44px is a warning on the
// phone, phone-landscape and small viewports. Inline links in a sentence are exempt from both.
//
// Exit: 0 nothing measured wrong (warnings allowed), 1 problems, 2 could not run (no playwright, bad arguments,
// a missing file, or every navigation failed). Exit 2 is never a pass.
//
// Needs: npm install (playwright, @axe-core/playwright) and `npx playwright install chromium`.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const args = process.argv.slice(2);
const flag = (n) => args.includes(`--${n}`);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const many = (n) => args.flatMap((a, i) => (a === `--${n}` && args[i + 1] ? [args[i + 1]] : []));
const VALUED = ['--out', '--viewports', '--file', '--json-out'];
const urls = args.filter((a, i) => !a.startsWith('--') && !VALUED.includes(args[i - 1]));
const files = many('file');
const jsonOut = opt('json-out', null);

function finish(exit, findings, summary, extra = {}) {
  if (jsonOut) {
    fs.mkdirSync(path.dirname(path.resolve(jsonOut)), { recursive: true });
    fs.writeFileSync(jsonOut, JSON.stringify({ ok: exit === 0, exit, tool: 'shots', findings, summary, ...extra }, null, 1));
  }
  process.exit(exit);
}
function cannot(message) {
  console.error(message);
  finish(2, [{ severity: 'error', rule: 'tool.could-not-run', message }], message);
}

if (!urls.length && !files.length) {
  cannot('usage: node tools/shots.mjs <url> [url...] [--file page.html] [--out dir] [--flat] [--full] [--viewports mac-1512x820,phone-390x844] [--no-axe] [--dark] [--json-out file]');
}
const goneFiles = files.filter((f) => !fs.existsSync(f));
if (goneFiles.length) cannot(`not found: ${goneFiles.join(', ')}`);

const VIEWPORTS = {
  'mac-1512x820': { width: 1512, height: 820, isMobile: false, hasTouch: false },
  'mac-1440x780': { width: 1440, height: 780, isMobile: false, hasTouch: false },
  'desktop-1440x900': { width: 1440, height: 900, isMobile: false, hasTouch: false },
  'phone-390x844': { width: 390, height: 844, isMobile: true, hasTouch: true },
  'phone-landscape-844x390': { width: 844, height: 390, isMobile: true, hasTouch: true },
  'small-320x568': { width: 320, height: 568, isMobile: true, hasTouch: true },
  // the original names, kept working
  desktop: { width: 1440, height: 900, isMobile: false, hasTouch: false },
  laptop: { width: 1280, height: 720, isMobile: false, hasTouch: false },
  tablet: { width: 820, height: 1180, isMobile: true, hasTouch: true },
  phone: { width: 390, height: 844, isMobile: true, hasTouch: true },
  small: { width: 320, height: 568, isMobile: true, hasTouch: true },
};
const DEFAULT = 'mac-1512x820,mac-1440x780,desktop-1440x900,phone-390x844,phone-landscape-844x390,small-320x568';
const asked = opt('viewports', DEFAULT).split(',').map((v) => v.trim()).filter(Boolean);
const unknown = asked.filter((v) => !VIEWPORTS[v]);
if (unknown.length || !asked.length) {
  cannot(`unknown viewport(s): ${unknown.join(', ') || '(none given)'}. Choose from: ${Object.keys(VIEWPORTS).join(', ')}`);
}
const chosen = asked;

let chromium, AxeBuilder;
try {
  ({ chromium } = await import('playwright'));
} catch {
  cannot('Playwright is not installed. Run in the design-director repo: npm install && npx playwright install chromium');
}
try { AxeBuilder = (await import('@axe-core/playwright')).default; } catch { AxeBuilder = null; }

const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
const outDir = flag('flat') ? path.resolve(opt('out', '.design/shots')) : path.resolve(opt('out', '.design/shots'), stamp);
fs.mkdirSync(outDir, { recursive: true });

const GENERIC = /^(serif|sans-serif|monospace|cursive|fantasy|system-ui|ui-serif|ui-sans-serif|ui-monospace|ui-rounded|emoji|math|fangsong|-apple-system|BlinkMacSystemFont|inherit|initial)$/i;
const PROBE = 'data-ddr-font-probe';

// Runs inside the page. Pure measurement; the only change is a probe attribute on one sample
// node per font family, removed again after the font check.
function measure({ probeAttr, generic }) {
  const GENERIC_RE = new RegExp(generic, 'i');
  const vw = window.innerWidth, vh = window.innerHeight;
  const doc = document.documentElement;
  const main = document.querySelector('main') || document.body;
  const words = (main.innerText || '').split(/\s+/).filter(Boolean).length;
  const shown = (el) => !el.checkVisibility || el.checkVisibility({ opacityProperty: true, visibilityProperty: true });
  const clipped = (el) => {
    for (let n = el, depth = 0; n && n !== document.body && depth < 6; n = n.parentElement, depth++) {
      const s = getComputedStyle(n);
      if (/rect\(\s*0(px)?[\s,]+0(px)?[\s,]+0(px)?[\s,]+0(px)?\s*\)/.test(s.clip)) return true;
      if (/inset\(\s*50%/.test(s.clipPath)) return true;
      const r = n.getBoundingClientRect();
      if ((s.overflow === 'hidden' || s.overflow === 'clip') && (r.width <= 1 || r.height <= 1)) return true;
    }
    return false;
  };
  const visibleText = (el) => {
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'TITLE', 'OPTION'].includes(el.tagName)) return false;
    if (!shown(el)) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1) return false;
    if (r.right <= 0 || r.bottom + window.scrollY <= 0) return false;   // pushed off the page
    return !clipped(el);
  };
  const textEls = [];
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const t = walker.currentNode;
    const el = t.parentElement;
    if (!el || seen.has(el) || !t.nodeValue.trim()) continue;
    seen.add(el);
    if (visibleText(el)) textEls.push(el);
  }
  const sizes = new Set();
  let smallest = null, smallestAt = '';
  const families = new Map();
  for (const el of textEls) {
    const s = getComputedStyle(el);
    const px = Math.round(parseFloat(s.fontSize) * 10) / 10;
    sizes.add(px);
    if (smallest === null || px < smallest) {
      smallest = px;
      smallestAt = `${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/)[0] : ''} "${(el.innerText || '').trim().slice(0, 40)}"`;
    }
    const first = s.fontFamily.split(',')[0].replace(/["']/g, '').trim();
    if (first && !GENERIC_RE.test(first) && !families.has(first)) families.set(first, el);
  }
  document.querySelectorAll(`[${probeAttr}]`).forEach((el) => el.removeAttribute(probeAttr));
  const probes = [];
  [...families].forEach(([family, el], i) => { el.setAttribute(probeAttr, String(i)); probes.push({ family, i }); });

  // Text-only sections: a top-level block of main with no picture of any kind and over 40 words.
  let blocks = [...main.children];
  while (blocks.length === 1 && blocks[0].children.length > 1) blocks = [...blocks[0].children];
  let run = 0, maxRun = 0, textOnly = 0;
  for (const b of blocks) {
    if (!shown(b)) continue;
    const n = (b.innerText || '').split(/\s+/).filter(Boolean).length;
    const isText = n > 40 && !b.querySelector('img, svg, canvas, video, picture, iframe') && !['IMG', 'SVG', 'CANVAS', 'VIDEO', 'PICTURE', 'IFRAME'].includes(b.tagName.toUpperCase());
    if (isText) { run += 1; textOnly += 1; maxRun = Math.max(maxRun, run); } else run = 0;
  }

  const interactive = [...document.querySelectorAll('a[href], button, input, select, textarea, [role="button"], [tabindex]:not([tabindex="-1"])')]
    .filter((el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden'; });
  // WCAG 2.5.8 exempts links inline in a sentence, so skip an <a> whose parent holds more text than it does
  const inline = (el) => el.tagName === 'A' && el.parentElement && (el.parentElement.innerText || '').trim().length > (el.innerText || '').trim().length + 12;
  const under = (px) => interactive.filter((el) => { const r = el.getBoundingClientRect(); return (r.width < px || r.height < px) && !inline(el); })
    .slice(0, 12).map((el) => `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''} "${(el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().width)}x${Math.round(el.getBoundingClientRect().height)}`);
  const small = under(24);    // WCAG 2.5.8 minimum: an error everywhere
  const thumb = under(44);    // a comfortable touch target: a warning on touch viewports
  const wide = [...document.querySelectorAll('body *')].filter((el) => el.getBoundingClientRect().right > vw + 1)
    .slice(0, 8).map((el) => `${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''}`);
  const imgs = [...document.images];
  const loaded = [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family.replace(/["']/g, ''));
  const h1 = [...document.querySelectorAll('h1')].map((h) => h.innerText.trim().slice(0, 80));
  return {
    title: document.title,
    lang: doc.getAttribute('lang'),
    h1,
    words,
    screens: +(doc.scrollHeight / vh).toFixed(1),
    textOnlySections: textOnly,
    maxConsecutiveTextOnly: maxRun,
    fontSizes: [...sizes].sort((a, b) => a - b),
    smallestTextPx: smallest,
    smallestTextAt: smallestAt,
    horizontalOverflow: doc.scrollWidth > vw + 1 ? doc.scrollWidth - vw : 0,
    overflowingElements: doc.scrollWidth > vw + 1 ? wide : [],
    interactiveCount: interactive.length,
    tapTargetsUnder24px: small,
    tapTargetsUnder44px: thumb,
    imagesMissingAlt: imgs.filter((i) => !i.hasAttribute('alt')).length,
    imagesMissingSize: imgs.filter((i) => !i.getAttribute('width') && !i.style.aspectRatio && !getComputedStyle(i).aspectRatio.includes('/')).length,
    fontsUsed: [...families.keys()],
    fontsLoaded: [...new Set(loaded)],
    probes,
    text: document.body.innerText || '',
    // The words as written, before CSS text-transform (innerText applies it). Visible text nodes only.
    textAuthored: (() => {
      const out = [];
      const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = walk.nextNode(); n; n = walk.nextNode()) {
        const el = n.parentElement;
        if (!el || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(el.tagName)) continue;
        if (el.closest('[hidden],[aria-hidden="true"]')) continue;
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden' || !el.getClientRects().length) continue;
        out.push(n.nodeValue);
      }
      return out.join(' ').replace(/\s+/g, ' ').trim();
    })(),
  };
}

// Which platform font painted each sampled family, asked of the browser itself.
async function paintedFonts(ctx, page, probes) {
  const painted = {}, falling = [];
  if (!probes.length) return { painted, falling };
  const cdp = await ctx.newCDPSession(page);
  try {
    await cdp.send('DOM.enable');
    await cdp.send('CSS.enable');
    const { root } = await cdp.send('DOM.getDocument', { depth: 0 });
    for (const { family, i } of probes) {
      const { nodeId } = await cdp.send('DOM.querySelector', { nodeId: root.nodeId, selector: `[${PROBE}="${i}"]` });
      if (!nodeId) { falling.push(family); painted[family] = []; continue; }
      const { fonts } = await cdp.send('CSS.getPlatformFontsForNode', { nodeId });
      const used = fonts.map((f) => f.familyName);
      // A web font reports the name inside its file ("Brand Sans 250"), so it counts when a face
      // registered under this family loaded and a custom font painted the node.
      const webFace = await page.evaluate((name) => [...document.fonts].some((face) => face.status === 'loaded'
        && face.family.replace(/^["']|["']$/g, '').toLowerCase() === name.toLowerCase()), family);
      const ok = used.some((n) => n.toLowerCase() === family.toLowerCase()) || (webFace && fonts.some((f) => f.isCustomFont));
      painted[family] = used;
      if (!ok) falling.push(family);
    }
  } finally {
    await page.evaluate((attr) => document.querySelectorAll(`[${attr}]`).forEach((el) => el.removeAttribute(attr)), PROBE).catch(() => {});
    await cdp.detach().catch(() => {});
  }
  return { painted, falling };
}

function baseSlug(p) {
  return p.replace(/\.[^.]+$/, '').replace(/\W+/g, '-').replace(/^-+|-+$/g, '');
}

// A file target is named by its file name; when two targets share one (site/index.html and
// site/pricing/index.html), each is named by its path below their common folder instead, so
// neither overwrites the other's shots. Names never depend on the working directory.
function fileSlugs(files) {
  const out = new Map();
  const counts = {};
  for (const f of files) { const b = baseSlug(path.basename(f)); counts[b] = (counts[b] || 0) + 1; }
  const clash = files.filter((f) => counts[baseSlug(path.basename(f))] > 1);
  let common = clash.length ? path.dirname(path.resolve(clash[0])) : '';
  for (const f of clash) { while (common && !path.resolve(f).startsWith(common + path.sep)) common = path.dirname(common); }
  for (const f of files) {
    const b = baseSlug(path.basename(f));
    out.set(f, counts[b] > 1 ? baseSlug(path.relative(common, path.resolve(f))) : b);
  }
  return out;
}

function slugFor(target) {
  if (target.kind === 'file') return target.slug;
  const u = new URL(target.url);
  const q = u.search ? '-q' + [...u.search].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7).toString(36) : '';
  return `${u.hostname}${u.port ? '-' + u.port : ''}${u.pathname.replace(/\W+/g, '-')}`.replace(/-+$/, '') + q;
}

const targets = [
  ...urls.map((u) => ({ kind: 'url', url: u, label: u })),
  ...files.map((f) => ({ kind: 'file', path: path.resolve(f), url: pathToFileURL(path.resolve(f)).href, label: f,
    slug: fileSlugs(files).get(f) })),
];

let browser;
try {
  // file targets load their own stylesheets (and axe reads them) from a file origin
  browser = await chromium.launch(files.length ? { args: ['--allow-file-access-from-files'] } : {});
} catch (e) {
  cannot(`Chromium would not start: ${e.message.split('\n')[0]}. Run: npx playwright install chromium`);
}
const report = [];
let navigated = 0, attempts = 0;
for (const target of targets) {
  const slug = slugFor(target);
  for (const vpName of chosen) {
    for (const motion of ['no-preference', 'reduce']) {
      const vp = VIEWPORTS[vpName];
      const ctx = await browser.newContext({
        viewport: { width: vp.width, height: vp.height }, isMobile: vp.isMobile, hasTouch: vp.hasTouch,
        deviceScaleFactor: vp.isMobile ? 2 : 1, reducedMotion: motion, colorScheme: flag('dark') ? 'dark' : 'light',
      });
      const page = await ctx.newPage();
      const consoleErrors = [];
      page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });
      page.on('pageerror', (e) => consoleErrors.push(String(e).slice(0, 200)));
      const t0 = Date.now();
      let status = null, navError = null;
      attempts += 1;
      try {
        // Wait for the document, then give the network a bounded chance to settle: analytics-heavy
        // sites never go fully idle, and waiting for them turned every render into a 45s timeout.
        const res = await page.goto(target.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
        status = res && res.status();
        navigated += 1;
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
      } catch (e) {
        navError = `navigation: ${e.message.split('\n')[0]}`;
        consoleErrors.push(navError);
      }
      if (navError) {
        report.push({ url: target.url, viewport: vpName, motion, status, loadMs: Date.now() - t0, navError, consoleErrors });
        await ctx.close();
        continue;
      }
      await page.evaluate(() => document.fonts && document.fonts.ready).catch(() => {});
      await page.waitForTimeout(motion === 'reduce' ? 300 : 1200);
      const base = `${slug}__${vpName}__${motion === 'reduce' ? 'reduced' : 'motion'}`;
      await page.screenshot({ path: path.join(outDir, `${base}__fold.png`) });
      if (flag('full') && motion === 'no-preference') {
        await page.screenshot({ path: path.join(outDir, `${base}__full.png`), fullPage: true });
      }
      const m = await page.evaluate(measure, { probeAttr: PROBE, generic: GENERIC.source });
      const { probes, ...metrics } = m;
      let fontsPainted = null, fontsFallingBack = [];
      if (motion === 'no-preference') {
        try {
          const r = await paintedFonts(ctx, page, probes);
          fontsPainted = r.painted;
          fontsFallingBack = r.falling;
        } catch (e) {
          consoleErrors.push(`font check failed: ${e.message.split('\n')[0]}`);
        }
        fs.writeFileSync(path.join(outDir, `${base}__text.txt`), metrics.text);
      }
      let axe = null;
      if (AxeBuilder && !flag('no-axe') && motion === 'no-preference' && vpName === chosen[0]) {
        try {
          const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
          axe = r.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help }));
        } catch (e) { axe = [{ id: 'axe-failed', help: e.message.slice(0, 120) }]; }
      }
      report.push({ url: target.url, viewport: vpName, motion, status, loadMs: Date.now() - t0, ...metrics,
        fontsPainted, fontsFallingBack, consoleErrors, axe });
      await ctx.close();
    }
  }
}
await browser.close();

const findings = [];
const add = (rule, at, message, severity = 'error') => findings.push({ severity, rule, message: `${at}: ${message}`, file: at.split(' ')[0] });
// Touch viewports, where a 44px target is the standard (the 24px floor applies everywhere).
const TOUCH = (vp) => /^(phone|small)/.test(vp);
for (const r of report) {
  const at = `${r.url} ${r.viewport}/${r.motion}`;
  if (r.navError) { add('render.navigation', at, r.navError); continue; }
  if (r.status && r.status >= 400) add('render.http', at, `HTTP ${r.status}`);
  if (r.horizontalOverflow) add('render.overflow', at, `page scrolls sideways by ${r.horizontalOverflow}px (${r.overflowingElements.join(', ')})`);
  if (r.tapTargetsUnder24px.length) add('render.tap-target', at, `${r.tapTargetsUnder24px.length}+ tap targets under 24px, e.g. ${r.tapTargetsUnder24px[0]}`);
  if (TOUCH(r.viewport) && r.motion === 'no-preference' && r.tapTargetsUnder44px.length) {
    add('render.tap-target-44', at, `${r.tapTargetsUnder44px.length}+ tap targets under 44px, e.g. ${r.tapTargetsUnder44px[0]}`, 'warn');
  }
  if (r.fontsFallingBack.length) add('render.font-fallback', at, `fonts not painted, falling back: ${r.fontsFallingBack.map((f) => `${f} (painted with ${(r.fontsPainted?.[f] || []).join(', ') || 'nothing'})`).join('; ')}`);
  if (r.imagesMissingAlt) add('render.alt', at, `${r.imagesMissingAlt} images without alt`);
  if (r.consoleErrors.length) add('render.console', at, `${r.consoleErrors.length} console errors, first: ${r.consoleErrors[0]}`);
  if (r.h1.length !== 1) add('render.h1', at, `${r.h1.length} h1 elements`);
  for (const v of r.axe || []) if (['serious', 'critical'].includes(v.impact)) add('render.axe', at, `axe ${v.impact} ${v.id} on ${v.nodes} nodes (${v.help})`);
}
const allFailed = attempts > 0 && navigated === 0;
if (allFailed) findings.unshift({ severity: 'error', rule: 'tool.could-not-run', message: 'every navigation failed, so nothing was rendered' });

const pick = (names, test) => report.find((r) => !r.navError && r.motion === 'no-preference' && (names.includes(r.viewport))) ||
  report.find((r) => !r.navError && r.motion === 'no-preference' && test(r.viewport));
const desktop = pick(['desktop-1440x900', 'desktop'], (v) => /^(desktop|mac|laptop)/.test(v));
const phone = pick(['phone-390x844', 'phone'], (v) => v.startsWith('phone') && !v.includes('landscape'));
const md = [
  `# Shots ${stamp}`, '',
  `Screenshots: ${outDir}`, '',
  desktop ? `Desktop (${desktop.viewport}): ${desktop.words} words in main, ${desktop.screens} screens tall, ${desktop.maxConsecutiveTextOnly} text-only sections in a row, fonts used: ${desktop.fontsUsed.join(', ') || 'generic only'}` : '',
  phone ? `Phone (${phone.viewport}): ${phone.screens} screens tall, ${phone.fontSizes.length} text sizes, smallest ${phone.smallestTextPx}px. A marketing page over about 400 words of prose, or more than one text-only section in a row, reads as a wall.` : '',
  '', '## Problems', '', ...(findings.length ? findings.map((p) => `- ${p.severity === 'warn' ? '(warning) ' : ''}${p.message}`) : ['- None measured. That says nothing about whether it is beautiful: look at the screenshots.']),
  '', '## Look at these before saying anything', '',
  '- Each viewport\'s fold, with motion and reduced. Does the reduced version land on the finished state?',
  '- The phone fold: does the main action sit fully on the first screen?',
  '- Name three decisions in the screenshots a model would not have made by default (CHECKLIST.md section 2).', '',
];
fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify(report, null, 1));
fs.writeFileSync(path.join(outDir, 'report.md'), md.join('\n'));
console.log(md.join('\n'));
const errors = findings.filter((f) => f.severity === 'error').length;
const exit = allFailed ? 2 : errors ? 1 : 0;
finish(exit, findings, allFailed ? 'every navigation failed' : `${errors} problems and ${findings.length - errors} warnings over ${report.length} renders`,
  { outDir, viewports: chosen, results: report });
