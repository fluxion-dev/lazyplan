"""Drive the real setup wizard through a pseudo-terminal."""

import os
import pty
import subprocess
import tempfile
import unittest
from pathlib import Path

from home_sandbox import sandbox_env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LPUI = ROOT / ".venv" / "bin" / "lpui"


def run_pty(argv: list[str], inputs: list[str], env: dict[str, str], cwd: Path) -> tuple[int, str]:
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        argv,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        close_fds=True,
        cwd=cwd,
    )
    os.close(slave)
    for line in inputs:
        os.write(master, line.encode())
    chunks: list[bytes] = []
    while True:
        try:
            data = os.read(master, 4096)
        except OSError:
            break
        if not data:
            break
        chunks.append(data)
    proc.wait(timeout=30)
    os.close(master)
    return proc.returncode, b"".join(chunks).decode(errors="replace")


@unittest.skipUnless(LPUI.is_file(), "venv lpui entry point missing")
class TestSetupWizard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        repo = Path(self.tmp.name) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", repo], check=True)
        self.repo = repo
        self.env = dict(os.environ)
        sandbox_env(self.env, str(self.home))
        self.env.pop("LAZYPLAN_DB", None)
        self.env.pop("LAZYPLAN_NO_SETUP", None)
        self.env["TERM"] = "xterm-256color"
        self.env["NO_COLOR"] = ""
        self.env.pop("NO_COLOR", None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_wizard_creates_home_database_and_skill_with_color(self):
        code, text = run_pty(
            [str(LPUI), "setup"],
            ["1\n", "\n", "y\n"],
            self.env,
            self.repo,
        )
        self.assertEqual(code, 0, text)
        self.assertIn("lazyplan setup", text)
        self.assertIn("\x1b[36m", text)
        self.assertIn("plugins", text)
        self.assertIn("lazyplan.js", text)
        self.assertTrue((self.home / ".lazyplan/lazyplan.db").is_file())
        self.assertTrue((self.home / ".lazyplan/setup.json").is_file())
        self.assertIn("Setup complete", text)

    def test_interrupt_writes_nothing(self):
        code, text = run_pty([str(LPUI), "setup"], ["\x04"], self.env, self.repo)
        self.assertEqual(code, 0, text)
        self.assertIn("cancelled", text.lower())
        self.assertFalse((self.home / ".lazyplan/lazyplan.db").exists())
        self.assertFalse((self.home / ".lazyplan/setup.json").exists())

    def test_no_skills_flag_wins_in_the_wizard(self):
        code, text = run_pty(
            [str(LPUI), "setup", "--no-skills"],
            ["\n", "\n", "y\n"],
            self.env,
            self.repo,
        )
        self.assertEqual(code, 0, text)
        self.assertFalse((self.home / ".agents/skills/lazyplan/SKILL.md").exists())
        self.assertFalse((self.home / ".config/opencode/skills/lazyplan/SKILL.md").exists())

    def test_placement_flag_seeds_the_wizard(self):
        code, text = run_pty(
            [str(LPUI), "setup", "--placement", "repo"],
            ["\n", "\n", "y\n"],
            self.env,
            self.repo,
        )
        self.assertEqual(code, 0, text)
        self.assertTrue((self.repo / ".agents/lazyplan/lazyplan.db").is_file())
        self.assertFalse((self.home / ".lazyplan/lazyplan.db").exists())

    def test_no_hooks_flag_hides_plugins_and_installs_none(self):
        code, text = run_pty(
            [str(LPUI), "setup", "--no-hooks"],
            ["\n", "\n", "y\n"],
            self.env,
            self.repo,
        )
        self.assertEqual(code, 0, text)
        self.assertNotIn("lazyplan.js", text)
        self.assertFalse((self.home / ".config/opencode/plugins/lazyplan.js").exists())


if __name__ == "__main__":
    unittest.main()
