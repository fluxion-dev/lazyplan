"""Per-repo creation templates: parse, scaffold, fill/enforce/auto-criteria."""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from lazyplan import services, templates
from lazyplan.cli import main as lpui_main
from lazyplan.store import Store
from tests.support.home import sandbox_home


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestParseTemplate(unittest.TestCase):
    def test_full_frontmatter(self):
        text = (
            "---\n"
            "defaults:\n"
            '  why: "W"\n'
            "  what: ''\n"
            "  priority: p1\n"
            "required: [title, why]\n"
            "criteria:\n"
            '  - "First"\n'
            "  - Second\n"
            "---\n"
            "# guidance ignored\n"
        )
        t = templates.parse_template("plan", text)
        # retired priority key in old templates is ignored, not rejected
        self.assertEqual(t.defaults, {"why": "W", "what": ""})
        self.assertEqual(t.required, ["title", "why"])
        self.assertEqual(t.criteria, ["First", "Second"])

    def test_block_lists(self):
        text = (
            "---\n"
            "defaults:\n"
            '  desc: "D"\n'
            "required:\n"
            "  - title\n"
            "  - desc\n"
            "criteria:\n"
            "  - Given x, when y, then z\n"
            "---\n"
        )
        t = templates.parse_template("milestone", text)
        self.assertEqual(t.defaults, {"desc": "D"})
        self.assertEqual(t.required, ["title", "desc"])
        self.assertEqual(t.criteria, ["Given x, when y, then z"])

    def test_no_frontmatter_is_empty(self):
        t = templates.parse_template("task", "# just guidance\n")
        self.assertEqual((t.defaults, t.required, t.criteria), ({}, [], []))

    def test_starters_parse_and_stay_opinionated(self):
        expected_required = {
            "plan": ["title", "why", "what"],
            "milestone": ["title", "desc"],
            "task": ["title", "desc"],
        }
        for kind, text in templates.STARTERS.items():
            with self.subTest(kind=kind):
                t = templates.parse_template(kind, text)
                self.assertEqual(t.required, expected_required[kind])
                # Starters ship empty: real criteria come from the interview,
                # never from placeholder or example text.
                self.assertEqual(t.criteria, [])
                self.assertNotIn("edit or delete me", text)
        task = templates.parse_template("task", templates.STARTERS["task"])
        self.assertNotIn("priority", task.defaults)

    def test_starters_carry_commit_slice_guidance(self):
        fragments = {
            "plan": (
                "Commit strategy",
                "ordered slices of small commits",
                "Do not plan one batch commit",
            ),
            "milestone": (
                "ordered commit slices",
                "Commit order",
                "map each task to the slice",
            ),
            "task": (
                "Commit slice",
                "one or more small commits",
                "Every commit is green",
                "verification that keeps it green",
            ),
        }
        for kind, expected in fragments.items():
            with self.subTest(kind=kind):
                body = templates.STARTERS[kind]
                for fragment in expected:
                    self.assertIn(fragment, body)

    def test_local_repo_templates_match_starters_when_present(self):
        repo_templates = Path(__file__).parent.parent / ".agents/lazyplan/templates"
        if not repo_templates.is_dir():
            self.skipTest("repo templates are local-only (gitignored)")
        for kind, starter in templates.STARTERS.items():
            with self.subTest(kind=kind):
                self.assertEqual(
                    (repo_templates / f"{kind}.md").read_text(encoding="utf-8"), starter
                )

    def test_render_starter_choices(self):
        lean = templates.TemplateChoices(
            require_why_what=False,
            require_desc=False,
            with_examples=False,
        )
        p = templates.parse_template("plan", templates.render_starter("plan", lean))
        self.assertEqual((p.required, p.criteria), (["title"], []))
        s = templates.parse_template("milestone", templates.render_starter("milestone", lean))
        self.assertEqual((s.required, s.criteria), (["title"], []))
        t = templates.parse_template("task", templates.render_starter("task", lean))
        self.assertEqual(t.required, ["title"])
        self.assertNotIn("priority", t.defaults)
        self.assertEqual(t.criteria, [])
        with self.assertRaises(ValueError):
            templates.render_starter("nope", templates.OPINIONATED)

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError):
            templates.parse_template("plan", "---\ndefaults:\n  nope: x\n---\n")
        with self.assertRaises(ValueError):
            templates.parse_template(
                "milestone",
                "---\nrequired: [title, why]\n---\n",  # why is plan-only
            )

    def test_retired_priority_key_ignored(self):
        # Old template files still carry priority; parsing must not fail.
        t = templates.parse_template(
            "task", "---\ndefaults:\n  priority: p9\nrequired: [title]\n---\n"
        )
        self.assertEqual(t.required, ["title"])
        self.assertNotIn("priority", t.defaults)
        t2 = templates.parse_template("task", "---\nrequired:\n  - title\n  - priority\n---\n")
        self.assertEqual(t2.required, ["title"])

    def test_unclosed_frontmatter_rejected(self):
        with self.assertRaises(ValueError):
            templates.parse_template("plan", "---\ndefaults:\n  why: x\n")


