"""Skill-installer tests: `lpui init` wizard paths stay non-interactive-safe."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import skills
from lazyplan.cli import main as lpui_main
from lazyplan.cli_parser import build_parser


def _answers(items):
    it = iter(items)
    return lambda: next(it)


# Every `lpui` example taught by the templates, as parser argv (ids substituted).
# If a template gains an example, add its argv here — this is the drift guard.
TEMPLATE_EXAMPLE_ARGV = [
    ["list", "--status", "todo", "--project", "1", "--owner", "a1"],
    ["show", "--kind", "project", "--id", "1"],
    ["show", "--kind", "story", "--id", "1"],
    ["show", "--kind", "task", "--id", "1"],
    ["gantt", "--tasks", "--width", "40"],
    ["feed", "--limit", "20"],
    ["export", "--format", "json"],
    ["list", "--json"],
    ["--json", "list"],
    ["--actor", "opencode", "add-task", "--story", "1", "--title", "Do X"],
    ["add-task", "--story", "1", "--title", "Do X", "--actor", "opencode"],
    [
        "--actor",
        "opencode",
        "add-task",
        "--story",
        "1",
        "--title",
        "Do X",
        "--desc",
        "ctx",
        "--owner",
        "me",
        "--priority",
        "p1",
        "--estimate",
        "2d",
    ],
    ["--actor", "opencode", "add-story", "--project", "1", "--title", "F"],
    [
        "--actor",
        "opencode",
        "add-project",
        "--name",
        "API v2",
        "--goal",
        "g",
        "--metrics",
        "m",
        "--scope-in",
        "i",
        "--scope-out",
        "o",
    ],
    ["--actor", "opencode", "status", "--kind", "task", "--id", "1", "--to", "doing"],
    ["--actor", "opencode", "status", "--kind", "task", "--id", "1", "--to", "done"],
    ["--actor", "opencode", "status", "--kind", "project", "--id", "1", "--to", "doing"],
    ["--actor", "opencode", "update", "--kind", "task", "--id", "1", "--title", "N"],
    ["--actor", "opencode", "update", "--kind", "story", "--id", "1", "--priority", "none"],
    ["--actor", "opencode", "delete", "--kind", "task", "--id", "1"],
    ["--actor", "opencode", "delete", "--kind", "story", "--id", "1"],
    ["--actor", "opencode", "delete", "--kind", "project", "--id", "1"],
    ["--actor", "opencode", "add-criteria", "--kind", "task", "--id", "1", "--text", "T"],
    ["criteria", "--kind", "task", "--id", "1"],
    ["check", "--id", "1"],
    ["uncheck", "--id", "1"],
    ["--actor", "opencode", "delete-criteria", "--id", "1"],
    ["--actor", "opencode", "add-link", "--kind", "task", "--id", "1", "--url", "https://x"],
    ["links", "--kind", "task", "--id", "1"],
    ["--actor", "opencode", "delete-link", "--id", "1"],
    ["--actor", "opencode", "add-risk", "--project", "1", "--title", "Slip"],
    ["risks", "--project", "1"],
    ["--actor", "opencode", "risk-status", "--id", "1", "--to", "mitigated"],
    ["--actor", "opencode", "add-milestone", "--project", "1", "--title", "Beta"],
    ["milestones", "--project", "1"],
    ["--actor", "opencode", "delete-milestone", "--id", "1"],
    ["--actor", "opencode", "import", "--file", "dump.json"],
    ["info"],
    ["--actor", "opencode", "propose", "--kind", "task", "--parent", "1", "--title", "R"],
    ["--actor", "opencode", "propose", "--kind", "story", "--parent", "1", "--title", "R"],
    ["--actor", "opencode", "ask", "--question", "Which scope?"],
    ["questions", "--all"],
    ["proposals", "--status", "pending"],
]

# Canonical fragments that must appear verbatim in the rendered skill.
# Ties the argv table above to the actual template text.
TEMPLATE_FRAGMENTS = [
    "--actor",
    "--json",
    "lpui list",
    "lpui show --kind project|story|task --id N",
    "lpui gantt [--tasks] [--width 40]",
    "lpui feed --limit 20",
    "lpui export --format json",
    "lpui info",
    "add-project --name",
    "add-story --project P",
    "add-task --story S",
    "status --kind task --id T --to doing|done",
    "update --kind task --id T",
    "delete --kind task --id T",
    "add-criteria --kind task --id T",
    "criteria --kind task --id T",
    "lpui check --id C / lpui uncheck --id C",
    "delete-criteria --id C",
    "add-link --kind task --id T --url URL",
    "links --kind task --id T",
    "delete-link --id L",
    "add-risk --project P --title",
    "risks --project P",
    "risk-status --id R --to mitigated",
    "add-milestone --project P --title",
    "milestones --project P",
    "delete-milestone --id M",
    "import --file dump.json",
    "propose --kind task --parent S",
    "ask --question",
    "questions --all",
    "proposals --status pending",
]


class TestTemplateParity(unittest.TestCase):
    """Templates must teach only real `lpui` invocations (best-practice drift guard)."""

    def test_every_template_example_parses(self):
        parser = build_parser()
        for argv in TEMPLATE_EXAMPLE_ARGV:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)  # raises SystemExit on unknown flags
                self.assertTrue(args.cmd)

    def test_fragments_appear_in_rendered_skill(self):
        text = skills.render_skill()
        for frag in TEMPLATE_FRAGMENTS:
            with self.subTest(frag=frag):
                self.assertIn(frag, text)

    def test_frontmatter_honest(self):
        text = skills.render_skill()
        self.assertIn("name: lazyplan", text)
        self.assertIn("description:", text)
        self.assertTrue(text.startswith("---\n"))
        # License claim must match the repo: LICENSE exists, so MIT is honest.
        self.assertIn("license: MIT", text.split("---", 2)[1])
        self.assertTrue((Path(__file__).parent.parent / "LICENSE").is_file())

    def test_human_only_verbs_flagged(self):
        text = skills.render_skill()
        for verb in ("approve", "reject", "answer"):
            self.assertIn(verb, text)
        self.assertIn("belong to the human", text)

    def test_snippet_teaches_nothing_the_skill_does_not(self):
        import re

        body, snippet = skills.SKILL_BODY, skills.AGENTS_SNIPPET
        for verb in set(re.findall(r"`lpui ([a-z-]+)", snippet)):
            with self.subTest(verb=verb):
                self.assertIn(verb, body)
        expected_path = f"{skills.AGENTS_DIR}/{skills.SKILLS_DIR}/{skills.SKILL_NAME}/SKILL.md"
        self.assertIn(expected_path, snippet)

    def test_all_skill_copies_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "proj"
            (repo / ".git").mkdir(parents=True)
            home = Path(tmp) / "home"
            home.mkdir()
            skills.install("both", repo, home, with_claude_copy=True, with_agents_md=False)
            copies = [
                repo / ".agents" / "skills" / "lazyplan" / "SKILL.md",
                home / ".agents" / "skills" / "lazyplan" / "SKILL.md",
                repo / ".claude" / "skills" / "lazyplan" / "SKILL.md",
                home / ".claude" / "skills" / "lazyplan" / "SKILL.md",
            ]
            for dest in copies:
                with self.subTest(dest=str(dest)):
                    self.assertTrue(dest.is_file())
                    self.assertEqual(dest.read_text(), skills.render_skill())


class TestSkillContent(unittest.TestCase):
    def test_frontmatter_required_fields(self):
        text = skills.render_skill()
        self.assertIn("name: lazyplan", text)
        self.assertIn("description:", text)
        self.assertTrue(text.startswith("---\n"))

    def test_detect_agents_reports_known_hosts(self):
        with tempfile.TemporaryDirectory() as home:
            hosts = skills.detect_agents(Path(home))
        keys = {h.key for h in hosts}
        self.assertTrue({"opencode", "claude", "codex", "gemini"}.issubset(keys))

    def test_default_scope(self):
        self.assertEqual(skills.default_scope(Path("/repo")), "project")
        self.assertEqual(skills.default_scope(None), "global")


class TestInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "proj"
        (self.repo / ".git").mkdir(parents=True)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_project_install_writes_skill_and_agents_md(self):
        res = skills.install("project", self.repo, self.home)
        skill = self.repo / ".agents" / "skills" / "lazyplan" / "SKILL.md"
        self.assertTrue(skill.is_file())
        self.assertIn("lazyplan", skill.read_text())
        self.assertIsNotNone(res.updated_agents_md)
        self.assertTrue((self.repo / "AGENTS.md").is_file())
        self.assertIn("lazyplan", (self.repo / "AGENTS.md").read_text())
        self.assertIsNone(res.skipped)

    def test_global_install_stays_out_of_repo(self):
        res = skills.install("global", self.repo, self.home)
        self.assertTrue((self.home / ".agents" / "skills" / "lazyplan" / "SKILL.md").is_file())
        self.assertFalse((self.repo / ".agents").exists())
        self.assertIsNone(res.updated_agents_md)
        self.assertIsNone(res.skipped)

    def test_none_skips(self):
        res = skills.install("none", self.repo, self.home)
        self.assertEqual(res.skipped, "user skipped skill setup")
        self.assertEqual(res.installed, [])

    def test_reinstall_is_idempotent(self):
        skills.install("project", self.repo, self.home)
        res = skills.install("project", self.repo, self.home)
        self.assertTrue(all("up-to-date" in line for line in res.installed))
        # AGENTS.md not duplicated
        text = (self.repo / "AGENTS.md").read_text()
        self.assertEqual(text.count(skills.AGENTS_MARK_BEGIN), 1)

    def test_agents_md_preserves_existing_content(self):
        (self.repo / "AGENTS.md").write_text("# Mine\n\nCustom rules.\n")
        skills.install("project", self.repo, self.home)
        text = (self.repo / "AGENTS.md").read_text()
        self.assertIn("Custom rules.", text)
        self.assertIn("lazyplan", text)


class TestWizard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "proj"
        (self.repo / ".git").mkdir(parents=True)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_wizard_skip(self):
        err = io.StringIO()
        res = skills.run_wizard(self.repo, self.home, read=_answers(["4"]), write=err)
        self.assertEqual(res.scope, "none")
        self.assertFalse((self.repo / ".agents").exists())

    def test_wizard_project_with_agents_md_yes(self):
        err = io.StringIO()
        res = skills.run_wizard(self.repo, self.home, read=_answers(["1", "Y"]), write=err)
        self.assertEqual(res.scope, "project")
        self.assertTrue((self.repo / ".agents" / "skills" / "lazyplan" / "SKILL.md").is_file())
        self.assertTrue((self.repo / "AGENTS.md").is_file())

    def test_wizard_eof_defaults_to_skip_or_default(self):
        err = io.StringIO()

        def _eof():
            raise EOFError

        res = skills.run_wizard(self.repo, self.home, read=_eof, write=err)
        # EOF takes defaults: project scope, AGENTS.md yes
        self.assertEqual(res.scope, "project")
        self.assertTrue((self.repo / ".agents" / "skills" / "lazyplan" / "SKILL.md").is_file())


class TestInitCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "myproj")
        os.makedirs(os.path.join(self.repo, ".git"))
        self.old_cwd = os.getcwd()
        self.old_env = os.environ.pop("LAZYPLAN_DB", None)
        self.old_xdg = os.environ.get("XDG_DATA_HOME")
        self.old_noskills = os.environ.get("LAZYPLAN_NO_SKILLS")
        os.environ["XDG_DATA_HOME"] = os.path.join(self.tmp.name, "xdg")
        os.environ.pop("LAZYPLAN_NO_SKILLS", None)
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = os.path.join(self.tmp.name, "home")
        os.makedirs(os.environ["HOME"], exist_ok=True)

    def tearDown(self):
        os.chdir(self.old_cwd)
        if self.old_env is not None:
            os.environ["LAZYPLAN_DB"] = self.old_env
        if self.old_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.old_xdg
        if self.old_noskills is None:
            os.environ.pop("LAZYPLAN_NO_SKILLS", None)
        else:
            os.environ["LAZYPLAN_NO_SKILLS"] = self.old_noskills
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def _init_json(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(lpui_main(argv), 0)
        return json.loads(buf.getvalue())

    def test_init_no_skills_flag(self):
        os.chdir(self.repo)
        payload = self._init_json(["init", "--no-skills"])
        self.assertEqual(payload["skills"]["scope"], "none")
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".agents")))

    def test_init_scope_project_writes_files(self):
        os.chdir(self.repo)
        payload = self._init_json(["init", "--skills-scope", "project"])
        self.assertEqual(payload["skills"]["scope"], "project")
        self.assertTrue(
            os.path.isfile(os.path.join(self.repo, ".agents", "skills", "lazyplan", "SKILL.md"))
        )
        self.assertTrue(any("SKILL.md" in line for line in payload["skills"]["installed"]))

    def test_init_json_stays_machine_readable(self):
        # --json must not prompt even on a tty: stdout parses as JSON.
        os.chdir(self.repo)
        payload = self._init_json(["init", "--json"])
        self.assertIn("db", payload)
        self.assertIn("skills", payload)

    def test_init_yes_installs_defaults(self):
        os.chdir(self.repo)
        payload = self._init_json(["init", "--yes"])
        self.assertEqual(payload["skills"]["scope"], "project")


if __name__ == "__main__":
    unittest.main()
