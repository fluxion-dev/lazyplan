# Newcomer journey walkthrough

Each journey was walked headlessly at 80x24 and 120x40 with
`tests/tui/test_newcomer_journeys.py`. No journey needed the CLI or the docs.
The screen is read-only by default, so write journeys begin by pressing `O`
(or the palette's **Toggle manual override**); that gate is intentional, not
friction to remove.

| Journey | Route | Result at both sizes |
| --- | --- | --- |
| Capture | `O` → `c` → type `create plan` → `enter` | Plan form opens; `escape` returns |
| Organize | tree → plan detail → `n` | Milestone form opens; `escape` returns |
| Execute | tree → task detail → `k` (claims) | Claim hub opens and offers claim/renew/release |
| Prove | tree → task detail → `t` (criteria) | Criteria hub opens; `p` records proof |
| Ship | tree → plan detail → palette **Show plan diff** | Diff path is reachable; the CLI remains the export/file path |
| Inspect | tree → task detail → `g` | Source trail opens; `escape` restores detail and tree |
| Coordinate | tree → task detail → `k` / `m` | Claims, touch-points, comments, and notes are selectable |
| Administer | `?` help, `c` palette | Help and palette open above any screen |

## Friction found and fixed

- The activity hub first reused the generic `u` filter for overrides and added
  a second `u` binding. The subclass binding was removed; the generic filter
  now toggles overrides, and `f`/`K` filter by actor and kind.
- The pull request hub sent its callback as the prompt's initial value. The
  callback is now the screen dismiss handler, so link and filter actions work.
- Criteria and comments had no edit path. Both gained an `e` key whose prompt
  pre-fills the current text.

## Accepted friction

- Write actions require override mode. This is the product's read-only safety
  gate, not a navigation defect; the palette shows the same gate.
- Export and setup stay CLI-only on purpose. The parity matrix records them as
  approved exceptions.

## Gate evidence

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.tui.test_newcomer_journeys \
  tests.tui.test_ux_viewports -v
```
