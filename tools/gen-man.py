#!/usr/bin/env python3
"""Generate docs/lpui.1 (roff man page) from the argparse parser.

Single source of truth stays in `src/lazyplan/cli_parser.py`; this script
renders every global flag and subcommand so `man lpui` never drifts.
Usage: python3 tools/gen-man.py [--check]  (--check diffs without writing)
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lazyplan.cli_parser import build_parser  # noqa: E402


def _version() -> str:
    text = (ROOT / "pyproject.toml").read_text()
    m = re.search(r'^version = "(.*)"$', text, re.M)
    if not m:
        raise RuntimeError("version not found in pyproject.toml")
    return m.group(1)


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("-", "\\-").replace(".", "\\.")


def _opt_invocation(a: argparse.Action) -> str:
    if isinstance(a, argparse._HelpAction):
        return "\\-h, \\-\\-help"
    parts = list(a.option_strings)
    inv = ", ".join(_esc(p) for p in parts)
    if isinstance(a, (argparse._StoreTrueAction, argparse._StoreFalseAction, argparse._CountAction)):
        return inv
    meta = ""
    if isinstance(a.metavar, str):
        meta = f" {a.metavar}"
    elif isinstance(a.metavar, (list, tuple)):
        meta = f" {'|'.join(str(m) for m in a.metavar)}"
    elif a.choices:
        meta = " {" + "|".join(str(c) for c in a.choices) + "}"
    elif a.type in (int, float):
        meta = " N"
    else:
        meta = " VALUE"
    return f"{inv}{_esc(meta)}"


def _opt_desc(a: argparse.Action) -> str:
    bits: list[str] = []
    if a.help:
        bits.append(a.help)
    if a.choices and not isinstance(a, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        bits.append(f"Choices: {', '.join(str(c) for c in a.choices)}.")
    # Skip env-dependent and already-documented defaults to keep `man` stable.
    help_has_default = bool(a.help and "default" in a.help.lower())
    if (
        a.dest != "actor"
        and not help_has_default
        and a.default not in (None, "", argparse.SUPPRESS)
        and not isinstance(a, (argparse._StoreTrueAction, argparse._StoreFalseAction))
    ):
        bits.append(f"Default: {a.default}.")
    if a.required:
        bits.append("Required.")
    return " ".join(bits) or "No description."


def render() -> str:
    parser = build_parser()
    version = _version()
    today = datetime.date.today().isoformat()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    names = list(sub.choices.keys())
    help_by_name = {a.dest: a.help for a in sub._choices_actions}

    out: list[str] = []
    out.append(f'.TH LPUI 1 "{today}" "lazyplan-tui {version}" "User Commands"')
    out.append(".SH NAME")
    out.append("lpui \\- local project journal for humans and coding agents")
    out.append(".SH SYNOPSIS")
    out.append(".B lpui")
    out.append("[\\fIGLOBAL OPTIONS\\fR] [\\fICOMMAND\\fR [\\fICOMMAND OPTIONS\\fR]]")
    out.append(".br")
    out.append(".B lazyplan")
    out.append("is the same program under its long name.")
    out.append(".br")
    out.append("With no COMMAND, \\fBlpui\\fR launches the Textual TUI (same as \\fBlpui ui\\fR).")
    out.append(".SH DESCRIPTION")
    out.append(
        "lazyplan tracks projects > stories > tasks in a per\\-repo SQLite database. "
        "A project is a title plus a priority, a why, a what, and acceptance "
        "criteria; stories cut it into slices and tasks cut stories into "
        "prioritized units of work. Humans drive the keyboard\\-first Textual TUI; "
        "coding agents drive the same database through this CLI with "
        "\\fB\\-\\-actor NAME\\fR and \\fB\\-\\-json\\fR. Every mutation appends a "
        "feed event; the running TUI polls and toasts arrivals."
    )
    out.append(".SH GLOBAL OPTIONS")
    for a in parser._actions:
        if a.dest in ("help", "cmd"):
            continue
        out.append(".TP")
        out.append(f".B {_opt_invocation(a)}")
        out.append(_esc(_opt_desc(a)))
    out.append(".SH COMMANDS")
    out.append(
        "Flags work before or after the verb: \\fBlpui list \\-\\-json\\fR == "
        "\\fBlpui \\-\\-json list\\fR. Run \\fBlpui COMMAND \\-\\-help\\fR for details."
    )
    for name in names:
        sp = sub.choices[name]
        out.append(".TP")
        out.append(f".B lpui {_esc(name)}")
        out.append(_esc(help_by_name.get(name) or sp.description or ""))
        for a in sp._actions:
            if a.dest in ("help",):
                continue
            if not a.option_strings and a.dest == "cmd":
                continue
            # Skip suppressed globals already documented; document real flags only.
            if a.default is argparse.SUPPRESS and not a.help:
                continue
            out.append(".RS")
            out.append(".TP")
            out.append(f".B {_opt_invocation(a)}")
            out.append(_esc(_opt_desc(a)))
            out.append(".RE")
    out.append(".SH EXAMPLES")
    out.append(".nf")
    for line in [
        "lpui                             # TUI (same as `lpui ui`)",
        "lpui list                        # ascii tree",
        "lpui list --status doing --priority p0",
        "lpui show --kind project --id 1",
        "lpui --actor alice add-project --title \\(dqAPI v2\\(dq --why \\(dq..\\(dq --priority p1",
        "lpui --actor alice add-criteria --kind project --id 1 --text \\(dqWorks offline\\(dq",
        "lpui --actor alice add-task --story 1 --title \\(dqFix bug\\(dq --priority p1",
        "lpui status --kind task --id 3 --to done",
        "lpui feed --limit 20",
        "lpui export --format json > backup.json",
        "lpui import --file backup.json",
    ]:
        out.append(line)
    out.append(".fi")
    out.append(".SH ENVIRONMENT")
    out.append(".TP")
    out.append(".B LAZYPLAN_DB")
    out.append("SQLite path override (same as \\fB\\-\\-db\\fR).")
    out.append(".TP")
    out.append(".B USER")
    out.append("Default for \\fB\\-\\-actor\\fR when not given.")
    out.append(".SH FILES")
    out.append(".TP")
    out.append(".B .lazyplan/lazyplan.db")
    out.append("Per\\-repo database (resolved via git rev\\-parse; commit it to share).")
    out.append(".TP")
    out.append(".B ~/.local/share/lazyplan/lazyplan.db")
    out.append("Global fallback when outside a repo.")
    out.append(".SH EXIT STATUS")
    out.append(".TP")
    out.append(".B 0")
    out.append("Success.")
    out.append(".TP")
    out.append(".B 1")
    out.append("Row not found (e.g. task #7 not found).")
    out.append(".TP")
    out.append(".B 2")
    out.append("Usage or validation error (argparse or error: ... on stderr).")
    out.append(".TP")
    out.append(".B 3")
    out.append("TUI unavailable (Textual not installed).")
    out.append(".SH SEE ALSO")
    out.append(".BR lazyplan (1),")
    out.append("lpui \\fB\\-\\-help\\fR, lpui \\fICOMMAND\\fR \\fB\\-\\-help\\fR, "
               "lpui \\fBhelp\\fR (TUI keys, same as ? in the TUI)")
    out.append("Full docs: https://github.com/fluxion-dev/lazyplan")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Render or check the man page."""
    check = argv is not None and "--check" in argv
    text = render()
    docs = ROOT / "docs"
    target = docs / "lpui.1"
    if check:
        current = target.read_text() if target.exists() else ""
        # Ignore the quoted date line: compare everything else.
        def _strip_date(s: str) -> str:
            return re.sub(r'^\.TH LPUI 1 ".*"$', ".TH", s, flags=re.M)

        if _strip_date(current) != _strip_date(text):
            print("docs/lpui.1 is stale: run `python3 tools/gen-man.py`", file=sys.stderr)
            return 1
        return 0
    docs.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    (docs / "lazyplan.1").write_text(".so lpui.1\n")
    print(f"wrote {target} (+ lazyplan.1 stub)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
