# lazyplan design system

Source: [UXPin — Design Consistency Guide](https://www.uxpin.com/studio/blog/guide-design-consistency-best-practices-ui-ux-designers/)
(mapped here from web UI to a terminal TUI + companion CLI).
Enforced in code by `src/lazyplan/design.py` — **add it there first** if you
add a view, command, label, empty state, or message.

## Python standards (pyguide-based, S#12 decisions)

- Line length **100**, enforced by `ruff format` (E501 ignored: the formatter,
  not the author, wraps code; Google-80 would reformat 200+ lines for no gain).
- Lint: `ruff check` with `E,F,I,UP,B,W` (+ isort first-party `lazyplan`).
- Types: `mypy` with `disallow_untyped_defs`, zero `type: ignore`;
  new ignores need a TODO/bug link (pyguide §2.21.4). Prefer `StrEnum`
  over `str, Enum` (honest `str()`); validate at boundaries so dataclass
  fields keep honest types (`list[str]`, not `list[str] | str`).
- Imports: absolute `from .x import` within the package (in-package
  relative — never bare); no unused imports; stdlib → third-party → first-party.
- Errors: raise `ValueError`/`KeyError` in store; CLI prints via
  `design.msg_error` / `msg_not_found`; TUI notifies via the same helpers.
  `except Exception` only as a documented isolation point, otherwise narrow.
- No mutable defaults, no `assert` for logic, no eval/exec (audited clean).
- Naming matches pyguide §3.16 as-is (argparse-builder temporaries and
  gantt math variables excepted as conventional).
- Reference: https://google.github.io/styleguide/pyguide.html — §2.1 lint,
  §2.2 imports, §2.4 exceptions, §2.5 globals, §2.21/§3.19 types,
  §3.8 docstrings, §3.16 naming.

## The commitment

Wherever you see `T#12 [doing] Title @agent-1`, it means the same thing in
`lpui list`, the TUI tree, JSON output, and the gantt tooltip. Wherever you type
`status --kind task --id 1 --to done` (shell or `:` bar), it does the same
thing. That predictability is the whole system.

## The four consistencies (UXPin) → lazyplan

| Type | Realization |
|---|---|
| Visual | Tokens in `design.py`: one border (`solid green`), one panel height, one-row bars, one plain label grammar, one TUI project row (`[reverse]` pill + title + `(due DATE)`), one date shape `(start..end)`, one owner shape `@name` |
| Functional | `lpui` verbs == TUI `:` verbs; one key does one thing in every view (`1/2/3` views, `space` cycles status, `enter` details) |
| Internal | CLI and TUI render from `design.*` helpers — no local format strings (`test_design.py` fails the build on drift) |
| External | Shell conventions: `--help`, `--json` before or after the verb, `--db`/`$LAZYPLAN_DB`/repo/global resolution, exit non-zero on error, `KEY=value` env overrides |

## User goals (research first)

Two users share one DB in tmux: a **human planner** (stream-of-consciousness
capture, keyboard-first, glanceable roadmap) and **coding agents** (inject work
via `lpui --actor NAME`, read context via `lpui show`/`--json`, never touch the TUI
process). Every design decision serves both: human-readable first,
machine-parseable always.

## Patterns (don't reinvent)

- nano/vi: always-visible footer hints, `/` focuses the command bar, `?` overlay, `q` quits
- Single panel, three views (`1` tree · `2` gantt · `3` feed) — never split panes
- Modal forms: title + inputs with examples + Create/Save + Cancel, `esc` backs out

## Hierarchy (what the eye hits, in order)

`Header` (app + clock) → `#panel` (tree/gantt/feed, exactly one visible) →
`#activity` (last agent/human event) → `#statusbar` (`[scope] P/S/T · filters · zoom · note`)
→ `#cmdbar` (`:` verbs) → `Footer` (keys). Secondary info (descriptions,
links, narrative) lives one `enter` away in the detail modal, never in the row.

## Components

- Rows: `KIND#id [status] !p0 title @owner (dates) ~estimate [done/total✓] [!blocked by ids]` (`design.*_label`)
- Status tokens: `todo` / `doing` / `done` — lowercase, everywhere, JSON included
- Forms: one `_Form` base; project/story/task create + edit + detail + help
- Feedback: toast on every external change, activity line shows latest event,
  every refresh carries a note, every mutation is a feed row

## Content rules

- Glossary (never synonyms): project > story > task; **owner** (responsible) vs
  **actor** (who acted); `doing`, not "in progress"
- Errors: `error: <what>` on stderr, exit 2; missing rows: `<kind> #<id> not found`, exit 1
- Empty states: `EMPTY_NO_PROJECTS` / `EMPTY_FILTERED` / `EMPTY_FEED` — same words in CLI and TUI
- Defaults: gantt width 40 (zoom 20–100), feed limit 20, poll 1s, empty dates sort as undated

## Communication rules

No silent state changes: a write always logs a feed event; a reload always
updates the activity line; destructive or surprising outcomes get a toast.
(`lpui delete` is immediate — no confirm — matching CLI norms; a TUI delete with
confirm is a tracked gap, S#2.)

## Adding something — checklist

1. Token/label/message/help in `design.py` (+ `HELP_TEXT` if it needs documenting)
2. CLI verb + TUI `:` verb with identical spelling and flags
3. Row/label reuse — no new format strings in `cli.py`/`tui.py`
4. Empty + error + not-found paths covered
5. `tests/test_design.py` parity case; pilot the keys headlessly
