# Working title

Asked by: who, in their words, and when. Needed by: a date, or no date.

Write it in your own words. Leave a field out rather than writing "n/a", and mark anything
you inferred rather than were told with "(inferred)".

## The piece

- Goal: what someone should do or believe after seeing it.
- Audience and place: who sees it first, and where (a phone in a feed, a laptop at work, a deck on stage).
- One message: one sentence a stranger could repeat. If it needs two, it is two pieces.
- Proof: what on screen makes the message true (the real product, a number with its source, a before and after).

## Deliverables

| File | Size | Format | Notes |
| --- | --- | --- | --- |
| name | width x height, or length | html, png, pdf | channel, variant of |

## Must include

- Copy that ships verbatim: also add each line with `ddr contract add --kind copy --exact "..."`.
- Marks and assets: which logo, which supplied files.
- Must not: anything the ask rules out.

## Look

- Brand pack: the slug in `.design/brand`, read with `ddr brand show <slug>`.
- Ground and mood: from the brand pack, or the reference.
- Reference: the path, and whether it is preserved (a restyle) or a direction (an inspiration).

## Precedence

When two sources disagree, the higher one wins:

1. The person's explicit ask for this piece.
2. A supplied reference.
3. The brand pack.
4. Standing taste (the taste ledger and house rules).
5. Skill defaults.

## Decisions made

- Each call a person might not expect, with one line of why.

## Open

- Anything still missing, and what was done instead.

## Ledgers

- Requirements: `.design/brief/contract.json` (`ddr contract init`, then `ddr contract check --phase plan`).
- Claims: `.design/brief/claims.json`, every number and product claim with its source and check (`ddr claims add`).
