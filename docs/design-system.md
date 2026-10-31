# lazyplan design system

Single source of truth: `src/lazyplan/design.py` for rows, glyphs, chips,
empty states, and CSS; `src/lazyplan/palette.py and help.py` for command names,
sections, context rules, key hints, and help text. If you add a view,
command, or message, add it there first. Research:
`docs/textual-research.md`. Local skills: `.agents/skills/tui-*`.

## Tokens

Visual: `BORDER = "solid green"`, one-row `#status` and `#hints`.
No `Header`, no `Footer`, no bottom input. Adaptive shell: `#main` holds
`#nav` (focused `FoldTree`) and `#preview` (`VerticalScroll` +
`Static#preview-body`) side by side at >= 100 columns; below that
`#main.narrow` hides the preview and the tree owns the width.
Status glyphs are single-cell: `○ todo`, `◐ doing`, `● done`, with ANSI
(CLI tty) and Rich (TUI) variants. In the TUI a doing row animates through
`◐ ◓ ◑ ◒` every 160ms. The CLI, export, preview, and detail screens keep the
static `◐`; `LAZYPLAN_NO_SPINNER=1` freezes the tree too. Row grammar:
`GLYPH KIND<id> title`, plus `done/total` progress on plan and milestone
rows. Titles are bold, ids and progress are dim, done rows are dim.
Long titles end in `…`; the full title lives in the preview/detail.
Plan and milestone rows show compact source counts (`2c · 1 PR · 1 stale`)
and repo chips; task rows show up to two short SHAs plus `+N`, a stale `!`,
and a PR chip. The preview expands those counts with the newest commit and
changed-file count. Titles keep priority over chips via width truncation.
Provenance stays in the chips; rows do not append a separate marker glyph.

Empty states come from `EMPTY_NO_PLANS` / `EMPTY_FEED` (same in CLI and
TUI).

## Shell (`tui/app.py`)

- `FoldTree` extends the shared `NavTree` (`tree_nav.py`) and posts
  `SelectionChanged` / `RowAction` (see `messages.py`); `NodeHighlighted`
  also tracks for compatibility. `NavTree` owns the unified gestures:
  `j`/`k` move, `left` collapses or walks to the parent, `right` expands or
  walks to the first child, and clicking a row arrow toggles it. Textual
  dispatches `_on_click` for every class in the MRO, so `FoldTree` must not
  call `super()._on_click` or an arrow click toggles twice. `update_preview()`
  renders a bounded card from `store.get_full`: title, progress, why/what,
  three next open tasks, acceptance progress, commit/PR/file counts, newest
  commit, repos, and `enter open · e edit`.
- Progressive disclosure: plans start collapsed. Right/`z` reveals
  milestones; tasks appear only when their milestone is expanded.
  `_expanded` is the source of truth; `_refreshing` suppresses the Tree's
  own expand/collapse events during rebuilds. Done plans are dimmed and
  sorted last.
- Reactive `rev` drives local refreshes; `_poll` handles external
  `fingerprint()` diffs plus a `feed` toast. A separate update timer polls
  the shared cache every 60s; one guarded worker calls `refresh_update`, and
  the shared gate limits network refreshes to once per 5 minutes.
- `#status` is human: `3 plans · 12 open · 1 doing`, active filters,
  the update chip, and a truncated last event. The chip clears when the
  installed version catches up, and each version toasts once. `#hints` is
  the current key bar from `commands.hint_bar()`.
- `_on_resize` re-applies the narrow/wide class and refreshes widths.
- Native Tree space/shift+space stay parked no-ops; direct keys own
  status, folding, and creation.

## Metrics dashboard (`tui/metrics/`)

- `#metrics` is a third always-on section inside `#panel`, below `#main`.
  It is 13 rows tall, holds three bordered cards in a `Horizontal` row,
  and hides below 100 columns; `_apply_layout` toggles `#metrics.narrow`
  with the same breakpoint as the preview.
- `MetricsSection` hosts `metric-heatmap` (Daily activity),
  `metric-progress` (Project progress), and `metric-status` (Task status).
  Every card has a one-row title, a `PlotextPlot`, and an explicit empty
  label that replaces the plot when there is no data.
- Charts use `textual-plotext` (`PlotextPlot`) with the app's auto theme
  and green bars. Plotext owns the axes, ticks, scaling, and resize
  behavior; cards only configure the data and refresh the widget.
- `refresh_all` builds one read-only `metrics.snapshot(store)` and calls
  `MetricsSection.refresh_snapshot`. `metrics.py` holds frozen dataclasses
  and chart-row helpers (`activity_weeks`, `milestone_bars`,
  `status_bars`); it never writes, caches, or calls the network.
- The Daily activity card sums the 84 local daily completions into 12
  weekly bars. It labels every few weeks and uses two integer y ticks.
  Counts come only from `task #N -> done` events, so a reopened task that
  finishes again counts again.
- The Project progress card is global: it rolls up every plan and does not
  follow tree focus. A headline shows done/total and a percentage, the top
  five milestones by newest task event (then open tasks, then id), elapsed
  time from the earliest add event, and an ETA. The ETA is
  `ceil(remaining / (completions in the last 14 days / 14))`; it reads
  `complete` when nothing remains and `—` when there is no velocity. The
  plot shows those five milestones as horizontal bars on a 0/50/100% axis.
  No estimates or invented timestamps are used.
- The Task status card shows `todo`, `doing`, `done`, and `blocked` as
  horizontal bars labelled with their share. Status shares use all tasks
  and sum to 100%. `blocked` is an overlay count from `Task.blocked`: a
  blocked task stays in its status row, so the four rows can add up to more
  than 100%. With no tasks the card shows its empty state.

## Command registry (`palette.py and help.py`)

