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

`tui/theme/tokens.py` defines `DARK_TOKENS` (Catppuccin Mocha),
`LIGHT_TOKENS` (Latte), and `VOID_TOKENS` (OLED black); `tui/theme/themes.py`
registers `lazyplan-dark`, `lazyplan-void`, and `lazyplan-light`. `t` cycles
them in that order and the metrics chart redraws after the CSS. `LAZYPLAN_THEME`
accepts `mocha`/`dark`, `void`/`oled`, and `latte`/`light`; anything else falls
back to mocha. All three themes carry the same semantic keys:

`lp-surface`, `lp-surface-alt`, `lp-surface-raised`, `lp-surface-overlay`,
`lp-border`, `lp-border-muted`, `lp-border-focus`, `lp-text-muted`,
`lp-text-faint`, `lp-accent`, `lp-accent-muted`, `lp-focus`, `lp-cursor`,
`lp-modal-bg`, `lp-overlay`, `lp-status-todo`, `lp-status-doing`,
`lp-status-done`, `lp-status-blocked`, `lp-chip-bg`, `lp-chip-fg`,
`lp-git-clean`, `lp-git-dirty`, `lp-chart-bar`, `lp-chart-axis`,
`lp-chart-label`, `lp-chart-lane-*`, `lp-diff-add`, `lp-diff-remove`.

Use these as `$lp-*` variables in CSS. Do not put hex, `rgb()`, or named
colours in `.tcss`; add the semantic key to every theme first. The same rule
applies to chart configuration once the metrics band is themed.

## CSS modules

`tui/app.py` loads `tui/css/app.tcss` (shell regions and breakpoints),
`components.tcss` (cards and action rows), and `screens.tcss` (dialogs,
detail, source). Put a new selector in the narrowest module that owns it, and
add `.tcss` files to `[tool.setuptools.package-data]` so installed wheels keep
them.

## Row language and icons

Status glyphs are single-cell: `○ todo`, `◐ doing`, `● done`, with ANSI
(CLI tty) and Rich (TUI) variants. In the TUI a doing row animates through
`◐ ◓ ◑ ◒` every 160ms. The CLI, export, preview, and detail screens keep the
static `◐`; `LAZYPLAN_NO_SPINNER=1` freezes the tree too. Row grammar:
`GLYPH KIND<id> title`, followed by a fixed stats grid. The title is the only
flexible cell; it is bold and truncates with `…`. Ids and stats are dim, and
done rows are dim. The full title lives in the preview/detail.

A second icon family labels structure without competing with the status
glyph: `◈` plan, `◇` milestone, `▹` task, `⎇` git/checkout, `◆` commit,
`⇄` pull request, `⌁` source, `◎` why, `▸` next, `✓` acceptance, and `✎`
notes. `design/tokens.py` owns `KIND_ICON`, `SECTION_ICON`, and `STATE_ICON`;
views and screens read them instead of spelling glyphs locally. Rows keep the
canonical grammar; the structural icons live in preview headings, breadcrumbs,
the GIT pane, and the source trail.

The stats grid uses fixed-width slots. Source stats come first: `progress`
(plan and milestone), `commits` (`2c`), `pulls` (`1PR`, `PR`, `PR!`, `PR…`),
and `stale` (`1!`). State markers follow: `blocked` (`⚑ blocked`), `claim`
(`◉ @actor`), and `marked` (`✓`). Missing stats reserve blanks, so the block
start and right edge do not move when a row changes state. A one-space gap
separates visible slots, and the whole block is right-aligned.

| slot | full | compact |
|---|---|---|
| progress | 11 | 8 |
| commits | 4 | 4 |
| pulls | 4 | 4 |
| stale | 2 | 2 |
| blocked | 9 | 2 |
| claim | 12 | 8 |
| marked | 2 | 2 |

At narrow widths the renderer uses compact forms (`▰▰▱ 3/7`, `⚑`, `◉ @a…`) and
drops provenance slots first, then the larger state slots, while keeping
progress and PR longest. Task rows show a commit count (`2c`) instead of SHAs.
Plan rows no longer show repo chips; the preview keeps aggregate counts and the
GIT pane lists the linked checkouts, newest commits, changed-file counts, and
pull requests. Rows reserve a fixed trailing mark slot, so marking a row never
shifts the stats.

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
  widgets. `widgets/preview_panel.py` renders that document with a sticky
  header above a scrolling body.
- `views/git.py` builds the pure GIT document; `widgets/git_panel.py` renders
  it under the preview. `controllers/git_state.py` supplies the cached
  branch/dirty snapshot.
- `widgets/plan_tree.py` is the `FoldTree`; `tree.py` keeps the event
  handlers and delegates behaviour to the tree controller.
- `theme/` owns the mocha, void, and latte themes and semantic `lp-*` tokens;
  `css/` owns the shell, component, and screen stylesheets.
- Data flows down through controllers and state; intents flow up as
  `SelectionChanged` / `RowAction` messages. Local writes bump `rev`; external
  writes arrive through the fingerprint poll.

