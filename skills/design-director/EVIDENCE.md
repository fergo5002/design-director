# Evidence

**A beautiful page that argues something false is not a near miss. It is a failure.**

This file exists because of a specific incident. A page was built to test this skill.
It passed every gate the skill had: no banned typeface, a palette built in OKLCH and
verified at 4.58:1, real data from a real API, `prefers-reduced-motion`, focus rings,
44px targets, no horizontal scroll, two designed themes. It was genuinely good
looking. Its headline was **"The sea is two months behind the sky"**, and that was
false. Measured across all six places in its own dataset, the lag was 0 to 2 months,
mean 0.5. It was true at the first place looked at and generalised from there.

Four more errors were in the same page's copy. Every one would have shipped.

Nothing in a visual quality gate can catch this. So there is a separate gate.

---

## The rule

**Every claim in the copy is part of the deliverable and gets checked against the
source before the page ships.** A claim is any sentence containing a number, a
count, a comparison, a superlative, a date range, a causal statement, or a
recommendation.

"Real copy, never lorem" is not enough. Real and wrong is worse than lorem, because
lorem cannot be believed.

## How to check

Write a script. Not a re-read, a script. Re-reading your own copy against your own
memory of the data is how the error got in.

```python
# claims.py -- one assertion per claim the page makes
d = json.load(open("data.json"))

print("CLAIM: 'coldest in March' -- at how many of the six?")
mar = sum(1 for s in d.values() if argmin(s["sea"]) == 2)
print(f"  -> {mar} of 6. Page says 'four'. {'OK' if mar == 4 else 'WRONG'}")
```

Run it, paste the output into your working notes, and fix the copy to match the
output rather than fixing the output to match the copy. In the incident above this
took four minutes and found five errors, including the headline.

Keep the script. When the data is refreshed, the claims are re-checked for free.

## Data has to be checked before it is averaged

The same page reported a "2021 to 2024" record. The sea series actually began on
**24 November 2022**: 769 of 1461 days were `null`. The averaging code skipped nulls,
so the *numbers* were right and only the *provenance* was wrong, which is the most
dangerous shape an error can take. It looks fine.

Before you take a mean of anything:

```python
n_null = sum(1 for v in series if v is None)
assert n_null == 0, f"{n_null}/{len(series)} values are null -- do not average this"
```

Then state the window you actually have, not the window you asked for. If it is two
years, say two years, and say what two years cannot tell you.

## Never transcribe data into markup

Injecting numbers by hand into HTML or a JS literal is how a page ends up
contradicting its own source file. Put a marker in the template and generate:

```python
src = src.replace("/*@DATA@*/", literal_from(json.load(open("data.json"))))
```

Now the page cannot drift from the data, and refreshing the data refreshes the page.

## State uncertainty in the design, not just the footnotes

The honest version is usually the more interesting one. When the false two-month lag
was replaced with what the data actually supported, the page got better:

> From September to January, at all six of these places, the water is warmer than the
> air above it. In November the cold part of a swim is not the water. It is the
> twenty minutes afterwards.

That is true, it is universal across the sample, it is counterintuitive, and it is
useful to the reader. **Look for the claim the data does support before you weaken
the one it does not.** There is almost always a better sentence hiding in the real
numbers.

Give the caveat design weight rather than burying it. A colophon that says which two
years, why those two, and what they cannot separate is a mark of confidence.

## Charts

- **The graphic should carry the argument, not decorate it.** If the point is a
  difference, shade the difference. A reader should be able to see the claim without
  reading the caption.
- **Do not encode meaning in hue alone.** A single hue varying in lightness survives
  colour blindness and a monochrome printer. Diverging red-to-blue is the default and
  usually the wrong one.
- **Cell text over a colour scale must use pure `#000` and `#fff`.** Picking the
  better of two inks leaves a dead zone unless the pair is at the extremes: with
  `#0e130d` and `#f8f5ec` the best available contrast bottoms out at 4.15:1 in the
  mid-range. With `#000` and `#fff` the two curves cross at exactly **4.58:1**, so
  every possible background clears 4.5. Verify across the ramp, do not spot-check:

  ```
  python tools/palette.py check --ground "cell=#6a8374" --fg "b=#000000,w=#ffffff"
  ```
- **Do not smooth beyond the resolution of the data.** A spline through monthly means
  invents readings that never happened. A straight polyline reads as a spreadsheet.
  Catmull-Rom with the control points held inside the segment sits between the two.
- **Say what the units are.** "Wind" was labelled as gusts when the field was the
  daily maximum ten-metre wind speed. Different thing, and someone will rely on it.

## Copy that makes a factual claim about the world

If the page tells a reader what to do with their body, their money or their safety,
the standard rises:

- Distinguish **established** from **commonly repeated**. An almanac records folklore
  and marks it as folklore. "One minute per degree" has no clinical basis, and saying
  so is more interesting than repeating it.
- Do not overstate a mechanism you cannot cite. "Cold shock is what harms people in
  the opening minutes" is defensible. "Most drownings happen in the first minute" is
  a statistic, and you do not have it.
- Put the disclaimer where it will be read, in the same type size as the rest.
