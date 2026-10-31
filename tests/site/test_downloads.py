"""Offline tests for the PyPI and GitHub download snapshot."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import urllib.error
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from tests.support.paths import ROOT

SPEC = importlib.util.spec_from_file_location(
    "fetch_downloads", ROOT / "tools" / "fetch-downloads.py"
)
assert SPEC is not None and SPEC.loader is not None
downloads = importlib.util.module_from_spec(SPEC)
sys.modules["fetch_downloads"] = downloads
SPEC.loader.exec_module(downloads)

FIXED = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
PACKAGE = "lazyplan-tui"
REPO = "fluxion-dev/lazyplan"


def payload() -> dict:
    data = []
    for day, without in enumerate(range(100, 900, 100), start=20):
        data.append(
            {
                "category": "without_mirrors",
                "date": f"2026-10-{day}",
                "downloads": without,
            }
        )
        data.append(
            {
                "category": "with_mirrors",
                "date": f"2026-10-{day}",
                "downloads": without * 10,
            }
        )
    return {"data": data, "package": PACKAGE, "type": "overall_downloads"}


def releases_page_one() -> list[dict]:
    return [
        {"assets": [{"name": "install.sh", "download_count": 3}]},
        {"assets": [{"name": "lazyplan-tui.whl", "download_count": 1}]},
    ]


def releases_page_two() -> list[dict]:
    return [{"assets": [{"name": "install.sh", "download_count": 2}]}]


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def json_opener(body: object):
    def open_url(_request, timeout=0):
        assert timeout > 0
        return FakeResponse(json.dumps(body).encode())

    return open_url


def raw_opener(body: bytes):
    def open_url(_request, timeout=0):
        assert timeout > 0
        return FakeResponse(body)

    return open_url


def pypi_opener(body: object = None):
    return json_opener(payload() if body is None else body)


def github_opener(pages: list[list[dict]] | None = None):
    pages = pages or [releases_page_one(), releases_page_two()]

    def open_url(request, timeout=0):
        assert timeout > 0
        page = int(str(request.full_url).rsplit("page=", 1)[1])
        body = pages[page - 1] if page <= len(pages) else []
        return FakeResponse(json.dumps(body).encode())

    return open_url


def broken(_request, timeout=0):
    raise urllib.error.URLError("offline")


class TestSummarize(unittest.TestCase):
    def test_splits_both_pypi_series(self):
        snapshot = downloads.summarize(payload(), FIXED)
        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["schema"], 2)
        self.assertEqual(snapshot["generated_at"], "2026-10-27T12:00:00Z")
        mirrors = snapshot["channels"]["pypi_with_mirrors"]
        direct = snapshot["channels"]["pypi_direct"]
        self.assertEqual(mirrors["total"], 36000)
        self.assertEqual(mirrors["last_7_days"], 35000)
        self.assertEqual(mirrors["metric"], "with_mirrors")
        self.assertEqual(direct["total"], 3600)
        self.assertEqual(direct["last_7_days"], 3500)
        self.assertEqual(direct["metric"], "without_mirrors")

    def test_missing_series_marks_one_channel_unavailable(self):
        body = {"data": [row for row in payload()["data"] if row["category"] == "with_mirrors"]}
        snapshot = downloads.summarize(body, FIXED)
        self.assertTrue(snapshot["channels"]["pypi_with_mirrors"]["available"])
        self.assertFalse(snapshot["channels"]["pypi_direct"]["available"])

    def test_rejects_negative_downloads_for_a_series(self):
        body = payload()
        body["data"][0]["downloads"] = -1
        snapshot = downloads.summarize(body, FIXED)
        self.assertFalse(snapshot["channels"]["pypi_direct"]["available"])
        self.assertTrue(snapshot["channels"]["pypi_with_mirrors"]["available"])

    def test_rejects_missing_series(self):
        body = {"data": [{"category": "other", "date": "2026-10-20", "downloads": 1}]}
        with self.assertRaises(downloads.StatsError):
            downloads.summarize(body, FIXED)

    def test_rejects_missing_data(self):
        with self.assertRaises(downloads.StatsError):
            downloads.summarize({}, FIXED)


class TestGitHubAssets(unittest.TestCase):
    def test_sums_artifacts_across_releases(self):
        channel = downloads.summarize_github(releases_page_one() + releases_page_two())
        self.assertTrue(channel["available"])
        self.assertEqual(channel["total"], 6)
        self.assertEqual(channel["artifacts"]["install.sh"], 5)

    def test_empty_release_list_is_available_zero(self):
        channel = downloads.summarize_github([])
        self.assertTrue(channel["available"])
        self.assertEqual(channel["total"], 0)

    def test_rejects_negative_asset_count(self):
        with self.assertRaises(downloads.StatsError):
            downloads.summarize_github([{"assets": [{"name": "x", "download_count": -1}]}])

    def test_paginates_until_a_short_page(self):
        with mock.patch.object(downloads, "PAGE_SIZE", 2):
            releases = downloads.fetch_releases(REPO, opener=github_opener())
        self.assertEqual(len(releases), 3)


class TestFetchAndWrite(unittest.TestCase):
    def test_fetch_parses_json(self):
        payload_data = downloads.fetch_payload(opener=pypi_opener())
        self.assertEqual(payload_data["package"], PACKAGE)

    def test_invalid_json_raises(self):
        with self.assertRaises(downloads.StatsError):
            downloads.fetch_payload(opener=raw_opener(b"not json"))

    def test_write_is_atomic_and_leaves_no_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "downloads.json"
            downloads.write_snapshot(out, {"available": True})
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")), {"available": True})
            self.assertEqual([p.name for p in out.parent.iterdir()], ["downloads.json"])

    def test_total_failure_writes_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "downloads.json"
            snapshot = downloads.run(out=out, opener=broken, now=FIXED)
            self.assertFalse(snapshot["available"])
            self.assertEqual(snapshot["generated_at"], "2026-10-27T12:00:00Z")
            self.assertEqual(snapshot["channels"], {})
            self.assertFalse(json.loads(out.read_text(encoding="utf-8"))["available"])

    def test_partial_failure_keeps_the_working_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "downloads.json"
            with mock.patch.object(downloads, "PAGE_SIZE", 2):
                snapshot = downloads.run(
                    out=out,
                    opener=broken,
                    github_opener=github_opener(),
                    now=FIXED,
                )
            self.assertTrue(snapshot["available"])
            self.assertFalse(snapshot["channels"]["pypi_direct"]["available"])
            self.assertFalse(snapshot["channels"]["pypi_with_mirrors"]["available"])
            self.assertEqual(snapshot["channels"]["github_assets"]["total"], 6)

    def test_success_writes_both_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "downloads.json"
            with mock.patch.object(downloads, "PAGE_SIZE", 2):
                snapshot = downloads.run(
                    out=out,
                    opener=pypi_opener(),
                    github_opener=github_opener(),
                    now=FIXED,
                )
            self.assertTrue(snapshot["available"])
            stored = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(stored["channels"]["pypi_with_mirrors"]["total"], 36000)
            self.assertEqual(stored["channels"]["github_assets"]["total"], 6)


if __name__ == "__main__":
    unittest.main()
