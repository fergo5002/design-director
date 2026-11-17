// motion-probe.js: is the page smooth, idle and while scrolling, and what makes it work hard? One function
// expression: tools/motion.mjs calls it headless; in a real Chrome tab paste it followed by `({ scroll: true })`.
//
// It grows from frame-probe.js in the design-director skill (2026-11-09): the same 14 px a frame scroll, the same
// buckets by the section in the middle of the screen, and the same pass rule (each section's p95 within 1.5 refresh
// intervals plus 1 ms, no frame over 100 ms, no long animation frame over 100 ms during the run). Added: an idle
// phase, percentiles and dropped frames per phase, long tasks over 50 ms, layout shifts with the nodes that moved,
// and the elements animating layout properties (CSS animations and transitions on them, and scripts writing them to
// an element's style again and again).
//
// It never hangs: a hidden or background tab never runs requestAnimationFrame, so every wait is raced against a
// timer, and a run with too few frames says INSTRUMENT DEGRADED rather than judging the page.
// Headless frames are paced by a timer, not a display: a main-thread stall shows; a compositor-only judder (two
// videos holding a 120 Hz screen at 30 fps) does not. For that, run it in the real browser, foreground.
async (opts = {}) => {
  const idleMs = opts.idleMs ?? 3000;
  const doScroll = opts.scroll ?? true;
  const maxScrollMs = opts.maxScrollMs ?? 12000;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const t0 = performance.now();

  const esc = (s) => (window.CSS && CSS.escape ? CSS.escape(s) : s);
  const sel = (el) => {
    if (!el || el.nodeType !== 1) return el && el.nodeType === 3 ? sel(el.parentElement) : '(gone)';
    const parts = [];
    for (let n = el, d = 0; n && n.nodeType === 1 && n !== document.body && n !== document.documentElement && d < 4; n = n.parentElement, d++) {
      if (n.id) { parts.unshift(`#${esc(n.id)}`); break; }
      const cls = typeof n.className === 'string' ? n.className.trim().split(/\s+/).filter((c) => c && !/[:[\]/]/.test(c)).slice(0, 2) : [];
      parts.unshift(n.tagName.toLowerCase() + (cls.length ? '.' + cls.map(esc).join('.') : ''));
    }
    return parts.join(' > ') || el.tagName.toLowerCase();
  };

  // ---- what the browser reports while we watch
  const longtasks = [], shifts = [], loaf = [], observers = [];
  const watch = (type, sink) => {
    try { const o = new PerformanceObserver((l) => sink.push(...l.getEntries())); o.observe({ type, buffered: true }); observers.push(o); } catch { /* not supported here */ }
  };
  watch('longtask', longtasks); watch('layout-shift', shifts); watch('long-animation-frame', loaf);

  // ---- layout properties: animations on them, and scripts writing them over and over
  const LAYOUT = /^(width|height|min-width|min-height|max-width|max-height|top|left|right|bottom|inset.*|margin.*|padding.*|border(-top|-right|-bottom|-left)?-width|font-size|line-height|letter-spacing|flex-basis|flex-grow|flex-shrink|grid-template-.*|gap|row-gap|column-gap)$/;
  const writes = new Map();   // el -> Map(prop -> count)
  const scratch = document.createElement('div');
  const mo = new MutationObserver((list) => {
    for (const m of list) {
      const el = m.target;
      if (!el.style) continue;
      scratch.setAttribute('style', m.oldValue || '');
      const props = new Set([...scratch.style, ...el.style]);
      for (const p of props) {
        if (!LAYOUT.test(p) || scratch.style.getPropertyValue(p) === el.style.getPropertyValue(p)) continue;
        let byProp = writes.get(el);
        if (!byProp) { byProp = new Map(); writes.set(el, byProp); }
        byProp.set(p, (byProp.get(p) || 0) + 1);
      }
    }
  });
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ['style'], attributeOldValue: true, subtree: true });
  const animated = new Map();   // key -> { selector, props, kind, name }
  const sampleAnimations = () => {
    for (const a of document.getAnimations ? document.getAnimations() : []) {
      const target = a.effect && a.effect.target;
      if (!target) continue;
      const props = new Set();
      try {
        for (const k of a.effect.getKeyframes()) for (const p of Object.keys(k)) {
          if (!['offset', 'easing', 'composite', 'computedOffset'].includes(p)) props.add(p.replace(/[A-Z]/g, (c) => '-' + c.toLowerCase()));
        }
      } catch { /* a cross-origin or odd effect */ }
      if (a.transitionProperty) props.add(a.transitionProperty);
      const layout = [...props].filter((p) => LAYOUT.test(p));
      if (!layout.length) continue;
      const kind = a.constructor && a.constructor.name === 'CSSTransition' ? 'CSS transition' : a.constructor && a.constructor.name === 'CSSAnimation' ? 'CSS animation' : 'Web Animation';
      const key = sel(target) + '|' + layout.join(',');
      if (!animated.has(key)) animated.set(key, { selector: sel(target), props: layout, kind, name: a.animationName || a.transitionProperty || a.id || '' });
    }
  };

  // ---- frames, with every wait raced against a timer
  const frames = [];   // { dt, phase, at }
  let rafs = 0, lastSample = 0;
  const sections = [...document.querySelectorAll('section, [data-section]')].filter((s) => s.getBoundingClientRect().height > 0);
  const name = (s) => s.id || s.getAttribute('aria-labelledby') || (s.className && String(s.className).split(' ')[0]) || s.tagName.toLowerCase();
  const at = (y) => {
    const mid = y + innerHeight / 2;
    for (const s of sections) { const r = s.getBoundingClientRect(); const top = r.top + scrollY; if (mid >= top && mid < top + r.height) return name(s); }
    return '(between sections)';
  };
  const loop = (phase, ms, step) => new Promise((resolve) => {
    let last = null, over = false;
    const end = performance.now() + ms;
    const finish = (why) => { if (!over) { over = true; resolve(why); } };
    setTimeout(() => finish('timer'), ms + 2000);   // a page with no frames must still come back
    const f = (now) => {
      if (over) return;
      rafs += 1;
      if (last !== null) frames.push({ dt: now - last, phase, at: phase === 'scroll' ? at(scrollY) : 'idle' });
      last = now;
      if (now - lastSample > 250) { lastSample = now; sampleAnimations(); }
      const more = step ? step() : true;
      if (now >= end || more === false) { finish('done'); return; }
      requestAnimationFrame(f);
    };
    requestAnimationFrame(f);
  });

  const startY = scrollY;
  scrollTo(0, 0);
  await sleep(300);
  const tIdle = performance.now();
  await loop('idle', idleMs);
  const idleFrames = frames.length;
  let step = opts.step || 14, max = 0, tScroll = null;
  if (doScroll) {
    max = Math.max(0, document.documentElement.scrollHeight - innerHeight);
    if (max / step / 60 * 1000 > maxScrollMs) step = Math.ceil(max / ((maxScrollMs / 1000) * 60));   // a long page in about maxScrollMs
    tScroll = performance.now();
    let y = 0;
    if (max > 0) await loop('scroll', maxScrollMs * 2, () => { y += step; scrollTo(0, y); return y < max; });
  }
  sampleAnimations();
  await sleep(300);   // let the observers deliver
  mo.disconnect();
  for (const o of observers) o.disconnect();
  scrollTo(0, startY);

  // ---- numbers
  const q = (a, p) => (a.length ? a[Math.min(a.length - 1, Math.floor(a.length * p))] : null);
  const r1 = (v) => (v === null ? null : Math.round(v * 10) / 10);
  const all = frames.map((f) => f.dt).sort((a, b) => a - b);
  const refresh = q(all, 0.5) || 16.7;
  const stats = (list) => {
    const s = list.map((f) => f.dt).sort((a, b) => a - b);
    const dropped = s.reduce((n, dt) => n + Math.max(0, Math.round(dt / refresh) - 1), 0);
    return { frames: s.length, p50: r1(q(s, 0.5)), p95: r1(q(s, 0.95)), p99: r1(q(s, 0.99)), worst: r1(s[s.length - 1] ?? null), dropped,
      ok: s.length ? q(s, 0.95) <= refresh * 1.5 + 1 && s[s.length - 1] <= 100 : true };
  };
  const phases = { idle: stats(frames.filter((f) => f.phase === 'idle')), scroll: stats(frames.filter((f) => f.phase === 'scroll')) };
  const bySection = {};
  for (const f of frames.filter((f) => f.phase === 'scroll')) (bySection[f.at] ||= []).push(f);
  const sectionRows = Object.fromEntries(Object.entries(bySection).map(([k, list]) => [k, stats(list)]));
  const during = (e) => e.startTime >= t0;
  const ms = (v) => Math.round(v);
  const lt = longtasks.filter(during).sort((a, b) => b.duration - a.duration);
  const loafLong = loaf.filter((e) => during(e) && e.duration > 100);
  const realShifts = shifts.filter((e) => during(e) && !e.hadRecentInput);
  const shiftBy = new Map();
  for (const e of realShifts) for (const s of e.sources || []) { const k = sel(s.node); shiftBy.set(k, (shiftBy.get(k) || 0) + e.value); }
  const layoutAnimations = [...animated.values()];
  for (const [el, byProp] of writes) {
    const props = [...byProp].filter(([, n]) => n >= 3).map(([p]) => p);
    if (props.length) layoutAnimations.push({ selector: sel(el), props, kind: 'script', name: '', writes: Math.max(...byProp.values()) });
  }
  const measured = frames.length;
  const seconds = (performance.now() - tIdle) / 1000;
  const degraded = measured < Math.max(10, seconds * 5);
  const pass = phases.idle.ok && phases.scroll.ok && Object.values(sectionRows).every((r) => r.ok) && loafLong.length === 0;
  return {
    verdict: degraded ? 'INSTRUMENT DEGRADED' : pass ? 'SMOOTH' : 'NOT SMOOTH',
    why: degraded ? `only ${measured} animation frames in ${seconds.toFixed(1)}s: requestAnimationFrame is not running (a hidden or background tab), so nothing here is evidence about the page` : undefined,
    refreshMs: r1(refresh),
    viewport: `${innerWidth}x${innerHeight}@${devicePixelRatio}`,
    headless: /HeadlessChrome/.test(navigator.userAgent) || navigator.webdriver === true,
    idleMs, scrolled: doScroll ? { px: max, step, ms: tScroll ? ms(performance.now() - tScroll - 300) : 0 } : null,
    phases, sections: sectionRows, idleFrames,
    longTasks: { count: lt.length, over100: lt.filter((e) => e.duration > 100).length, items: lt.slice(0, 5).map((e) => ({ at: ms(e.startTime - t0), ms: ms(e.duration) })) },
    longAnimationFramesOver100ms: loafLong.slice(0, 5).map((e) => ({ at: ms(e.startTime - t0), ms: ms(e.duration) })),
    layoutShift: { total: Math.round(realShifts.reduce((n, e) => n + e.value, 0) * 1000) / 1000, count: realShifts.length,
      sources: [...shiftBy].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([selector, v]) => ({ selector, value: Math.round(v * 1000) / 1000 })) },
    layoutAnimations: layoutAnimations.slice(0, 10),
  };
}
