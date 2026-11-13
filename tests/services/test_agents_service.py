"""Agent services: payload identity, exact binding, refusal, and events."""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from lazyplan import services
from lazyplan.services.agents import AgentStartError
from lazyplan.store import Store


class AgentServiceCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.worktree = Path(self.tmp.name) / "worktree"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=self.repo, check=True)
        (self.repo / "f").write_text("one\n", encoding="utf-8")
        subprocess.run(["git", "add", "f"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "worktree", "add", "-q", "-b", "plan/1-test", str(self.worktree)],
            cwd=self.repo,
            check=True,
        )
        self.store = Store(os.path.join(self.tmp.name, "agents.db"))
        self.plan = self.store.add_plan("Plan")
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(self.milestone.id, "T")
        self.store.register_plan_worktree(
            self.plan.id, str(self.repo), str(self.worktree), "plan/1-test"
        )

    def test_every_host_payload_normalizes_identity(self) -> None:
        payloads = {
            "opencode": {"sessionID": "oc-1", "agent": "build", "model": "m1"},
            "claude": {
                "session_id": "cl-1",
                "hook_event_name": "SessionStart",
                "agent": "build",
                "model": "m1",
            },
            "gemini": {"session_id": "gm-1", "source": "startup", "agent": "build"},
            "codex": {"thread_id": "cx-1", "agent": "build"},
            "cursor": {"workspace_roots": ["/repo"], "session_id": "cu-1", "agent": "build"},
        }
        for host, payload in payloads.items():
            with self.subTest(host=host):
                identity = services.extract_identity(host, payload, self.worktree, pid=1234)
                self.assertEqual(identity.host, host)
                self.assertTrue(identity.host_session)
                self.assertEqual(identity.agent, "build")
                self.assertEqual(identity.cwd, str(self.worktree))
                self.assertEqual(identity.pid, 1234)

    def test_a_child_payload_is_a_subagent_with_its_parent_session(self) -> None:
        payload = {"session_id": "child-1", "parent_session_id": "parent-1"}
        identity = services.extract_identity("claude", payload, self.worktree)
        self.assertEqual(identity.role, "subagent")
        self.assertEqual(identity.parent_session, "parent-1")

    def test_managed_start_binds_plan_and_claimed_task(self) -> None:
        self.store.claim_task(self.task.id, "ana")
        agent = services.start_agent(
            self.store,
            "ana",
            host="opencode",
            host_session="host-1",
            agent="builder",
            plan_id=self.plan.id,
            cwd=str(self.worktree),
        )
        self.assertEqual(agent.plan_id, self.plan.id)
        self.assertEqual(agent.task_id, self.task.id)
        self.assertEqual(agent.worktree, str(self.worktree))
        self.assertEqual(len(agent.head_sha), 40)
        self.assertEqual(agent.branch, "plan/1-test")

    def test_ambiguous_worktree_refusal_writes_no_row(self) -> None:
        other = self.store.add_plan("Other")
        self.store.register_plan_worktree(
            other.id, str(self.repo), str(self.worktree), "plan/1-test"
        )
        with self.assertRaises(AgentStartError) as caught:
            services.start_agent(
                self.store,
                "ana",
                host="opencode",
                host_session="host-1",
                agent="builder",
                cwd=str(self.worktree),
            )
        self.assertIn("more than one plan", str(caught.exception))
        self.assertEqual(self.store.list_agents(), [])

    def test_force_reason_is_the_only_override(self) -> None:
        with self.assertRaises(AgentStartError):
            services.start_agent(
                self.store,
                "ana",
                host="manual",
                agent="builder",
                plan_id=self.plan.id,
                cwd=str(self.repo / "missing"),
            )
        agent = services.start_agent(
            self.store,
            "ana",
            host="manual",
            agent="builder",
            plan_id=self.plan.id,
            cwd=str(self.repo / "missing"),
            force=True,
            reason="pairing",
        )
        self.assertTrue(agent.unbound_reason.startswith("override: pairing"))

    def test_each_host_event_writes_one_transition(self) -> None:
        identity = services.extract_identity("opencode", {"sessionID": "host-1"}, self.worktree)
        agent = services.apply_event(self.store, "ana", "session-start", identity)
        assert agent is not None
        for event in ("prompt-submit", "pre-tool", "post-tool", "stop", "pre-compact"):
            services.apply_event(self.store, "ana", event, identity)
        self.assertEqual(
            [row.event for row in self.store.agent_events(agent.id)],
            ["pre-compact", "stop", "post-tool", "pre-tool", "prompt-submit", "start"],
        )
        self.assertEqual(len(self.store.agent_events(agent.id)), 6)

    def test_child_events_link_their_parent_and_end_with_it(self) -> None:
        parent = services.apply_event(
            self.store,
            "ana",
            "session-start",
            services.extract_identity("opencode", {"sessionID": "parent"}, self.worktree),
        )
        assert parent is not None
        child = services.apply_event(
            self.store,
            "ana",
            "session-start",
            services.extract_identity(
                "opencode",
                {"sessionID": "child", "parent_session": "parent"},
                self.worktree,
            ),
        )
        assert child is not None
        self.assertEqual(child.parent_id, parent.id)
        self.assertEqual(child.role, "subagent")
        ended = services.end_agent(self.store, parent.id, "ana", summary="done")
        self.assertEqual(ended.status, "ended")
        self.assertEqual(self.store.get_agent(child.id).status, "ended")

    def test_a_dead_pid_is_lost_and_never_closed_by_time(self) -> None:
        agent = self.store.add_agent(
            "ana", host="manual", agent="builder", pid=999_999, process_start="1"
        )
        with (
            mock.patch("lazyplan.services.agents.process_alive", return_value=False),
            mock.patch("lazyplan.infrastructure.process.process_start", return_value="1"),
        ):
            lost = services.sweep_lost(self.store)
        self.assertEqual([row.id for row in lost], [agent.id])
        with mock.patch("lazyplan.services.agents.process_alive", return_value=True):
            self.assertEqual(services.sweep_lost(self.store, now=time.time() + 86_400), [])
        self.assertEqual(self.store.get_agent(agent.id).status, "lost")


if __name__ == "__main__":
    unittest.main()
