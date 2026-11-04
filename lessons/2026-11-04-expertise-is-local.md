# Expertise is local

**What happened.** The maintainer's own setup made strong work in the areas it had a long
record in: fintech, wellness booking, onboarding flows. Someone cloned it and used it to
redesign a small self-catering accommodation business's site. The result was worse than
their own earlier attempt without it, and they were not sure the skill had even been used.

**Why.** Two separate causes, both now addressed.

1. *The skill had taste but no knowledge of the category.* Its rules (no default fonts,
   one memorable thing, measured contrast) apply everywhere, but what made the
   maintainer's work good was a record of what the best fintech and wellness sites do,
   what their slop looks like, and what had been praised and rejected. None of that
   transfers to cottages. The agent designed confidently from general rules in an area
   it had never studied, and nothing told it, or the user, that it was guessing.
2. *Installed is not used.* Skills trigger on their description. With other design
   instructions already in the user's setup, the agent followed those first.

**What changed.**

- Every brief is matched to a design domain with a confidence score built from evidence
  (references looked at and how, counter-examples, the category's slop written down,
  breadth, shipped work), decaying over a year. Below the stakes target the agent says
  so and researches the category before designing (`ddr domain`, the design-research
  skill).
- The research has instruments, not just instructions: `ddr teardown` captures and
  measures references, `ddr sheet` puts work beside the category's best at the same
  size, `ddr history` shows how old a look is.
- `ddr install` adds a short fenced routing block to the agent's global instructions, and
  `ddr doctor` lists other design skills and generic design rules that compete with it.

**The rule.** A design agent's quality is a property of the domain, not of the agent.
Measure it per domain, say it out loud, and research before designing where it is thin.
