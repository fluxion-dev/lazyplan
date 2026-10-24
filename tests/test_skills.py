"""Skill-installer tests: `lpui init` wizard paths stay non-interactive-safe."""

import io
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
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
    ["list", "--status", "todo", "--plan", "1"],
    ["list", "--status", "all"],
    ["list", "--archived"],
    ["show", "--kind", "plan", "--id", "1"],
    ["show", "--kind", "milestone", "--id", "1"],
    ["show", "--kind", "task", "--id", "1"],
    ["feed", "--limit", "20"],
    ["export", "--format", "json"],
    ["list", "--json"],
    ["--json", "list"],
    ["--actor", "opencode", "add-task", "--milestone", "1", "--title", "Do X"],
    ["add-task", "--milestone", "1", "--title", "Do X", "--actor", "opencode"],
    [
        "--actor",
        "opencode",
        "add-task",
        "--milestone",
        "1",
        "--title",
        "Do X",
        "--desc",
        "ctx",
    ],
    ["--actor", "opencode", "add-milestone", "--plan", "1", "--title", "F"],
    [
        "--actor",
        "opencode",
        "add-milestone",
        "--plan",
        "1",
        "--title",
        "F",
        "--desc",
        "d",
    ],
    [
        "--actor",
        "opencode",
        "add-plan",
        "--title",
        "API v2",
        "--why",
        "w",
        "--what",
        "x",
    ],
    ["--actor", "opencode", "status", "--kind", "task", "--id", "1", "--to", "doing"],
    ["--actor", "opencode", "status", "--kind", "task", "--id", "1", "--to", "done"],
    ["--actor", "opencode", "status", "--kind", "plan", "--id", "1", "--to", "doing"],
    ["--actor", "opencode", "update", "--kind", "task", "--id", "1", "--title", "N"],
    [
        "--actor",
        "opencode",
        "update",
        "--kind",
        "plan",
        "--id",
        "1",
        "--why",
        "w2",
    ],
    ["--actor", "opencode", "delete", "--kind", "task", "--id", "1"],
    ["--actor", "opencode", "delete", "--kind", "milestone", "--id", "1"],
    ["--actor", "opencode", "delete", "--kind", "plan", "--id", "1"],
    ["--actor", "opencode", "add-criteria", "--kind", "plan", "--id", "1", "--text", "T"],
    ["--actor", "opencode", "add-criteria", "--kind", "task", "--id", "1", "--text", "T"],
    ["criteria", "--kind", "plan", "--id", "1"],
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
    "lpui plan show --id N",
    "lpui feed --limit 20",
    "lpui export --format json",
    "lpui info",
    "plan add --title",
    "milestone add --plan P",
    "task add --milestone S",
    "task move --id T --to doing|done",
    "task edit --id T",
    "plan edit --id P",
    "task delete --id T",
    "criterion add --kind plan --id P",
    "criterion list --kind plan --id P",
    "lpui criterion tick --id C / lpui criterion untick --id C",
    "criterion delete --id C",
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
    "a milestone without them is not ready to cut",
    "names the technical approach",
    "a task missing any of them is not ready to cut",
    "Commit strategy",
    "ordered slices of small commits",
    "one or more small commits",
    "Every commit is green",
    "independently reviewable",
    "Never batch a whole milestone or plan into one commit",
    "Link commits after the fact",
    "no commit trailer is required",
    "Do not defer commits to the end of the plan",
    "ordered commit slices",
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
        self.assertIn("Never decide a plan's why/what", text)
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


