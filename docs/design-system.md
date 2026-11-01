# lazyplan design system

Single source of truth: `src/lazyplan/design/` for rows, glyphs, chips,
empty states, and messages; `src/lazyplan/tui/theme/` for colour tokens and
Textual themes; `src/lazyplan/tui/css/` for layout and component CSS;
`src/lazyplan/palette.py` and `help.py` for command names, sections, context
rules, key hints, and help text. If you add a view, command, or message, add
it to the narrowest module first. Research: `docs/textual-research.md`.
Local skills: `.agents/skills/tui-*`.

## Tokens

`design/tokens.py` keeps non-colour tokens: `INDENT`, the setup-wizard `ANSI`
codes, and `ICONS` / `ASCII_ICONS`. `design/text.py` owns status glyphs,
truncation, progress text, and provenance chips; `design/rows.py` owns the
canonical labels and Rich rows; `design/empty.py` owns empty states and
standard messages. `design/__init__.py` is the stable façade, so callers keep
using `from lazyplan.design import plan_row`.

## Themes and colour tokens

`tui/theme/tokens.py` defines `DARK_TOKENS` and `LIGHT_TOKENS`;
`tui/theme/themes.py` registers `lazyplan-dark` and `lazyplan-light`.
`LAZYPLAN_THEME=light` (or `lazyplan-light`) selects the light theme; any
other value falls back to dark. Both themes carry the same semantic keys:

`lp-surface`, `lp-surface-alt`, `lp-surface-raised`, `lp-border`,
`lp-border-muted`, `lp-text-muted`, `lp-text-faint`, `lp-accent`,
`lp-accent-muted`, `lp-focus`, `lp-status-todo`, `lp-status-doing`,
`lp-status-done`, `lp-status-blocked`, `lp-chip-bg`, `lp-chip-fg`,
`lp-chart-bar`, `lp-chart-axis`, `lp-chart-label`, `lp-diff-add`,
`lp-diff-remove`.

Use these as `$lp-*` variables in CSS. Do not put hex, `rgb()`, or named
colours in `.tcss`; add the semantic key to both themes first. The same rule
applies to chart configuration once the metrics band is themed.

## CSS modules

`tui/app.py` loads `tui/css/app.tcss` (shell regions and breakpoints),
`components.tcss` (cards and action rows), and `screens.tcss` (dialogs,
detail, source). Put a new selector in the narrowest module that owns it, and
add `.tcss` files to `[tool.setuptools.package-data]` so installed wheels keep
them.

## Row language

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

## TUI module map

- `app.py` is the shell: composition, global bindings, layout, lifecycle, and
  wiring. It is kept under 250 lines.
- `state.py` holds `AppState` (selection, filters, marks, folds, preview key,
  and transient flags). `base.py` exposes it through properties and defines
  the small `TuiHost` contract used by the mixins.
- `controllers/tree.py` owns tree loading, filtering, folds, selection
  restoration, source counts, and row building.
- `controllers/updates.py` owns the update timer, cache read, chip, and toast.
- `controllers/spinner.py` owns frame timing and doing-row repaint.
- `controllers/git_state.py` owns the preview's git probe and TTL cache.
- `views/preview.py` returns a structured `PreviewDocument`; it never touches
  widgets. `widgets/preview_panel.py` renders that document inside
  `#preview-body`.
- `widgets/plan_tree.py` is the `FoldTree`; `tree.py` keeps the event
  handlers and delegates behaviour to the tree controller.
- `theme/` owns the dark and light themes and semantic `lp-*` tokens; `css/`
  owns the shell, component, and screen stylesheets.
- Data flows down through controllers and state; intents flow up as
  `SelectionChanged` / `RowAction` messages. Local writes bump `rev`; external
  writes arrive through the fingerprint poll.

## Shell (`tui/app.py`)

Visual: one-row `#hints` command bar. No `Header`, no `Footer`, no status
bar, no bottom input. Each main section is a rounded card
with a left-aligned title label, following Posting's pane treatment: `#nav`
is `PLANS`, `#preview` is `PREVIEW`, and `#metrics` is `METRICS`. The focused
pane gets the accent border. Adaptive shell: `#main` holds `#nav` (focused
`FoldTree`) and `#preview` (`PreviewPanel`) side by side at >= 100 columns;
below that `#main.narrow` hides the preview and the tree owns the width.
Above the breakpoint the tree takes 35% of the width and the preview 65%.

