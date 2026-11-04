# design-director for coding agents

This repo is a design workflow for coding agents (Claude Code, Codex, Cursor, Gemini
CLI and anything else that reads AGENTS.md). If you are an agent doing design work in
a project that has this installed, start here.

## When to use it

Any design work: a page, a component, a dashboard, a brand, a deck, motion, imagery,
or a review of any of those. Load the skill before writing markup, picking a colour or
choosing a typeface.

## The four skills

| Skill | Read | When |
|---|---|---|
| design-director | `skills/design-director/SKILL.md` | Any design work. The lead: names the job, routes to the guides, sets the gate. |
| design-research | `skills/design-research/SKILL.md` | When domain confidence is below the stakes, a brief is new territory, or the work looks generic. |
| design-review | `skills/design-review/SKILL.md` | Before calling anything done. |
| design-taste | `skills/design-taste/SKILL.md` | Whenever someone praises or rejects a design, something ships, or a process goes wrong. |

Agents that support skills natively get them from `python tools/ddr.py install`. Agents
that do not should read the SKILL.md files above directly when the trigger applies.

## The tools

Run `ddr <command>` (or `python tools/ddr.py <command>` from this repo):

- `ddr domain match "<brief>"`: read first. Which design domains the brief falls in and how much you actually know about each (0 to 100). Below the stakes target, research before designing.
- `ddr domain brief <slug>`: the dossier, exemplars, counter-examples and ledger for a domain.
- `ddr domain new|ref add|ref retire|relate|merge|audit|status|plan`: build and curate the expertise.
- `ddr taste brief`: what was rejected, what landed, what is saturated.
- `ddr sources search "<need>" -v`: the verified catalogue of sites, libraries, MCP servers, skills and AI tools.
- `ddr sources shuffle -n 3`: a random cross-discipline draw, for a direction that is not your default.
- `ddr lint <src>`: the obvious generated-design tells.
- `ddr shots <url> --full`: render at desktop, phone and 320px, with and without reduced motion, and measure.
- `ddr palette ramp|check|blend`: OKLCH ramps and measured contrast.
- `ddr fonts`: inline a subset webfont for sandboxed pages.
- `ddr mcp`: recommended MCP servers with setup per agent.
- `ddr taste win|miss|shipped|error`: log outcomes as they happen.

## Rules that apply to every agent

- Say your domain confidence before designing, and research on your own when it is too low for the stakes.
- Never record a reference as seen that you did not see. The confidence score is only worth anything if the evidence behind it is true.

- Never claim more than you checked. Say what you verified and what you did not.
- Prove the instrument before blaming the page: run `tools/instrument-check.js` before
  diagnosing any rendering, freeze or timeout problem in a browser.
- Never scrape a site whose terms forbid it, never copy paywalled screens into a
  public repo, never pirate a typeface.
- When changing this repo: run `python -m unittest discover -s tests`,
  `python tools/ddr.py sources validate`, `python tools/check_routes.py` and
  `python tools/ddr.py sources render` before committing. Starter domains live in `domains/`;
  write to them with `DDR_HOME=<this repo>` so `ddr domain` edits them in place.
