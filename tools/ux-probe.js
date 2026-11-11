// ux-probe.js: the UX rules a script can count, in one pass over the rendered page (UX.md, "Cheap checks").
// Paste into a browser console or run headless with `ddr ux --file page.html` (or `--url`).
// Returns { viewport, fails, warns, findings: [{ rule, severity, where }] }. A clean result means the countable
// rules passed. It cannot see whether the words, the flow or the hierarchy are right, and it skips iframes and
// shadow DOM.
(() => {
  const findings = [];
  const add = (rule, severity, el, note) => findings.push({ rule, severity, where: (el ? describe(el) : '') + (note ? ` ${note}` : '') });
  const describe = (el) => {
    const t = el.tagName.toLowerCase();
    const id = el.id ? `#${el.id}` : '';
    const text = (el.innerText || el.value || el.getAttribute('aria-label') || el.placeholder || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    return `${t}${id}${text ? ` "${text}"` : ''}`;
  };
  const shown = (el) => (el.checkVisibility ? el.checkVisibility({ opacityProperty: true, visibilityProperty: true }) : el.getClientRects().length > 0) && el.getBoundingClientRect().width > 0;
  // Visually hidden on purpose (sr-only, visually-hidden-focusable): a 1px box or a clip.
  const srOnly = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return (r.width <= 2 && r.height <= 2) || /rect\(0/.test(s.clip) || s.clipPath === 'inset(50%)'; };
  const doc = document.documentElement;
  const standards = document.compatMode === 'CSS1Compat';
  // Never innerWidth alone: under phone emulation it stretches to fit wide content, so overflow can never show.
  const vw = doc.clientWidth || innerWidth;
  const vh = standards ? (doc.clientHeight || innerHeight) : innerHeight;
  const touch = matchMedia('(pointer: coarse)').matches || vw < 700;
  const own = (el) => [...(el.labels || [])].map((l) => l.textContent).join(' ') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.placeholder || '') + ' ' + (el.name || '') + ' ' + (el.id || '');
  const accName = (el) => (el.getAttribute('aria-label') || '').trim() || (el.getAttribute('aria-labelledby') || '').trim()
    || [...(el.labels || [])].some((l) => l.textContent.trim()) || (el.title || '').trim();

  // Page
  const meta = document.querySelector('meta[name=viewport]');
  if (!meta) add('page.no-viewport-meta', 'fail', null, '(phones lay the page out at 980px and shrink it)');
  else {
    const max = /maximum-scale\s*=\s*([\d.]+)/i.exec(meta.content);
    if (/user-scalable\s*=\s*(no|0)\b/i.test(meta.content) || (max && parseFloat(max[1]) < 2)) add('page.zoom-blocked', 'fail', meta);
  }
  if (!doc.lang) add('page.no-lang', 'fail', null);
  const h1 = document.querySelectorAll('h1').length;
  if (h1 !== 1) add('page.h1-count', 'warn', null, `(${h1} h1 elements)`);

  // Fields
  const textual = (f) => !['checkbox', 'radio', 'range', 'color', 'file'].includes(f.type) && f.tagName !== 'SELECT';
  const fields = [...document.querySelectorAll('input, select, textarea')].filter((e) => !['hidden', 'submit', 'button', 'reset', 'image'].includes(e.type) && shown(e));
  for (const f of fields) {
    const labels = [...(f.labels || [])].filter((l) => l.textContent.trim());
    const visibleLabel = labels.some((l) => shown(l) && !srOnly(l)) || (f.getAttribute('aria-labelledby') || '').trim();
    if (!accName(f)) add(f.placeholder ? 'field.placeholder-as-label' : 'field.no-label', 'fail', f);
    else if (!visibleLabel && !(f.type === 'search' || f.getAttribute('role') === 'searchbox' || f.closest('[role=search], search'))) add('field.no-visible-label', 'warn', f);
    if (!textual(f)) continue;
    const l = own(f).toLowerCase();
    const ac = (f.getAttribute('autocomplete') || '').trim();
    if (/\be-?mail\b/.test(l) && f.type !== 'email') add('field.wrong-type', 'warn', f, '(email field without type=email)');
    if (/\b(phone|mobile|tel)\b/.test(l) && f.type !== 'tel') add('field.wrong-type', 'warn', f, '(phone field without type=tel)');
    if (/card number|cc-?num|cardnumber/.test(l) && !(f.inputMode === 'numeric' || f.type === 'tel')) add('field.wrong-keyboard', 'warn', f, '(card number without inputmode=numeric)');
    if (/\b(full name|first name|last name|surname|given name|your name)\b|^\s*name\b|\be-?mail\b|\b(phone|mobile)\b|\b(home|street|postal|billing|delivery) address\b|^\s*address\b|postcode|post code|eircode|zip code|card number|expiry|date of birth|birthday/.test(l) && !ac)
      add('field.no-autocomplete', 'warn', f);
    if (touch && parseFloat(getComputedStyle(f).fontSize) < 16) add('field.zooms-on-focus', 'warn', f, `(${getComputedStyle(f).fontSize}, under 16px)`);
  }
  for (const box of document.querySelectorAll('input[type=checkbox]')) {
    if (!box.checked || !shown(box)) continue;
    const l = own(box).toLowerCase();
    if (!/\b(consent|marketing|newsletter|offers|promotions|partners|agree)\b/.test(l) || /\bdisagree\b/.test(l)) continue;
    // A checked box on a settings page is a saved choice; on a sign-up or checkout form it is pre-ticked.
    const form = box.closest('form');
    const signup = form && form.querySelector('input[type=email], input[type=password], input[autocomplete$=cc-number]');
    add('dark.pre-ticked', signup ? 'fail' : 'warn', box);
  }
  for (const form of document.querySelectorAll('form')) {
    if (form.querySelector('[required]') && !form.noValidate) add('form.browser-bubbles-only', 'warn', form, '(required fields without novalidate: errors appear as browser bubbles)');
  }

  // Buttons, links and targets
  const inlineLink = (a) => {
    if (a.tagName !== 'A' || getComputedStyle(a).display !== 'inline') return false;
    const p = a.parentElement;
    return !!p && (p.innerText || '').replace(/\s+/g, '').length > (a.innerText || '').replace(/\s+/g, '').length;
  };
  // WCAG 2.5.8 spacing exception: an undersized target passes when a 24px circle on its centre touches no other target.
  const spaced = (a, all) => {
    const r = a.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    return all.every((b) => {
      if (b === a || b.contains(a) || a.contains(b)) return true;
      const s = b.getBoundingClientRect();
      const dx = Math.max(s.left - cx, 0, cx - s.right), dy = Math.max(s.top - cy, 0, cy - s.bottom);
      return Math.hypot(dx, dy) >= 12;
    });
  };
  const actions = [...document.querySelectorAll('a[href], button, input[type=submit], input[type=button], input[type=reset], [role=button], [role=link]')].filter(shown);
  for (const a of actions) {
    const defaultLabel = a.tagName === 'INPUT' && !a.hasAttribute('value') ? { submit: 'Submit', reset: 'Reset' }[a.type] || '' : '';
    const name = (a.innerText || a.value || defaultLabel || a.getAttribute('aria-label') || a.title || '').trim();
    const named = name || (a.getAttribute('aria-labelledby') || '').trim() || ['submit', 'reset'].includes(a.type) && a.tagName === 'INPUT'
      || a.querySelector('img[alt]:not([alt=""]), svg[aria-label], svg title, [aria-label]');
    if (!named) add('action.no-name', 'fail', a);
    if (/^(submit|ok|okay|click here|here|read more|learn more|more|go|yes|no|continue reading)$/i.test(name)) add('action.vague-label', 'warn', a);
    if (srOnly(a) || inlineLink(a)) continue;
    const r = a.getBoundingClientRect();
    if ((r.width < 24 || r.height < 24) && !spaced(a, actions)) add('target.under-24', 'fail', a, `(${Math.round(r.width)}x${Math.round(r.height)})`);
    else if (touch && (r.width < 44 || r.height < 44)) add('target.under-44-touch', 'warn', a, `(${Math.round(r.width)}x${Math.round(r.height)})`);
  }
  const interactive = 'a,button,input,select,textarea,label,summary,option,[tabindex],[contenteditable],[role=button],[role=link],[role=tab],[role=menuitem],[role=menuitemcheckbox],[role=menuitemradio],[role=option],[role=switch],[role=checkbox],[role=radio],[role=treeitem],[role=gridcell],[role=row],[role=slider]';
  for (const el of document.querySelectorAll('body *')) {
    if (el.matches(interactive) || el.closest(interactive) || el.querySelector(interactive)) continue;
    const pointer = el.hasAttribute('onclick') || (getComputedStyle(el).cursor === 'pointer' && (!el.parentElement || getComputedStyle(el.parentElement).cursor !== 'pointer'));
    if (pointer && shown(el)) add('action.clickable-div', 'fail', el, '(clickable but not a button or link: no keyboard, no role)');
  }

  // Wayfinding
  const navLinks = document.querySelectorAll('nav a[href], header a[href]');
  if (navLinks.length >= 3) {
    const first = [...document.querySelectorAll('a[href], button, input, select, textarea, [tabindex]')].find((e) => e.tabIndex >= 0 && e.type !== 'hidden');
    if (!(first && first.tagName === 'A' && (first.getAttribute('href') || '').startsWith('#') && /skip/i.test(first.textContent))) add('nav.no-skip-link', 'warn', null);
    if (!document.querySelector('[aria-current]')) add('nav.no-current', 'warn', null, '(no aria-current on the navigation)');
  }
  for (const img of document.querySelectorAll('img')) if (!img.hasAttribute('alt')) add('img.no-alt', 'fail', img);

  // Sideways: the page scrolls, or html/body clip it and content is cut off past the edge.
  const clips = [doc, document.body].some((e) => e && ['hidden', 'clip'].includes(getComputedStyle(e).overflowX));
  if (!clips && doc.scrollWidth > vw + 1) add('layout.sideways-scroll', 'fail', null, `(page is ${doc.scrollWidth}px wide in a ${vw}px viewport)`);
  else {
    // Off-canvas drawers (anything inside position:fixed) and decoration (aria-hidden, pointer-events:none) may bleed.
    const exempt = (el) => { for (let e = el; e && e !== document.body; e = e.parentElement) { const s = getComputedStyle(e); if (s.position === 'fixed' || e.getAttribute('aria-hidden') === 'true' || s.pointerEvents === 'none') return true; } return false; };
    const scroller = (el) => { for (let p = el.parentElement; p && p !== document.body && p !== doc; p = p.parentElement) { const x = getComputedStyle(p).overflowX; if (x !== 'visible') return true; } return false; };
    const cut = [...document.querySelectorAll('body *')].filter((el) => {
      const r = el.getBoundingClientRect();
      if (!r.width || r.right <= vw + 1) return false;
      return shown(el) && !srOnly(el) && !exempt(el) && !scroller(el);
    });
    const cutSet = new Set(cut);
    const outer = cut.filter((el) => !cutSet.has(el.parentElement));
    if (outer.length) add('layout.cut-off', 'fail', outer[0], `(${outer.length} element${outer.length > 1 ? 's' : ''} run past the ${vw}px edge and html or body hides it)`);
  }

  // Numbers in tables: quantities only (an amount, a percentage or a decimal). Identifiers stay left-aligned.
  const quantity = /^[\s(+-]*(([€$£¥]|EUR|USD|GBP)\s?-?\d[\d,.\s]*|-?\d[\d,\s]*([.,]\d+)\s*([€$£]|EUR|USD|GBP|%|k|m)?|-?\d[\d,.\s]*\s*([€$£]|EUR|USD|GBP|%))[\s)]*$/i;
  const cells = [...document.querySelectorAll('td, [role=cell], [role=gridcell]')].filter((c) => shown(c) && quantity.test(c.textContent.trim()));
  const tabular = (c) => [c, ...c.querySelectorAll('*')].some((x) => { const s = getComputedStyle(x); return /tabular-nums/.test(s.fontVariantNumeric) || /tnum/.test(s.fontFeatureSettings) || /mono/i.test(s.fontFamily); });
  const right = (c) => { const s = getComputedStyle(c); return /right|end/.test(s.textAlign) || ['flex-end', 'end'].includes(s.justifyContent); };
  const notRight = cells.filter((c) => !right(c)).length, notTab = cells.filter((c) => !tabular(c)).length;
  if (notRight) add('table.numbers-not-right-aligned', 'warn', null, `(${notRight} of ${cells.length} numeric cells)`);
  if (notTab) add('table.numbers-not-tabular', 'warn', null, `(${notTab} of ${cells.length} numeric cells; fine if the face's digits are already uniform)`);

  return { viewport: `${vw}x${vh}`, fails: findings.filter((f) => f.severity === 'fail').length, warns: findings.filter((f) => f.severity === 'warn').length, findings };
})()
