"""GitHub read client: cache, ETag revalidation, rate limits, redaction."""

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.forge import AuthStatus, RepoRef
from lazyplan.github import GitHubClient, GitHubError, GitHubRateLimit
from lazyplan.store import Store

REF = RepoRef("github", "github.com", "org", "repo")


class FakeResponse:
    def __init__(self, data, status=200, headers=None):
        self._body = json.dumps(data).encode()
        self.status = status
        self.headers = headers or {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def http_error(code, headers=None, body=b""):
    return urllib.error.HTTPError(
        "https://api.github.com/x",
        code,
        "error",
        headers or {},
        io.BytesIO(body),
    )


class TestGitHubClient(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))
        self.auth = AuthStatus(source="TEST", token="secret-token")
        self.client = GitHubClient(auth=self.auth, store=self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pulls_for_branch_and_merge_are_read_only(self):
        calls = []

        def opener(request, timeout):
            calls.append(request)
            return FakeResponse([{"number": 1}])

        with mock.patch("lazyplan.github.urllib.request.urlopen", side_effect=opener):
            branch = self.client.pulls_for_branch(REF, "task/7-fix")
            merge = self.client.pulls_for_merge(REF, "a" * 40)
        self.assertEqual(branch.data, [{"number": 1}])
        self.assertEqual(merge.data, [{"number": 1}])
        self.assertIn("/pulls?head=org:task/7-fix&state=all", calls[0].full_url)
        self.assertIn(f"/commits/{'a' * 40}/pulls", calls[1].full_url)
        self.assertTrue(all(call.get_method() == "GET" for call in calls))

    def test_get_caches_and_revalidates_with_etag(self):
        calls = []

        def opener(request, timeout):
            calls.append(request)
            return FakeResponse([{"number": 1}], headers={"ETag": 'W/"1"'})

        with mock.patch("lazyplan.github.urllib.request.urlopen", side_effect=opener):
            first = self.client.get_json("/repos/org/repo/pulls/1")
            second = self.client.get_json("/repos/org/repo/pulls/1")
        self.assertEqual(first.data, [{"number": 1}])
        self.assertFalse(first.from_cache)
        self.assertTrue(second.from_cache)
        self.assertEqual(len(calls), 1)
        cached = self.store.cache_get("github:/repos/org/repo/pulls/1")
        assert cached is not None
        self.assertEqual(cached["etag"], 'W/"1"')

        with mock.patch(
            "lazyplan.github.urllib.request.urlopen",
            side_effect=http_error(304),
        ) as urlopen:
            third = self.client.get_json("/repos/org/repo/pulls/1", force=True)
        self.assertEqual(len(urlopen.call_args_list), 1)
        self.assertTrue(third.from_cache)
        self.assertEqual(third.status, 304)

    def test_authorization_header_is_sent(self):
        seen = {}

        def opener(request, timeout):
            seen.update(request.headers)
            return FakeResponse({"ok": True})

        with mock.patch("lazyplan.github.urllib.request.urlopen", side_effect=opener):
            self.client.get_json("/x")
        self.assertEqual(seen.get("Authorization"), "Bearer secret-token")

    def test_rate_limit_errors_are_typed_and_redacted(self):
        with mock.patch(
            "lazyplan.github.urllib.request.urlopen",
            side_effect=http_error(
                403,
                headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "123"},
            ),
        ):
            with self.assertRaises(GitHubRateLimit) as caught:
                self.client.get_json("/x", force=True)
        self.assertEqual(caught.exception.reset_at, 123)
        self.assertIn("rate limit", str(caught.exception))
        self.assertNotIn("secret-token", str(caught.exception))

        with mock.patch(
            "lazyplan.github.urllib.request.urlopen",
            side_effect=http_error(429, headers={"Retry-After": "30"}),
        ):
            with self.assertRaises(GitHubRateLimit) as caught:
                self.client.get_json("/x", force=True)
        self.assertEqual(caught.exception.retry_after, 30)
        self.assertIn("30s", str(caught.exception))

    def test_error_body_is_redacted(self):
        body = b'{"message": "bad token secret-token"}'
        with mock.patch(
            "lazyplan.github.urllib.request.urlopen",
            side_effect=http_error(500, body=body),
        ):
            with self.assertRaises(GitHubError) as caught:
                self.client.get_json("/x", force=True)
        self.assertNotIn("secret-token", str(caught.exception))
        self.assertIn("[redacted]", str(caught.exception))

    def test_network_failure_falls_back_to_stale_cache(self):
        self.store.cache_put("github:/x", 'W/"1"', 1, '{"cached": true}')
        with mock.patch(
            "lazyplan.github.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            result = self.client.get_json("/x", force=True)
        self.assertTrue(result.from_cache)
        self.assertTrue(result.stale)
        self.assertEqual(result.data, {"cached": True})

    def test_read_helpers_build_github_paths(self):
        paths = []

        def opener(request, timeout):
            paths.append(request.full_url)
            return FakeResponse([])

        with mock.patch("lazyplan.github.urllib.request.urlopen", side_effect=opener):
            self.client.pulls_for_commit(REF, "abc")
            self.client.pull(REF, 7)
            self.client.checks(REF, "abc")
            self.client.reviews(REF, 7)
        self.assertEqual(
            paths,
            [
                "https://api.github.com/repos/org/repo/commits/abc/pulls",
                "https://api.github.com/repos/org/repo/pulls/7",
                "https://api.github.com/repos/org/repo/commits/abc/check-runs",
                "https://api.github.com/repos/org/repo/pulls/7/reviews",
            ],
        )


if __name__ == "__main__":
    unittest.main()
