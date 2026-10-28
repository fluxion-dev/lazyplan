"""Forge identity: GitHub remote parsing and provider detection."""

import unittest

from lazyplan.forge import (
    AuthStatus,
    GitHubForge,
    RepoRef,
    UnsupportedRemote,
    detect_forge,
    forges,
    parse_pull_url,
    redact,
    resolve_auth,
)


class TestForge(unittest.TestCase):
    def setUp(self):
        self.forge = GitHubForge()

    def test_registry_has_github(self):
        self.assertTrue(any(forge.name == "github" for forge in forges()))

    def test_parse_https_and_ssh_remotes(self):
        expected = RepoRef("github", "github.com", "org", "repo")
        for remote in (
            "https://github.com/org/repo.git",
            "https://github.com/org/repo",
            "https://github.com/org/repo/",
            "https://user@github.com/org/repo.git",
            "git@github.com:org/repo.git",
            "ssh://git@github.com/org/repo.git",
            "git+ssh://git@github.com/org/repo.git",
            "git://github.com/org/repo.git",
        ):
            with self.subTest(remote=remote):
                self.assertEqual(self.forge.parse_remote(remote), expected)

    def test_preserves_owner_and_repo_case(self):
        ref = self.forge.parse_remote("https://github.com/Org/Repo.git")
        assert ref is not None
        self.assertEqual((ref.owner, ref.repo), ("Org", "Repo"))
        self.assertEqual(ref.slug, "Org/Repo")
        self.assertEqual(ref.web_url, "https://github.com/Org/Repo")

    def test_other_hosts_raise(self):
        for remote in (
            "https://gitlab.com/org/repo.git",
            "git@gitlab.com:org/repo.git",
            "https://github.enterprise.test/org/repo.git",
        ):
            with self.subTest(remote=remote):
                with self.assertRaises(UnsupportedRemote):
                    self.forge.parse_remote(remote)

    def test_malformed_github_paths_raise(self):
        for remote in (
            "https://github.com/org",
            "https://github.com/org/repo/extra",
            "git@github.com:org",
        ):
            with self.subTest(remote=remote):
                with self.assertRaises(UnsupportedRemote):
                    self.forge.parse_remote(remote)

    def test_local_and_empty_remotes_are_ignored(self):
        for remote in ("", "/tmp/repo", "../repo", "repo.git"):
            with self.subTest(remote=remote):
                self.assertIsNone(self.forge.parse_remote(remote))

    def test_detect_forge(self):
        found = detect_forge("git@github.com:org/repo.git")
        assert found is not None
        forge, ref = found
        self.assertEqual(forge.name, "github")
        self.assertEqual(ref.owner, "org")
        self.assertEqual(ref.repo, "repo")
        self.assertIsNone(detect_forge("git@gitlab.com:org/repo.git"))
        self.assertIsNone(detect_forge("/tmp/repo"))

    def test_parse_pull_url(self):
        parsed = parse_pull_url("https://github.com/org/repo/pull/42")
        assert parsed is not None
        ref, number = parsed
        self.assertEqual((ref.owner, ref.repo, number), ("org", "repo", 42))
        for url in (
            "https://gitlab.com/org/repo/pull/42",
            "https://github.com/org/repo/issues/42",
            "https://github.com/org/repo/pull/nope",
        ):
            with self.subTest(url=url):
                self.assertIsNone(parse_pull_url(url))

    def test_auth_precedence_and_gh_fallback(self):
        status = resolve_auth(
            {
                "LAZYPLAN_GITHUB_TOKEN": "lazy",
                "GITHUB_TOKEN": "github",
                "GH_TOKEN": "gh",
            }
        )
        self.assertEqual(status.source, "LAZYPLAN_GITHUB_TOKEN")
        self.assertEqual(status.token, "lazy")
        status = resolve_auth({"GITHUB_TOKEN": "github", "GH_TOKEN": "gh"})
        self.assertEqual(status.source, "GITHUB_TOKEN")
        status = resolve_auth({"GH_TOKEN": " gh "})
        self.assertEqual(status.source, "GH_TOKEN")
        self.assertEqual(status.token, "gh")
        status = resolve_auth({}, gh_runner=lambda: "cli-token")
        self.assertEqual(status.source, "gh")
        self.assertEqual(status.token, "cli-token")
        status = resolve_auth({}, gh_runner=lambda: None)
        self.assertEqual(status.source, "none")
        self.assertFalse(status.available)

    def test_auth_repr_hides_the_token(self):
        status = resolve_auth({"GITHUB_TOKEN": "super-secret"})
        self.assertTrue(status.available)
        self.assertNotIn("super-secret", repr(status))
        self.assertEqual(AuthStatus().source, "none")

    def test_redact_removes_tokens_and_token_shapes(self):
        self.assertEqual(redact("token super-secret", "super-secret"), "token [redacted]")
        self.assertEqual(redact("ghp_" + "a" * 30), "[redacted]")
        self.assertEqual(redact("github_pat_" + "b" * 30), "[redacted]")
        self.assertEqual(redact("ordinary error"), "ordinary error")


if __name__ == "__main__":
    unittest.main()
