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
    ["list", "--status", "todo", "--project", "1", "--priority", "p0"],
    ["list", "--status", "all"],
    ["list", "--archived"],
    ["show", "--kind", "project", "--id", "1"],
    ["show", "--kind", "story", "--id", "1"],
    ["show", "--kind", "task", "--id", "1"],
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
        "--priority",
        "p1",
    ],
    ["--actor", "opencode", "add-story", "--project", "1", "--title", "F"],
    [
        "--actor",
        "opencode",
        "add-story",
        "--project",
        "1",
        "--title",
        "F",
        "--desc",
        "d",
        "--priority",
        "p0",
    ],
    [
        "--actor",
        "opencode",
        "add-project",
        "--title",
        "API v2",
        "--why",
        "w",
        "--what",
        "x",
        "--priority",
        "p1",
    ],
    ["--actor", "opencode", "status", "--kind", "task", "--id", "1", "--to", "doing"],
    ["--actor", "opencode", "status", "--kind", "task", "--id", "1", "--to", "done"],
    ["--actor", "opencode", "status", "--kind", "project", "--id", "1", "--to", "doing"],
    ["--actor", "opencode", "update", "--kind", "task", "--id", "1", "--title", "N"],
    ["--actor", "opencode", "update", "--kind", "task", "--id", "1", "--priority", "none"],
    [
        "--actor",
        "opencode",
        "update",
        "--kind",
        "project",
        "--id",
        "1",
        "--why",
        "w2",
        "--priority",
        "none",
    ],
    ["--actor", "opencode", "delete", "--kind", "task", "--id", "1"],
    ["--actor", "opencode", "delete", "--kind", "story", "--id", "1"],
    ["--actor", "opencode", "delete", "--kind", "project", "--id", "1"],
    ["--actor", "opencode", "add-criteria", "--kind", "project", "--id", "1", "--text", "T"],
    ["--actor", "opencode", "add-criteria", "--kind", "task", "--id", "1", "--text", "T"],
    ["criteria", "--kind", "project", "--id", "1"],
    ["criteria", "--kind", "task", "--id", "1"],
    ["check", "--id", "1"],
    ["uncheck", "--id", "1"],
    ["--actor", "opencode", "delete-criteria", "--id", "1"],
    ["--actor", "opencode", "import", "--file", "dump.json"],
    ["reconcile"],
    ["info"],
]

