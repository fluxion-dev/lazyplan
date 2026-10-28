"""Offline tests for the PyPI download snapshot."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import urllib.error
from datetime import UTC, datetime
from pathlib import Path

from tests.support.paths import ROOT

SPEC = importlib.util.spec_from_file_location(
    "fetch_downloads", ROOT / "tools" / "fetch-downloads.py"
)
assert SPEC is not None and SPEC.loader is not None
downloads = importlib.util.module_from_spec(SPEC)
sys.modules["fetch_downloads"] = downloads
SPEC.loader.exec_module(downloads)

FIXED = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


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
    return {"data": data, "package": "lazyplan-tui", "type": "overall_downloads"}


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def opener(body: bytes):
    def open_url(_request, timeout=0):
        assert timeout > 0
        return FakeResponse(body)

    return open_url


class TestSummarize(unittest.TestCase):
    def test_uses_without_mirrors_only(self):
        snapshot = downloads.summarize(payload(), FIXED)
        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["total"], 3600)
        self.assertEqual(snapshot["last_7_days"], 3500)
        self.assertEqual(snapshot["metric"], "without_mirrors")
        self.assertEqual(snapshot["generated_at"], "2026-10-27T12:00:00Z")

    def test_rejects_negative_downloads(self):
        body = payload()
        body["data"][0]["downloads"] = -1
        with self.assertRaises(downloads.StatsError):
            downloads.summarize(body, FIXED)

    def test_rejects_missing_series(self):
        body = {"data": [{"category": "with_mirrors", "date": "2026-10-20", "downloads": 1}]}
        with self.assertRaises(downloads.StatsError):
            downloads.summarize(body, FIXED)

    def test_rejects_missing_data(self):
        with self.assertRaises(downloads.StatsError):
            downloads.summarize({}, FIXED)


class TestFetchAndWrite(unittest.TestCase):
    def test_fetch_parses_json(self):
        body = json.dumps(payload()).encode()
        self.assertEqual(downloads.fetch_payload(opener=opener(body))["package"], "lazyplan-tui")

    def test_invalid_json_raises(self):
        with self.assertRaises(downloads.StatsError):
            downloads.fetch_payload(opener=opener(b"not json"))

    def test_write_is_atomic_and_leaves_no_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "downloads.json"
            downloads.write_snapshot(out, {"available": True})
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")), {"available": True})
            self.assertEqual([p.name for p in out.parent.iterdir()], ["downloads.json"])

    def test_network_failure_writes_unavailable(self):
        def broken(_request, timeout=0):
            raise urllib.error.URLError("offline")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "downloads.json"
            snapshot = downloads.run(out=out, opener=broken, now=FIXED)
            self.assertFalse(snapshot["available"])
            self.assertEqual(snapshot["generated_at"], "2026-10-27T12:00:00Z")
            self.assertFalse(json.loads(out.read_text(encoding="utf-8"))["available"])

    def test_success_writes_snapshot(self):
        body = json.dumps(payload()).encode()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "downloads.json"
            snapshot = downloads.run(out=out, opener=opener(body), now=FIXED)
            self.assertTrue(snapshot["available"])
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["total"], 3600)


if __name__ == "__main__":
    unittest.main()
