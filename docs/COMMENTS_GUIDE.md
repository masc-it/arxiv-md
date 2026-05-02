# Comments Guide

Senior rule: comment why, not what.

Code says what. Tests say expected. Comments say why code cannot be simpler.

## Keep comments only when they earn rent

Good comments explain:

- technical detail caller/user must know
- reason code cannot be simpler
- non-obvious constraint
- tradeoff
- external contract
- footgun
- failure mode
- compatibility requirement
- security boundary
- performance reason
- link between behavior and spec/test/bug
- public API semantics

Bad comments:

- repeat code
- explain syntax
- narrate steps
- describe obvious control flow
- cite stale tickets with no context
- say “temporary” with no expiry/removal condition
- preserve refactor history that git already stores
- name specific implementation libraries
- expose implementation technical details caller does not need

## Examples

Bad:

```py
# Increment counter
count += 1
```

Good:

```py
# arXiv mirror pages can repeat IDs; count unique PDFs only.
count += 1
```

Bad:

```py
# Loop through files and parse each one.
for path in paths:
    parse(path)
```

Good:

```py
# Preserve input order: downstream snapshot names depend on first-seen order.
for path in paths:
    parse(path)
```

Bad docstring:

```py
def parse_tex(text: str) -> Document:
    """Parse TeX text and return Document."""
```

Good docstring:

```py
def parse_tex(text: str) -> Document:
    """Best-effort parse: malformed groups emit diagnostics, not exceptions."""
```

## Before adding comment

Ask:

1. Could clearer name remove it?
2. Could smaller function remove it?
3. Could test name cover it?
4. Does it explain reason, contract, or failure mode?
5. Does it avoid specific implementation library names?
6. When reason disappears, will comment be deleted?

If answer is no, delete comment.

## Docstrings

Use docstrings for public or semi-public API contracts.

Good docstrings specify:

- behavior caller depends on
- error/diagnostic behavior
- units, limits, side effects
- ordering/stability guarantees
- compatibility promises

Skip docstrings that only restate signature, name implementation libraries, or describe internals callers do not need.

## Principle

Avoid implementation technical details unless caller/user must know them or they explain why code cannot be simpler.

Never reference specific implementation libraries in comments or docstrings. Describe capability or contract instead.

Senior comments sparse, sharp, tied to risk.
