# What you are allowed to claim

TYPE.md governs how it looks. This file governs what you may say about it. It exists
because of one repeated failure in agent design work: **collapsing "consistent with"
into "caused by", and "the check passed" into "the thing is right".** Both are the same
missing question, asked at two moments:

> **What would have to be true if I am wrong?**

Before naming a cause: what else must hold if this is really it, and what would I be
seeing instead if it were not? Before saying "done": what result would have made this
check fail, and what can this check not see?

## The ladder. Never use a word above the rung you earned

| Word | What it costs to say it |
|---|---|
| **guessed** | A story that fits. No test. Most first thoughts belong here. |
| **observed** | You ran something and this was the output. The output, not your reading of it. |
| **reproduced** | It happens on demand, twice or more, from a stated starting state. |
| **isolated** | One variable, changed alone, turns it on and off. |
| **explained** | You can state the mechanism, it predicted something else, and that prediction checked out. |
| **fixed** | The isolation test no longer reproduces, **and reverting the fix brings the bug back**. |

Say the rung out loud. "A guess, untested" is a complete and useful sentence. The
taste ledger records it (`ddr taste error --rung guessed`).

## Rules

1. **Prove the instrument before you accuse the object.** A tool that times out,
   returns null or reports something odd is evidence about the measuring path until
   that path is shown healthy. Run `tools/instrument-check.js` in the page first. An
   agent's browser tab is usually hidden, and a hidden tab never fires
   `requestAnimationFrame`, so it looks exactly like a frozen page.
2. **Predict, then look.** Before accepting a cause, write down what else must be true
   if it is right. Check that.
3. **Revert to confirm.** A fix that coincides with the symptom going away is not
   confirmed until putting the bug back brings the symptom back.
4. **Two failed diagnoses means stop guessing.** Bisect from a known-good state, one
   variable at a time, and write down what each step rules out.
5. **Every completion claim carries its limits.** "Checked desktop and phone in
   Chromium. Did not check Safari or a real device." A clean console means the console
   is clean, not that the feature works.
6. **Check the thing that ships, not the thing you built.** Contrast on tokens is not
   contrast on the composited pixel. A bare fragment on a local server is not the page
   the host serves. A screenshot of the design is not the design on a phone.