## Shell (`tui/app.py`)

Visual: one-row `#hints` command bar. No `Header`, no `Footer`, no status
bar, no bottom input. Each main section is a rounded card with a left-aligned
lowercase title label: `plans`, `preview`, `git`, and `timeline`. The focused
pane gets the accent border. Adaptive shell: `#main` holds `#nav` (focused
`FoldTree`) and a `#side` column. `#side` stacks the preview above the GIT
pane. At >= 100 columns the tree takes 45% and the side column 55%; below
that `#main.narrow` hides the whole side column and the tree owns the width.
The tree rows keep their canonical labels; the side column is the reading
surface.

Three layout tiers share one breakpoint:
- compact (< 80): `#nav` drops its border and minimum width, `#main` loses its
  gutter, and `#hints` loses a padding cell.
- standard (80–99): the narrow shell hides preview, GIT, and timeline; tree
  rows own the width.
- wide (>= 120): `#main.wide` adds more preview/GIT padding. The 100-column
  visibility breakpoint stays the single responsive rule; only crossing it
  rebuilds the tree.

The preview's `PreviewDocument` supplies a status pill, breadcrumb, meta
counts, section headings, acceptance `○` rows, next tasks, and provenance
counts. `PreviewPanel` fixes the header while the body scrolls. `GitDocument`
supplies checkout state, commits, PRs, and a border subtitle with counts.
The GIT pane's height follows its content between 3 and 10 rows, so an empty
selection gives the room back to the preview. `#tree` uses Rich `Text` row
labels; the component classes draw muted guides, a raised cursor, and an
accent cursor when the tree has focus.

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

- `#metrics` is the third always-on section inside `#panel`, below `#main`.
  It takes 40% of the shell height with an 11-row minimum and a 16-row
  maximum, carries a `timeline` border title and the scoped plan name as its
  border subtitle, and hides below 100 columns; `_apply_layout` toggles
  `#metrics.narrow` with the same breakpoint as the side column.
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
  selected task. Each lane keeps its wall-clock `start`/`end` and its `active`
  doing intervals. Project, milestone, and task lanes set `trace` to the
  `active` intervals, so a pause leaves a gap and resumed work starts a new
  segment. A lane that never entered doing keeps its `add` start and legend
  entry but has an empty trace.
- `tui/metrics/timeline_layout.py` holds the pure helpers: adaptive
  `axis_ticks`, one-row `lane_window` spacing, `legend_layout` wrapping and
  overflow, kind `trace_glyph`s (`═` project, `─` milestone, `·` task; bold
  `╍`/`━`/`●`), shared `active_segments`/`trace_segments` clipping, and
  `trace_points` density for bold traces. `TimelineCard` stays a thin
  renderer.
- Every lane draws a dim full-width baseline from the chart's left x-limit to
  its right x-limit using `lane_baseline_rgb`; doing segments draw on top.
  Selection is data-driven: `TimelineLane.selected` marks only the cursor row,
  and `TimelineCard` renders its segments with ANSI bold and the heavy glyph.
  The selected legend entry is bold and has no `*` suffix. The baseline is
  identical for selected and unselected lanes.
- The horizontal legend sits at the chart top, truncates titles with an
  ellipsis, and folds overflow into `+N more`. Every segment gets start and
  finish dots; any open lane gets a dim vertical `now` marker. No estimates or
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
Read mode: a rounded `detail` card with a sticky title/status/breadcrumb
header and a sectioned body. `views/detail.py` builds a `DetailDocument`
containing the title, status pill, why/what (or details), acceptance
checklist, child milestones/tasks with progress, pull requests, and one
merged `git · source` block with each checkout's branch/dirty state, commits
(short SHA, subject, file count, URL, stale marker), and the `g source trail`
entry point. No editable widgets.
Edit mode (`e`): a labeled Title/Why/What or Details form with visible
field labels, a multi-line TextArea, a footer action row, `ctrl+s`, and a
dirty guard that confirms before discarding. Row actions: `s` status,
`x` tick next criterion, `a` add criterion, `g` source trail, `n` add
child, `d` delete with an exact cascade summary; `Esc` backs out. Delete
focuses Cancel by default.

## Source screen (`tui/screens/source.py`)

`SourceScreen` is a plain `Screen` opened by `g` from the tree or detail.
It is a rounded `source` card with `trail` and `diff` pane titles. Rows carry
one kind icon: `⎇` repository, `◆` commit, `▪` file, `⇄` pull request.
Its tree is the same `NavTree`, so `j`/`k`, `left`/`right`, click-select,
and click-arrow folding behave exactly like the main tree. It groups cached
provenance into repository → commit → changed file, with linked PRs under
the repo, and keeps a Static preview for the highlighted node. Row labels,
preview bodies, and diff rendering live in `views/source.py`; the screen
only builds the tree data and handles actions. Rows carry a kind icon and
their counts. Highlighting a commit or file
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
| t | cycle theme (mocha / void / latte) | tree |
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
