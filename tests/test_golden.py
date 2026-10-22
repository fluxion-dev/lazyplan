"""Golden outputs: byte-exact list/show/export snapshots.

Any refactoring that changes user-visible output must update these on
purpose, never by accident.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import render, services
from lazyplan.models import Status
from lazyplan.store import Store


def build_fixture(db_path: str) -> tuple[Store, int, int, int]:
    """Deterministic plan + milestone + task + criterion, task doing."""
    s = Store(db_path)
    p = s.add_plan("Website", "Marketing site", goal="Convert")
    m = s.add_milestone(p.id, "Homepage", "Hero work")
    t = s.add_task(m.id, "Design hero")
    s.add_criteria("plan", p.id, "Loads fast")
    services.set_status(s, "task", t.id, Status.DOING)
    return s, p.id, m.id, t.id


class TestGoldenOutputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store, self.pid, self.mid, self.tid = build_fixture(
            os.path.join(self.tmp.name, "g.db")
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_tree_lines(self):
        self.assertEqual(
            render.tree_lines(self.store, None, None),
            ["◐ P1 Website", "  ◐ M1 Homepage", "    ◐ T1 Design hero"],
        )

    def test_render_full_plan(self):
        full = self.store.get_full("plan", self.pid)
        assert full is not None
        self.assertEqual(
            render.render_full("plan", full),
            "◐ P1 Website\n"
            "why: Convert\n"
            "\nwhat: Marketing site\n"
            "\nacceptance:\n"
            "  [ ] Loads fast\n"
            "\n  ◐ M1 Homepage",
        )

    def test_render_full_milestone(self):
        full = self.store.get_full("milestone", self.mid)
        assert full is not None
        self.assertEqual(
            render.render_full("milestone", full),
            "◐ M1 Homepage (P1)\n\ndetails: Hero work\n\n  ◐ T1 Design hero",
        )

    def test_render_markdown(self):
        data = services.export_all(self.store)
        text = render.render_markdown(data)
        self.assertIn("## ◐ P1 Website", text)
        self.assertIn("> why: Convert", text)
        self.assertIn("- [ ] Loads fast", text)
        self.assertIn("### ◐ M1 Homepage", text)
        self.assertIn("- [ ] T1 Design hero (doing)", text)

    def test_render_plan_markdown_full_fidelity(self):
        data = services.export_all(self.store)
        (entry,) = data["plans"]
        text = render.render_plan_markdown(entry)
        self.assertIn("## ◐ P1 Website", text)
        self.assertNotIn("priority", text)
        self.assertIn("- [ ] Loads fast", text)
        self.assertIn("### ◐ M1 Homepage", text)
        self.assertIn("Hero work", text)
        self.assertIn("- [ ] T1 Design hero (doing)", text)
        self.assertIn("Design hero", text)
        entry2 = services.export_plan(self.store, 1)
        assert entry2 is not None
        self.assertEqual(render.render_plan_markdown(entry2), text)
        self.assertIsNone(services.export_plan(self.store, 9999))

    def test_export_json_shape(self):
        data = services.export_all(self.store)
        self.assertEqual(data["lazyplan"], 1)
        (entry,) = data["plans"]
        self.assertEqual(entry["plan"]["name"], "Website")
        self.assertEqual(entry["plan"]["status"], "doing")
        self.assertEqual(entry["criteria"][0]["text"], "Loads fast")
        (mentry,) = entry["milestones"]
        self.assertEqual(mentry["milestone"]["title"], "Homepage")
        (tentry,) = mentry["tasks"]
        self.assertEqual(tentry["task"]["title"], "Design hero")
        self.assertEqual(tentry["task"]["status"], "doing")


if __name__ == "__main__":
    unittest.main()
