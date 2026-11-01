# A hidden tab looks exactly like a frozen page

**Kind:** process error. **Rung reached:** explained.

Three wrong diagnoses in one session (a "ResizeObserver loop", a "slow chart", a
"stale colour") all came from the measuring path, not the page. Browser tabs driven by
an agent are usually backgrounded, and a background tab never fires
`requestAnimationFrame`, so every frame-based probe and screenshot hangs. Separately,
`getComputedStyle` reported a colour that the composited pixels did not show.

**Prevention:** run `tools/instrument-check.js` before diagnosing any rendering,
freeze or timeout problem. Anything below `CLEAR` means fix the instrument first.
Judge colour from a screenshot, not from computed style.