class TestReadability(unittest.TestCase):
    def test_short_text_always_passes(self):
        out = templates.apply_template(
            "task", {"title": "T", "desc": "Do the thing"}, "/tmp/nonexistent.db"
        )
        self.assertEqual(out["desc"], "Do the thing")

    def test_long_single_blob_rejected_per_field(self):
        blob = "x" * (templates.READABILITY_THRESHOLD + 1)
        for kind, fields in [
            ("plan", {"title": "P", "why": blob, "what": "short"}),
            ("plan", {"title": "P", "why": "short", "what": blob}),
            ("milestone", {"title": "M", "desc": blob}),
            ("task", {"title": "T", "desc": blob}),
        ]:
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError) as ctx:
                    templates.apply_template(kind, fields, "/tmp/nonexistent.db")
                self.assertIn("paragraphs and sections", str(ctx.exception))

    def test_boundary_length_passes(self):
        ok = "x" * templates.READABILITY_THRESHOLD
        out = templates.apply_template("task", {"title": "T", "desc": ok}, "/tmp/nonexistent.db")
        self.assertEqual(out["desc"], ok)

    def test_long_sectioned_text_passes(self):
        bodies = [
            "First paragraph.\n\nSecond paragraph. " + "y" * templates.READABILITY_THRESHOLD,
            "# Head\n\n" + "y" * templates.READABILITY_THRESHOLD,
            "Intro.\n- one\n- " + "z" * templates.READABILITY_THRESHOLD,
        ]
        for body in bodies:
            with self.subTest(body=body[:20]):
                out = templates.apply_template(
                    "task", {"title": "T", "desc": body}, "/tmp/nonexistent.db"
                )
                self.assertEqual(out["desc"], body)


class TestTemplateDirs(unittest.TestCase):
    def test_repo_scoped_dirs_resolve(self):
        self.assertEqual(
            templates.templates_dir_for_db("/r/.agents/lazyplan/lazyplan.db"),
            Path("/r/.agents/lazyplan/templates"),
        )
        self.assertEqual(
            templates.templates_dir_for_db("/r/.plan/lazyplan.db"),
            Path("/r/.plan/templates"),
        )

    def test_home_db_uses_its_templates_dir(self):
        self.assertEqual(
            templates.templates_dir_for_db("/home/u/.lazyplan/lazyplan.db"),
            Path("/home/u/.lazyplan/templates"),
        )
        self.assertIsNone(templates.templates_dir_for_db("/tmp/x/t.db"))

    def test_explicit_db_uses_a_sibling_templates_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "custom.db"
            (Path(tmp) / "templates").mkdir()
            self.assertEqual(
                templates.templates_dir_for_db(db),
                Path(tmp) / "templates",
            )

    def test_home_template_changes_a_new_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / ".lazyplan"
            home.mkdir()
            tdir = home / "templates"
            tdir.mkdir()
            (tdir / "task.md").write_text(
                '---\ndefaults:\n  desc: "from home"\nrequired: [title]\ncriteria: []\n---\n',
                encoding="utf-8",
            )
            db = home / "lazyplan.db"
            out = templates.apply_template("task", {"title": "T"}, db)
            self.assertEqual(out["desc"], "from home")

    def test_ensure_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / ".agents/lazyplan"
            first = templates.ensure_templates(plan)
            self.assertEqual(len(first), 3)
            self.assertTrue((plan / "templates" / "plan.md").is_file())
            (plan / "templates" / "plan.md").write_text("edited", encoding="utf-8")
            second = templates.ensure_templates(plan)
            self.assertEqual(second, [])
            self.assertEqual((plan / "templates" / "plan.md").read_text(encoding="utf-8"), "edited")


