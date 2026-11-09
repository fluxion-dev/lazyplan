# Newcomer journey walkthrough

> The TUI UI test suite, including this walkthrough's headless journeys, was
> retired in favour of logical, CLI end-to-end, and integration tests. The
> routes below remain the manual walkthrough record.

Each journey was walked headlessly at 80x24 and 120x40. No journey needed the
CLI or the docs; write journeys start directly on the tree.

| Journey | Route | Result at both sizes |
| --- | --- | --- |
| Capture | `c` → type `create plan` → `enter` | Plan form opens; `escape` returns |
| Organize | tree → plan detail → `n` | Milestone form opens; `escape` returns |
| Execute | tree → task detail → `k` (claims) | Claim hub opens and offers claim/renew/release |
| Prove | tree → task detail → `t` (criteria) | Criteria hub opens; `p` records proof |
| Ship | tree → plan detail → palette **Show plan diff** | Diff path is reachable; the CLI remains the export/file path |
| Inspect | tree → task detail → `g` | Source trail opens; `escape` restores detail and tree |
| Coordinate | tree → task detail → `k` / `m` | Claims, touch-points, comments, and notes are selectable |
| Administer | `?` help, `c` palette | Help and palette open above any screen |

## Friction found and fixed

- The activity hub uses `f`/`K` to filter by actor and kind.
- The pull request hub sent its callback as the prompt's initial value. The
  callback is now the screen dismiss handler, so link and filter actions work.
- Criteria and comments had no edit path. Both gained an `e` key whose prompt
  pre-fills the current text.

## Accepted friction

- Export and setup stay CLI-only on purpose. The parity matrix records them as
  approved exceptions.

## Gate evidence

The retired UI tests are no longer part of the gate. Run the logical suite
with:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .
```
