# Contributing

The point of this repo being public is that it gets better faster than any one
person's setup could. Three kinds of contribution are most useful.

## 1. A source for the catalogue

Add it with the tool, which validates as it writes:

```bash
python tools/ddr.py sources add --id refero --name Refero --url https://refero.design \
  --kind site --category product-ui --best-for "Searchable real-app screens and flows" \
  --cost freemium --agent-access mcp --signal 4 --evidence visited \
  --take "..." --avoid "..." --file community.toml
python tools/ddr.py sources render
```

The bar:

- **You visited it** (`--evidence visited`) or read its official docs (`docs`). Search
  results alone (`search`) are accepted only with signal 2 or lower.
- **Signal is honest.** 5 means it regularly changes real design decisions. Most
  sources are a 3. A dead or stale source is worth adding at 1 with an `avoid` line.
- **`take` and `avoid` are specific.** "Great inspiration" is not a take.
- **For code, MCP servers and skills:** the exact install command from the official
  docs, the licence, and anything that bites (SSR, bundle size, broad tokens).
- **No affiliate links, no self-promotion without saying so.**

## 2. A lesson

A rejection, a win or a process error that would help anyone, not just one client.
Export from your ledger with `python tools/ddr.py taste export`, trim it to the
lessons that generalise, and add a file to `lessons/` named `YYYY-MM-DD-short-name.md`.
Include before and after screenshots or values where you can. Lessons that keep
recurring become rules in the skills or checks in the linter.

## 3. A rule, a check or a tool

- A change to a skill must say what failure it prevents. "Make it better" is not a reason.
- Every tool change comes with a test that fails without it.
- Keep the tools standard-library Python (3.9+) plus the optional Node screenshot tool.

## Before you open a pull request

```bash
python -m unittest discover -s tests
python tools/ddr.py sources validate
python tools/check_routes.py
python tools/ddr.py sources render
python tools/ddr.py lint skills templates
```

## Review

Every change to `main` goes through a pull request and is reviewed by the maintainer
(see `.github/CODEOWNERS`). Forks are welcome to diverge: the taste in this repo is a
starting point, and your own `.design/taste.md` and ledger always outrank it.

## Writing style

British English, plain words, no em dashes, no marketing voice. Lead with the point.
