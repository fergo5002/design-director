// audit-probe.js: what is wrong on the screen as it stands, measured, for one scroll stop.
// tools/audit.mjs scrolls the page, calls this at each stop, and dedupes and caps what it returns. It is one
// function expression: `(audit-probe.js)({ touch: true, fold: true })` in a browser console works too.
//
// Every item carries a CSS selector, the text involved and its rect in page pixels, so a fix needs no screenshot.
// Measures: clipped text (ink, not the font box, against each ancestor that clips), boxes too small for their
// words, text and controls running off the viewport, overlapping text, tap targets (touch only), the text runs
// whose pixels audit.mjs samples for contrast, line length, small text (touch only) and the first screen.
// It skips iframes and shadow DOM, and it reads the layout as it stands at this instant.
(opts = {}) => {
  const doc = document.documentElement;
  // clientWidth, never innerWidth: under phone emulation innerWidth stretches to fit wide content (2026-11-11).
  const vw = doc.clientWidth || innerWidth;
  const vh = (document.compatMode === 'CSS1Compat' && doc.clientHeight) || innerHeight;
  const sx = scrollX, sy = scrollY;
  const touch = !!opts.touch;
  const out = { 'clip.text': [], 'clip.box': [], offscreen: [], overlap: [], 'tap.small': [], 'tap.close': [],
    'line.length': [], 'text.small': [] };
  const runs = [];   // text runs for the pixel contrast pass in audit.mjs

  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'TITLE', 'OPTION', 'HEAD']);
  const css = new Map();
  const cs = (el) => { let s = css.get(el); if (!s) { s = getComputedStyle(el); css.set(el, s); } return s; };
  const esc = (s) => (window.CSS && CSS.escape ? CSS.escape(s) : s.replace(/[^\w-]/g, '\\$&'));
  const sel = (el) => {
    const parts = [];
    for (let n = el, depth = 0; n && n.nodeType === 1 && n !== document.body && n !== doc && depth < 5; n = n.parentElement, depth++) {
      if (n.id && document.querySelectorAll(`#${esc(n.id)}`).length === 1) { parts.unshift(`#${esc(n.id)}`); break; }
      let p = n.tagName.toLowerCase();
      const cls = typeof n.className === 'string' ? n.className.trim().split(/\s+/).filter((c) => c && !/[:[\]/]/.test(c)).slice(0, 2) : [];
      if (cls.length) p += '.' + cls.map(esc).join('.');
      const label = n.getAttribute && n.getAttribute('aria-label');
      if (label && !cls.length) p += `[aria-label="${label.replace(/"/g, '\\"').slice(0, 40)}"]`;
      const same = n.parentElement ? [...n.parentElement.children].filter((c) => c.tagName === n.tagName) : [];
      const twins = same.filter((c) => cls.every((k) => c.classList.contains(k)) && (!label || cls.length || c.getAttribute('aria-label') === label));
      if (twins.length > 1) p += `:nth-of-type(${same.indexOf(n) + 1})`;
      parts.unshift(p);
    }
    return parts.join(' > ') || el.tagName.toLowerCase();
  };
  const snip = (s, n = 80) => String(s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const page = (r) => [Math.round(r.left + sx), Math.round(r.top + sy), Math.round(r.width), Math.round(r.height)];
  const shown = (el) => !el.checkVisibility || el.checkVisibility({ opacityProperty: true, visibilityProperty: true });
  const tiny = (r) => r.width <= 2 || r.height <= 2;
  const inView = (r) => r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw;
  const clipsAxis = (v) => v === 'hidden' || v === 'clip';
  const scrolls = (v) => v === 'auto' || v === 'scroll';

  // Ancestors that clip this element, honouring the containing-block chain: an absolutely positioned box is not
  // clipped by an overflow:hidden parent that is not positioned, and a fixed one only by a transformed ancestor.
  const clipCache = new Map();
  const clipOf = (a) => {
    const s = cs(a);
    const x = clipsAxis(s.overflowX), y = clipsAxis(s.overflowY), scx = scrolls(s.overflowX), scy = scrolls(s.overflowY);
    if (!(x || y || scx || scy)) return null;
    const r = a.getBoundingClientRect();
    const box = { left: r.left + a.clientLeft, top: r.top + a.clientTop, right: r.left + a.clientLeft + a.clientWidth, bottom: r.top + a.clientTop + a.clientHeight };
    return { el: a, box, x, y, scrollX: scx, scrollY: scy, ellipsis: s.textOverflow === 'ellipsis', clamp: s.webkitLineClamp && s.webkitLineClamp !== 'none', tiny: a.clientWidth <= 2 || a.clientHeight <= 2 };
  };
  // For text, the element holding it clips it too (own = true); a box is never clipped by its own overflow.
  const clippers = (el, own = false) => {
    const key = own ? 'own' : 'box';
    let byEl = clipCache.get(el);
    if (!byEl) { byEl = {}; clipCache.set(el, byEl); }
    if (byEl[key]) return byEl[key];
    const list = [];
    if (own && el !== document.body && el !== doc) { const c = clipOf(el); if (c) list.push(c); }
    let skip = null;   // null, 'abs' or 'fixed'
    const startPos = cs(el).position;
    if (startPos === 'absolute') skip = 'abs';
    if (startPos === 'fixed') skip = 'fixed';
    for (let a = el.parentElement; a && a !== document.body && a !== doc; a = a.parentElement) {
      const s = cs(a);
      const transformed = s.transform !== 'none' || s.filter !== 'none' || /paint|strict|content/.test(s.contain) || s.willChange.includes('transform');
      const contains = skip === 'abs' ? (s.position !== 'static' || transformed) : skip === 'fixed' ? transformed : true;
      if (contains) {
        const c = clipOf(a);
        if (c) list.push(c);
        if (skip) skip = null;
      }
      if (s.position === 'absolute') skip = 'abs';
      else if (s.position === 'fixed') skip = 'fixed';
    }
    byEl[key] = list;
    return list;
  };
  // The visible part of a rect after every clipping (or scrolling) ancestor; null when nothing of it shows.
  const visiblePart = (r, el, own = false) => {
    let { left, top, right, bottom } = r;
    for (const c of clippers(el, own)) {
      if (c.x || c.scrollX) { left = Math.max(left, c.box.left); right = Math.min(right, c.box.right); }
      if (c.y || c.scrollY) { top = Math.max(top, c.box.top); bottom = Math.min(bottom, c.box.bottom); }
    }
    return right - left > 0.5 && bottom - top > 0.5 ? { left, top, right, bottom, width: right - left, height: bottom - top } : null;
  };

  // Ink: the glyphs' own box for a run of text, from canvas metrics in the element's computed font. A range's rect
  // is the font's box (ascent plus descent), which a tight line-height overflows with no ink there at all.
  const canvas = document.createElement('canvas').getContext('2d');
  // Any CSS colour (oklch, color-mix, a named one) as sRGB [r, g, b, a], read back off a one-pixel canvas.
  const dot = document.createElement('canvas'); dot.width = dot.height = 1;
  const dc = dot.getContext('2d', { willReadFrequently: true });
  const rgba = (c) => { dc.clearRect(0, 0, 1, 1); dc.fillStyle = '#000'; dc.fillStyle = c; dc.fillRect(0, 0, 1, 1); const d = dc.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], +(d[3] / 255).toFixed(3)]; };
  const inkCache = new Map();
  const transform = (t, s) => (s.textTransform === 'uppercase' ? t.toUpperCase() : s.textTransform === 'lowercase' ? t.toLowerCase() : t);
  const ink = (rect, word, s) => {
    const key = `${s.font}|${s.letterSpacing}|${s.textTransform}|${word}`;
    let m = inkCache.get(key);
    if (!m) {
      canvas.font = s.font;
      try { canvas.letterSpacing = s.letterSpacing === 'normal' ? '0px' : s.letterSpacing; } catch { /* older engines */ }
      const t = canvas.measureText(transform(word, s));
      m = { a: t.actualBoundingBoxAscent, d: t.actualBoundingBoxDescent, fa: t.fontBoundingBoxAscent, fd: t.fontBoundingBoxDescent,
        l: t.actualBoundingBoxLeft, r: t.actualBoundingBoxRight };
      inkCache.set(key, m);
    }
    const scale = m.fa + m.fd > 0 ? rect.height / (m.fa + m.fd) : 1;
    const base = rect.top + m.fa * scale;
    return { left: rect.left - Math.max(0, m.l), right: Math.max(rect.right, rect.left + m.r), top: base - m.a, bottom: base + m.d };
  };

  // Text nodes in or near this screen, grouped by element.
  const texts = new Map();   // el -> [textNode]
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const t = walker.currentNode;
    const el = t.parentElement;
    if (!el || SKIP.has(el.tagName) || !t.nodeValue.trim() || el.closest('svg')) continue;
    if (!texts.has(el)) {
      const r = el.getBoundingClientRect();
      if (tiny(r) || r.bottom < -vh * 0.25 || r.top > vh * 1.25 || !shown(el)) { texts.set(el, null); continue; }
      texts.set(el, []);
    }
    const list = texts.get(el);
    if (list) list.push(t);
  }
  const range = document.createRange();
  const lineRects = (node) => { range.selectNodeContents(node); return [...range.getClientRects()].filter((r) => r.width > 0.5 && r.height > 0.5); };
  const words = (node) => {
    const res = [];
    const re = /\S+/g;
    let m, n = 0;
    while ((m = re.exec(node.nodeValue)) && n < 300) {
      range.setStart(node, m.index); range.setEnd(node, m.index + m[0].length);
      for (const r of range.getClientRects()) if (r.width > 0.5) res.push({ word: m[0], r });
      n++;
    }
    return res;
  };

  const lines = [];   // for overlap: { el, block, r }
  const blockOf = (el) => { for (let n = el; n; n = n.parentElement) { const d = cs(n).display; if (!/^inline/.test(d) && d !== 'contents') return n; } return document.body; };
  for (const [el, nodes] of texts) {
    if (!nodes || !nodes.length) continue;
    const s = cs(el);
    const cl = clippers(el, true);
    const fontPx = parseFloat(s.fontSize);
    const visibleLines = [];
    for (const node of nodes) {
      const rects = lineRects(node);
      let onScreen = false;
      for (const r of rects) {
        const v = visiblePart(r, el, true);
        if (v && inView(v)) { onScreen = true; visibleLines.push(v); lines.push({ el, block: blockOf(el), r: v }); }
      }
      if (!onScreen) continue;
      const cutBy = cl.filter((c) => (c.x || c.y) && !c.tiny);
      const offEdge = rects.some((r) => { const v = visiblePart(r, el, true); return v && (v.right > vw + 1 || v.left < -1); });
      if (!cutBy.length && !offEdge) continue;
      // (a) ink cut by a clipping ancestor, word by word
      const ws = words(node);
      for (const c of cutBy) {
        if ((c.ellipsis && c.x && !c.y) || (c.clamp && c.y && !c.x)) continue;   // a visible ellipsis is a choice
        const hit = { words: [], cut: { top: 0, bottom: 0, left: 0, right: 0 }, rect: null };
        for (const { word, r } of ws) {
          const g = ink(r, word, s);
          const meets = g.right > c.box.left && g.left < c.box.right && g.bottom > c.box.top && g.top < c.box.bottom;
          if (!meets) continue;   // wholly outside: hidden on purpose (a slide, a collapsed panel), not cut
          const cut = { top: c.y ? c.box.top - g.top : 0, bottom: c.y ? g.bottom - c.box.bottom : 0,
            left: c.x ? c.box.left - g.left : 0, right: c.x ? g.right - c.box.right : 0 };
          if (Math.max(cut.top, cut.bottom, cut.left, cut.right) <= 1) continue;
          hit.words.push(word);
          for (const k of Object.keys(cut)) hit.cut[k] = Math.max(hit.cut[k], Math.round(cut[k]));
          hit.rect = hit.rect || { left: g.left, top: g.top, width: g.right - g.left, height: g.bottom - g.top };
        }
        if (hit.words.length) {
          const worst = Math.max(...Object.values(hit.cut));
          const side = Object.entries(hit.cut).sort((a, b) => b[1] - a[1])[0][0];
          out['clip.text'].push({ selector: sel(el), text: snip(hit.words.join(' ')), rect: page(hit.rect), clipper: sel(c.el),
            cut: hit.cut, score: worst, detail: `${side === 'bottom' ? 'descenders' : side === 'top' ? 'ascenders' : side + ' edge'} cut by ${worst}px by ${sel(c.el)}` });
        }
      }
      // (b) text running off the viewport's side
      if (offEdge) {
        const past = ws.map(({ word, r }) => { const g = ink(r, word, s); return { word, r, v: visiblePart({ left: g.left, right: g.right, top: g.top, bottom: g.bottom }, el, true) }; })
          .filter(({ v }) => v && (v.right > vw + 1 || v.left < -1));
        const cutWords = past.filter(({ v }) => v.left < vw && v.right > 0);
        if (cutWords.length) {
          const r0 = cutWords[0].r;
          const px = Math.round(Math.max(...past.map(({ v }) => Math.max(v.right - vw, -v.left))));
          const gone = past.length - cutWords.length;
          out.offscreen.push({ _el: el, selector: sel(el), text: snip(el.innerText || node.nodeValue), rect: page(r0), px, score: px,
            detail: `"${cutWords.map((w) => w.word).join(' ')}" cut at the ${r0.right > vw ? 'right' : 'left'} edge${gone ? `, ${gone} more words past it` : ''}; runs ${px}px off` });
        }
      }
    }
    if (!visibleLines.length) continue;
    // (f) line length: a paragraph of three lines or more
    if (/^(P|LI|DD|BLOCKQUOTE|FIGCAPTION)$/.test(el.tagName) && !out['line.length'].some((i) => i._el === el)) {
      range.selectNodeContents(el);
      const all = [...range.getClientRects()].filter((r) => r.width > 1);
      const rows = [];
      for (const r of all) { const c = r.top + r.height / 2; const row = rows.find((x) => Math.abs(x.c - c) < r.height / 2); if (row) row.w = Math.max(row.w, r.right) - Math.min(row.l, r.left); else rows.push({ c, l: r.left, w: r.width }); }
      const chars = snip(el.innerText, 100000).length;
      if (rows.length >= 3) {
        const per = Math.round(chars / (rows.length - 0.5));
        const min = vw >= 600 ? 45 : 0;
        if (per > 85 || per < min) {
          const r = el.getBoundingClientRect();
          out['line.length'].push({ _el: el, selector: sel(el), text: snip(el.innerText, 60), rect: page(r), chars: per, lines: rows.length,
            score: per > 85 ? per - 85 : min - per, detail: `about ${per} characters a line over ${rows.length} lines (45 to 85 reads best)` });
        }
      }
    }
    // (f) small text on a touch screen
    if (touch && fontPx < 16 && !el.closest('sup, sub')) {
      const r = visibleLines[0];
      out['text.small'].push({ selector: sel(el), text: snip(el.innerText || nodes[0].nodeValue, 60), rect: page(r), px: Math.round(fontPx * 10) / 10,
        score: 16 - fontPx, detail: `${Math.round(fontPx * 10) / 10}px text on a phone (16px is the floor for reading)` });
    }
    // (e) contrast: the run's colour and where its lines are; audit.mjs reads the pixels behind them
    const fill = s.webkitTextFillColor;
    let opacity = 1;
    for (let n = el; n && n !== doc; n = n.parentElement) opacity *= parseFloat(cs(n).opacity);
    runs.push({ selector: sel(el), text: snip(el.innerText || nodes.map((n) => n.nodeValue).join(' '), 60), fg: rgba(fill || s.color),
      clipText: s.backgroundClip === 'text' || s.webkitBackgroundClip === 'text', opacity, px: fontPx, weight: parseInt(s.fontWeight, 10) || 400,
      rects: visibleLines.filter(inView).slice(0, 6).map((r) => [Math.max(0, r.left), Math.max(0, r.top), Math.min(vw, r.right), Math.min(vh, r.bottom)]),
      rect: page(visibleLines[0]) });
  }

  // (a) a box that clips whole lines of its own words: a card too short for its copy
  for (const el of document.querySelectorAll('body *')) {
    const s = cs(el);
    if (!clipsAxis(s.overflowY) || el.scrollHeight <= el.clientHeight + 2 || el.clientHeight <= 2) continue;
    if (s.webkitLineClamp && s.webkitLineClamp !== 'none') continue;
    const r = el.getBoundingClientRect();
    if (!inView(r) || !shown(el)) continue;
    const box = { top: r.top + el.clientTop, bottom: r.top + el.clientTop + el.clientHeight };
    const hidden = [];
    const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    while (tw.nextNode() && hidden.length < 3) {
      const t = tw.currentNode;
      if (!t.nodeValue.trim() || !t.parentElement || !shown(t.parentElement)) continue;
      if (!clippers(t.parentElement, true).some((c) => c.el === el)) continue;   // positioned out of this box's reach
      for (const lr of lineRects(t)) if (lr.top >= box.bottom - 1 || lr.bottom <= box.top + 1) hidden.push(lr);
    }
    if (hidden.length) {
      const px = Math.round(el.scrollHeight - el.clientHeight);
      out['clip.box'].push({ selector: sel(el), text: snip(el.innerText, 60), rect: page(r), px, score: px,
        detail: `${px}px of its content is hidden by overflow ${s.overflowY}: whole lines of text do not show` });
    }
  }

  // (b) controls and pictures running off the viewport's side
  const KEY = 'a[href], button, input, select, textarea, [role="button"], img, video, canvas, svg, h1, h2, h3';
  for (const el of document.querySelectorAll(KEY)) {
    if (el.closest('svg') && el.tagName.toLowerCase() !== 'svg') continue;
    const r = el.getBoundingClientRect();
    if (tiny(r) || !shown(el)) continue;
    const v = visiblePart(r, el);
    if (!v || !inView(v) || !(v.right > vw + 1 || v.left < -1)) continue;
    if (out.offscreen.some((i) => i._el === el || el.contains(i._el || null))) continue;
    const px = Math.round(Math.max(v.right - vw, -v.left));
    out.offscreen.push({ _el: el, selector: sel(el), text: snip(el.innerText || el.getAttribute('aria-label') || el.getAttribute('alt') || ''), rect: page(r), px, score: px,
      detail: `${el.tagName.toLowerCase()} runs ${px}px off the ${v.right > vw ? 'right' : 'left'} edge` });
  }
  const sideways = doc.scrollWidth > vw + 1 ? doc.scrollWidth - vw : 0;

  // (c) text on top of text: the middle of each line box, so tight leading between a block's own lines is no overlap
  const core = (r) => { const pad = r.height * 0.3; return { left: r.left + 1, right: r.right - 1, top: r.top + pad, bottom: r.bottom - pad }; };
  const seenPair = new Set();
  for (let i = 0; i < lines.length && out.overlap.length < 40; i++) {
    for (let j = i + 1; j < lines.length; j++) {
      const A = lines[i], B = lines[j];
      if (A.el === B.el || A.block === B.block || A.el.contains(B.el) || B.el.contains(A.el)) continue;
      const a = core(A.r), b = core(B.r);
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left), h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (w <= 2 || h <= 2) continue;
      const key = sel(A.el) + '|' + sel(B.el);
      if (seenPair.has(key)) continue;
      seenPair.add(key);
      out.overlap.push({ selector: sel(A.el), text: snip(A.el.innerText, 60), rect: page({ left: Math.max(a.left, b.left), top: Math.max(a.top, b.top), width: w, height: h }),
        other: { selector: sel(B.el), text: snip(B.el.innerText, 60) }, score: Math.round(w * h), detail: `overlaps ${sel(B.el)} by ${Math.round(w)}x${Math.round(h)}px` });
    }
  }

  // (d) tap targets on a touch screen: under 44 by 44, and closer than 8 px to the next one
  if (touch) {
    const inline = (el) => {
      if (el.tagName !== 'A' || !/^inline/.test(cs(el).display) || cs(el).display === 'inline-block') return false;
      const p = el.parentElement;
      return !!p && (p.innerText || '').replace(/\s+/g, '').length > (el.innerText || '').replace(/\s+/g, '').length + 12;
    };
    const targets = [...document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, summary, [role="button"], [role="link"], [tabindex]:not([tabindex="-1"])')]
      .filter((el) => !el.disabled && shown(el) && !inline(el))
      .filter((el) => !el.parentElement || !el.parentElement.closest('a[href], button'))   // the outer one is the target
      .map((el) => {
        let r = el.getBoundingClientRect();
        if ((el.type === 'checkbox' || el.type === 'radio') && el.labels && el.labels[0]) {
          const l = el.labels[0].getBoundingClientRect();
          r = { left: Math.min(r.left, l.left), top: Math.min(r.top, l.top), right: Math.max(r.right, l.right), bottom: Math.max(r.bottom, l.bottom) };
          r.width = r.right - r.left; r.height = r.bottom - r.top;
        }
        return { el, r, v: visiblePart(r, el) };
      })
      .filter((t) => t.v && inView(t.v) && !tiny(t.r));
    const name = (el) => snip(el.getAttribute('aria-label') || el.innerText || el.value || el.getAttribute('title') || '', 40);   // aria-label is the accessible name when set
    for (const t of targets) {
      if (t.r.width < 44 || t.r.height < 44) {
        out['tap.small'].push({ selector: sel(t.el), text: name(t.el), rect: page(t.r), size: [Math.round(t.r.width), Math.round(t.r.height)],
          score: 44 - Math.min(t.r.width, t.r.height), detail: `${Math.round(t.r.width)}x${Math.round(t.r.height)}px, under 44x44` });
      }
    }
    const listRow = (a, b) => a.r.width >= vw * 0.8 && b.r.width >= vw * 0.8;   // full-width rows stacked: a list, not a mis-tap
    for (let i = 0; i < targets.length; i++) {
      for (let j = i + 1; j < targets.length; j++) {
        const a = targets[i], b = targets[j];
        if (a.el.contains(b.el) || b.el.contains(a.el) || listRow(a, b)) continue;
        const dx = Math.max(0, b.r.left - a.r.right, a.r.left - b.r.right), dy = Math.max(0, b.r.top - a.r.bottom, a.r.top - b.r.bottom);
        const gap = Math.max(dx, dy);
        if (gap >= 8) continue;
        out['tap.close'].push({ selector: sel(a.el), text: name(a.el), rect: page(a.r), gap: Math.round(gap * 10) / 10,
          other: { selector: sel(b.el), text: name(b.el) }, score: 8 - gap, detail: `${Math.round(gap)}px from ${sel(b.el)} (8px apart at least)` });
      }
    }
  }

  // (g) the first screen: headings, filled actions, words and the largest text
  let fold = null;
  if (opts.fold) {
    const inFold = (r) => r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw && !tiny(r);
    const heads = [...document.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"]')].filter((h) => shown(h) && inFold(h.getBoundingClientRect()));
    const lum = (c) => { const m = /rgba?\(([\d.]+)[, ]+([\d.]+)[, ]+([\d.]+)(?:[, /]+([\d.]+))?/.exec(c); if (!m) return null; const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }; return { L: 0.2126 * f(+m[1]) + 0.7152 * f(+m[2]) + 0.0722 * f(+m[3]), a: m[4] === undefined ? 1 : +m[4] }; };
    const behind = (el) => { for (let n = el.parentElement; n; n = n.parentElement) { const l = lum(cs(n).backgroundColor); if (l && l.a > 0.5) return l.L; } return 1; };
    const actions = [...document.querySelectorAll('a[href], button, input[type=submit], input[type=button], [role="button"]')].filter((el) => {
      if (!shown(el) || !inFold(el.getBoundingClientRect())) return false;
      const s = cs(el), bg = lum(s.backgroundColor);
      const label = snip(el.innerText || el.value || '');
      if (label.length < 2) return false;
      if (/gradient/.test(s.backgroundImage)) return true;
      if (!bg || bg.a < 0.5) return false;
      const L2 = behind(el), hi = Math.max(bg.L, L2), lo = Math.min(bg.L, L2);
      return (hi + 0.05) / (lo + 0.05) >= 1.5;
    });
    let n = 0, largest = null;
    for (const [el, nodes] of texts) {
      if (!nodes) continue;
      for (const node of nodes) {
        const rs = lineRects(node).map((r) => visiblePart(r, el)).filter((r) => r && inFold(r));
        if (!rs.length) continue;
        n += node.nodeValue.split(/\s+/).filter(Boolean).length;
        const px = parseFloat(cs(el).fontSize);
        if (!largest || px > largest.px) largest = { selector: sel(el), text: snip(el.innerText, 60), px: Math.round(px * 10) / 10, rect: page(rs[0]) };
      }
    }
    fold = { headings: heads.length, headingText: heads.slice(0, 5).map((h) => `${h.tagName.toLowerCase()} "${snip(h.innerText, 50)}"`),
      primaryActions: actions.length, actionText: actions.slice(0, 5).map((a) => snip(a.innerText || a.value, 40)), words: n, largest };
  }

  for (const k of Object.keys(out)) for (const it of out[k]) delete it._el;
  return { vw, vh, scrollY: Math.round(sy), scrollHeight: doc.scrollHeight, sideways, fold, checks: out, runs };
}
