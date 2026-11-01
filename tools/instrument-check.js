/* instrument-check.js -- prove the instrument before you accuse the page.
 *
 * Paste the whole thing into mcp__claude-in-chrome__javascript_tool (or
 * playwright browser_evaluate) BEFORE diagnosing any rendering, layout,
 * freeze, timeout or style problem. It reports on the MEASUREMENT PATH,
 * not on the page.
 *
 * Why it exists: on 2026-08-21 three browser problems were diagnosed wrongly
 * and confidently. Two were a backgrounded tab (rAF never fires there, so any
 * probe that awaits a frame hangs for ever and every screenshot times out).
 * One was getComputedStyle reporting a stale colour while the pixels were
 * correct. In all three the page was fine and the instrument was lying.
 *
 * It is built so it CANNOT hang: rAF is raced against setTimeout, which does
 * still fire in a hidden tab (throttled to about 1s). That asymmetry is the
 * whole diagnostic.
 *
 * Read the verdict first. If it is not CLEAR, stop and fix the instrument.
 * Any measurement taken through a degraded instrument is not evidence.
 */
(async () => {
  const out = { blockers: [], warnings: [] };

  // --- the killer. rAF does not fire in a hidden tab; setTimeout does. -----
  out.visibilityState = document.visibilityState;
  out.hasFocus = document.hasFocus();
  if (document.visibilityState !== 'visible') {
    out.blockers.push(
      'TAB IS ' + document.visibilityState.toUpperCase() + '. requestAnimationFrame ' +
      'does not fire here, so frame-based probes hang and screenshots time out. ' +
      'This looks exactly like a frozen page and is not one. Foreground the tab ' +
      'and re-measure before concluding anything about the page.');
  }

  // Does rAF actually fire? Race it, never await it bare.
  out.rafFires = await new Promise(res => {
    let done = false;
    requestAnimationFrame(() => { if (!done) { done = true; res(true); } });
    setTimeout(() => { if (!done) { done = true; res(false); } }, 1200);
  });
  if (!out.rafFires) {
    out.blockers.push(
      'requestAnimationFrame did NOT fire within 1200ms. Every rAF-based probe ' +
      'you write will hang. This is a fact about the environment, not the page.');
  }

  // --- document identity: are you even auditing the right document? -------
  out.readyState  = document.readyState;
  out.compatMode  = document.compatMode;   // BackCompat === quirks mode
  out.doctype     = document.doctype ? document.doctype.name : null;
  out.charset     = document.characterSet;
  out.url         = location.href;
  if (document.compatMode === 'BackCompat') {
    out.warnings.push('QUIRKS MODE (no doctype). Box model and line-height differ ' +
      'from what the host will serve. You are auditing a different document.');
  }
  if (document.characterSet.toLowerCase() !== 'utf-8') {
    out.warnings.push('Charset is ' + document.characterSet + ', not UTF-8. ' +
      'Non-ASCII will render as mojibake here but may be fine where it ships.');
  }
  if (document.readyState !== 'complete') {
    out.warnings.push('readyState is "' + document.readyState + '". Layout and ' +
      'measurements are not final.');
  }

  // --- fonts: layout that depends on text width is wrong until these land -
  try {
    out.fontsStatus = document.fonts.status;
    if (document.fonts.status !== 'loaded') {
      out.warnings.push('document.fonts.status is "' + document.fonts.status +
        '". Any text measurement now is provisional. Await document.fonts.ready.');
    }
    // Did an @font-face actually apply, or did it silently fall back?
    const faces = [...document.fonts].map(f => f.family + ' ' + f.weight + ' ' + f.status);
    out.loadedFaces = faces.slice(0, 12);
    const unloaded = [...document.fonts].filter(f => f.status !== 'loaded');
    if (unloaded.length) {
      out.warnings.push(unloaded.length + ' declared face(s) not loaded: ' +
        unloaded.map(f => f.family).join(', ') + '. Silent fallback to a system ' +
        'face is the most common invisible design failure.');
    }
  } catch (e) { out.fontsStatus = 'unavailable: ' + e.message; }

  // --- getComputedStyle control reading -----------------------------------
  // It has reported stale values for script-created elements while the pixels
  // were correct. Take a control on a known element before trusting any read.
  try {
    const probe = document.createElement('div');
    probe.style.cssText = 'position:fixed;left:-9999px;color:rgb(1,2,3);width:37px';
    document.body.appendChild(probe);
    const cs = getComputedStyle(probe);
    out.gcsControl = { color: cs.color, width: cs.width };
    const sane = cs.color === 'rgb(1, 2, 3)' && cs.width === '37px';
    probe.remove();
    if (!sane) {
      out.blockers.push('getComputedStyle FAILED its control: set rgb(1,2,3)/37px, ' +
        'read back ' + cs.color + '/' + cs.width + '. Do not trust any style read ' +
        'from this page. Confirm against pixels (screenshot) instead.');
    }
    out.gcsTrustworthy = sane;
  } catch (e) { out.gcsControl = 'failed: ' + e.message; }

  // --- viewport sanity: are you measuring the width you think you are? ----
  out.viewport = {
    inner: innerWidth + 'x' + innerHeight,
    dpr: devicePixelRatio,
    scrollWidth: document.documentElement.scrollWidth,
    scrolledSideways: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
  if (out.viewport.scrolledSideways > 0) {
    out.warnings.push('Page scrolls sideways by ' + out.viewport.scrolledSideways +
      'px. Needs overflow-x:clip on html AND body; html alone leaves body as the ' +
      'scroll container.');
  }
  if (innerWidth < 300 || innerHeight < 300) {
    out.warnings.push('Window is ' + innerWidth + 'x' + innerHeight + '. Too small ' +
      'to audit; layout conclusions from this size are about the window, not the design.');
  }

  // --- errors already on the record ---------------------------------------
  out.verdict = out.blockers.length ? 'INSTRUMENT DEGRADED -- do not diagnose the page yet'
              : out.warnings.length ? 'USABLE WITH CAVEATS -- read warnings before concluding'
              : 'CLEAR -- instrument is sound, findings from here are about the page';

  return out;
})();