Three layout tiers share one breakpoint:
- compact (< 80): `#nav` drops its border, loses its minimum width, and
  `#hints` loses its padding.
- standard (80–99): the narrow shell hides preview and metrics; tree rows
  own the width.
- wide (>= 120): `#main.wide` adds more preview padding. The 100-column
  visibility breakpoint stays the single responsive rule; only crossing it
  rebuilds the tree.

The preview's `PreviewDocument` supplies a status pill, breadcrumb, section
headings, acceptance `○` rows, next tasks, provenance, and a key legend. `#tree` uses
Rich `Text` row labels; the component classes draw a muted guide, a raised
cursor, and an accent cursor when the tree has focus.

- `FoldTree` (`widgets/plan_tree.py`) extends the shared `NavTree`
  (`tree_nav.py`) and posts `SelectionChanged` / `RowAction` (see
  `messages.py`); `NodeHighlighted` also tracks for compatibility. `NavTree`
  owns the unified gestures: `j`/`k` move, `left` collapses or walks to the
  parent, `right` expands or walks to the first child, and clicking a row
  arrow toggles it. Textual dispatches `_on_click` for every class in the
  MRO, so `FoldTree` must not call `super()._on_click` or an arrow click
  toggles twice. `PreviewMixin.update_preview()` asks
  `views/preview.py` for a `PreviewDocument` and hands it to
  `PreviewPanel`.
- Progressive disclosure: plans start collapsed. Right/`z` reveals
  milestones; tasks appear only when their milestone is expanded.
  `AppState.expanded` is the source of truth; `AppState.refreshing`
  suppresses the Tree's own expand/collapse events during rebuilds. Done
  plans are dimmed and sorted last.
- Reactive `rev` drives local refreshes; `TreeController.poll()` handles
  external `fingerprint()` diffs plus a `feed` toast. `UpdateController`
  polls the shared cache every 60s; one guarded worker calls
  `refresh_update`, and the shared gate limits network refreshes to once per
  5 minutes.
- `#hints` is the command bar and the only bottom row. `help.hint_bar()`
  builds it with reverse-video keycaps and a width-based drop order. Counts,
  active filters, marks, and update notices are not shown in a persistent
  bar; actions report through toasts, and each new version toasts once.
- `_on_resize` re-applies the compact/narrow/wide classes and refreshes
  widths when the 100-column breakpoint changes.
- Native Tree space/shift+space stay parked no-ops; direct keys own
  status, folding, and creation.

## Metrics dashboard (`tui/metrics/`)

- `#metrics` is a third always-on section inside `#panel`, below `#main`.
  It takes 45% of the shell height with a 14-row minimum, has no border
  title, and hides below 100 columns; `_apply_layout` toggles
  `#metrics.narrow` with the same breakpoint as the preview.
- `MetricsSection` hosts `metric-timeline` (Project timeline), which spans
  the full `#metric-cards` row. The card is a `VerticalScroll` around a
  `PlotextPlot`; the plot grows with the lane count and scrolls when lanes
  outgrow the panel. Empty copy, the legend, markers, and traces are all drawn
  by Plotext, so no secondary widget or border competes with the chart.
- Charts use `textual-plotext` (`PlotextPlot`) through
  `theme/charts.py`: `apply_chart_theme` sets canvas, axes, and tick colours
  from the active theme, and `chart_color` maps the bar token to `green+`
  in dark and `green` in light. `lane_color` and `lane_rgb` cycle the
  `lp-chart-lane-*` theme tokens for timeline lanes. The card module contains
  no literal chart colours. Plotext owns the axes, ticks, scaling, and resize
  behavior; the card only configures the data and refreshes the widget.
- `MetricsController` owns a 120 ms selection debounce and a 15-second now
  tick. `TreeController.track` requests a refresh on cursor changes, and
  `refresh_all` refreshes immediately after restoring the selection. The
  controller resolves the selected row's parent plan through `_plan_ctx`,
  passes the selected kind/id as the timeline scope, and builds one read-only
  `metrics.snapshot(store, plan_id=..., scope_kind=..., scope_id=...)` for
  `MetricsSection.refresh_snapshot`. The now tick is silent, skips modal
  screens, and stops on unmount. Tree filters, the plan limit, and space-marks
  never change the scope.
