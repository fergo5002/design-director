# UX

How a screen works: what people can find, understand, do, undo and trust. TYPE.md, COLOUR.md and
UI.md cover how it looks. Load this file for any product UI, form, flow, onboarding, dashboard,
checkout, settings page or app screen, and for the working parts of a marketing page (sign-up,
pricing, contact, navigation).

## The canon, and what each source is for

Three sources cover UX across every industry. Everything below traces to one of them unless it
says otherwise.

| Source | Use it for | Read it at |
|---|---|---|
| **Nielsen Norman Group** | The ten usability heuristics, response times, forms, empty states, navigation, disclosure. Dated research articles from real usability studies | nngroup.com/articles (free) |
| **WCAG 2.2 and the W3C WAI** | The only testable standard: contrast, keyboard, focus, target size, names, errors, motion. W3C Recommendation since 5 October 2023, current edition 12 December 2024 | w3.org/TR/WCAG22, plus each criterion's Understanding page |
| **GOV.UK Design System and Service Manual** | Patterns built from published user research: question pages, validation, dates, addresses, check answers, confirmation, task lists, problem pages | design-system.service.gov.uk/patterns |

Add **Baymard Institute** for commerce: 70.22% average cart abandonment across 50 studies
(baymard.com/lists/cart-abandonment-rate, dated 2026-10-28). The US reasons: extra costs 40%, slow
delivery 20%, distrust with card details 19%, forced account creation 18%, too long or complicated
17%, errors or crashes 17%. Use **Norman** (The Design of Everyday Things), **Krug** (Don't Make Me
Think) and **Shneiderman's eight golden rules** for vocabulary, not as the evidence.

Take GOV.UK's interaction rules, never its look. Take NN/g's findings, never its page style.

**Myths not to apply.** Miller's "7 plus or minus 2" measured short-term recall, not menu length;
never cap a menu at seven. Hick's law says decisions slow with more and harder choices, not that
fewer is always better; a grouped, scannable list beats a short one that hides what people need.
The "three-click rule" has no evidence behind it. Nielsen's 0.1, 1 and 10 second limits are better
sourced than Doherty's 400 ms.

## Before building any screen

Write these down in the brief. They take five minutes and catch most UX failures before any markup
exists.

1. **The job.** One sentence: who is here, what they came to do, what counts as done.
2. **One primary action.** Exactly one element on the screen is the main thing to press.
3. **The states.** For every block that shows data or responds to input: empty, loading, error,
   success, partial, and (for apps) offline and stale. A block without its states is unfinished.
4. **The patterns.** Name every pattern on the screen (form, validation, dialog, table, tabs,
   combobox, date input, search, filter, toast, wizard) and fetch its pattern page from the table
   below before building it. Never hand-roll a dialog, menu, combobox or date picker from memory.
5. **The words.** The nouns the user would use for each object, one noun per object, and the verb
   on every button.

## Pattern pages to fetch

Free and readable as plain text by an agent (each checked 2026-11-11). Fetch the page for the pattern
you are about to build, follow it, and say in the brief which one you used.

| Pattern | Behaviour and research | Component code |
|---|---|---|
| Forms, questions, validation, dates, addresses, names, phone numbers, check answers, confirmation, problem pages | GOV.UK: `https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/patterns/<name>/index.md` (names: `validation`, `dates`, `addresses`, `names`, `phone-numbers`, `check-answers`, `confirmation-pages`, `question-pages`, `complete-multiple-tasks`, `step-by-step-navigation`, `page-not-found-pages`, `problem-with-the-service-pages`) | shadcn `field`, `input` |
| Dialog, alert dialog, menu button, tabs, combobox, listbox, disclosure, accordion, switch, slider, toolbar, tooltip, grid, treegrid | WAI-ARIA Authoring Practices: `https://github.com/w3c/aria-practices/tree/main/content/patterns/<name>` (for example `dialog-modal`, `alertdialog`, `combobox`, `tabs`) | React Aria: `https://react-aria.adobe.com/<Component>.md` (index at `/llms.txt`), shadcn: `https://ui.shadcn.com/docs/components/<name>.md` |
| Data tables, notifications, UI shell | Carbon: `https://carbondesignsystem.com/llms.txt` | shadcn `table`, `sonner` |
| Government-grade forms with accessibility tests | USWDS: `https://designsystem.digital.gov/llms.txt` | its own markup |
| Hard widgets: date picker, calendar, combobox, table with selection, drag and drop, anything that must work in many languages | React Aria (Adobe), the deepest behaviour library; `@react-aria/mcp` serves its docs to an agent | React Aria Components |

