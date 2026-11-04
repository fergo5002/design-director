#!/usr/bin/env node
// Tear down a reference: look at it the way a designer would, and measure what a designer
// would otherwise guess. For each URL it saves the desktop and phone folds, a full-page
// capture, and a strip of scroll-stop frames, then measures the live page: the type scale
// and faces by how much text they set, the palette by how much area each colour covers, the
// radii, shadows, spacing and content width, the motion, the stack it was built on, the
// structure and calls to action, and the generated-design tells. Optionally it walks a
// journey by clicking through named links or buttons, screenshotting every step, and never
// submits a form or touches a payment or password field.
//
//   node tools/teardown.mjs <url> [more urls] [--out dir] [--frames 6] [--walk "Book now>Check availability"]
//                           [--viewports desktop,phone] [--no-full]
//
// The numbers are evidence for a take, never the take itself: open the images and judge.
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const flag = (n) => args.includes(`--${n}`);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const VALUED = ['--out', '--frames', '--walk', '--viewports', '--full-max'];
const urls = args.filter((a, i) => !a.startsWith('--') && !VALUED.includes(args[i - 1]));
if (!urls.length) {
  console.error('usage: node tools/teardown.mjs <url> [url...] [--out dir] [--frames 6] [--walk "A>B"] [--viewports desktop,phone] [--no-full]');
  process.exit(2);
}
let chromium;
try { ({ chromium } = await import('playwright')); } catch {
  console.error('Playwright is not installed. Run in the design-director repo: npm install && npx playwright install chromium');
  process.exit(2);
}

