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
Each finding below started as an `expectedFailure` case; the decorator was
removed with its fix, so a regression now fails the suite.

## Findings

| Id | Surface | Size | Symptom | Fix |
| --- | --- | --- | --- | --- |
| R1 | every hub | 40×24 | `#hub-main` keeps the side-by-side split: list at x=2 and preview at x=38, so preview paints 36 cells past the last column | T460, fixed |
| R2 | agents card | 40×24 | claim rows keep the width they were painted at (73 cells) and clip inside a 36-cell panel | T459, fixed |
| R3 | timeline card | 120→160 | the chart frame redraws at the new width but the legend x positions and lane rows were computed for the old width | T459, fixed |
| R4 | modal forms | height 24↔40 | `short` is set once in `on_mount`; resizing across 30 rows leaves it stale (`compact`/`wide` come from the app) | T462, fixed |
| R5 | command palette | 40×24 | the title label keeps its auto width (50 cells) inside a 38-cell dialog and clips | T462, fixed |
| R6 | export picker | 40×24 | the long export title keeps its auto width, so the dialog reports 65 cells in a 38-cell box | T462, fixed |
| R7 | source | any→any | resizing re-rendered the diff with `reset_page`, sending a paged diff back to its first page | T461, fixed |

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

## Matrix results

`tests.presentation.test_resize_surfaces` is the recorded run: every surface
group below walks 40×24, 80×24, 120×40, and 160×50 from one mount.

| Surface group | 40×24 | 80×24 | 120×40 | 160×50 |
| --- | --- | --- | --- | --- |
| shell, plan queue/review, agents, git, preview, timeline, taskbar | pass | pass | pass | pass |
| criteria, evidence, questions, references, claims, comments, PRs, activity, maintenance hubs | pass | pass | pass | pass |
| source (stacked below 100 columns) | pass | pass | pass | pass |
| plan diff | pass | pass | pass | pass |
| setup wizard (rail hidden below 80 columns) | pass | pass | pass | pass |
| plan, milestone, task, criterion, confirm, filter, help, palette, update, health, notes, export | pass | pass | pass | pass |

Repeat runs: `python tools/repeat-tests.py --times 3 --seed 0` was clean
before the size-class refactor, and `python tools/repeat-tests.py --times 2
--seed 7` is clean on the final tip.

## Notes

- Emoji status width (P28) is not on this branch's base. Rows are measured with
  `rich.cells.cell_len`, the same measure the fallback uses, so a wide-glyph row
  is caught by the same matrix once P28 merges.
- A parent container deliberately contains its taskbar; only sibling regions
  are checked for overlap.
- Text wider than its widget with an enabled scrollbar is allowed; text wider
  than its widget with no way to reach it is a finding.
