# Resize audit (P29 / M83)

Every TUI surface was mounted once and resized in place through 40×24, 80×24,
120×40, and 160×50 with `tests.support.resize`. The harness records each
surface's widget regions, virtual content size, source text width, selection,
cursor, and scroll offset at every size.

Reproduce one surface with:

```bash
PYTHONPATH=src python -m unittest tests.presentation.test_resize_surfaces
```

`tests.presentation.test_resize_surfaces` holds one matrix per surface group.
Cases marked `expectedFailure` record a defect until its fix task lands; the
decorator is removed with the fix, so a regression fails the suite.

## Findings

| Id | Surface | Size | Symptom | Fix |
| --- | --- | --- | --- | --- |
| R1 | every hub | 40×24 | `#hub-main` keeps the side-by-side split: list at x=2 and preview at x=38, so preview paints 36 cells past the last column | T460 |
| R2 | agents card | 40×24 | claim rows keep the width they were painted at (73 cells) and clip inside a 36-cell panel | T459 |
| R3 | timeline card | 120→160 | the chart frame redraws at the new width but the legend x positions and lane rows were computed for the old width | T459 |
| R4 | modal forms | height 24↔40 | `short` is set once in `on_mount`; resizing across 30 rows leaves it stale (`compact`/`wide` come from the app) | T462 |
| R5 | command palette | 40×24 | the title label keeps its auto width (50 cells) inside a 38-cell dialog and clips | T462 |
| R6 | export picker | 120→40 | the directory tree keeps the virtual width it had at the wider size, so the dialog reports 63 cells in a 38-cell box | T462 |

## Verified by the matrix (no fix needed)

| Surface | Case |
| --- | --- |
| main shell | tiers, card stacking, tree reflow, selection, preview scroll, git scroll, taskbar |
| plan queue / plan review | active and finished panels hide when empty and reflow with the tree |
| preview | Markdown re-wraps at every width, selection survives, scroll stays inside the new maximum |
| source | stacked below 100 columns, side-by-side above, cursor and diff page survive |
| plan diff | body re-wraps, page position stays valid |
| setup wizard | rail hides below 80 columns, rail/content split reflows, `compact`/`wide`/`short` stay current |
| help / release notes / health / update / confirm / filter / criterion | dialog fits and keeps focus at 40 and 160 columns |
| export picker size classes | the app keeps `compact`/`wide` current on the modal |

## Notes

- Emoji status width (P28) is not on this branch's base. Rows are measured with
  `rich.cells.cell_len`, the same measure the fallback uses, so a wide-glyph row
  is caught by the same matrix once P28 merges.
- A parent container deliberately contains its taskbar; only sibling regions
  are checked for overlap.
- Text wider than its widget with an enabled scrollbar is allowed; text wider
  than its widget with no way to reach it is a finding.