`Command` carries id, label, section, canonical verb/nouns, direct key,
help key/hint, context, handler, and search aliases. The palette, keymap,
help screen, and `lpui help` all render from it.

### Palette

`PaletteScreen` renders four sections: Create, Edit, View, App. It filters
by label, id, verb, noun, and aliases; shows `N commands`; disables
commands that cannot run and appends the reason (`Select a row first`,
`Select a milestone first`); and scrolls inside a fixed-height `#dlg` so
every item is reachable at 80x24. `c` opens it; `Enter` runs the first
enabled match; `Esc` cancels. `_run_palette_command` dispatches through
the registry handler map.

### Help

`HELP_TEXT` is grouped as MOVE / CHANGE / FIND / APP and includes
`lpui help` as the same text at the shell. `?` and F1 open `HelpScreen`
inside a scrolling `#help` panel. `lpui help` prints the same string.

## Detail (`tui/screens/`)

`DetailScreen` is a plain `Screen` with two modes.
Read mode: breadcrumb (`P2 › M3 › T4`), title/status, why/what (or
details), acceptance checklist, child milestones/tasks with progress,
pull requests, source summary (repos, branch/dirty, commit/file/PR counts,
latest commits), commits, and repos. No editable widgets.
Edit mode (`e`): labeled Title/Why/What or Details fields, a multi-line
TextArea, Save/Cancel, `ctrl+s`, and a dirty guard that confirms before
discarding. Row actions: `s` status, `x` tick next criterion, `a` add
criterion, `g` source trail, `n` add child, `d` delete with an exact
cascade summary; `Esc` backs out. Delete focuses Cancel by default.

## Source screen (`source_screen.py`)

`SourceScreen` is a plain `Screen` opened by `g` from the tree or detail.
Its tree is the same `NavTree`, so `j`/`k`, `left`/`right`, click-select,
and click-arrow folding behave exactly like the main tree. It groups cached
provenance into repository → commit → changed file, with linked PRs under
the repo, and keeps a Static preview for the highlighted node. Rows rely on
their labels and counts; no marker glyph is appended. Highlighting a commit or
file reads a
bounded unified diff through `source.read_diff` (LRU keyed by repo, sha,
path) and renders file/hunk headers, old/new line numbers, and green/red
add/remove lines. Preview caps are `DIFF_PREVIEW_LINES` and
`DIFF_PREVIEW_FILES`, with `+N more` notices and `o` as the browser
fallback. Binary, root, merge, empty, missing, and non-git states render
explicit messages. `o` opens the selected commit/PR/file URL, `y` copies
the SHA/path/URL, `/` filters, `r` rebuilds and clears the diff cache, and
`Esc` returns. The model is built by `source.build_source_trail`; opening
the screen never calls the network, and live git reads are limited to
selected repos.

## Forms

`_Form(ModalScreen)` is the shared base: Esc cancels, a starting-value
snapshot detects real drafts, and a dirty cancel asks first. Every field
has a visible `Label`; required inputs are validated inline. `#dlg` is
90% wide (max 72) so forms fit 80x24. Button rows use `.btn-row` with
3-row buttons (height 1 clips the label in Textual 8.2.8).

## Keymap

Canonical table in `palette.py and help.py` as `KEYMAP`; `HELP_TEXT` mirrors it and
tests enforce the match.

| Key | Action | Surface |
| --- | ------ | ------- |
| j/k, up/down, click | move cursor / select | tree, source |
| left/right, click arrow | fold / unfold | tree, source |
| enter, double-click | open detail | tree |
| n | create by context | tree |
| e | edit selection | tree, detail |
| s | advance status | tree, detail |
| x | tick next criterion | tree, detail |
| a | add criterion | tree, detail |
| d | delete selection | tree, detail |
| / | filter by text | tree |
| f | change status filter | tree |
| F | cycle source filter | tree |
| g | open source trail | tree, detail |
| A | show/hide completed plans | tree |
| z / Z | fold one / fold all | tree |
| ? / F1 | help | tree |
| c | command palette | tree |
| q | quit | tree |
| esc | back / cancel / clear filter | all |
| o | open selected source item | source |
| y | copy selected SHA/path/URL | source |
| / | filter source tree | source |
| r | rebuild source trail | source |

## Reusable bases

- `_Form(ModalScreen)`: Esc cancel, dirty snapshot, centered `#dlg`.
- `_row(*buttons) -> Horizontal` (`.btn-row`): every action row.
- `FilterPromptScreen(title, placeholder, submit_label)`: one-line prompts
  used by tree filter and add-criterion.
- `ConfirmScreen(text, confirm_label, variant)`: one destructive confirm,
  Cancel focused by default.
- `UpdateScreen(installed, latest, info)`: one staged download with Download,
  Later, a retryable error, and method-specific guard text; `U` opens it.

## Site navigation

The marketing site keeps a compact primary bar. Desktop (768px and up) shows
the logo, Features, Screenshots, FAQ, Docs, and one Install button; mobile shows
the logo and a Menu disclosure with the same destinations.

- **Desktop:** Features, Screenshots, FAQ, Docs, Install.
- **Mobile:** the same links inside one Menu panel.

Use native `<details>`/`<summary>` for the mobile panel so it works without
JavaScript. A small enhancement closes it on outside click and Escape, returns
focus to the summary, keeps `aria-expanded` in sync, and closes after a link is
chosen. The panel scrolls inside `calc(100vh - 4rem)`.

The page is a marketing landing only: hero, four benefits, five screenshots,
three start steps, install, five FAQs, and a closing CTA. Keep the bar one row
at 64px or less, preserve 24px targets, and verify 360/768/1024/1440/1920
widths plus Lighthouse accessibility.