class TestToolTargets(unittest.TestCase):
    def test_every_tool_both_scopes(self):
        repo, home = Path("/repo"), Path("/home")
        self.assertEqual(
            skills.tool_skill_targets("opencode", "both", repo, home),
            [
                repo / ".opencode/skills/lazyplan/SKILL.md",
                home / ".config/opencode/skills/lazyplan/SKILL.md",
            ],
        )
        self.assertEqual(
            skills.tool_skill_targets("gemini", "project", repo, home),
            [repo / ".gemini/skills/lazyplan/SKILL.md"],
        )
        self.assertEqual(
            skills.tool_skill_targets("cursor", "global", repo, home),
            [home / ".cursor/skills/lazyplan/SKILL.md"],
        )

    def test_codex_has_no_project_side(self):
        repo, home = Path("/repo"), Path("/home")
        self.assertEqual(skills.tool_skill_targets("codex", "project", repo, home), [])
        self.assertEqual(
            skills.tool_skill_targets("codex", "global", repo, home),
            [home / ".codex/skills/lazyplan/SKILL.md"],
        )

    def test_unknown_tool_yields_nothing(self):
        repo, home = Path("/repo"), Path("/home")
        for scope in ("project", "global", "both", "none"):
            self.assertEqual(skills.tool_skill_targets("copilot", scope, repo, home), [])

    def test_no_repo_means_no_project_side(self):
        home = Path("/home")
        self.assertEqual(skills.tool_skill_targets("opencode", "project", None, home), [])
        self.assertEqual(
            skills.tool_skill_targets("opencode", "both", None, home),
            [home / ".config/opencode/skills/lazyplan/SKILL.md"],
        )


class TestNativeInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "proj"
        self.repo.mkdir()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_native_tools_written_alongside_standard(self):
        res = skills.install("project", self.repo, self.home, tools=["opencode", "cursor"])
        paths = [line.rsplit(" (", 1)[0] for line in res.installed]
        self.assertIn(str(self.repo / ".agents/skills/lazyplan/SKILL.md"), paths)
        self.assertIn(str(self.repo / ".opencode/skills/lazyplan/SKILL.md"), paths)
        self.assertIn(str(self.repo / ".cursor/skills/lazyplan/SKILL.md"), paths)
        for p in paths:
            self.assertTrue(Path(p).is_file())

    def test_unknown_tool_ignored(self):
        res = skills.install("project", self.repo, self.home, tools=["copilot"])
        self.assertEqual(len(res.installed), 1)

    def test_claude_deduped_across_flag_and_tools(self):
        res = skills.install("both", self.repo, self.home, with_claude_copy=True, tools=["claude"])
        claude_lines = [line for line in res.installed if ".claude/skills/" in line]
        self.assertEqual(len(claude_lines), 2)

    def test_second_run_reports_up_to_date(self):
        skills.install("project", self.repo, self.home, tools=["opencode"])
        res = skills.install("project", self.repo, self.home, tools=["opencode"])
        self.assertTrue(all("up-to-date" in line for line in res.installed))

    def test_global_install_is_one_dir_per_agent(self):
        res = skills.install("global", self.repo, self.home, tools=["opencode", "claude"])
        paths = sorted(line.rsplit(" (", 1)[0] for line in res.installed)
        self.assertEqual(
            paths,
            sorted(
                [
                    str(self.home / ".config/opencode/skills/lazyplan/SKILL.md"),
                    str(self.home / ".claude/skills/lazyplan/SKILL.md"),
                ]
            ),
        )
        self.assertFalse((self.home / ".agents").exists())

    def test_global_unknown_tool_falls_back_to_universal(self):
        res = skills.install("global", self.repo, self.home, tools=["copilot"])
        self.assertEqual(
            res.installed,
            [f"{self.home}/.agents/skills/lazyplan/SKILL.md (wrote)"],
        )