- `metrics.py` holds frozen dataclasses and chart-row helpers
  (`activity_weeks`, `milestone_bars`, `status_bars`); it never writes,
  caches, or calls the network. A snapshot carries its `plan_id`,
  `plan_title`, and a `timeline`, and `plan_id=None` keeps the all-plans view.
- The timeline is selection-scoped: a plan, milestone, or task row scopes it
  to that row's parent plan, and no selection gives every plan a lane. A
  scoped plan gets a project lane plus one lane per milestone; a milestone or
  task selection adds the focused milestone's task lanes and marks the
  selected task. Each lane keeps its wall-clock `start`/`end`, while `active`
  holds only the `doing` intervals parsed from status events. Todo, paused,
  and done gaps therefore draw no trace, but the lane and its legend entry
  remain. Resumed work renders multiple segments.
- `tui/metrics/timeline_layout.py` holds the pure helpers: adaptive
  `axis_ticks`, one-row `lane_window` spacing, `legend_layout` wrapping and
  overflow, kind `trace_glyph`s (`═` project, `─` milestone, `·` task), and
  `active_segments` clipping. `TimelineCard` stays a thin renderer.
- The horizontal legend sits at the chart top, truncates titles with an
  ellipsis, and folds overflow into `+N more`. Active segments get start and
  finish dots; open work gets a dim vertical `now` marker. No estimates or
  invented timestamps are used.

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
Read mode: a rounded `DETAIL` card with a breadcrumb/status header and a
sectioned body. `views/detail.py` builds a `DetailDocument` containing the
title, status pill, why/what (or details), acceptance checklist, child
milestones/tasks with progress, pull requests, source summary (repos,
branch/dirty, commit/file/PR counts, latest commits), commits, and repos.
No editable widgets.
Edit mode (`e`): a labeled Title/Why/What or Details form with visible
field labels, a multi-line TextArea, a footer action row, `ctrl+s`, and a
dirty guard that confirms before discarding. Row actions: `s` status,
`x` tick next criterion, `a` add criterion, `g` source trail, `n` add
child, `d` delete with an exact cascade summary; `Esc` backs out. Delete
focuses Cancel by default.

## Source screen (`tui/screens/source.py`)

`SourceScreen` is a plain `Screen` opened by `g` from the tree or detail.
It is a rounded `SOURCE` card with `TRAIL` and `DETAIL` pane titles.
Its tree is the same `NavTree`, so `j`/`k`, `left`/`right`, click-select,
and click-arrow folding behave exactly like the main tree. It groups cached
provenance into repository → commit → changed file, with linked PRs under
the repo, and keeps a Static preview for the highlighted node. Row labels,
preview bodies, and diff rendering live in `views/source.py`; the screen
only builds the tree data and handles actions. Rows rely on their labels
and counts; no marker glyph is appended. Highlighting a commit or file
reads a bounded unified diff through `source.read_diff` (LRU keyed by repo,
sha, path) and renders file/hunk headers, old/new line numbers, and
green/red add/remove lines. Preview caps are `DIFF_PREVIEW_LINES` and
`DIFF_PREVIEW_FILES`, with `+N more` notices and `o` as the browser
fallback. Binary, root, merge, empty, missing, and non-git states render
explicit messages. `o` opens the selected commit/PR/file URL, `y` copies
the SHA/path/URL, `/` filters, `r` rebuilds and clears the diff cache, and
`Esc` returns. The model is built by `source.build_source_trail`; opening
the screen never calls the network, and live git reads are limited to
selected repos.

## Forms

`_Form(ModalScreen)` is the shared base: Esc cancels, a starting-value
snapshot detects real drafts, and a dirty cancel asks first. It also sets
the compact/wide screen classes and writes `dialog_title` into the `#dlg`
border title. `EntityForm` drives New plan, New milestone, and New task
from one `FormField` spec: heading, labeled fields, Input or TextArea, and a
compact Create/Cancel row. Every field has a visible label; required inputs
validate inline. `#dlg` is a rounded card at 90% width (max 72) so forms fit
80x24; compact screens use 96% and wide screens allow 84. Button rows use
`.btn-row` with 3-row buttons (height 1 clips the label in Textual 8.2.8).

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

- `_Form(ModalScreen)`: Esc cancel, dirty snapshot, centered `#dlg`, dialog title.
- `EntityForm(_Form)`: one field-spec-driven create form for all three entities.
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