# Canonical fragments that must appear verbatim in the rendered skill.
# Ties the argv table above to the actual template text.
TEMPLATE_FRAGMENTS = [
    "--actor",
    "--json",
    "lpui list",
    "lpui show --kind project|story|task --id N",
    "lpui feed --limit 20",
    "lpui export --format json",
    "lpui info",
    "add-project --title",
    "add-story --project P",
    "add-task --story S",
    "status --kind task --id T --to doing|done",
    "update --kind task --id T",
    "update --kind project --id P",
    "delete --kind task --id T",
    "add-criteria --kind project --id P",
    "criteria --kind project --id P",
    "lpui check --id C / lpui uncheck --id C",
    "delete-criteria --id C",
    "import --file dump.json",
    "lpui reconcile",
    "recompute parent statuses from children",
    "roll parents up automatically",
    "in-scope and out-of-scope",
    "scout the codebase",
    "Scout the codebase during the interview",
    "As a [persona], I want [action] so that [benefit]",
    "Given [context], when [action], then [outcome]",
    "independent, negotiable, valuable, estimable, small",
    "Task titles start with a verb",
    "definition of done",
    "Cut tasks only from scouted ground",
    "whether QA testing, refactoring, and documentation cleanup",
    "what testing is relevant to the changes",
    "All three are included by default",
    "Only an explicit user opt-out",
    "Run the relevant test suites",
    "Refactor what the change touched",
    "Clean up touched documentation",
    "cleanup by default",
    "Ground every QA task in the acceptance criteria",
    "each criterion is exercised by a named test task",
    "vague scope is rejected, not recorded",
    "Scouting is mandatory before creating anything",
    "No row is written from unscouted ground, in any case, no exceptions",
    "At creation, `--desc` carries the narrative plus the INVEST check",
    "a story without them is not ready to cut",
    "names the technical approach",
    "a task missing either is not ready to cut",
    "Format for scanability",
    "present the plan for check-off before implementing anything",
    "make last edits on the spot",
    "the plan stays the truth",
    "The plan is the truth for the desired implementation",
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

    def test_human_in_loop_flagged(self):
        text = skills.render_skill()
        self.assertIn("interview", text)
        self.assertIn("Never decide a project's why/what", text)
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

    def test_init_yes_adds_gitignore(self):
        os.chdir(self.repo)
        payload = self._init_json(["init", "--yes"])
        gi = os.path.join(self.repo, ".gitignore")
        self.assertTrue(os.path.isfile(gi))
        text = open(gi).read()
        self.assertIn(".lazyplan/", text)
        self.assertIn(".agents/skills/lazyplan/", text)
        self.assertIn(".lazyplan/", payload["gitignore"]["added"])
        # second run adds nothing twice
        self._init_json(["init", "--yes"])
        self.assertEqual(open(gi).read().count(".lazyplan/"), 1)

    def test_init_without_yes_leaves_gitignore_alone(self):
        os.chdir(self.repo)
        self._init_json(["init", "--skills-scope", "project"])
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".gitignore")))

    def test_offer_gitignore_tty_accept(self):
        from unittest import mock

        from lazyplan.cli import _maybe_offer_gitignore

        os.chdir(self.repo)
        plan = os.path.join(self.repo, ".lazyplan")
        os.makedirs(plan)
        skilldir = os.path.join(self.repo, ".agents", "skills", "lazyplan")
        os.makedirs(skilldir)
        import argparse

        args = argparse.Namespace(yes=False, json=False)
        skills_info = {"installed": [f"{skilldir}/SKILL.md (wrote)"]}
        with (
            mock.patch.object(sys.stdin, "isatty", return_value=True),
            mock.patch("builtins.input", return_value="Y"),
        ):
            added = _maybe_offer_gitignore(args, Path(self.repo), Path(plan), skills_info)
        self.assertEqual(added, [".lazyplan/", ".agents/skills/lazyplan/"])
        self.assertIn(".lazyplan/", open(os.path.join(self.repo, ".gitignore")).read())

    def test_offer_gitignore_decline_and_json(self):
        from unittest import mock

        from lazyplan.cli import _maybe_offer_gitignore

        os.chdir(self.repo)
        plan = os.path.join(self.repo, ".lazyplan")
        os.makedirs(plan)
        import argparse

        args = argparse.Namespace(yes=False, json=False)
        with (
            mock.patch.object(sys.stdin, "isatty", return_value=True),
            mock.patch("builtins.input", return_value="n"),
        ):
            self.assertEqual(_maybe_offer_gitignore(args, Path(self.repo), Path(plan), {}), [])
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".gitignore")))
        args = argparse.Namespace(yes=False, json=True)
        self.assertEqual(_maybe_offer_gitignore(args, Path(self.repo), Path(plan), {}), [])


class TestAppendGitignore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "r")
        os.makedirs(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_adds_and_dedupes(self):
        from lazyplan.skills import append_gitignore

        root = Path(self.repo)
        self.assertTrue(append_gitignore(root, ".lazyplan/"))
        self.assertFalse(append_gitignore(root, ".lazyplan/"))
        self.assertFalse(append_gitignore(root, ".lazyplan"))
        self.assertFalse(append_gitignore(root, ""))
        self.assertEqual(open(root / ".gitignore").read(), ".lazyplan/\n")

    def test_missing_trailing_newline(self):
        from lazyplan.skills import append_gitignore

        root = Path(self.repo)
        (root / ".gitignore").write_text("*.db")
        self.assertTrue(append_gitignore(root, ".lazyplan/"))
        self.assertEqual(open(root / ".gitignore").read(), "*.db\n.lazyplan/\n")


class TestPromptConfirm(unittest.TestCase):
    def test_yes_variants(self):
        for ans in ("Y", "y", ""):
            self.assertTrue(skills.prompt_confirm("Q?", read=_answers([ans])))

    def test_no_variants(self):
        for ans in ("N", "n"):
            self.assertFalse(skills.prompt_confirm("Q?", read=_answers([ans])))

    def test_eof_means_default(self):
        def _boom():
            raise EOFError

        self.assertTrue(skills.prompt_confirm("Q?", read=_boom))
        self.assertFalse(skills.prompt_confirm("Q?", default_yes=False, read=_boom))

    def test_invalid_falls_back_to_default(self):
        self.assertTrue(skills.prompt_confirm("Q?", read=_answers(["maybe"])))


if __name__ == "__main__":
    unittest.main()