class TestSkillsDirOverride(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "proj"
        self.repo.mkdir()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.old_env = os.environ.pop("LAZYPLAN_SKILLS_DIR", None)

    def tearDown(self):
        if self.old_env is None:
            os.environ.pop("LAZYPLAN_SKILLS_DIR", None)
        else:
            os.environ["LAZYPLAN_SKILLS_DIR"] = self.old_env
        self.tmp.cleanup()

    def test_flag_redirects_all_skill_writes(self):
        custom = self.tmp.name + "/custom-skills"
        res = skills.install("both", self.repo, self.home, tools=["opencode"], skills_dir=custom)
        self.assertEqual(res.installed, [f"{custom}/lazyplan/SKILL.md (wrote)"])
        self.assertTrue(Path(custom, "lazyplan/SKILL.md").is_file())
        self.assertFalse((self.repo / ".agents").exists())

    def test_flag_beats_env(self):
        os.environ["LAZYPLAN_SKILLS_DIR"] = "/tmp/from-env"
        args = Namespace(skills_dir="/tmp/from-flag")
        self.assertEqual(skills._skills_dir_override(args), "/tmp/from-flag")

    def test_env_used_when_no_flag(self):
        os.environ["LAZYPLAN_SKILLS_DIR"] = "/tmp/from-env"
        args = Namespace(skills_dir="")
        self.assertEqual(skills._skills_dir_override(args), "/tmp/from-env")

    def test_none_when_neither(self):
        args = Namespace(skills_dir="")
        self.assertIsNone(skills._skills_dir_override(args))


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
        res = skills.run_wizard(self.repo, self.home, read=_answers(["", "5"]), write=err)
        self.assertEqual(res.scope, "none")
        self.assertFalse((self.repo / ".agents").exists())

    def test_wizard_custom_skills_dir(self):
        err = io.StringIO()
        custom = str(self.home / "custom-skills")
        res = skills.run_wizard(
            self.repo, self.home, read=_answers(["opencode", "4", custom]), write=err
        )
        self.assertEqual(res.scope, "global")
        self.assertEqual(res.installed, [f"{custom}/lazyplan/SKILL.md (wrote)"])
        self.assertTrue(Path(custom, "lazyplan", "SKILL.md").is_file())
        self.assertTrue(Path(custom, "lazyplan", "lazyplan.db").parent.is_dir())
        self.assertFalse((self.repo / ".agents").exists())

    def test_wizard_project_with_agents_md_yes(self):
        err = io.StringIO()
        res = skills.run_wizard(self.repo, self.home, read=_answers(["", "2", "Y"]), write=err)
        self.assertEqual(res.scope, "project")
        self.assertTrue((self.repo / ".agents" / "skills" / "lazyplan" / "SKILL.md").is_file())
        self.assertTrue((self.repo / "AGENTS.md").is_file())

    def test_wizard_eof_defaults_to_skip_or_default(self):
        err = io.StringIO()

        def _eof():
            raise EOFError

        res = skills.run_wizard(self.repo, self.home, read=_eof, write=err)
        # EOF takes defaults: tools fallback, local scope, no repo writes.
        self.assertEqual(res.scope, "global")
        self.assertFalse((self.repo / ".agents").exists())
        # One dir per agent: opencode's canonical folder, no universal duplicate.
        self.assertTrue(
            (self.home / ".config" / "opencode" / "skills" / "lazyplan" / "SKILL.md").is_file()
        )
        self.assertFalse((self.home / ".agents" / "skills" / "lazyplan" / "SKILL.md").exists())

    def test_wizard_tailors_fresh_templates(self):
        err = io.StringIO()
        res = skills.run_wizard(
            self.repo,
            self.home,
            read=_answers(["", "2", "Y", "n"]),
            write=err,
        )
        self.assertEqual(res.scope, "project")
        summary = res.to_dict()["templates"]
        self.assertEqual(len(summary["added"]), 3)
        proj = (self.repo / ".agents/lazyplan" / "templates" / "plan.md").read_text()
        self.assertIn("required: [title]", proj)
        self.assertNotIn("edit or delete me", proj)
        task = (self.repo / ".agents/lazyplan" / "templates" / "task.md").read_text()
        self.assertNotIn("priority", task)

    def test_wizard_rerun_keeps_edits_by_default(self):
        tdir = self.repo / ".agents/lazyplan" / "templates"
        tdir.mkdir(parents=True)
        (tdir / "plan.md").write_text("edited")
        err = io.StringIO()
        res = skills.run_wizard(
            self.repo,
            self.home,
            read=_answers(["", "2", "Y", "Y", "", "", "", "", "k"]),
            write=err,
        )
        summary = res.to_dict()["templates"]
        self.assertEqual((tdir / "plan.md").read_text(), "edited")
        self.assertTrue((tdir / "milestone.md").is_file())
        self.assertIn(str(tdir / "plan.md"), summary["kept"])
        self.assertIn(str(tdir / "milestone.md"), summary["added"])


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
        if self.old_env is None:
            os.environ.pop("LAZYPLAN_DB", None)
        else:
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
            self.assertEqual(lpui_main([*argv, "--json"]), 0)
        return json.loads(buf.getvalue())

    def test_setup_no_skills_flag(self):
        os.chdir(self.repo)
        payload = self._init_json(["setup", "--yes", "--no-skills"])
        self.assertEqual(payload["skills"], [])
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".agents", "skills")))

    def test_setup_repo_writes_files(self):
        os.chdir(self.repo)
        payload = self._init_json(["setup", "--placement", "repo", "--yes"])
        self.assertTrue(
            os.path.isfile(os.path.join(self.repo, ".agents", "skills", "lazyplan", "SKILL.md"))
        )
        self.assertTrue(any("SKILL.md" in line for line in payload["installed"]))

    def test_setup_json_stays_machine_readable(self):
        # --json must not prompt even on a tty: stdout parses as JSON.
        os.chdir(self.repo)
        payload = self._init_json(["setup", "--json"])
        self.assertIn("db", payload)
        self.assertIn("skills", payload)

    def test_setup_yes_installs_defaults(self):
        os.chdir(self.repo)
        self._init_json(["setup", "--yes"])
        # Zero-touch default: local install, no repo writes, one dir per agent.
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".agents")))
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    os.environ["HOME"], ".config", "opencode", "skills", "lazyplan", "SKILL.md"
                )
            )
        )
        self.assertFalse(os.path.exists(os.path.join(os.environ["HOME"], ".agents", "skills")))

    def test_setup_repo_yes_writes_repo_files(self):
        os.chdir(self.repo)
        self._init_json(["setup", "--placement", "repo", "--yes"])
        self.assertTrue(
            os.path.isfile(os.path.join(self.repo, ".agents", "skills", "lazyplan", "SKILL.md"))
        )

    def test_setup_adds_gitignore_once(self):
        os.chdir(self.repo)
        # Zero-touch setup leaves the repo alone.
        self._init_json(["setup", "--yes"])
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".gitignore")))
        # Repo placement writes lazyplan entries.
        self._init_json(["setup", "--placement", "repo", "--yes"])
        gi = os.path.join(self.repo, ".gitignore")
        text = open(gi).read()
        self.assertIn(".agents/lazyplan/", text)
        self.assertIn(".agents/skills/lazyplan/", text)
        # second run adds nothing twice
        self._init_json(["setup", "--placement", "repo", "--yes"])
        self.assertEqual(open(gi).read().count(".agents/lazyplan/"), 1)


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
        self.assertTrue(append_gitignore(root, ".agents/lazyplan/"))
        self.assertFalse(append_gitignore(root, ".agents/lazyplan/"))
        self.assertFalse(append_gitignore(root, ".agents/lazyplan"))
        self.assertFalse(append_gitignore(root, ""))
        self.assertEqual(open(root / ".gitignore").read(), ".agents/lazyplan/\n")

    def test_missing_trailing_newline(self):
        from lazyplan.skills import append_gitignore

        root = Path(self.repo)
        (root / ".gitignore").write_text("*.db")
        self.assertTrue(append_gitignore(root, ".agents/lazyplan/"))
        self.assertEqual(open(root / ".gitignore").read(), "*.db\n.agents/lazyplan/\n")


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