In a React project the default build is shadcn for the shell and React Aria for the hard widgets.
In plain HTML use the native element first (`<dialog>`, `<details>`, `<select>`, `<input
type=date>` only where its picker suits the question), then the APG pattern.

## 1. Foundations

### The ten heuristics (NN/g)

Visibility of system status; match between system and the real world; user control and freedom;
consistency and standards; error prevention; recognition rather than recall; flexibility and
efficiency; minimalist design; help users recognise, diagnose and recover from errors; help and
documentation. Add Shneiderman's **closure** (every task has a visible start, middle and end) and
**universal usability** (novices, experts, small screens, older people, assistive technology).

- Before calling a screen done, walk the ten and write one line each: pass, fail or not relevant.
- Prefer the known pattern. People spend most of their time on other products and expect yours to
  work the same way (Jakob's law). Invent only where the product's mechanic is genuinely new.

### Mental models

The user's belief about how the thing works, built from other products and the real world. The
interface either matches it or has to teach the difference.

- Name things in the user's words, from their task, never from the database or the org chart.
  "Invoices", not "Billing documents"; "Bin day", not "Waste collection schedule".
- One metaphor per product (inbox, cart, project) and verbs that fit it, used the same way on every
  screen. Three names for one object is the commonest model-made failure.
- Where the system differs from what people expect (autosave instead of Save), say so once, where it
  matters.

### Signifiers, feedback and mapping (Norman)

An affordance is what something allows; a signifier is the visible cue that says so; mapping is how
a control relates to its effect; feedback shows the result.

- Everything clickable looks clickable and nothing else does. Links differ from body text by more
  than colour (WCAG 1.4.1).
- Every control has hover, focus, active, disabled and busy states. Disabled says why ("Add a card
  to continue"), or stays enabled and explains on press.
- Respond within 0.1 s. Past 1 s show that work is happening. Past 10 s show progress and a way to
  cancel, or move it to the background and notify (Nielsen's limits).
- Put the control next to the thing it changes.

### Cognitive load

The mental effort the screen asks for. Levers: how many options, how hard each is, what people must
remember, how things are grouped.

- Reduce, group, order. Cut what few people need (or disclose it later), group the rest by meaning,
  order by frequency or by the natural sequence.
- Recognition over recall: show options, recent items, suggestions and defaults. Never make people
  carry a value from one screen to another; repeat it where it is needed.
- When a choice is hard, recommend one option and mark it. Only one.
- When people compare, line the attributes up in a table.
- Complexity moves, it does not vanish (Tesler). Decide who carries it and make it the system.

## 2. Structure

### Navigation and information architecture

How content is grouped, named and reached. Every page answers: where am I, where can I go, how do I
get back.

- Organise by the user's top tasks. On a service site the home page leads with search and the most
  common tasks as plain links ("Check your bin day"), not a welcome banner.
- Global navigation stays the same on every page, in the same place, with the current page marked
  visibly and in markup (`aria-current="page"`).
- Labels are short, specific and front-loaded. No "Solutions", "Resources", "More".
- Breadcrumbs for hierarchies deeper than two levels. They show the path, not the history.
- A skip link is the first focusable element: the usual way to meet WCAG 2.4.1 (landmarks and headings help too).
- Search in the header of any site with more than a handful of pages.
- Never a dead end: every page has a way up, a way back and a next step. A 404 offers search and
  the top tasks.
- Phone: top tasks visible, not all behind a menu. App-like products use a bottom bar of three to
  five items.

**Good.** GOV.UK: task-led links, the same header everywhere, breadcrumbs, one h1 per page.
**Bad.** A council home page opening on a full-screen photograph and "Welcome to our vibrant
community", with eleven header links and bins three screens down.

### Search and filtering

- An open search field with a visible label or magnifier, not a lone icon.
- Forgiving matches: case, plurals, typos, partial words.
- Keep the query in the box and in the results heading; show the count; let people clear it.
- Zero results is a designed state: say so, suggest a correction, offer the popular items.
- Filters people use most go first, with counts. Active filters show as removable chips with
  "Clear all". The most common narrowing ("Late", "Unpaid") is one press, not a dropdown hunt.
- State lives in the URL so Back works and results can be shared.

### Progressive disclosure

Show what most people need first; put the rest behind a labelled control.

- Label the reveal with what is inside ("Delivery options"), never "More" or "...".
- Two levels at most (NN/g). Beyond that, simplify instead.
- Never hide what someone needs to finish the task or understand an error.
- `<details>` and `<summary>`, or a button with `aria-expanded` and `aria-controls`. A collapsed
  group that holds an active value shows it.

### Multi-step flows

- A wizard only when the task is linear and its steps barely depend on each other. One question per
  page for hard questions (GOV.UK question pages); one page for a simple form.
- Say where they are ("Step 2 of 4: Delivery") and tell the truth about progress.
- Back never loses data. Each step has its own URL so the browser's Back works.
- End with a check-your-answers page that links each answer to its edit, then a confirmation page
  with a reference number and what happens next.
- Never ask for the same thing twice (WCAG 3.3.7). Never force sign-in halfway through.
- Long flows say how long they take ("about 5 minutes") and save progress.

### Onboarding and first run

- Name the first moment of value in one sentence and count the steps to it. Cut every step before
  it that is not essential.
- Delay account creation until the value is shown where you can.
- Teach by doing: real UI, sample data, an empty state that offers the first action. People skip
  tours (the paradox of the active user); if there is one, three or four steps, skippable.
- Ask setup questions only when the answer changes what they see next, and say why you ask.
- Permission prompts (notifications, location) only in context, after the benefit is clear.

## 3. Input

### Forms

- One column. A visible label above every field, always. A placeholder is never the label: it
  vanishes on typing, fails contrast and is not reliably read out.
- Ask only for what you can name a use for. Mark the few optional fields "(optional)" rather than
  starring every required one.
- The right `type`, `inputmode` and `autocomplete` on every personal field (WCAG 1.3.5): `name`,
  `given-name`, `family-name`, `email` with `type=email`, `tel` with `type=tel`, `street-address`
  or `address-line1`, `postal-code`, `bday`, `cc-number` with `inputmode=numeric`, `cc-exp`,
  `cc-csc`, and `one-time-code` for codes sent by text. These bring up the right keyboard and let the browser fill the form.
- Inputs at 16 px or more, or iOS zooms the page on focus.
- Memorable dates (date of birth) as three labelled boxes for day, month and year, not a calendar
  picker (GOV.UK dates pattern). Pickers suit dates near today.
- Accept input loosely and tidy it yourself: spaces in card numbers, any case in postcodes.
- Hints go above the field, outside the placeholder, linked with `aria-describedby`.
- Radios for two to five options (no dropdown for three choices); a select or a searchable combobox
  for long lists. `fieldset` and `legend` around radio and checkbox groups; the legend is the
  question.
- The button says what happens: "Register", "Book appointment", "Pay €42.50". Never "Submit".
- Never pre-tick consent or marketing boxes.

### Validation and error messages

From the GOV.UK validation pattern and NN/g's form error guidelines.

- Validate on submit, not when the person leaves a field (GOV.UK). Check as they type only where
  research shows it helps, such as password rules. Never flag a field at the first keystroke.
- On submit with errors: stay on the page, keep everything typed, show an error summary at the top
  linking to each field, and put the message beside each field as well. Move focus to the summary.
- In markup: `aria-invalid="true"` on the field and `aria-describedby` pointing at its message.
  Browser validation bubbles alone are not enough: they vanish, cannot be styled and are read out
  inconsistently. Use `novalidate` and your own messages.
- Say what is wrong and how to fix it, in the user's terms: "Enter your date of birth, for example
  27 3 1958", not "Invalid input". Colour plus text or an icon, never colour alone.
- If the same field fails again, give more help.

### Destructive actions and undo

- Prefer reversal to confirmation: an Undo toast, a bin with a retention period, a send delay,
  version history. Asking "Are you sure?" on everything trains people to click through.
- Confirm only what cannot be undone. The confirmation names the object and the consequence
  ("Delete harbour-api? Every deployment and its history will be removed. This can't be undone."),
  the destructive button repeats the verb and the object ("Delete harbour-api"), and Cancel is
  there and safe.
- For the highest stakes, ask the person to type the name, or to sign in again.
- The destructive button is never the most prominent thing on the page in its normal state, and
  sits apart from the frequent actions.
- A modal dialog moves focus inside on open, traps Tab, closes on Escape and returns focus to the
  button that opened it (APG dialog pattern). The native `<dialog>` with `showModal()` does most
  of this for you.

### Settings

- Good defaults mean most people never visit. Group by what the user recognises (Account,
  Notifications, Privacy, Billing), not by system component.
- Either save each change at once and say "Saved", or use one Save button with an unsaved-changes
  marker. Never both on one page.
- Show the current value and say in one line what each setting does.
- Destructive account actions sit in a separate section at the bottom.
- Switches are real switches (`role=switch` or a checkbox) with labels.

## 4. Output

### System states

No screen is only "data present".

- **Empty.** Say what this area is for and offer the first action as a button ("Create your first
  invoice"). An illustration without an action is decoration. Never show "No results" while still
  loading.
- **Loading.** Nothing under 1 s beyond immediate feedback. Past 1 s, a skeleton that matches the
  final layout for content, a spinner for a short action. Mark the region `aria-busy="true"` or
  announce it with `role="status"`. Reserve the space so nothing jumps.
- **Error.** What happened, in plain words, what to do, a retry button, and the user's work kept.
  No "Oops", no error codes unless support needs them, no blame.
- **Success.** Confirm the outcome in words and say what happens next, where the person is looking.
- **Partial.** If one block fails, render the rest and give that block its own retry.
- **Offline and stale.** Say "You're offline" or "Updated 10:42" plainly; keep cached data readable.

### Notifications

- Match the interruption to the importance: a blocking dialog is rare; a banner for important
  news; inline or a toast for confirmation of the user's own action; a badge for the rest.
- Toasts stay at least five seconds, pause on hover and focus, carry Undo where it applies, and use
  `role="status"`. Errors that need action never live in a toast.
- No pop-up within seconds of arrival. Nothing hides the focused control (2.4.11 bans hiding it
  entirely; aim for 2.4.12, not covered at all).

### Tables and lists

- Tabular data in a real `<table>` with `<th scope>` and a caption or `aria-label`. A grid of divs
  is not a table to a screen reader.
- Text left-aligned, numbers right-aligned with tabular figures (`font-variant-numeric:
  tabular-nums`), the same decimals, units in the header. The first column identifies the row.
- Sortable columns are buttons in the header with `aria-sort` on the sorted one.
- A long table keeps its header in view (`position: sticky` on `th`).
- Row actions in the same place on every row, named with the row ("Edit order 1042").
- On a phone, the page itself never scrolls sideways: the table scrolls inside a labelled container,
  or rows restack as cards.
- Show the total count; prefer pagination or "Load more" to infinite scroll when people need the
  footer or their place.

### Dashboards and data-dense tools

Load DASHBOARDS.md and the dataviz skill as well. The UX rules:

- Start from the question each block answers. The most important figure is first and largest, and
  no number stands alone: give it a period, a comparison and a unit.
- Filters and the date range are obvious, persistent and echoed in the heading ("Last 30 days, all
  shops").
- Experts return daily: saved views, keyboard shortcuts, bulk actions, density, sortable columns.
- Live updates never move what someone is reading. Every aggregate drills down to its records.

## 5. Words

- Plain language: short words, short sentences, the user's vocabulary, active voice.
- Front-load headings, links, labels and list items: people read the first two words and move on.
- Buttons are a verb and an object. Link text says where it goes: WCAG 2.4.4 lets the sentence
  around it help, 2.4.9 asks for the link alone, so aim for that. No "Click here",
  "Learn more" or "Read more" alone.
- Errors say what happened and how to fix it. No jokes in errors.
- Sentence case. One term per concept. Numbers and units in full where money is involved ("€12 a
  month, billed yearly").
- Microcopy sits next to the decision it informs (why you need the phone number, beside the phone
  field).

## 6. Everyone

### Accessibility floor (WCAG 2.2 AA)

The gate runs axe; these are the parts a model most often gets wrong and axe cannot always see.

- Real elements: `button` for actions, `a` for navigation, `label`, `table`, `nav`, `main`, one `h1`
  and headings in order. ARIA only where HTML cannot say it. A `div` with an `onclick` is invisible to
  a keyboard and a screen reader.
- Contrast 4.5:1 for text, 3:1 for large text, controls, focus rings and chart marks, measured on
  the composited pixel.
- Every control works by keyboard, in a sensible order, with a visible focus style. Nothing focused
  is entirely hidden under a sticky bar (2.4.11; use `scroll-padding-top`).
- Targets at least 24 by 24 CSS px (2.5.8 minimum); 44 by 44 on touch (Apple 44 pt, Material
  48 dp). Dragging always has a single-pointer alternative (2.5.7).
- Every image has `alt` (empty for decoration); every icon button has an accessible name that
  contains its visible text, if any.
- Status messages announced without moving focus (`role="status"`, 4.1.3).
- Works at 200% zoom and at 320 px wide without sideways scroll. Never block pinch zoom in the viewport tag.
- Respect `prefers-reduced-motion`; anything that moves for more than five seconds can be paused.
- Help and contact sit in the same place on every page (3.2.6). Allow paste and password managers
  on sign-in (3.3.8).

### Touch and phones

- The phone is its own design. Frequent actions within thumb reach in the lower half; destructive
  ones away from it.
- Every gesture has a visible button too. Nothing essential lives in a hover or a tooltip.
- The right keyboard for every field (`type`, `inputmode`) and native pickers where they suit.
- When the keyboard opens, sticky bars must not cover the focused field.
- Save state constantly: people get interrupted.

### Speed

- Feedback within 100 ms of any input. Optimistic updates for low-risk actions (like, toggle,
  reorder), rolled back with a visible message on failure.
- Show the page's main content early and reserve space for everything that loads later (CLS 0.1
  or less; LCP 2.5 s or less; INP 200 ms or less, the Core Web Vitals targets).
- Never block input while secondary content loads.

## 7. Honesty

### Trust

- Real, specific proof near the decision: named customers, real numbers with sources, real photos,
  an address and a contact route. Never stock teams or unattributed superlatives.
- The total cost early: the top reason people abandon a purchase is extra costs (40%), and 12% could
  not see the total up front (Baymard).
- Say why you ask for sensitive data and what you will do with it, beside the field.
- Regulated sectors show the regulator's name and number and the terms in plain words.

### Dark patterns: never build these

Confirmshaming ("No thanks, I hate saving money"); hidden or drip-fed fees; forced account creation
before purchase; cancelling harder than signing up; pre-ticked consent or add-ons; fake urgency,
scarcity, viewers or reviews; a reject button styled as faint text beside a bright accept; nagging;
items sneaked into the basket; double negatives. If a tactic only works when the person is
confused, drop it.

### Checkout

- Guest checkout by default; offer an account after payment with one field.
- Delivery cost and date per option, and the running total, on every step.
- Wallets first on a phone, the right keyboards, card number autofill, billing address same as
  delivery by default.
- A failed payment says why and offers another way, with everything typed still there.
- The pay button carries the amount ("Pay €42.50").

## Cheap checks

Run `ddr ux --file <page.html>` on the built page (a phone and a desktop size by default; exit 1 on
any fail), or paste `tools/ux-probe.js` into a browser console on a live page. It lists what a
script can count: unlabelled fields, missing input types and autofill tokens,
inputs under 16 px on a phone, vague button text, clickable divs, missing skip link and
`aria-current`, numbers not right-aligned or tabular, targets under 24 px (and under 44 on touch),
sideways scroll, and pre-ticked consent boxes. Measure sideways scroll against
`document.documentElement.clientWidth`, never `innerWidth`: under phone emulation `innerWidth`
stretches to fit the content, so the check can never fail.

Then do what a script cannot: submit the empty form and read the errors; press Tab through the
whole page; flip every block through its states; read every label as a stranger would. A clean probe
means the countable rules passed, not that the screen works. Real users on the real flow are the
only proof for anything important; say when nobody has tried it.
