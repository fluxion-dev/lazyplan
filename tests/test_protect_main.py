"""The committed ruleset payload describes the protection main actually needs."""

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / ".github" / "rulesets" / "main.json"
SCRIPT = ROOT / "tools" / "protect-main.sh"

FAKE_GH_SCRIPT = """#!/usr/bin/env bash
printf '%s\\n' "$*" >>"$FAKE_LOG"

if [ "${1:-}" = "repo" ] && [ "${2:-}" = "view" ]; then
  printf '%s\\n' "owner/repo"
  exit 0
fi

if [ "${1:-}" = "api" ]; then
  shift
  if [ "${1:-}" = "-X" ]; then
    method="$2"
    path="$3"
    printf '%s %s\\n' "$method" "$path" >>"$FAKE_STATE/writes"
    if [ "$method" = "POST" ]; then
      printf '8' >"$FAKE_STATE/existing"
      printf '%s\\n' '{"id": 8}'
    elif [ "$method" = "PUT" ]; then
      printf '%s\\n' '{"id": 7}'
    else
      printf '%s\\n' '{}'
    fi
    exit 0
  fi
  case "$1" in
    repos/owner/repo)
      printf '%s\\n' "${FAKE_ADMIN:-true}"
      ;;
    repos/owner/repo/rulesets)
      if [ -f "$FAKE_STATE/existing" ]; then
        cat "$FAKE_STATE/existing"
      fi
      ;;
    repos/owner/repo/rulesets/7)
      cat "$FAKE_STATE/current"
      ;;
    *)
      printf 'unexpected gh path: %s\\n' "$1" >&2
      exit 9
      ;;
  esac
  exit 0
fi

printf 'unexpected gh call: %s\\n' "$*" >&2
exit 9
"""


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
        self.assertFalse(params["require_extra_approval_for_unattributed_changes"])
        self.assertEqual(params["allowed_merge_methods"], ["merge", "squash", "rebase"])

    def test_requires_the_ci_gate(self):
        rule = self._rule("required_status_checks")
        checks = rule["parameters"]["required_status_checks"]
        self.assertEqual([check["context"] for check in checks], ["gates"])

    def test_bypass_is_admin_only(self):
        actors = {
            (actor["actor_type"], actor["actor_id"]) for actor in self.payload["bypass_actors"]
        }
        self.assertEqual(actors, {("RepositoryRole", 5)})
        for actor in self.payload["bypass_actors"]:
            self.assertEqual(actor["bypass_mode"], "always")

    def _rule(self, rule_type):
        for rule in self.payload["rules"]:
            if rule["type"] == rule_type:
                return rule
        self.fail(f"missing rule {rule_type}")


class ScriptCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(FAKE_GH_SCRIPT)
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        self.state = self.root / "state"
        self.state.mkdir()
        self.log = self.root / "calls"
        self.log.touch()
        self.payload = json.loads(PAYLOAD.read_text())
        self.env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "FAKE_LOG": str(self.log),
            "FAKE_STATE": str(self.state),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args, repo="owner/repo", **extra_env):
        return subprocess.run(
            ["bash", str(SCRIPT), "--repo", repo, *args],
            capture_output=True,
            text=True,
            env={**self.env, **extra_env},
            cwd=ROOT,
        )

    def writes(self):
        path = self.state / "writes"
        return path.read_text().splitlines() if path.exists() else []

    def seed(self, *, existing, current):
        if existing:
            (self.state / "existing").write_text(str(existing))
        (self.state / "current").write_text(json.dumps(current))

    def test_script_is_executable(self):
        self.assertTrue(SCRIPT.is_file())
        self.assertTrue(SCRIPT.stat().st_mode & stat.S_IXUSR)

    def test_dry_run_writes_nothing(self):
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would upsert ruleset 'main-protection'", result.stdout)
        self.assertEqual(self.writes(), [])

    def test_create_posts_and_reports_the_new_id(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("created ruleset 'main-protection' (8)", result.stdout)
        self.assertEqual(self.writes(), ["POST repos/owner/repo/rulesets"])

    def test_update_puts_when_payload_drifts(self):
        self.seed(existing=7, current={**self.payload, "id": 7, "enforcement": "disabled"})
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("updated ruleset 'main-protection' (7)", result.stdout)
        self.assertEqual(self.writes(), ["PUT repos/owner/repo/rulesets/7"])

    def test_noop_skips_writes_when_payload_matches(self):
        self.seed(existing=7, current={**self.payload, "id": 7, "source_type": "Repository"})
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no change: ruleset 'main-protection' (7)", result.stdout)
        self.assertEqual(self.writes(), [])

    def test_status_reports_without_writes(self):
        self.seed(existing=7, current={**self.payload, "id": 7})
        result = self.run_script("--status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("main-protection", result.stdout)
        self.assertEqual(self.writes(), [])

    def test_requires_admin(self):
        result = self.run_script(FAKE_ADMIN="false")
        self.assertEqual(result.returncode, 1)
        self.assertIn("needs admin", result.stderr)
        self.assertEqual(self.writes(), [])

    def test_rejects_a_repo_without_an_owner(self):
        result = self.run_script(repo="not-a-repo")
        self.assertEqual(result.returncode, 2)
        self.assertIn("OWNER/NAME", result.stderr)
        self.assertEqual(self.writes(), [])

    def test_help_names_every_mode(self):
        result = self.run_script("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--dry-run", result.stdout)
        self.assertIn("--status", result.stdout)


if __name__ == "__main__":
    unittest.main()
