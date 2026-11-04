# Onboarding and signup flows

## Who it is for

Someone who has decided to try a product but has not yet decided to trust it. They arrive with a job in mind (deploy a site, send money abroad, book a meeting, learn some Spanish) and every screen before that job is a cost they are weighing against walking away. Baymard puts forced account creation at 18% of checkout abandonment, and Duolingo's growth lead said moving the sign-up screen back a few steps lifted daily active users by about 20%.

What they worry about depends on the product. In developer and work tools it is time and lock-in: will this take ten minutes, will it want my card, will my team be able to join (Calendly answers with "No credit card required. Upgrade anytime."; Notion and Slack both nudge towards the work address so colleagues can find you). In money products it is exposure: why do you need my passport, how long until I can use this, what happens if the check fails (Monzo says why in one sentence and says up front it takes about 10 minutes; Wise says review usually takes 1 to 2 working days). Low-confidence and older users are the reason GOV.UK starts every form with one question per page.

They compare a signup with the last good one they used, which today is two or three provider buttons and one field, not with the category's competitors.

## What the best do

- **Ask for one thing first.** Linear, Vercel, Notion, Slack, Figma, Wise and Calendly all open with either provider buttons or a single email field and a single primary button. Of the exemplars, Stripe is the most demanding and still stops at four fields (Email, Full name, Password, Country, with Country pre-filled from location and shown with a flag). Everything else (workspace name, role, team size) comes on later screens, one decision at a time.
- **Say what happens next in the heading or label.** "First, enter your email" (Slack, set at about 48px), "First, enter your email address" (Wise's field label), "Your first deploy is just a sign-up away." (Vercel), "Create your workspace" (Linear). Each one names a sequence or an outcome rather than the word "Sign up". GOV.UK recommends "Create an account" over "Register" or "Sign up", and "Create a password" over "Password".
- **Give the reason beside the ask.** Notion: "Tip: Use your work email (if you have one) so it's easier for your team to join you on Notion". Calendly: "Continue with Google or Microsoft to connect your calendar." Monzo, for the selfie video: banks "have to know exactly who has accounts with us". Plaid's guidance says Link converts best when the host app has already said why, what the person gets and what they will need.
- **Show the reward behind the form.** Stripe, Notion and Jira float the signup card over a blurred or greyed skeleton of the product you are about to get (Jira's is a board of cards, Stripe's a payments dashboard). Duolingo goes further and has no form on the first screen at all, just "GET STARTED" and "I ALREADY HAVE AN ACCOUNT", and runs a lesson before asking for an account.
- **Defer identity and paperwork until it is needed.** Wise verifies depending on amount, currency and transfer count ("We might only verify your identity at first, but may need to verify your address later on"). Stripe Connect names the choice outright: up-front (everything eventually due) or incremental (only what is currently due), with "Save for later" anywhere in the flow. citizenM did the same in a hotel: check in on your phone on the way, then one stop at a kiosk, key in hand in about a minute, "no forms to fill out".
- **Tell people what to have ready and how long it takes.** Monzo lists the accepted IDs (passport, driving licence with provisional fine, national ID card, no CitizenCards) before you start. PureGym's first-visit programme lists kit, trainers, water bottle and a padlock, and suggests quieter times using the live busyness tracker.
- **Teach by doing, then end on a real object.** Linear's post-signup flow (every screen seen in the Growth Dives teardown) is about ten dark screens, each one heading, one grey line and one action, no imagery. It teaches the command menu by making you press the two keys shown as large keycaps, then says "That was easy!". Joining and creating a team are two tabs, so nobody makes a duplicate workspace. The invite step has "I'll do this later" under Continue, and the last screen is "You're good to go / When you're ready, create your first issue by pressing c". No confetti. Runna does the same with facts: pick your actual race and it shows "Flat, 230 other Runnas" and a 34 metre elevation gain. Appcues reports Calendly's onboarding ends when you have a shareable link.
- **Validate on blur, keep success visible.** Wroblewski's test: inline validation after the field is left gave 22% more successes, 22% fewer errors and 42% faster completion than submit-and-reload. Validating while typing was worse, except for strict-format fields like a password rule.

## Conventions to keep

- Provider sign-in buttons (Google first almost everywhere; GitHub for developer tools, Microsoft for work tools, Apple on phone). People look for them now. Keep the provider's own mark and say "Continue with X".
- A visible "Already have an account? Log in" (or "Sign in to an existing workspace", Slack) on the first screen, separate from the create path. GOV.UK warns that putting the two side by side is not enough to tell them apart.
- Labels above fields, not placeholder-only (Stripe, Notion, Supabase, Wise). Full-width primary button the same width as the field.
- Terms in one small line under the action ("By signing up, you agree to our Terms of Service, Privacy Policy, and Data Processing Agreement.", Linear). Not a checkbox, unless the law requires one.
- Email confirmation that shows the address it was sent to, lets you resend to a different one, and expires the link with a reason (GOV.UK pattern).
- For identity checks: say which documents are accepted, ask for a photo with "all four corners of the document visible" (Wise), offer an accessible alternative to speaking on video (Monzo accepts written, signed and AAC), and show where the check has got to.

## Conventions to break

- **The intro carousel.** Swipeable cards before the product. NN/g found they did not improve task performance and made simple apps look more complicated; even skipping costs a tap. Replace with a first screen that works without explanation, or Linear's approach of making the onboarding tasks real items in your workspace.
- **The signup wall before value.** A modal over the content the visitor came for, with no visible way to close it (Pinterest). Duolingo replaced a red "Discard my progress" button with a quiet "Later" and kept the hard wall for after several lessons; Baymard says make the guest path the most prominent option and offer the account at the confirmation step.
- **The disabled submit button with no reason.** Stripe and Supabase both show a pale disabled primary until the form is valid. People press it and nothing happens. Leave it enabled and say what is missing on submit, beside the field.
- **Sales qualification on the first screen.** Zoho CRM's trial asks for Full Name, Email, Create Password and Phone Number, then a marketing checkbox and a Terms checkbox, all before anything is shown. Phone, job title and company size are for the sales team. Ask them after the first useful moment, or not at all, and replace the Terms checkbox with one line under the button.
- **Setup screens that sell.** Windows 11's first run puts eight upsell screens between sign-in and the desktop. Every screen that serves the vendor rather than the person's first job should go.
- **"Sign up" as the heading.** Name what the person gets ("Create your workspace", "Your first deploy is just a sign-up away.").

## Category slop

Ask a model or a template for "onboarding" and you get the Dribbble search page: three phones side by side, each a welcome card with a 3D illustration or a stock photo of smiling people on top, a title-case slogan with no noun you can act on ("Perfectly Organize Your Family Life", "AI That Organizes For Your Work Priority", "Stay Connected Together"), a grey sentence, page dots and a full-width pill "Next" or "Get Started". The B2B version is a left-hand checklist of steps beside "Create your workspace" and "Set up email forwarding" panels on a pale tint. Swap the logo and either one fits any app, which is the swap test failing.

The tells, layer by layer:

- **Structure:** a carousel or tour before the product; a signup wall dropped over content the visitor came to see (Pinterest's logged-out Explore dims the page behind "Welcome to Pinterest / Log in to discover more ideas just for you" and offers a new visitor a password field first); setup screens that sell (Windows 11's eight upsells in a row, Calendly's trial panel inside the signup card); twenty-odd setup questions before anything useful (Runna's 30 screens and about 12 minutes, birthday and gender included).
- **Copy:** slogans where an instruction should be (the Dribbble cards above; Notion's grey second line "Sign up with your work email" under "Notion: your AI workspace."), "Sign up" as the only heading, social proof on the task screen (Vercel's "80% faster from design to live", Supabase's half-screen customer quote).
- **Form craft:** placeholder-only fields (Calendly's "Enter your email"), a password placeholder of dots that looks already filled (Supabase), a pale disabled submit with no reason (Stripe, Supabase), icon-only provider buttons (Wise), and a legal line that quietly signs you up for email (Supabase: "and to receive periodic emails with updates").
- **Visuals:** a gradient wash behind a centred card (Calendly's blue to mint), a tracked uppercase eyebrow over a sales panel ("TRY TEAMS PLUS EXPERIENCE FREE"), 3D illustration and stock lifestyle photography standing in for the product.

I did not see "Welcome aboard!" copy, confetti screens or emoji step icons in this round; SLOP.md's general list still applies, but those are not evidenced here.

## Language

The best signups are almost silent visually and loud only in one place: the heading or the reward behind the form. Linear is a logo, an 18px heading (measured: Inter, weight 500) and three buttons on a pale grey page. Figma is three elements on white. Slack spends its boldness on one huge instruction and keeps the rest small. Of the signup screens I rendered, only Duolingo uses illustration, and its owl and cast are the product's own characters, not stock, with a 3D-edged green button that belongs to the app it opens.

Type: the product's own UI face at a single size for labels and body (13px on Linear, measured; about 15 to 17px on Duolingo), one heading between 18px (Linear, measured) and about 48px (Slack, estimated from the render). Colour: the brand's primary on the main action only; providers outlined and neutral. Copy is the main design material: imperative, second person, one sentence of reason under the heading, sequence words ("First,"), outcomes instead of "Sign up". For money and identity steps the voice can be warmer (Monzo admits "Sending your bank a selfie might sound a bit weird") but the facts stay exact: which documents, how long, why. Motion belongs to field focus, inline validation and the step change; comparing the motion and reduced-motion captures, Linear's form does not move at all, and Vercel's only movement is the customer-proof line under the card, caught mid-swap and blurred in the motion capture. The form itself stays still.

## Open questions

- I have not created an account anywhere or submitted anything. Post-signup steps come from public teardowns (Linear and Runna through Growth Dives) and help pages (Monzo, Wise). A walk with test identities would show how errors and the verification wait actually look.
- Rendering was blocked at GitHub ("Access is temporarily restricted"), Mercury (Cloudflare), Oracle's account page ("System Error"), Salesforce's trial form ("Access Denied") and Quora (Cloudflare check), so I have no first-hand ten-field enterprise form. Instagram's logged-out Explore showed content behind a cookie dialog, not a signup wall, on the day I looked.
- No first-hand view of an in-app identity capture screen (document photo, selfie, liveness). Monzo and Wise are described from their help pages only. A public teardown with screens of a KYC step would close this.
- Growth.design's case studies would be a strong leader source, but its robots.txt disallows AI crawlers, so I did not read them.
- No numbers on how much a blurred product preview behind the form helps, or whether one-question-per-page beats a short single page for account creation outside government services.