class TestStoreTemplates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.db = self.repo / ".agents/lazyplan" / "lazyplan.db"
        self.store = Store(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_templates_is_legacy(self):
        p = self.store.add_plan("P")
        self.assertEqual(p.goal, "")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        self.assertFalse(hasattr(s, "priority"))
        self.assertFalse(hasattr(t, "priority"))
        self.assertEqual(self.store.list_criteria("plan", p.id), [])

    def test_fill_and_auto_criteria(self):
        templates.ensure_templates(self.db.parent)
        (self.db.parent / "templates" / "plan.md").write_text(
            "---\ndefaults:\n  why: W\nrequired: [title]\ncriteria:\n  - C1\n  - C2\n---\nbody\n",
            encoding="utf-8",
        )
        store = Store(self.db)
        p = services.create_plan(store, "P")
        self.assertEqual(p.goal, "W")
        self.assertEqual([c.text for c in store.list_criteria("plan", p.id)], ["C1", "C2"])

    def test_enforce_names_field(self):
        templates.ensure_templates(self.db.parent)
        (self.db.parent / "templates" / "plan.md").write_text(
            "---\nrequired: [title]\n---\n", encoding="utf-8"
        )
        (self.db.parent / "templates" / "milestone.md").write_text(
            "---\nrequired:\n  - title\n  - desc\n---\n", encoding="utf-8"
        )
        store = Store(self.db)
        p = services.create_plan(store, "P")
        with self.assertRaises(ValueError) as ctx:
            services.create_milestone(store, p.id, "S")
        self.assertIn("'desc'", str(ctx.exception))

    def test_retired_priority_default_ignored(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        store = Store(self.db)
        t = services.create_task(store, s.id, "A")
        self.assertFalse(hasattr(t, "priority"))
        templates.ensure_templates(self.db.parent)
        (self.db.parent / "templates" / "task.md").write_text(
            "---\ndefaults:\n  priority: p2\nrequired: [title]\n---\n", encoding="utf-8"
        )
        store = Store(self.db)
        t2 = services.create_task(store, s.id, "B")
        self.assertFalse(hasattr(t2, "priority"))

    def test_malformed_template_raises(self):
        templates.ensure_templates(self.db.parent)
        (self.db.parent / "templates" / "plan.md").write_text(
            "---\ndefaults:\n  nope: x\n---\n", encoding="utf-8"
        )
        store = Store(self.db)
        with self.assertRaises(ValueError):
            services.create_plan(store, "P")


class TestTemplateSetup(unittest.TestCase):
    def test_silent_writes_opinionated_without_prompting(self):
        def _boom():
            raise AssertionError("silent setup must not prompt")

        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / ".agents/lazyplan"
            summary = templates.run_template_setup(
                plan, interactive=False, read=_boom, write=io.StringIO()
            )
            self.assertEqual(len(summary["added"]), 3)
            self.assertEqual((summary["kept"], summary["reset"]), ([], []))
            proj = templates.parse_template(
                "plan", (plan / "templates" / "plan.md").read_text(encoding="utf-8")
            )
            self.assertEqual(proj.required, ["title", "why", "what"])
            # Opinionated starters ship empty: criteria come from the interview.
            self.assertEqual(proj.criteria, [])

    def test_rerun_missing_only_never_clobbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / ".agents/lazyplan"
            templates.run_template_setup(plan, interactive=False)
            dest = plan / "templates" / "plan.md"
            dest.write_text("edited", encoding="utf-8")
            summary = templates.run_template_setup(plan, interactive=False)
            self.assertEqual((summary["added"], summary["reset"]), ([], []))
            self.assertEqual(len(summary["kept"]), 3)
            self.assertEqual(dest.read_text(encoding="utf-8"), "edited")

    def test_interactive_keep_edit_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / ".agents/lazyplan"
            templates.run_template_setup(plan, interactive=False)
            dest = plan / "templates" / "plan.md"
            dest.write_text(dest.read_text(encoding="utf-8") + "\n# mine\n", encoding="utf-8")
            lean = templates.TemplateChoices(
                require_why_what=False,
                require_desc=False,
                with_examples=False,
            )
            summary = templates.run_template_setup(
                plan,
                interactive=True,
                choices=lean,
                decisions={"plan": "keep", "milestone": "reset", "task": "edit"},
            )
            self.assertEqual(summary["kept"], [str(plan / "templates" / "plan.md")])
            self.assertIn("# mine", dest.read_text(encoding="utf-8"))
            milestone = templates.parse_template(
                "milestone", (plan / "templates" / "milestone.md").read_text(encoding="utf-8")
            )
            self.assertEqual((milestone.required, milestone.criteria), (["title"], []))
            task = templates.parse_template(
                "task", (plan / "templates" / "task.md").read_text(encoding="utf-8")
            )
            self.assertEqual(task.required, ["title"])
            self.assertNotIn("priority", task.defaults)
            # edit preserves the file's own criteria lines (starters ship empty)
            self.assertEqual(task.criteria, [])

    def test_edit_unparseable_keeps(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / ".agents/lazyplan"
            templates.run_template_setup(plan, interactive=False)
            dest = plan / "templates" / "task.md"
            dest.write_text("---\ndefaults:\n  nope: x\n---\n", encoding="utf-8")
            summary = templates.run_template_setup(
                plan,
                interactive=True,
                decisions={"plan": "keep", "milestone": "keep", "task": "edit"},
            )
            self.assertIn(str(dest), summary["kept"])
            self.assertEqual(dest.read_text(encoding="utf-8"), "---\ndefaults:\n  nope: x\n---\n")


class TestTemplateCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        (self.repo / ".git").mkdir(parents=True)
        self.db = str(self.repo / ".agents/lazyplan" / "lazyplan.db")
        self.old_cwd = os.getcwd()
        os.chdir(self.repo)
        self.old_env = os.environ.pop("LAZYPLAN_DB", None)
        sandbox_home(self, os.path.join(self.tmp.name, "home"))
        os.makedirs(os.environ["HOME"], exist_ok=True)
        self.old_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = os.path.join(self.tmp.name, "xdg")

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
        self.tmp.cleanup()

    def _run(self, argv):
        buf, err = io.StringIO(), io.StringIO()
        old_err = sys.stderr
        sys.stderr = err
        try:
            with redirect_stdout(buf):
                rc = lpui_main(argv)
        finally:
            sys.stderr = old_err
        return rc, buf.getvalue(), err.getvalue()

    def test_setup_scaffolds_templates(self):
        # Repo placement scaffolds repo-shared templates.
        rc, _out, _ = self._run(["setup", "--placement", "repo", "--yes", "--no-skills"])
        self.assertEqual(rc, 0)
        self.assertTrue((self.repo / ".agents/lazyplan" / "templates" / "milestone.md").is_file())

    def test_zero_touch_setup_leaves_repo_alone(self):
        rc, _out, _ = self._run(["setup", "--yes", "--no-skills"])
        self.assertEqual(rc, 0)
        self.assertFalse((self.repo / ".agents").exists())

    def test_cli_required_error_is_exit_2(self):
        self._run(["setup", "--placement", "repo", "--yes", "--no-skills"])
        (self.repo / ".agents/lazyplan" / "templates" / "plan.md").write_text(
            "---\nrequired: [title]\n---\n", encoding="utf-8"
        )
        (self.repo / ".agents/lazyplan" / "templates" / "milestone.md").write_text(
            "---\nrequired: [title]\n---\n", encoding="utf-8"
        )
        (self.repo / ".agents/lazyplan" / "templates" / "task.md").write_text(
            "---\nrequired:\n  - title\n  - desc\n---\n", encoding="utf-8"
        )
        rc, _, _ = self._run(["add-plan", "--title", "P"])
        self.assertEqual(rc, 0)
        rc, _, _ = self._run(["add-milestone", "--plan", "1", "--title", "S"])
        self.assertEqual(rc, 0)
        rc, _, err = self._run(["add-task", "--milestone", "1", "--title", "T"])
        self.assertEqual(rc, 2)
        self.assertIn("'desc'", err)


if __name__ == "__main__":
    unittest.main()