const VIEWPORTS = {
  desktop: { width: 1440, height: 900, isMobile: false, hasTouch: false, deviceScaleFactor: 1 },
  laptop: { width: 1280, height: 720, isMobile: false, hasTouch: false, deviceScaleFactor: 1 },
  phone: { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
};
const viewports = opt('viewports', 'desktop,phone').split(',').map((v) => v.trim()).filter((v) => VIEWPORTS[v]);
const frames = Math.max(0, Math.min(12, parseInt(opt('frames', '6'), 10) || 0));
const walk = (opt('walk', '') || '').split('>').map((s) => s.trim()).filter(Boolean);
const outRoot = path.resolve(opt('out', '.design/teardowns'));
// Never click these: a teardown looks, it never buys, books, signs up or logs in.
const FORBIDDEN = /\b(pay|payment|purchase|checkout|place order|confirm|submit|complete booking|sign ?up|register|create account|log ?in|sign ?in|subscribe|donate)\b/i;

// ------------------------------------------------------------------ in-page measurement
function measure() {
  const vw = window.innerWidth, vh = window.innerHeight;
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05; };
  const rgb = (c) => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); if (p.length > 3 && p[3] < 0.5) return null; return '#' + p.slice(0, 3).map((x) => Math.round(x).toString(16).padStart(2, '0')).join(''); };
  const bump = (map, k, w) => { if (k) map.set(k, (map.get(k) || 0) + w); };
  const top = (map, n, total) => [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map(([k, w]) => ({ value: k, share: +(w / (total || 1)).toFixed(3) }));
  const all = [...document.querySelectorAll('body *')].slice(0, 6000).filter(vis);

  // type: weight each text style by the characters it actually sets
  const fam = new Map(), sizes = new Map(), styles = new Map();
  let chars = 0;
  for (const el of all) {
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim();
    if (!own) continue;
    const s = getComputedStyle(el); const n = own.length; chars += n;
    bump(fam, s.fontFamily.split(',')[0].replace(/["']/g, '').trim(), n);
    bump(sizes, Math.round(parseFloat(s.fontSize)) + 'px', n);
  }
  const role = (sel) => { const el = [...document.querySelectorAll(sel)].find(vis); if (!el) return null; const s = getComputedStyle(el);
    return { text: (el.innerText || '').trim().slice(0, 90), family: s.fontFamily.split(',')[0].replace(/["']/g, ''), size: s.fontSize, weight: s.fontWeight,
      lineHeight: s.lineHeight, tracking: s.letterSpacing, transform: s.textTransform, colour: rgb(s.color) }; };
  for (const [k, sel] of Object.entries({ h1: 'h1', h2: 'h2', h3: 'h3', body: 'main p, article p, p', button: 'button, a[class*="btn" i], a[class*="button" i]', nav: 'nav a, header a' })) styles.set(k, role(sel));

  // colour: backgrounds by painted area, text by characters, accents from controls
  const bg = new Map(), fg = new Map(), accent = new Map();
  let area = 0;
  const bodyBg = rgb(getComputedStyle(document.body).backgroundColor) || rgb(getComputedStyle(document.documentElement).backgroundColor) || '#ffffff';
  bump(bg, bodyBg, vw * document.documentElement.scrollHeight * 0.25); area += vw * document.documentElement.scrollHeight * 0.25;
  for (const el of all) {
    const s = getComputedStyle(el); const r = el.getBoundingClientRect(); const a = Math.min(r.width, vw) * Math.min(r.height, 4000);
    const c = rgb(s.backgroundColor); if (c) { bump(bg, c, a); area += a; }
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim();
    if (own) bump(fg, rgb(s.color), own.length);
  }
  // controls weighted by painted area; an unstyled browser-default control is a tell, not an accent
  let defaultControls = 0;
  for (const el of [...document.querySelectorAll('button, a[class*="btn" i], a[class*="button" i], [role="button"], input[type="submit"], input[type="button"]')].filter(vis).slice(0, 60)) {
    const s = getComputedStyle(el); const r = el.getBoundingClientRect(); const c = rgb(s.backgroundColor);
    if (c === '#efefef' || c === '#e9e9ed' || c === '#f0f0f0') { defaultControls++; continue; }
    bump(accent, c || rgb(s.color), r.width * r.height);
  }

  // shape and space
  const radii = new Map(), shadows = { count: 0 }, gaps = new Map();
  for (const el of all.slice(0, 3000)) {
    const s = getComputedStyle(el);
    if (s.borderTopLeftRadius !== '0px') bump(radii, s.borderTopLeftRadius, 1);
    if (s.boxShadow && s.boxShadow !== 'none') shadows.count++;
    if (s.rowGap && s.rowGap !== 'normal' && s.rowGap !== '0px') bump(gaps, s.rowGap, 1);
  }
  const blocks = [...document.querySelectorAll('main > *, body > section, main section, body > div > section')].filter(vis).slice(0, 40);
  const sectionPad = blocks.map((el) => { const s = getComputedStyle(el); return Math.round(parseFloat(s.paddingTop) + parseFloat(s.paddingBottom)); }).filter((x) => x > 0);
  const textWidths = [...document.querySelectorAll('p')].filter(vis).map((p) => Math.round(p.getBoundingClientRect().width)).sort((a, b) => a - b);
  const measureCh = textWidths.length ? textWidths[Math.floor(textWidths.length / 2)] : null;

  // motion and media
  const durs = new Map(); let animated = 0;
  for (const el of all.slice(0, 3000)) { const s = getComputedStyle(el);
    if (s.transitionDuration && s.transitionDuration !== '0s') bump(durs, s.transitionDuration.split(',')[0], 1);
    if (s.animationName && s.animationName !== 'none') animated++; }
  const motion = { transitions: top(durs, 4, [...durs.values()].reduce((a, b) => a + b, 0)), cssAnimations: animated,
    libraries: ['gsap', 'ScrollTrigger', 'Lenis', 'lenis', 'LocomotiveScroll', 'THREE', 'Swiper', 'AOS', 'framerMotion'].filter((k) => k in window),
    videos: [...document.querySelectorAll('video')].map((v) => ({ autoplay: v.autoplay, muted: v.muted, loop: v.loop })).slice(0, 6),
    canvases: document.querySelectorAll('canvas').length,
    reducedMotionRules: [...document.styleSheets].some((sh) => { try { return [...sh.cssRules].some((r) => r.media && /prefers-reduced-motion/.test(r.media.mediaText)); } catch { return false; } }) };

  // stack: what it was built on (a template platform is a lead for a counter-example, never proof)
  const html = document.documentElement.outerHTML.slice(0, 400000);
  const gen = document.querySelector('meta[name="generator"]');
  const stack = [
    [/__NEXT_DATA__|\/_next\//, 'Next.js'], [/data-wf-site|webflow/i, 'Webflow'], [/framerusercontent|data-framer/i, 'Framer'],
    [/cdn\.shopify|Shopify\.theme/, 'Shopify'], [/static\.wixstatic|wix\.com/i, 'Wix'], [/squarespace/i, 'Squarespace'],
    [/wp-content|wp-includes/, 'WordPress'], [/elementor/i, 'Elementor'], [/et_pb_|\/themes\/Divi\//, 'Divi'], [/astro-island|\/_astro\//, 'Astro'],
    [/__nuxt|_nuxt\//, 'Nuxt'], [/data-reactroot|react/i, 'React'], [/tailwind/i, 'Tailwind classes'],
  ].filter(([re]) => re.test(html)).map(([, n]) => n);
  if (gen) stack.unshift(`generator: ${gen.content}`);

  // structure and copy
  const headings = [...document.querySelectorAll('h1, h2, h3')].filter(vis).slice(0, 30).map((h) => `${h.tagName.toLowerCase()} ${(h.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 90)}`);
  const navLabels = [...document.querySelectorAll('nav a, header a')].filter(vis).map((a) => (a.innerText || '').trim()).filter((t) => t && t.length < 30).slice(0, 14);
  const ctas = [...document.querySelectorAll('button, a[class*="btn" i], a[class*="button" i], [role="button"], input[type="submit"]')].filter(vis)
    .map((b) => (b.innerText || b.value || b.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ')).filter((t) => t && t.length < 40 && t.length > 2 && !/^[\d\s.<>‹›«»←→]+$/.test(t));
  const ctaCounts = {}; for (const c of ctas) ctaCounts[c] = (ctaCounts[c] || 0) + 1;
  const aboveFoldCta = ctas.length && [...document.querySelectorAll('button, a[class*="btn" i], a[class*="button" i]')].filter(vis).some((b) => b.getBoundingClientRect().top < vh);
  const main = document.querySelector('main') || document.body;
  const words = (main.innerText || '').split(/\s+/).filter(Boolean).length;
  const forms = [...document.forms].map((f) => ({ fields: f.querySelectorAll('input:not([type=hidden]), select, textarea').length })).slice(0, 6);
  const phone = /(\+?\d[\d ()-]{7,}\d)/.test((document.querySelector('header') || document.body).innerText || '');

  // generated-design tells, measured
  const text = (main.innerText || '').toLowerCase();
  const SLOP_WORDS = ['seamless', 'unlock', 'elevate', 'empower', 'revolutionise', 'revolutionize', 'cutting-edge', 'next-level', 'supercharge', 'effortless', 'game-changer', 'in today\'s', 'your journey', 'world-class', 'tailored solutions', 'nestled', 'oasis', 'hidden gem', 'home away from home', 'look no further', 'unforgettable', 'second to none', 'one-stop shop'];
  const eyebrows = [...document.querySelectorAll('h1, h2')].filter(vis).filter((h) => { const prev = h.previousElementSibling; if (!prev || !vis(prev)) return false;
    const s = getComputedStyle(prev); return s.textTransform === 'uppercase' && parseFloat(s.fontSize) < 15 && (prev.innerText || '').length < 40; }).length;
  const gradientText = all.filter((el) => { const s = getComputedStyle(el); return (s.webkitBackgroundClip === 'text' || s.backgroundClip === 'text') && /gradient/.test(s.backgroundImage); }).length;
  const purpleGradients = all.filter((el) => /gradient/.test(getComputedStyle(el).backgroundImage) && /(rgb\((1[0-4]\d|[6-9]\d), ?\d{1,2}, ?2[0-5]\d\)|#(6|7|8)[0-9a-f][0-9a-f]{2}f[0-9a-f])/i.test(getComputedStyle(el).backgroundImage)).length;
  const glass = all.filter((el) => { const s = getComputedStyle(el); return (s.backdropFilter || s.webkitBackdropFilter || 'none') !== 'none'; }).length;
  const emojiHeadings = [...document.querySelectorAll('h1,h2,h3,h4')].filter((h) => /\p{Extended_Pictographic}/u.test(h.innerText || '')).length;
  const triads = [...document.querySelectorAll('div, ul, section')].filter((el) => { const k = [...el.children]; return k.length === 3 && k.every((c) => c.tagName === k[0].tagName && c.className === k[0].className) && k.every((c) => c.querySelector('svg, img') && c.querySelector('h3, h4, strong')); }).length;
  const OVERUSED = /^(inter|poppins|montserrat|roboto|open sans|lato|nunito|raleway|plus jakarta sans|space grotesk|dm sans|oswald|bebas neue|playfair display)$/i;
  const lead = top(fam, 1, chars)[0];
  const defaultFace = lead && OVERUSED.test(lead.value) ? `${lead.value} ${Math.round(lead.share * 100)}%` : null;
  const paras = [...document.querySelectorAll('p')].filter(vis).filter((x) => (x.innerText || '').length > 60);
  const justifiedParagraphs = paras.filter((x) => getComputedStyle(x).textAlign === 'justify').length;
  const hs = [...document.querySelectorAll('h1, h2, h3')].filter(vis);
  const shareOf = (f) => (hs.length ? +(hs.filter(f).length / hs.length).toFixed(2) : 0);
  const capsHeadings = shareOf((x) => getComputedStyle(x).textTransform === 'uppercase' || ((x.innerText || '').length > 6 && x.innerText === x.innerText.toUpperCase() && /[A-Z]/.test(x.innerText)));
  const centredHeadings = shareOf((x) => getComputedStyle(x).textAlign === 'center');
  const slop = { words: SLOP_WORDS.filter((w) => text.includes(w)), eyebrows, gradientText, purpleGradients, glass, emojiHeadings,
    iconCardTriads: triads, defaultControls, defaultFace, justifiedParagraphs, capsHeadings, centredHeadings };

  return {
    title: document.title, lang: document.documentElement.lang, words, screens: +(document.documentElement.scrollHeight / vh).toFixed(1),
    type: { families: top(fam, 4, chars), sizes: top(sizes, 8, chars), roles: Object.fromEntries(styles) },
    colour: { backgrounds: top(bg, 6, area), text: top(fg, 4, [...fg.values()].reduce((a, b) => a + b, 0)), accents: top(accent, 3, [...accent.values()].reduce((a, b) => a + b, 0)),
      distinct: new Set([...bg.keys(), ...fg.keys()]).size },
    shape: { radii: top(radii, 4, [...radii.values()].reduce((a, b) => a + b, 0)), shadowedElements: shadows.count },
    space: { sectionPaddingMedian: sectionPad.length ? sectionPad.sort((a, b) => a - b)[Math.floor(sectionPad.length / 2)] : null, gaps: top(gaps, 4, [...gaps.values()].reduce((a, b) => a + b, 0)),
      paragraphWidthMedian: measureCh },
    motion, stack: [...new Set(stack)],
    structure: { headings, navLabels, ctas: Object.entries(ctaCounts).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([t, n]) => (n > 1 ? `${t} (x${n})` : t)),
      ctaAboveFold: !!aboveFoldCta, forms, phoneInHeader: phone, images: document.images.length },
    slop,
  };
}

// ------------------------------------------------------------------ helpers
const slugOf = (u) => { const x = new URL(u); return `${x.hostname.replace(/^www\./, '')}${x.pathname.replace(/\W+/g, '-')}`.replace(/-+$/, ''); };
async function settle(page) {
  // dismiss the commonest cookie walls so the design, not the banner, gets measured
  for (const t of ['Accept all', 'Accept All', 'Accept', 'Allow all', 'I agree', 'Agree', 'Got it', 'OK']) {
    const b = page.getByRole('button', { name: t, exact: true }).first();
    try { if (await b.isVisible({ timeout: 300 })) { await b.click({ timeout: 1000 }); break; } } catch { /* none */ }
  }
  await page.waitForTimeout(600);
}
async function lazyScroll(page) {
  await page.evaluate(async () => { const h = document.documentElement.scrollHeight; for (let y = 0; y < h; y += window.innerHeight * 0.8) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 120)); } window.scrollTo(0, 0); });
  await page.waitForTimeout(500);
}
const fmt = (xs) => (xs || []).map((x) => `${x.value} ${Math.round(x.share * 100)}%`).join(', ');

// ------------------------------------------------------------------ run
const browser = await chromium.launch();
const summary = [];
for (const url of urls) {
  const dir = path.join(outRoot, slugOf(url));
  fs.mkdirSync(dir, { recursive: true });
  const rec = { url, captured: new Date().toISOString(), files: [], viewports: {}, walk: [] };
  for (const vp of viewports) {
    const v = VIEWPORTS[vp];
    const ctx = await browser.newContext({ viewport: { width: v.width, height: v.height }, isMobile: v.isMobile, hasTouch: v.hasTouch, deviceScaleFactor: v.deviceScaleFactor });
    const page = await ctx.newPage();
    let status = null, err = null;
    try { const res = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 }); status = res && res.status();
      await page.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => {}); } catch (e) { err = e.message.split('\n')[0]; }
    await settle(page);
    const fold = path.join(dir, `${vp}__fold.png`);
    await page.screenshot({ path: fold }).catch(() => {});
    rec.files.push(fold);
    await lazyScroll(page);
    if (!flag('no-full')) {
      // capped so a 20,000px page is still one image a person or a model can read
      const f = path.join(dir, `${vp}__full.png`);
      const h = await page.evaluate(() => document.documentElement.scrollHeight).catch(() => v.height);
      const cap = parseInt(opt('full-max', '9000'), 10);
      await page.screenshot({ path: f, fullPage: true, clip: { x: 0, y: 0, width: v.width, height: Math.min(h, cap) } }).catch(() => {});
      rec.files.push(f);
      if (h > cap) rec.fullTruncated = `${vp} page is ${h}px tall; the full capture stops at ${cap}px (--full-max)`;
    }
    if (vp === viewports[0] && frames) {
      const h = await page.evaluate(() => document.documentElement.scrollHeight);
      const step = Math.max(v.height, Math.floor(h / (frames + 1)));
      for (let i = 1; i <= frames && i * step < h; i++) {
        await page.evaluate((y) => window.scrollTo(0, y), i * step); await page.waitForTimeout(450);
        const f = path.join(dir, `${vp}__frame-${String(i).padStart(2, '0')}.png`); await page.screenshot({ path: f }).catch(() => {}); rec.files.push(f);
      }
      await page.evaluate(() => window.scrollTo(0, 0));
    }
    let m = null;
    try { m = await page.evaluate(measure); } catch (e) { err = err || `measure: ${e.message.split('\n')[0]}`; }
    rec.viewports[vp] = { status, error: err, ...m };

    if (vp === viewports[0] && walk.length) {
      for (const [i, label] of walk.entries()) {
        const step = { label, ok: false };
        if (FORBIDDEN.test(label)) { step.note = 'refused: a teardown never buys, books, signs up or logs in'; rec.walk.push(step); break; }
        const target = page.getByRole('link', { name: label }).or(page.getByRole('button', { name: label })).or(page.getByText(label, { exact: false })).first();
        try {
          // a control submits only when it has a form to submit; a bare <button> reports type "submit" anyway
          const isSubmit = await target.evaluate((el) => !!el.form && ['submit', 'image'].includes(el.type)).catch(() => false);
          if (isSubmit) { step.note = 'refused: that control submits a form'; rec.walk.push(step); break; }
          const before = await page.evaluate(() => location.href + '|' + document.body.innerText.length + '|' + document.body.innerText.slice(0, 2000));
          await target.click({ timeout: 6000 });
          await page.waitForLoadState('domcontentloaded', { timeout: 15000 }).catch(() => {});
          // let the next screen arrive: network settles, then transitions finish
          await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
          await page.waitForTimeout(1800);
          const f = path.join(dir, `walk-${String(i + 1).padStart(2, '0')}.png`);
          await page.screenshot({ path: f }); rec.files.push(f);
          step.ok = true; step.url = page.url(); step.shot = f;
          const after = await page.evaluate(() => location.href + '|' + document.body.innerText.length + '|' + document.body.innerText.slice(0, 2000));
          step.changed = after !== before;
          if (!step.changed) step.note = 'the click changed nothing visible: a hover menu, a dead control, or a script that did not load';
          step.sensitive = await page.evaluate(() => !!document.querySelector('input[type=password], input[autocomplete*="cc-"], input[name*="card" i]'));
          if (step.sensitive) { step.note = 'stopped: a password or card field is on screen'; rec.walk.push(step); break; }
        } catch (e) { step.note = `could not click: ${e.message.split('\n')[0].slice(0, 120)}`; rec.walk.push(step); break; }
        if (!step.changed) { rec.walk.push(step); continue; }
        rec.walk.push(step);
      }
    }
    await ctx.close();
  }
  fs.writeFileSync(path.join(dir, 'teardown.json'), JSON.stringify(rec, null, 1));

  const d = rec.viewports[viewports[0]] || {}, p = rec.viewports.phone || {};
  const r = (d.type && d.type.roles) || {};
  const line = (k) => (r[k] ? `${r[k].family} ${r[k].size}/${r[k].lineHeight} weight ${r[k].weight}${r[k].tracking !== 'normal' ? ' tracking ' + r[k].tracking : ''}${r[k].transform !== 'none' ? ' ' + r[k].transform : ''}` : 'none found');
  const s = d.slop || {};
  const tells = [s.words && s.words.length ? `stock copy (${s.words.join(', ')})` : '', s.eyebrows ? `${s.eyebrows} eyebrows` : '', s.gradientText ? `${s.gradientText} gradient-text elements` : '',
    s.purpleGradients ? 'purple-blue gradients' : '', s.glass ? `${s.glass} glass (backdrop-filter) elements` : '', s.emojiHeadings ? `${s.emojiHeadings} emoji headings` : '', s.iconCardTriads ? `${s.iconCardTriads} icon-card triads` : '', s.defaultControls ? `${s.defaultControls} browser-default controls` : '',
    s.defaultFace ? `an overused default face carries the text (${s.defaultFace})` : '', s.justifiedParagraphs ? `${s.justifiedParagraphs} justified paragraphs` : '',
    s.capsHeadings >= 0.6 ? `${Math.round(s.capsHeadings * 100)}% of headings in capitals` : '', s.centredHeadings >= 0.8 ? `${Math.round(s.centredHeadings * 100)}% of headings centred` : ''].filter(Boolean);
  const md = [
    `# Teardown: ${url}`, '', `Captured ${rec.captured}. Folder: ${dir}`, d.error ? `\nProblem: ${d.error}` : '', '',
    '## Look at these first', '', ...rec.files.map((f) => `- ${f}`), '',
    '## Measured',
    `- Status ${d.status}; ${d.words} words; ${d.screens} screens tall on desktop, ${p.screens ?? '?'} on phone`,
    `- Faces by text set: ${fmt(d.type && d.type.families)}`,
    `- Sizes by text set: ${fmt(d.type && d.type.sizes)}`,
    `- h1: ${line('h1')}${r.h1 ? ` "${r.h1.text}"` : ''}`, `- h2: ${line('h2')}`, `- body: ${line('body')}`, `- buttons: ${line('button')}`, `- nav: ${line('nav')}`,
    `- Backgrounds by area: ${fmt(d.colour && d.colour.backgrounds)}`, `- Text colours: ${fmt(d.colour && d.colour.text)}`, `- Control colours: ${fmt(d.colour && d.colour.accents)}; ${d.colour && d.colour.distinct} distinct colours`,
    `- Radii: ${fmt(d.shape && d.shape.radii) || 'square'}; ${d.shape && d.shape.shadowedElements} shadowed elements`,
    `- Section padding median ${d.space && d.space.sectionPaddingMedian}px; paragraph width median ${d.space && d.space.paragraphWidthMedian}px; gaps ${fmt(d.space && d.space.gaps)}`,
    `- Motion: transitions ${fmt(d.motion && d.motion.transitions) || 'none'}; ${d.motion && d.motion.cssAnimations} CSS animations; libraries ${(d.motion && d.motion.libraries || []).join(', ') || 'none'}; ${d.motion && d.motion.videos.length} videos; ${d.motion && d.motion.canvases} canvases; reduced-motion rules ${d.motion && d.motion.reducedMotionRules ? 'yes' : 'no'}`,
    `- Stack: ${(d.stack || []).join(', ') || 'unknown'}`,
    `- Nav: ${(d.structure && d.structure.navLabels || []).join(' | ')}`,
    `- Calls to action: ${(d.structure && d.structure.ctas || []).join(' | ')}; one above the fold: ${d.structure && d.structure.ctaAboveFold ? 'yes' : 'no'}; phone number in header: ${d.structure && d.structure.phoneInHeader ? 'yes' : 'no'}`,
    `- Outline: ${(d.structure && d.structure.headings || []).slice(0, 12).join(' / ')}`,
    `- Generated-design tells: ${tells.join('; ') || 'none measured (that does not make it good)'}`,
    ...(rec.walk.length ? ['', '## Walk', ...rec.walk.map((w, i) => `${i + 1}. ${w.label}: ${w.ok ? 'ok ' + w.url : ''}${w.note ? ' ' + w.note : ''}`)] : []),
    '', 'These numbers are evidence for a take, not the take. Open the images, then write what is worth taking or avoiding, with these values.', '',
  ];
  fs.writeFileSync(path.join(dir, 'teardown.md'), md.join('\n'));
  console.log(md.join('\n'));
  summary.push({ url, dir, ok: !d.error });
}
await browser.close();
process.exit(summary.every((s) => s.ok) ? 0 : 1);
