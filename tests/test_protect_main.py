"""The committed ruleset payload describes the protection main actually needs."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / ".github" / "rulesets" / "main.json"


class PayloadCase(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(PAYLOAD.read_text())

    def test_targets_the_main_branch(self):
        self.assertEqual(self.payload["name"], "main-protection")
        self.assertEqual(self.payload["target"], "branch")
        self.assertEqual(self.payload["enforcement"], "active")
        self.assertEqual(self.payload["conditions"]["ref_name"]["include"], ["refs/heads/main"])

    def test_blocks_deletion_and_force_pushes(self):
        types = {rule["type"] for rule in self.payload["rules"]}
        self.assertIn("deletion", types)
        self.assertIn("non_fast_forward", types)

    def test_requires_a_pull_request_without_approvals(self):
        rule = self._rule("pull_request")
        params = rule["parameters"]
        self.assertEqual(params["required_approving_review_count"], 0)
        self.assertEqual(params["allowed_merge_methods"], ["merge", "squash", "rebase"])

    def test_requires_the_ci_gate(self):
        rule = self._rule("required_status_checks")
        checks = rule["parameters"]["required_status_checks"]
        self.assertEqual([check["context"] for check in checks], ["gates"])

    def test_bypass_is_admin_and_release_automation_only(self):
        actors = {
            (actor["actor_type"], actor["actor_id"]) for actor in self.payload["bypass_actors"]
        }
        self.assertEqual(actors, {("RepositoryRole", 5), ("Integration", 15368)})
        for actor in self.payload["bypass_actors"]:
            self.assertEqual(actor["bypass_mode"], "always")

    def _rule(self, rule_type):
        for rule in self.payload["rules"]:
            if rule["type"] == rule_type:
                return rule
        self.fail(f"missing rule {rule_type}")


if __name__ == "__main__":
    unittest.main()
