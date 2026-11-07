"""External reference rules: URLs, providers, ids, and kinds."""

from __future__ import annotations

import unittest

from lazyplan.core.policies.refs import (
    external_id_from_url,
    infer_provider,
    normalize_ref,
    validate_kind,
    validate_url,
)


class TestRefPolicy(unittest.TestCase):
    def test_valid_urls_and_credentials(self) -> None:
        self.assertEqual(
            validate_url(" https://github.com/o/r/issues/7 "), "https://github.com/o/r/issues/7"
        )
        for value in ("ftp://x/y", "https://user:pass@x/y", "not a url", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_url(value)

    def test_provider_inference(self) -> None:
        self.assertEqual(infer_provider("https://github.com/o/r"), "github")
        self.assertEqual(infer_provider("https://linear.app/x/issue/Y-1"), "linear")
        self.assertEqual(infer_provider("https://org.atlassian.net/browse/X"), "jira")
        self.assertEqual(infer_provider("https://example.com/x"), "other")

    def test_kind_and_external_id(self) -> None:
        self.assertEqual(validate_kind(""), "issue")
        self.assertEqual(validate_kind("DOC"), "doc")
        with self.assertRaises(ValueError):
            validate_kind("ticket")
        self.assertEqual(external_id_from_url("https://x/y/issues/42/"), "42")
        self.assertEqual(external_id_from_url("https://x"), "")

    def test_normalize_ref_applies_defaults(self) -> None:
        ref = normalize_ref("https://github.com/o/r/issues/7")
        self.assertEqual(ref["provider"], "github")
        self.assertEqual(ref["kind"], "issue")
        self.assertEqual(ref["external_id"], "7")


if __name__ == "__main__":
    unittest.main()
