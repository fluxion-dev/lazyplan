"""Help + man page: `lpui --help` is comprehensive and `man lpui` ships."""

import argparse
import io
import os
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.cli_parser import build_parser

ROOT = Path(__file__).resolve().parent.parent


class TestComprehensiveHelp(unittest.TestCase):
    def test_top_help_covers_operator_basics(self):
        parser = build_parser()
        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as ctx:
                parser.parse_args(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        text = buf.getvalue()
        for needle in (
            "database",
            "examples:",
            "environment:",
            "files:",
            "exit codes",
            "man lpui",
            "lpui <command> --help",
        ):
            self.assertIn(needle, text.lower(), f"--help missing {needle!r}")

    def test_every_action_has_help(self):
        parser = build_parser()
        subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        self.assertTrue(len(subs.choices) >= 20, "expected 20+ subcommands")
        for name, sp in subs.choices.items():
            for a in sp._actions:
                if a.dest == "help":
                    continue
                if a.default is argparse.SUPPRESS and not a.help:
                    continue
                self.assertTrue(
                    bool(a.help and a.help.strip()),
                    f"lpui {name} {a.dest} is missing help=",
                )

    def test_every_subcommand_help_exits_zero(self):
        parser = build_parser()
        subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        for name in subs.choices:
            buf = io.StringIO()
            with redirect_stdout(buf):
                with self.assertRaises(SystemExit) as ctx:
                    parser.parse_args([name, "--help"])
            self.assertEqual(ctx.exception.code, 0, f"lpui {name} --help")
            self.assertTrue(buf.getvalue().strip(), f"lpui {name} --help is empty")

    def test_global_help_lists_commands(self):
        parser = build_parser()
        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit):
                parser.parse_args(["--help"])
        text = buf.getvalue()
        subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        for name in subs.choices:
            self.assertIn(name, text, f"--help missing command {name}")


class TestManPageInstalled(unittest.TestCase):
    def test_man_sources_exist(self):
        self.assertTrue((ROOT / "docs" / "lpui.1").is_file(), "docs/lpui.1 missing")
        self.assertTrue((ROOT / "docs" / "lazyplan.1").is_file(), "docs/lazyplan.1 missing")

    def test_man_covers_manual_sections(self):
        text = (ROOT / "docs" / "lpui.1").read_text(encoding="utf-8")
        plain = text.replace("\\-", "-")
        self.assertTrue(text.startswith(".TH LPUI 1"), "missing .TH header")
        for section in (
            ".SH NAME",
            ".SH SYNOPSIS",
            ".SH DESCRIPTION",
            ".SH GLOBAL OPTIONS",
            ".SH COMMANDS",
            ".SH EXAMPLES",
            ".SH ENVIRONMENT",
            ".SH FILES",
            ".SH EXIT STATUS",
            ".SH SEE ALSO",
        ):
            self.assertIn(section, text, f"man page missing {section}")
        # Version tracks pyproject.
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        version = re.search(r'^version = "(.*)"$', pyproject, re.M).group(1)  # type: ignore[union-attr]
        self.assertIn(version, text, "man page version drift")
        # Every CLI verb is documented.
        parser = build_parser()
        subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        for name in subs.choices:
            self.assertIn(f"lpui {name}", plain, f"man page missing command {name}")
        for env in ("LAZYPLAN_DB",):
            self.assertIn(env, text, f"man page missing {env}")

    def test_man_in_sync_with_parser(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("gen_man", ROOT / "tools" / "gen-man.py")
        assert spec is not None and spec.loader is not None
        gen_man = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen_man)
        current = (ROOT / "docs" / "lpui.1").read_text(encoding="utf-8")
        fresh = gen_man.render()

        def _strip_date(s: str) -> str:
            return re.sub(r'^\.TH LPUI 1 ".*"$', ".TH", s, flags=re.M)

        self.assertEqual(_strip_date(current), _strip_date(fresh), "run `python3 tools/gen-man.py`")

    def test_packaging_installs_man(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("share/man/man1", pyproject, "pyproject must install man pages")
        self.assertIn("docs/lpui.1", pyproject)
        self.assertIn("docs/lazyplan.1", pyproject)
        manifest = (
            (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
            if (ROOT / "MANIFEST.in").exists()
            else ""
        )
        self.assertIn("docs/lpui.1", manifest, "MANIFEST.in must ship the man page")

    def test_man_renders_without_warnings(self):
        import shutil
        import subprocess

        if shutil.which("man") is None:
            self.skipTest("man(1) not available")
        proc = subprocess.run(
            ["man", "--warnings", "-E", "UTF-8", "-l", "-Tutf8", str(ROOT / "docs" / "lpui.1")],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0 and "illegal option" in proc.stderr:
            self.skipTest("man(1) lacks GNU --warnings/-E/-T options")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr.strip(), "", f"man warnings: {proc.stderr}")
        self.assertIn("LPUI", proc.stdout)


if __name__ == "__main__":
    unittest.main()
