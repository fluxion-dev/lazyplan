"""Staged update cache, wheel verification, and apply-on-launch behavior."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan import update_stage
from lazyplan.upgrade import PIPX, VENV

WHEEL = b"fake wheel bytes"
VERSION = "0.28.0"
FILENAME = f"lazyplan_tui-{VERSION}-py3-none-any.whl"
URL = f"https://files.pythonhosted.org/packages/x/{FILENAME}"
SHA = hashlib.sha256(WHEEL).hexdigest()


def pypi_payload(**overrides: object) -> dict:
    item = {
        "packagetype": "bdist_wheel",
        "filename": FILENAME,
        "url": URL,
        "digests": {"sha256": SHA},
        "size": len(WHEEL),
        "yanked": False,
    }
    item.update(overrides)
    return {"urls": [item]}


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.offset = 0

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        if self.offset >= len(self.body):
            return b""
        end = len(self.body) if size < 0 else self.offset + size
        chunk = self.body[self.offset : end]
        self.offset = end
        return chunk


def api_opener(payload: object | None = None, wheel: bytes = WHEEL):
    body = json.dumps(pypi_payload() if payload is None else payload).encode()

    def open_url(request, timeout=0):
        assert timeout > 0
        if "pypi.org" in str(request.full_url):
            return FakeResponse(body)
        return FakeResponse(wheel)

    return open_url


def runner(returncode: int = 0, stderr: str = ""):
    result = mock.Mock(returncode=returncode, stderr=stderr, stdout="")
    return mock.Mock(return_value=result)


class TestPayload(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = self.tmp.name

    def test_roundtrip_and_malformed(self):
        update = update_stage.stage_update(
            VERSION, PIPX, home=self.home, opener=api_opener(), installed="0.27.0", now=1000.0
        )
        self.assertEqual(update_stage.read_stage(home=self.home), update)
        update_stage._state_path(update_stage.STAGED, self.home).write_text("{bad")
        self.assertIsNone(update_stage.read_stage(home=self.home))

    def test_rejects_untrusted_fields(self):
        base = update_stage.StagedUpdate(
            VERSION, PIPX, FILENAME, URL, SHA, len(WHEEL), 1000.0
        ).payload()
        for key, value in (
            ("schema", 2),
            ("method", "rpm"),
            ("filename", "../wheel.whl"),
            ("filename", "not-a-wheel.whl"),
            ("url", "http://files.pythonhosted.org/x.whl"),
            ("url", "https://example.com/x.whl"),
            ("sha256", "abc"),
            ("size", -1),
        ):
            data = dict(base)
            data[key] = value
            self.assertIsNone(update_stage.stage_from_payload(data), key)

    def test_wheel_path_stays_inside_the_update_dir(self):
        update = update_stage.StagedUpdate(
            VERSION, PIPX, "../escape.whl", URL, SHA, len(WHEEL), 1000.0
        )
        with self.assertRaises(update_stage.StageError):
            update_stage.wheel_path(update, self.home)


class TestMetadata(unittest.TestCase):
    def test_selects_the_wheel(self):
        meta = update_stage.fetch_metadata(VERSION, opener=api_opener())
        self.assertEqual(meta["filename"], FILENAME)
        self.assertEqual(meta["sha256"], SHA)

    def test_rejects_yanked_or_bad_host(self):
        for payload in (
            pypi_payload(yanked=True),
            pypi_payload(url="https://example.com/x.whl"),
            pypi_payload(filename="tool-1.0.tar.gz", packagetype="sdist"),
        ):
            with self.assertRaises(update_stage.StageError):
                update_stage.fetch_metadata(VERSION, opener=api_opener(payload))

    def test_download_rejects_bad_digest_and_leaves_no_temp(self):
        meta = update_stage.fetch_metadata(VERSION, opener=api_opener())
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / FILENAME
            with mock.patch.dict(meta, {"sha256": "0" * 64}):
                with self.assertRaises(update_stage.StageError):
                    update_stage.download_wheel(meta, target, opener=api_opener())
            self.assertEqual(list(Path(tmp).iterdir()), [])


class TestStage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = self.tmp.name

    def test_stage_writes_marker_and_wheel(self):
        update = update_stage.stage_update(
            VERSION, PIPX, home=self.home, opener=api_opener(), installed="0.27.0", now=1000.0
        )
        self.assertTrue(update_stage.wheel_path(update, self.home).is_file())
        self.assertEqual(update_stage.read_stage(home=self.home), update)

    def test_rejects_non_upgradeable_method(self):
        with self.assertRaises(update_stage.StageError):
            update_stage.stage_update(
                VERSION, "rpm", home=self.home, opener=api_opener(), installed="0.27.0"
            )

    def test_rejects_downgrade_and_equal_before_fetch(self):
        calls: list[object] = []

        def opener(request, timeout=0):
            calls.append(request)
            raise AssertionError("network should not run")

        for version, installed in (("0.27.0", "0.27.1"), ("0.27.1", "0.27.1")):
            with self.subTest(version=version):
                with self.assertRaises(update_stage.StageError):
                    update_stage.stage_update(
                        version, PIPX, home=self.home, opener=opener, installed=installed
                    )
        self.assertEqual(calls, [])

    def test_new_stage_replaces_an_older_wheel(self):
        first = update_stage.stage_update(
            VERSION, PIPX, home=self.home, opener=api_opener(), installed="0.27.0", now=1.0
        )
        orphan = update_stage.update_dir(self.home) / "old.whl"
        orphan.write_bytes(b"old")
        self.assertTrue(update_stage.wheel_path(first, self.home).is_file())
        update_stage.stage_update(
            VERSION, PIPX, home=self.home, opener=api_opener(), installed="0.27.0", now=2.0
        )
        self.assertFalse(orphan.exists())


class TestApply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = self.tmp.name

    def _stage(self) -> update_stage.StagedUpdate:
        return update_stage.stage_update(
            VERSION, PIPX, home=self.home, opener=api_opener(), installed="0.27.0", now=1000.0
        )

    def test_claim_is_single_slot(self):
        self._stage()
        first = update_stage.claim_stage(self.home)
        assert first is not None
        self.assertIsNone(update_stage.claim_stage(self.home))

    def test_pipx_and_venv_commands(self):
        update = self._stage()
        pipx_runner = runner()
        with mock.patch.object(update_stage.shutil, "which", return_value="/usr/bin/pipx"):
            update_stage.apply_update(update, self.home, runner=pipx_runner, installed="0.27.0")
        command = pipx_runner.call_args[0][0]
        self.assertEqual(
            command[:3],
            ["pipx", "install", str(update_stage.wheel_path(update, self.home))],
        )
        self.assertEqual(command[-1], "--force")
        venv = update_stage.StagedUpdate(VERSION, VENV, FILENAME, URL, SHA, len(WHEEL), 1000.0)
        venv_runner = runner()
        update_stage.apply_update(
            venv, self.home, exe="/venv/bin/python", runner=venv_runner, installed="0.27.0"
        )
        self.assertEqual(venv_runner.call_args[0][0][0], "/venv/bin/python")

    def test_install_failure_raises(self):
        update = self._stage()
        with mock.patch.object(update_stage.shutil, "which", return_value="/usr/bin/pipx"):
            with self.assertRaises(update_stage.StageError):
                update_stage.apply_update(
                    update, self.home, runner=runner(1, "boom"), installed="0.27.0"
                )

    def test_applies_and_clears(self):
        update = update_stage.stage_update(
            VERSION, VENV, home=self.home, opener=api_opener(), installed="0.27.0", now=1000.0
        )
        self.assertTrue(update_stage.wheel_path(update, self.home).is_file())
        ok = runner()
        state, detail = update_stage.apply_on_launch(
            "0.27.2", self.home, exe="/venv/bin/python", runner=ok
        )
        self.assertEqual((state, detail), ("applied", VERSION))
        self.assertIsNone(update_stage.read_stage(home=self.home))
        self.assertEqual(list(update_stage.update_dir(self.home).iterdir()), [])

    def test_skips_when_already_current(self):
        self._stage()
        state, _ = update_stage.apply_on_launch(VERSION, self.home)
        self.assertEqual(state, "skipped")
        self.assertIsNone(update_stage.read_stage(home=self.home))

    def test_corrupt_wheel_parks_the_stage(self):
        update = self._stage()
        update_stage.wheel_path(update, self.home).unlink()
        state, detail = update_stage.apply_on_launch("0.27.2", self.home)
        self.assertEqual(state, "error")
        self.assertIn("corrupt", detail)
        self.assertEqual(update_stage.read_failure(self.home), detail)

    def test_failed_install_parks_the_stage(self):
        self._stage()
        with mock.patch.object(update_stage.shutil, "which", return_value="/usr/bin/pipx"):
            state, detail = update_stage.apply_on_launch(
                "0.27.2", self.home, runner=runner(1, "boom")
            )
        self.assertEqual(state, "error")
        self.assertIn("boom", detail)
        self.assertEqual(update_stage.read_failure(self.home), detail)
        update_stage.clear_failure(self.home)
        self.assertIsNone(update_stage.read_failure(self.home))

    def test_apply_update_rejects_downgrade_without_a_runner(self):
        older = update_stage.StagedUpdate(
            "0.27.0",
            PIPX,
            "lazyplan_tui-0.27.0-py3-none-any.whl",
            URL,
            SHA,
            len(WHEEL),
            1000.0,
        )
        run = runner()
        with self.assertRaises(update_stage.StageError):
            update_stage.apply_update(older, self.home, runner=run, installed="0.28.0")
        run.assert_not_called()

    def test_planted_downgrade_is_cleared_without_install(self):
        older = update_stage.StagedUpdate(
            "0.27.0",
            PIPX,
            "lazyplan_tui-0.27.0-py3-none-any.whl",
            URL,
            SHA,
            len(WHEEL),
            1000.0,
        )
        update_stage.write_stage(older, home=self.home)
        run = runner()
        state, detail = update_stage.apply_on_launch("0.28.0", self.home, runner=run)
        self.assertEqual((state, detail), ("downgrade", "0.27.0"))
        run.assert_not_called()
        self.assertIsNone(update_stage.read_stage(home=self.home))


if __name__ == "__main__":
    unittest.main()
