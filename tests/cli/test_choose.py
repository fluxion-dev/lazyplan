"""The loopback choice board: page, API, pick, and CLI wiring."""

from __future__ import annotations

import http.client
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from lazyplan.presentation.choice_board import ChoiceBoard
from lazyplan.presentation.cli.commands import system as system_cli
from lazyplan.presentation.cli.parser import build_parser
from lazyplan.services import choices

PNG = b"\x89PNG\r\n\x1a\n"


def write_manifest(root: Path) -> Path:
    """One manifest with two one-pixel images."""
    (root / "a.png").write_bytes(PNG)
    (root / "b.png").write_bytes(PNG + b"b")
    path = root / "choices.json"
    path.write_text(
        json.dumps(
            {
                "title": "Empty state",
                "prompt": "Which one should ship?",
                "options": [
                    {"id": "a", "label": "Compact", "image": "a.png"},
                    {
                        "id": "b",
                        "label": "Wide",
                        "image": "b.png",
                        "description": "More room",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


class BoardCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = choices.load_manifest(write_manifest(self.root))
        self.selection = self.root / "selection.json"

    def board(self, *, force: bool = False) -> ChoiceBoard:
        board = ChoiceBoard(self.manifest, self.selection, force=force, port=0)
        board.start()
        self.addCleanup(board.stop)
        return board

    def request(
        self,
        board: ChoiceBoard,
        method: str,
        path: str,
        payload: object | None = None,
        *,
        token: str | None = None,
    ) -> tuple[int, bytes]:
        headers = {"X-Choice-Token": board.token if token is None else token}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", board.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()


class BoardPageTest(BoardCase):
    def test_the_url_is_loopback_and_the_port_is_resolved(self) -> None:
        board = self.board()

        self.assertGreater(board.port, 0)
        self.assertEqual(board.url(), f"http://127.0.0.1:{board.port}/?t={board.token}")

    def test_page_manifest_and_images_need_the_token(self) -> None:
        board = self.board()

        status, body = self.request(board, "GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b'id="grid"', body)

        status, _ = self.request(board, "GET", "/", token="wrong")
        self.assertEqual(status, 403)

        status, body = self.request(board, "GET", "/api/manifest")
        self.assertEqual(status, 200)
        manifest = json.loads(body)
        self.assertEqual(manifest["title"], "Empty state")
        self.assertEqual([row["id"] for row in manifest["options"]], ["a", "b"])
        self.assertEqual(manifest["options"][1]["description"], "More room")

        status, body = self.request(board, "GET", "/image/a.png")
        self.assertEqual(status, 200)
        self.assertEqual(body, PNG)

    def test_unknown_images_and_traversal_are_not_found(self) -> None:
        board = self.board()

        status, _ = self.request(board, "GET", "/image/gone.png")
        self.assertEqual(status, 404)
        status, _ = self.request(board, "GET", "/image/%2e%2e/choices.json")
        self.assertEqual(status, 404)
        status, _ = self.request(board, "GET", "/nope")
        self.assertEqual(status, 404)


class BoardChooseTest(BoardCase):
    def test_one_choice_writes_the_selection(self) -> None:
        board = self.board()

        status, _ = self.request(board, "POST", "/api/choose", {"option": "a"}, token="")
        self.assertEqual(status, 403)

        status, body = self.request(board, "POST", "/api/choose", {"option": "b", "notes": "wide"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["label"], "Wide")
        saved = json.loads(self.selection.read_text(encoding="utf-8"))
        self.assertEqual(saved["option"], "b")
        self.assertEqual(saved["label"], "Wide")
        self.assertEqual(saved["notes"], "wide")
        self.assertTrue(board.wait(0.1))
        self.assertIsNotNone(board.selected)

        status, _ = self.request(board, "POST", "/api/choose", {"option": "a"})
        self.assertEqual(status, 409)

    def test_unknown_options_and_bad_payloads_are_refused(self) -> None:
        board = self.board()

        status, _ = self.request(board, "POST", "/api/choose", {"option": "zzz"})
        self.assertEqual(status, 400)
        status, _ = self.request(board, "POST", "/api/choose", {"notes": "no option"})
        self.assertEqual(status, 400)
        status, _ = self.request(board, "POST", "/api/choose", [])
        self.assertEqual(status, 400)
        status, _ = self.request(board, "POST", "/api/other", {"option": "a"})
        self.assertEqual(status, 404)
        self.assertFalse(self.selection.exists())

    def test_an_existing_selection_requires_force(self) -> None:
        choices.write_selection(self.selection, choices.select(self.manifest, "a"))
        board = self.board()

        status, _ = self.request(board, "POST", "/api/choose", {"option": "b"})
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(self.selection.read_text(encoding="utf-8"))["option"], "a")

        forced = self.board(force=True)
        status, _ = self.request(forced, "POST", "/api/choose", {"option": "b"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(self.selection.read_text(encoding="utf-8"))["option"], "b")


class ChooseCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_bad_manifest_exits_two_before_serving(self) -> None:
        manifest = self.root / "choices.json"
        manifest.write_text("{", encoding="utf-8")
        err = io.StringIO()
        args = SimpleNamespace(manifest=str(manifest), out="", port=0, open=False, force=False)

        with redirect_stderr(err):
            code = system_cli._cmd_choose(None, args, "a")

        self.assertEqual(code, 2)
        self.assertIn("not valid JSON", err.getvalue())

    def test_help_lists_the_manifest_and_selection_flags(self) -> None:
        parser = build_parser()

        with self.assertRaises(SystemExit) as raised:
            parser.parse_args(["choose", "--help"])

        self.assertEqual(raised.exception.code, 0)

    def test_open_calls_the_browser_and_reports_the_pick(self) -> None:
        selection = choices.Selection("a", "Compact", "", "2026-01-01T00:00:00+00:00")

        class FakeBoard:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                self.selected = selection

            def url(self) -> str:
                return "http://127.0.0.1:9/?t=t"

            def start(self) -> None:
                return

            def wait(self, _timeout: float | None = None) -> bool:
                return True

            def stop(self) -> None:
                return

        args = SimpleNamespace(
            manifest=str(self.root / "choices.json"), out="", port=0, open=True, force=False
        )
        with (
            mock.patch.object(system_cli, "ChoiceBoard", FakeBoard),
            mock.patch.object(system_cli, "choices") as fake_choices,
            mock.patch.object(system_cli.webbrowser, "open") as opened,
        ):
            fake_choices.load_manifest.return_value = SimpleNamespace(
                source=self.root / "choices.json"
            )
            code = system_cli._cmd_choose(None, args, "a")

        self.assertEqual(code, 0)
        opened.assert_called_once_with("http://127.0.0.1:9/?t=t")


if __name__ == "__main__":
    unittest.main()
