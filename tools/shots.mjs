#!/usr/bin/env node
// The look gate. Renders a page the way people will actually see it and measures what
// eyeballing misses. Screenshots are for a human (or a vision model) to judge; the numbers
// are for catching regressions. Neither one says the design is good.
//
//   node tools/shots.mjs https://example.com [more urls] [--out .design/shots] [--full]
//                        [--viewports desktop,phone,small] [--no-axe] [--dark]
//
// Needs: npm install (playwright, @axe-core/playwright) and `npx playwright install chromium`.
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const flag = (n) => args.includes(`--${n}`);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const urls = args.filter((a, i) => !a.startsWith('--') && !['--out', '--viewports'].includes(args[i - 1]));
if (!urls.length) {
  console.error('usage: node tools/shots.mjs <url> [url...] [--out dir] [--full] [--viewports desktop,phone,small] [--no-axe] [--dark]');
  process.exit(2);
}

let chromium, AxeBuilder;
try {
  ({ chromium } = await import('playwright'));
} catch {
  console.error('Playwright is not installed. Run: npm install && npx playwright install chromium');
  process.exit(2);
}
try { AxeBuilder = (await import('@axe-core/playwright')).default; } catch { AxeBuilder = null; }

const VIEWPORTS = {
  desktop: { width: 1440, height: 900, isMobile: false, hasTouch: false },
  laptop: { width: 1280, height: 720, isMobile: false, hasTouch: false },
  tablet: { width: 820, height: 1180, isMobile: true, hasTouch: true },
  phone: { width: 390, height: 844, isMobile: true, hasTouch: true },
  small: { width: 320, height: 568, isMobile: true, hasTouch: true },
};
const chosen = opt('viewports', 'desktop,phone,small').split(',').filter((v) => VIEWPORTS[v]);
const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
const outDir = path.resolve(opt('out', '.design/shots'), stamp);
fs.mkdirSync(outDir, { recursive: true });

