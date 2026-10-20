# lazyplan design system

Source: [UXPin — Design Consistency Guide](https://www.uxpin.com/studio/blog/guide-design-consistency-best-practices-ui-ux-designers/)
(mapped here from web UI to a terminal TUI + companion CLI).
Enforced in code by `src/lazyplan/design.py` — **add it there first** if you
add a view, command, label, empty state, or message.

## Python standards (pyguide-based, M#12 decisions)

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
- Naming matches pyguide §3.16 as-is (argparse-builder temporaries excepted
  as conventional).
- Reference: https://google.github.io/styleguide/pyguide.html — §2.1 lint,
  §2.2 imports, §2.4 exceptions, §2.5 globals, §2.21/§3.19 types,
  §3.8 docstrings, §3.16 naming.

## The commitment

Wherever you see `🔵 T#12 Title`, it means the same thing in
`lpui list`, the TUI tree, and JSON output. Wherever you type
`status --kind task --id 1 --to done` (shell or `:` bar), it does the same
thing. That predictability is the whole system.

## The four consistencies (UXPin) → lazyplan

| Type | Realization |
|---|---|
| Visual | Tokens in `design.py`: one border (`solid green`), one panel height, one-row bars, one plain label grammar (`GLYPH KIND#id title`), one TUI plan row (`[reverse]` pill + title) |
| Functional | `lpui` verbs == TUI `:` verbs; one key does one thing (`space` cycles status, `enter` details) |
| Internal | CLI and TUI render from `design.*` helpers — no local format strings (`test_design.py` fails the build on drift) |
| External | Shell conventions: `--help`, `--json` before or after the verb, `--db`/`$LAZYPLAN_DB`/repo/global resolution, exit non-zero on error, `KEY=value` env overrides |

## User goals (research first)

Two users share one DB in tmux: a **human planner** (interviewed for each
plan's why/what/acceptance criteria, keyboard-first, glanceable tree) and
**coding agents** (cut prioritized milestones + tasks once the definition is
agreed, inject work via `lpui --actor NAME`, read context via `lpui show`/
`--json`, never touch the TUI process). Every design decision serves both:
human-readable first, machine-parseable always.

## The model (the whole thing)

Plan: title + priority (`p0`–`p3`) + why (`goal`) + what (`description`) +
acceptance criteria (plan-level checklist). Milestone: title + details +
priority. Task: title + details + priority. Every level: `todo` → `doing` →
`done`, and parents roll up automatically: all children done → done, any
child doing → doing, otherwise todo (childless rows keep manual status;
`lpui reconcile` recomputes everything). No dates, owners, labels, estimates, dependencies, links, risks, or
milestones — if it is not title/details/priority/status/why/what/criteria,
it does not exist. Per-repo `.agents/lazyplan/templates/{plan,milestone,task}.md`
files (scaffolded by `lpui init`) define creation defaults: `defaults` fill
empty flags, `required` enforces non-empty after fill (exit 2 naming the
field), `criteria` auto-adds rows on create; missing files mean legacy
defaults (tasks fall back to `p1`). `lpui init` walks through setup on a TTY
(four convention questions tailor the starters; silent runs use the
opinionated defaults), and reruns offer per-file keep/edit/reset — edits are
never overwritten without an explicit reset.

## Patterns (don't reinvent)

## Layers (import inward only)

Domain (`models.py`, `kinds.py`) ← data (`store.py`, `migrate.py`,
`repo.py`, `templates.py`) ← application (`services.py`, `skills.py`)
← presentation (`cli.py`, `cli_parser.py`, `tui.py`, `screens.py`, `render.py`,
`design.py`, `seed.py`, `vcs.py` helpers as used).

- Services own creation (with templates), status transitions, reconciliation,
  archival, and import/export. Store holds SQL plus row mapping only.
- Writes and policy go through services; reads and plain patch-writes may
  use Store directly (read-model bypass: no pass-through bloat).
- One kind vocabulary (`kinds.py`): tables, choices, labels, validators,
  error strings. Never retype a kind literal.
- Static budget: `vulture` clean outside `tools/vulture_allowlist.py`
  (framework dispatch + tested seams only), `xenon` no block worse than C.

- nano/vi: always-visible footer hints, `?` overlay, `q` quits
- Single panel, one view (tree) — never split panes, never extra views, no command entry
- Modal forms: title + inputs with examples + Create/Save + Cancel, `esc` backs out

## Hierarchy (what the eye hits, in order)

`Header` (app + clock) → `#panel` (tree) → `#activity` (last agent/human
event) → `#statusbar` (`[scope] P/M/T · Q:todo/doing/done · filters · note`) → `Footer` (keys). Secondary info (why/what, details, criteria) lives
one `enter` away in the detail modal, never in the row.

## Components

- Rows: `GLYPH KIND#id title` (`design.*_label`, GLYPH is
  ⬜/🔵/✅ for todo/doing/done, ANSI-colored on a tty, Rich-colored in the TUI)
- Status tokens: `todo` / `doing` / `done` — lowercase, everywhere, JSON included
- Forms: one `_Form` base; plan/milestone/task create + edit + detail + help
- Feedback: toast on every external change, activity line shows latest event,
  every refresh carries a note, every mutation is a feed row

## Content rules

- Glossary (never synonyms): plan > milestone > task; **why** (`goal`) vs
  **what** (`description`); **actor** (who acted); `doing`, not "in progress"
- Errors: `error: <what>` on stderr, exit 2; missing rows: `<kind> #<id> not found`, exit 1
- Empty states: `EMPTY_NO_PLANS` / `EMPTY_FILTERED` / `EMPTY_FEED` — same words in CLI and TUI
- Defaults: list and tree show everything; `--status` / `f` filter down,
  feed limit 20, poll 1s; priorities `p0` (highest) – `p3`

## Communication rules

No silent state changes: a write always logs a feed event; a reload always
updates the activity line; destructive or surprising outcomes get a toast.
(`lpui delete` is immediate — no confirm — matching CLI norms; a TUI delete with
confirm is a tracked gap, M#2.)

## Adding something — checklist

1. Token/label/message/help in `design.py` (+ `HELP_TEXT` if it needs documenting)
2. CLI verb + TUI `:` verb with identical spelling and flags
3. Row/label reuse — no new format strings in `cli.py`/`tui.py`
4. Empty + error + not-found paths covered
5. `tests/test_design.py` parity case; pilot the keys headlessly
