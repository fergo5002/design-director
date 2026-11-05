# Evals

`ddr eval` runs a design skill headless on real briefs, then grades what it made and what it
did. The point is to compare two versions of a skill (two arms) on the same cases and see
which one breaks fewer of the rules we already know matter. No model judges taste. The
graders count what can be counted, and a person looks at the contact sheets.

```bash
ddr eval list                                         # the cases in $DDR_HOME/evals/cases
ddr eval run --arm old=~/skills/old/design-director \
             --arm new=skills/design-director --dry-run     # the plan and the money ceiling
ddr eval run --arm old=... --arm new=... --jobs 2           # spend it
ddr eval run --arm before=git:~/skills@v1:design-director \
             --arm after=~/skills/design-director   # a tagged baseline against the working copy
ddr eval report latest                                # report.md again, or --json
ddr eval report latest --regrade                      # grade stored runs again after editing graders, free
ddr eval sheet latest                                 # one contact sheet per case, arms side by side
```

`run` exits 0 when every grader passed, 1 when any failed or a run timed out, 2 when a
grader or a run could not look. It refuses to start when the summed budget ceiling (each
case's `budget_usd` times the number of arms) is over `--max-total-usd` (default 25).

## Arms

An arm is `name=<skill directory>` (a folder holding `SKILL.md`) or
`name=git:<repo>@<ref>:<path>`. A git arm is checked before anything is spent (the ref must be
a commit and `<path>/SKILL.md` must exist in it) and then `git archive`d into
`<run>/arms/<name>/`, so the baseline is exactly that commit, whatever the working copy holds.
`results.json` records each arm's path, the git repo, ref and full commit, and a hash of the
files the run saw.

## Writing a case

A case is a real correction turned into a test. Each one lives in
`$DDR_HOME/evals/cases/<id>/case.toml` (private to you, never in this repo):

```toml
id = "sc-masthead-size"              # must match the directory name
title = "Make the tagline the same size as the name"
origin = "client 2026-11-04: 'the tagline should be the same size'"   # the correction it encodes
prompt = "In index.html, make the tagline in the masthead the same size as the name. Change nothing else."
# prompt_file = "prompt.md"          # instead of prompt, for a long or multi-line brief
fixture = "site"                     # optional: a directory beside case.toml, copied into the workdir
budget_usd = 3                       # default 4; passed to --max-budget-usd
timeout_min = 15                     # default 25; the run is killed after this
# model = "opus"                     # optional; `run --model` overrides every case
# append_system_prompt_file = "extra.md"   # optional; its text goes to --append-system-prompt
# main_html = "out/index.html"       # optional; the page the contact sheet renders
# preamble = false                   # optional; leave the isolation preamble off this case

[[grader]]
type = "unchanged"
properties = ["--ink", "--paper"]
glob = "**/*.css"

[[grader]]
type = "dom-probe"
viewport = "1440x900"
expr = "(() => { const [a, b] = ['.pfor', '.sc'].map(s => getComputedStyle(document.querySelector(s)).fontSize); return a === b })()"

[[grader]]
type = "questions-max"
max = 0
```

Keep the TOML flat: strings, numbers, booleans and arrays, one `[[grader]]` table per grader,
no inline tables and no triple-quoted strings (Python 3.9 reads cases with the repo's small
TOML reader). Every grader takes an optional `name` for the report.

## The graders

Each returns `pass`, `fail` or `error` with a reason. **Fail** means the output or the
transcript broke the rule, including when the agent never made the file the grader needs.
**Error** means the grader could not look: Chromium missing, `brandpack` missing, no
transcript, a bad regex, a fixture without the file to compare. An error is never a pass.

| type | keys | passes when |
|---|---|---|
| `file-exists` | `glob`, `min` (1) | at least `min` files match |
| `text-present` | `glob`, `pattern`, `flags` (`i`, `m`, `s`) | the regex matches in some file |
| `text-absent` | `glob`, `pattern`, `flags` | no match in any file; no file at all is a fail, not a pass |
| `max-count` | `selector`, `max`, `file` | at most `max` elements match. A plain tag list (`h1, h2`) is counted in the source with the stdlib parser; any other selector is counted in Chromium after load |
| `lint-clean` | `glob`, `rules`, `md` | none of the named `ddr lint` rules fire (opt-in rules such as `em-dash` are switched on by naming them); no `rules` means no error-level finding |
| `brand-lint-clean` | `glob`, `brand` | `brandpack.lint` exits 0; its exit 2, or no `brandpack`, is an error |
| `unchanged` | `files`, `properties`, `glob` (`**/*.css`) | each listed fixture file is byte-identical afterwards, and each CSS custom property keeps exactly the values the fixture gave it |
| `dom-probe` | `expr`, `viewport` (`1440x900`), `file`, `motion` (`reduce`) | the JS expression, evaluated in Chromium on the page, returns `true` |
| `trace-order` | `before_tool`, `before_match`, `after_tool`, `after_match` | the first call matching the first pair comes before the first call matching the second. Tools are regexes over the tool name (`Write\|Edit`), matches are regexes over the JSON of the call's input. Either side missing is a fail |
| `trace-present` | `tool`, `match`, `min` (1) | at least `min` matching calls |
| `trace-absent` | `tool`, `match` | no matching call |
| `questions-max` | `max` | sentences or list lines ending in `?` in the assistant's text before its first Write or Edit are at most `max` |
| `cost-max` | `max_usd` | the result event's `total_cost_usd` is at most `max_usd`; no result event is an error |
| `isolation` | none | the init event lists exactly one design-director skill, `dd:design-director`, and no hook fired. Added to every case automatically |

`file` defaults to the first `*.html` in the workdir: anything under `out/` first, then
shallowest first, `index.html` first at equal depth. `file-exists`, `text-present`,
`text-absent`, `lint-clean` and `brand-lint-clean` also take `root = "ddr_home"`, which points
their glob at the run's private copy of `$DDR_HOME` instead of the workdir, so a case can
check what the agent recorded (a note, a domain log line, a taste event, a gate waiver). Globs never look inside `.git` or `node_modules`. The Chromium graders need
`npm install` in this repo and run `tools/eval_render.mjs`; pages load from file URLs with
reduced motion, so a probe reads the finished state. Widths under 700 emulate a phone (`isMobile`), so a page with no viewport meta lays out at 980px, exactly as it would on a real phone: that is a real defect, and a probe will see it.

The trace ideas (order of tool calls, questions before acting, cost) are ported and
simplified from LangChain's design-agent (Apache License 2.0),
`src/design_agent/evals/graders.py` and `trace.py`.

## Isolation from real data

Every prompt starts with this preamble unless the case sets `preamble = false` or the run is
given `--no-preamble`:

> This is an evaluation run in an isolated folder. The person who asked is not available: do not ask
> questions, decide and say what you decided. Do not write to the vault or the brain, do not
> commit, push, deploy or publish. Save every deliverable under ./out/.

Each run (one case, one arm) gets its own copy of the real `$DDR_HOME` at
`<case>/<arm>/ddr_home/`: `domains/`, `brands/`, `notes/` and `taste.jsonl`, without `evals/`
or any `shots/` folder. The child process gets `DDR_HOME` pointed at that copy, so
`ddr domain log`, `ddr notes ingest`, `ddr taste` and `ddr gate waive` write there and the copy
stays in the run folder for a grader or a person to read. This guards the `ddr` tools only.
An agent that writes to a real repository or `~/.design-director` by absolute path is stopped by the
preamble and the deny list, not by the copy.

## What a run looks like

```
$DDR_HOME/evals/runs/<run_id>/
  results.json            every run's status, cost, turns, minutes and grades, plus the arms' hashes
  report.md               per case and arm, then totals per arm
  <case>/sheet.png        after `ddr eval sheet`
  <case>/<arm>/workdir/   the fixture, then whatever the agent made (its own git repository)
  <case>/<arm>/plugin/    the frozen copy of the arm, wrapped as a plugin
  <case>/<arm>/ddr_home/  the run's private copy of $DDR_HOME, with whatever the agent recorded
  arms/<name>/            a git arm, archived at its commit
  <case>/<arm>/transcript.jsonl   stream-json, one event per line
  <case>/<arm>/stderr.txt
  <case>/<arm>/grades.json
```

The workdir is made its own git repository with the fixture committed, so a stray
`git commit` lands there and not in whatever repository holds `$DDR_HOME`.

The launch is, in this order:

```
$DDR_CLAUDE_BIN -p <prompt> --output-format stream-json --verbose --include-hook-events
  --max-budget-usd <budget_usd> --setting-sources local --plugin-dir <arm>/plugin
  --settings '{"claudeMdExcludes": ["~/.claude/CLAUDE.md", "**/CLAUDE.md", "**/CLAUDE.local.md", "**/AGENTS.md"], "autoMemoryEnabled": false}'
  --strict-mcp-config --no-session-persistence
  --tools Read,Write,Edit,Glob,Grep,Bash,Skill --allowedTools Read,Write,Edit,Glob,Grep,Bash,Skill
  [--model <model>] [--append-system-prompt <text>]
  --disallowedTools "Bash(git push:*)" "Bash(git commit:*)" "Bash(brain:*)" "Bash(vercel:*)" "Bash(wrangler:*)"
                    "Bash(railway:*)" "Bash(netlify:*)" "Bash(gh:*)" (and the npx forms) "mcp__*"
                    <mail and messaging MCP servers by name> WebFetch WebSearch
```

The child's environment is the caller's with `DDR_HOME` replaced by the run's copy. stdin is
`/dev/null`, the process gets its own process group, and on timeout the group gets
SIGTERM then SIGKILL. Permissions stay in the default mode; nothing uses bypassPermissions.
Set `DDR_CLAUDE_BIN` to the real binary (with the native installer, `~/.local/bin/claude`): a plain
`claude` on PATH may be a wrapper that adds hooks, and the `isolation` grader will then fail.

**Web access is off.** WebFetch and WebSearch are denied for cost and so the same case gives
comparable runs. A skill whose method depends on live research is graded without it.

## The isolation finding (2026-11-05, Claude Code 2.1.318)

The question: how does a headless run see exactly one given version of `design-director`,
and not the user-level one at `~/.claude/skills/design-director`? `--bare` is out, because it
skips Keychain reads and a subscription sign-in is held in the login Keychain.

Method: two test arms, each a `design-director` skill whose description starts with a unique
marker (`PROBEMARK-ALPHA-4417`, `PROBEMARK-BRAVO-9052`). Each probe asked Haiku to list its
skills, print the first line of the design-director description, print the kernel canary from
`~/.claude/CLAUDE.md` if present (without being told the value; `~/AGENTS.md` has a different
canary), and say which instruction files it could see. The stream-json init event and a
`--debug-file` log were read alongside the answers. Common flags on every probe:
`-p <question> --model haiku --strict-mcp-config --no-session-persistence --output-format
stream-json --verbose --include-hook-events --max-budget-usd 0.15` (or 0.2).

| # | binary | cwd | flags that differ | skills with design-director | user CLAUDE.md | hooks |
|---|---|---|---|---|---|---|
| 1 | `claude` (shell function, through a terminal's wrapper scripts) | `w1`, arm ALPHA at `w1/.claude/skills/design-director` | `--setting-sources project,local` | `design-director`, description `PROBEMARK-ALPHA-4417 ...` | quoted the canary when asked if it was there | 2 SessionStart, 2 UserPromptSubmit, 4 Stop |
| 2 | same | `w1` | same, plus `--debug-file`; canary not named in the question | ALPHA only; debug: `user: 0, project: 1` | printed the canary unprompted, the `~/.claude/CLAUDE.md` value | the debug log names them: the terminal's own hooks. No hook from `~/.claude/settings.json` ran |
| 3 | `~/.local/bin/claude` | `w2` (empty) | `--setting-sources project,local --plugin-dir plugB` (arm BRAVO) | `ddarm:design-director`, `PROBEMARK-BRAVO-9052 ...` | yes, the canary | none |
| 4 | real | `w2` | `--safe-mode --plugin-dir plugB` | none: safe mode drops the `--plugin-dir` skill too | no | none |
| 5 | real | `w2` | probe 3 plus `--settings '{"claudeMdExcludes": [...]}'` | `ddarm:design-director`, BRAVO | no canary, no instruction file listed | none |
| 6 | real | `w1` (holds the ALPHA project skill) | probe 5 with `--setting-sources local` | only `ddarm:design-director`, BRAVO; debug: `project: 0` | no | none |
| 7 | real | `w7` (empty) | probe 6 plus `--tools ... --allowedTools ... --disallowedTools "Bash(git push:*)" "Bash(vercel:*)" WebFetch WebSearch` and `"autoMemoryEnabled": false`, a real task (load the skill, write a file, run `ls`, try `git push`) | `ddarm:design-director` | (not asked) | none |

What each showed:

- `--setting-sources` without `user` keeps user skills (`user: 0` in the debug log), user
  plugins and the hooks in `~/.claude/settings.json` out. It does **not** keep
  `~/.claude/CLAUDE.md` out (probes 1 to 3). `claudeMdExcludes` passed through `--settings`
  does (probe 5).
- With `project` in the sources, project skills load from the cwd's `.claude/skills` and from
  the git main checkout (the debug log listed `~/Dev/design-director/.claude/skills` for a
  worktree cwd). Dropping `project` stops that (probe 6), which matters when `$DDR_HOME`
  sits inside a git repository.
- A plugin's skill is named `<plugin>:<skill>`. Every arm is wrapped as plugin `dd`, so the
  run sees `dd:design-director` whichever arm it is, and the arm name never reaches the model.
- The hooks in probes 1 and 2 came from the `claude` wrapper chain in that terminal, not
  from user settings. The real binary ran none (probes 3 to 7).
- Probe 7: the init event listed exactly the seven tools, `memory_paths` was absent
  (it was present in every earlier probe), the Skill call's input was
  `{"skill": "ddarm:design-director"}`, `git push` was refused with
  `Permission to use Bash with command git push has been denied.` and appeared in the result's
  `permission_denials`, and the run warned about stdin until it was given `/dev/null`.

The chosen configuration is probe 7's, with the plugin renamed `dd`.

Stream-json shape, as observed: one JSON object per line. `{"type": "system", "subtype":
"init"}` carries `skills`, `plugins`, `tools`, `mcp_servers`, `model`, `cwd`, `memory_paths`.
Hook events are `system` with `subtype` `hook_started` / `hook_response` and `hook_name`
(only with `--include-hook-events`). An `assistant` event's `message.content` holds `text`,
`thinking` and `tool_use` blocks (`id`, `name`, `input`; Write's input has `file_path` and
`content`, Bash's has `command` and `description`). A `user` event holds `tool_result` blocks
(`tool_use_id`, `content`, `is_error`). The last event is `{"type": "result"}` with `subtype`,
`is_error`, `total_cost_usd`, `num_turns`, `duration_ms`, `duration_api_ms`, `stop_reason`,
`permission_denials`, `usage` and `modelUsage`.

A second smoke run (`e2e2`) with the preamble, the extended deny list (`Bash(git commit:*)`,
`Bash(brain:*)`, `mcp__*`) and a third arm taken as `git:<this repo>@main:skills/design-director`
finished on all three arms with an empty stderr, `isolation` passing, the page written to
`out/index.html` and each run's `ddr_home` copy in place. That shows the CLI accepts those
deny entries; no run tried `git commit` or `brain`, so the denials themselves were only
observed for `git push` (probe 7).

Not verified: that `**/CLAUDE.md` excludes a CLAUDE.md inside the workdir itself (the probes
only had ancestors), that the `mcp__<server>` deny entries work (with `--strict-mcp-config` no
MCP server loads at all, which is the real guard), that a compound Bash command such as
`cd x && git push` is denied, and any of it on a CLI version other than 2.1.318. The bundled
skills (`design`, `dataviz`, `deep-research` and others) are still listed in every run; both
arms see the same ones.

## Costs

The seven probes cost $0.0132 together on Haiku (each $0.0015 to $0.0022, from the result
events). A smoke run through the harness itself (`e2e-tiny`: load the skill, write one page,
two arms, Haiku) cost $0.0028 for both arms; `isolation` passed on both and each arm's
marker appeared only in its own transcript. A real case
on Opus with a full design skill will cost dollars, not cents: `budget_usd` defaults to 4 and
is a ceiling, not an estimate. `--dry-run` prints the ceiling for the whole plan.

## What the harness cannot see

Taste. A run can pass every grader and still be generic, ugly or wrong for the brand. The
graders catch the regressions that can be counted: the edit that touched the palette, the
copy that drifted, the third question before any work, the deploy attempt, the skill that was
never loaded. Whether the page is good is a person's call, made from `ddr eval sheet`, which
renders each arm's main page at 1440x900 and 390x844 at the same scale, one row per arm.

It also cannot see work done outside the workdir, files written by Bash heredocs when a
grader reads the trace (`questions-max` stops at the first Write or Edit tool call), anything
the web would have changed, or more than one run per arm per case: a single run is one
sample, so a difference of one grader between arms on one case is not yet evidence.