// Runs inside the page. Pure measurement, no styling changes.
function measure() {
  const vw = window.innerWidth, vh = window.innerHeight;
  const doc = document.documentElement;
  const main = document.querySelector('main') || document.body;
  const words = (main.innerText || '').split(/\s+/).filter(Boolean).length;
  const interactive = [...document.querySelectorAll('a[href], button, input, select, textarea, [role="button"], [tabindex]:not([tabindex="-1"])')]
    .filter((el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden'; });
  // WCAG 2.5.8 exempts links inline in a sentence, so skip an <a> whose parent holds more text than it does
  const inline = (el) => el.tagName === 'A' && el.parentElement && (el.parentElement.innerText || '').trim().length > (el.innerText || '').trim().length + 12;
  const small = interactive.filter((el) => { const r = el.getBoundingClientRect(); return (r.width < 24 || r.height < 24) && !inline(el); })
    .slice(0, 12).map((el) => `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''} "${(el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().width)}x${Math.round(el.getBoundingClientRect().height)}`);
  const wide = [...document.querySelectorAll('body *')].filter((el) => el.getBoundingClientRect().right > vw + 1)
    .slice(0, 8).map((el) => `${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''}`);
  const imgs = [...document.images];
  const families = new Set([...document.querySelectorAll('h1,h2,h3,p,a,button,li')].slice(0, 400)
    .map((el) => getComputedStyle(el).fontFamily.split(',')[0].replace(/["']/g, '').trim()));
  const loaded = [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family.replace(/["']/g, ''));
  const h1 = [...document.querySelectorAll('h1')].map((h) => h.innerText.trim().slice(0, 80));
  return {
    title: document.title,
    lang: doc.getAttribute('lang'),
    h1,
    words,
    screens: +(doc.scrollHeight / vh).toFixed(1),
    horizontalOverflow: doc.scrollWidth > vw + 1 ? doc.scrollWidth - vw : 0,
    overflowingElements: doc.scrollWidth > vw + 1 ? wide : [],
    interactiveCount: interactive.length,
    tapTargetsUnder24px: small,
    imagesMissingAlt: imgs.filter((i) => !i.hasAttribute('alt')).length,
    imagesMissingSize: imgs.filter((i) => !i.getAttribute('width') && !i.style.aspectRatio && !getComputedStyle(i).aspectRatio.includes('/')).length,
    fontsUsed: [...families],
    fontsLoaded: [...new Set(loaded)],
    fontsFallingBack: [...families].filter((f) => !loaded.includes(f) && !/^(system-ui|-apple-system|ui-|sans-serif|serif|monospace|Times|Arial|Helvetica)/i.test(f)),
  };
}

const browser = await chromium.launch();
const report = [];
for (const url of urls) {
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
      let status = null;
      try {
        const res = await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
        status = res && res.status();
      } catch (e) {
        consoleErrors.push(`navigation: ${e.message.split('\n')[0]}`);
      }
      await page.waitForTimeout(motion === 'reduce' ? 300 : 1200);
      const slug = `${new URL(url).hostname}${new URL(url).pathname.replace(/\W+/g, '-')}`.replace(/-+$/, '');
      const base = `${slug}__${vpName}__${motion === 'reduce' ? 'reduced' : 'motion'}`;
      await page.screenshot({ path: path.join(outDir, `${base}__fold.png`) });
      if (flag('full') && motion === 'no-preference') {
        await page.screenshot({ path: path.join(outDir, `${base}__full.png`), fullPage: true });
      }
      const m = await page.evaluate(measure);
      let axe = null;
      if (AxeBuilder && !flag('no-axe') && motion === 'no-preference' && vpName === chosen[0]) {
        try {
          const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
          axe = r.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help }));
        } catch (e) { axe = [{ id: 'axe-failed', help: e.message.slice(0, 120) }]; }
      }
      report.push({ url, viewport: vpName, motion, status, loadMs: Date.now() - t0, ...m, consoleErrors, axe });
      await ctx.close();
    }
  }
}
await browser.close();

const problems = [];
for (const r of report) {
  const at = `${r.url} ${r.viewport}/${r.motion}`;
  if (r.status && r.status >= 400) problems.push(`${at}: HTTP ${r.status}`);
  if (r.horizontalOverflow) problems.push(`${at}: page scrolls sideways by ${r.horizontalOverflow}px (${r.overflowingElements.join(', ')})`);
  if (r.tapTargetsUnder24px.length) problems.push(`${at}: ${r.tapTargetsUnder24px.length}+ tap targets under 24px, e.g. ${r.tapTargetsUnder24px[0]}`);
  if (r.fontsFallingBack.length) problems.push(`${at}: fonts not loaded, falling back: ${r.fontsFallingBack.join(', ')}`);
  if (r.imagesMissingAlt) problems.push(`${at}: ${r.imagesMissingAlt} images without alt`);
  if (r.consoleErrors.length) problems.push(`${at}: ${r.consoleErrors.length} console errors, first: ${r.consoleErrors[0]}`);
  if (r.h1.length !== 1) problems.push(`${at}: ${r.h1.length} h1 elements`);
  for (const v of r.axe || []) if (['serious', 'critical'].includes(v.impact)) problems.push(`${at}: axe ${v.impact} ${v.id} on ${v.nodes} nodes (${v.help})`);
}
const desktop = report.find((r) => r.viewport === 'desktop' && r.motion === 'no-preference');
const phone = report.find((r) => r.viewport === 'phone' && r.motion === 'no-preference');
const md = [
  `# Shots ${stamp}`, '',
  `Screenshots: ${outDir}`, '',
  desktop ? `Desktop: ${desktop.words} words in main, ${desktop.screens} screens tall, fonts used: ${desktop.fontsUsed.join(', ')}` : '',
  phone ? `Phone: ${phone.screens} screens tall. A marketing page over about 400 words of prose, or more than one text-only section in a row, reads as a wall.` : '',
  '', '## Problems', '', ...(problems.length ? problems.map((p) => `- ${p}`) : ['- None measured. That says nothing about whether it is beautiful: look at the screenshots.']),
  '', '## Look at these before saying anything', '',
  '- Each viewport\'s fold, with motion and reduced. Does the reduced version land on the finished state?',
  '- The phone fold: does the main action sit fully on the first screen?',
  '- Name three decisions in the screenshots a model would not have made by default (CHECKLIST.md section 2).', '',
];
fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify(report, null, 1));
fs.writeFileSync(path.join(outDir, 'report.md'), md.join('\n'));
console.log(md.join('\n'));
process.exit(problems.length ? 1 : 0);
