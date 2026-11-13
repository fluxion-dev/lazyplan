"""Startup health report: findings, capability text, and decisions."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from lazyplan.infrastructure import hook_install
from lazyplan.infrastructure.integrations import catalog, hook_id, skill_id
from lazyplan.presentation.setup import health
from lazyplan.presentation.setup.layout import SetupChoice
from lazyplan.presentation.setup.state import SetupState, state_path


class HealthCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.choice = SetupChoice(placement="home", agents=["claude"])
        self.state = SetupState()
        self.old_noskills = os.environ.pop("LAZYPLAN_NO_SKILLS", None)

    def tearDown(self):
        if self.old_noskills is not None:
            os.environ["LAZYPLAN_NO_SKILLS"] = self.old_noskills
        self.tmp.cleanup()

    def check(
        self,
        version: str = "1.0",
        missing: tuple[str, ...] = (),
        gh_exit: int = 0,
        env: dict[str, str] | None = None,
    ) -> health.HealthReport:
        self.ran: list[list[str]] = []

        def which(binary: str) -> str | None:
            return None if binary in missing else f"/bin/{binary}"

        def run(argv: list[str]) -> int:
            self.ran.append(argv)
            return gh_exit

        return health.check(
            self.choice, self.state, None, self.home, version, which, run, env or {}
        )

    def remember(self, item_id: str, decision: str, version: str = "1.0") -> None:
        item = next(item for item in catalog(self.home) if item.id == item_id)
        self.state.integration_choices[item_id] = {
            "decision": decision,
            "fingerprint": item.fingerprint,
            "version": version,
        }

    def by_id(self, report: health.HealthReport) -> dict[str, health.HealthFinding]:
        return {finding.id: finding for finding in report.findings}

    def install_skill(self) -> None:
        dest = self.home / ".claude" / "skills" / "lazyplan" / "SKILL.md"
        dest.parent.mkdir(parents=True)
        dest.write_text("installed", encoding="utf-8")


class IntegrationFindingsTest(HealthCase):
    def test_nothing_installed_reports_the_skill_and_one_finding_per_hook_host(self):
        findings = self.by_id(self.check())
        self.assertIn(skill_id("lazyplan"), findings)
        hooks = findings["hook:claude"]
        self.assertEqual(hooks.label, "Claude Code hooks")
        self.assertIn(hook_id("claude", "session-start"), {item.id for item in hooks.items})
        self.assertTrue(hooks.fixable)
        self.assertEqual(hooks.severity, health.ERROR)

    def test_every_finding_names_the_capability_it_costs(self):
        findings = self.by_id(self.check())
        self.assertIn("Claude Code sessions aren't tracked", findings["hook:claude"].capability)
        self.assertIn("instructions", findings[skill_id("lazyplan")].capability)

    def test_a_clean_install_reports_nothing(self):
        self.install_skill()
        hook_install.install(self.home, ["claude"])
        report = self.check()
        self.assertEqual(report.findings, ())

    def test_a_skill_deleted_after_install_is_an_open_fixable_finding(self):
        self.install_skill()
        hook_install.install(self.home, ["claude"])
        for item in catalog(self.home):
            if item.host in ("", "claude"):
                self.remember(item.id, "installed")
        self.assertEqual(self.check().findings, ())
        (self.home / ".claude" / "skills" / "lazyplan" / "SKILL.md").unlink()
        finding = self.by_id(self.check())[skill_id("lazyplan")]
        self.assertTrue(finding.open)
        self.assertTrue(finding.fixable)

    def test_undecided_findings_are_open(self):
        report = self.check()
        self.assertEqual(report.open, report.findings)

    def test_never_hides_the_finding_but_keeps_reporting_it(self):
        self.install_skill()
        for item in catalog(self.home):
            if item.host == "claude":
                self.remember(item.id, "never")
        report = self.check()
        finding = self.by_id(report)["hook:claude"]
        self.assertEqual(finding.decision, "never")
        self.assertEqual(report.open, ())

    def test_not_now_hides_until_the_next_version(self):
        self.install_skill()
        for item in catalog(self.home):
            if item.host == "claude":
                self.remember(item.id, "deferred", version="1.0")
        self.assertEqual(self.check("1.0").open, ())
        self.assertEqual(self.by_id(self.check("1.0"))["hook:claude"].decision, "deferred")
        self.assertIn("hook:claude", {finding.id for finding in self.check("2.0").open})

    def test_explicit_database_reports_nothing(self):
        self.choice = SetupChoice(placement="home", agents=["claude"], explicit_db="x.db")
        self.assertEqual(self.check().findings, ())

    def test_report_names_hosts_for_the_restart_notice(self):
        report = self.check()
        self.assertEqual(report.hosts(health.items_of(report.findings)), ["Claude Code"])

    def test_findings_serialize(self):
        payload = self.by_id(self.check())["hook:claude"].to_dict()
        self.assertTrue(payload["fixable"])
        self.assertIn(hook_id("claude", "stop"), payload["items"])

    def test_context_install_writes_the_fixable_items_and_clears_them(self):
        context = health.HealthContext(self.choice, self.state, None, self.home, "1.0")
        before = self.check()
        result = context.install(before.open)
        self.assertEqual(result.pending, ())
        self.assertTrue((self.home / ".claude" / "skills" / "lazyplan" / "SKILL.md").is_file())
        self.assertEqual(self.check().findings, ())

    def test_context_decide_hides_the_findings_until_their_rule_lifts(self):
        context = health.HealthContext(self.choice, self.state, None, self.home, "1.0")
        context.decide(self.check(missing=("git",)).open, "deferred")
        self.assertEqual(self.check(missing=("git",)).open, ())
        self.assertTrue(self.check("2.0", missing=("git",)).open)
        context.decide(self.check(missing=("git",)).findings, "never")
        self.assertEqual(self.check("2.0", missing=("git",)).open, ())
        self.assertTrue(state_path(self.home).is_file())

    def test_check_writes_nothing(self):
        before = sorted(path.relative_to(self.home) for path in self.home.rglob("*"))
        self.check()
        after = sorted(path.relative_to(self.home) for path in self.home.rglob("*"))
        self.assertEqual(before, after)


class ToolFindingsTest(HealthCase):
    def setUp(self):
        super().setUp()
        self.install_skill()
        hook_install.install(self.home, ["claude"])

    def test_tools_on_path_report_nothing(self):
        self.assertEqual(self.check().findings, ())
        self.assertEqual(self.ran, [["/bin/gh", "auth", "token"]])

    def test_missing_lpui_and_git_are_errors_with_a_manual_fix(self):
        findings = self.by_id(self.check(missing=("lpui", "git")))
        for tool_id in ("tool:lpui", "tool:git"):
            finding = findings[tool_id]
            self.assertEqual(finding.severity, health.ERROR)
            self.assertFalse(finding.fixable)
            self.assertTrue(finding.fix)
            self.assertTrue(finding.capability)
        self.assertIn("PATH", findings["tool:lpui"].fix)

    def test_missing_gh_is_a_warning(self):
        finding = self.by_id(self.check(missing=("gh",)))["tool:gh"]
        self.assertEqual(finding.severity, health.WARNING)
        self.assertIn("gh auth login", finding.fix)
        self.assertEqual(self.ran, [])

    def test_gh_without_a_login_is_a_warning(self):
        findings = self.by_id(self.check(gh_exit=1))
        self.assertEqual(set(findings), {"tool:gh-auth"})
        self.assertEqual(findings["tool:gh-auth"].severity, health.WARNING)

    def test_a_token_in_the_environment_skips_gh(self):
        for name in health.TOKEN_ENV:
            with self.subTest(name=name):
                report = self.check(missing=("gh",), env={name: "t"})
                self.assertEqual(report.findings, ())
                self.assertEqual(self.ran, [])

    def test_never_hides_a_tool_finding(self):
        self.state.integration_choices["tool:git"] = {"decision": "never", "fingerprint": ""}
        report = self.check(missing=("git",))
        self.assertEqual(self.by_id(report)["tool:git"].decision, "never")
        self.assertEqual(report.open, ())


if __name__ == "__main__":
    unittest.main()
