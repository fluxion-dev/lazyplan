"""Serve the visual choice board on a loopback port.

The board is a self-contained page plus a tiny JSON API. It binds 127.0.0.1,
requires a per-run token on every request, serves only images under the
manifest directory, and writes exactly one selection file.
"""

from __future__ import annotations

import json
import mimetypes
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from ..infrastructure.data_text import data_text
from ..services import choices

PAGE_FILE = "choice-board.html"
MAX_BODY = 16 * 1024
TOKEN_HEADER = "X-Choice-Token"


class ChoiceBoard:
    """One loopback server for one manifest and one selection file."""

    def __init__(
        self,
        manifest: choices.ChoiceManifest,
        selection_path: str | Path,
        *,
        force: bool = False,
        port: int = 0,
    ) -> None:
        self.manifest = manifest
        self.selection_path = Path(selection_path)
        self.force = force
        self.token = secrets.token_urlsafe(18)
        self.page = data_text(PAGE_FILE)
        self.selected: choices.Selection | None = None
        self._done = threading.Event()
        self._server = _BoardServer(("127.0.0.1", port), _Handler)
        self._server.board = self
        self._closed = False

    @property
    def port(self) -> int:
        """The bound port; resolved when the constructor asked for 0."""
        return int(self._server.server_address[1])

    def url(self) -> str:
        """The page URL, token included."""
        return f"http://127.0.0.1:{self.port}/?t={self.token}"

    def start(self) -> None:
        """Serve in a background thread; tests and the CLI both use this."""
        threading.Thread(
            target=self._server.serve_forever, name="choice-board", daemon=True
        ).start()

    def wait(self, timeout: float | None = None) -> bool:
        """Block until a choice is recorded, or the timeout elapses."""
        return self._done.wait(timeout)

    def stop(self) -> None:
        """Stop serving and release the port."""
        if self._closed:
            return
        self._closed = True
        self._server.shutdown()
        self._server.server_close()

    def record(self, selection: choices.Selection) -> None:
        """Keep the pick and wake the waiter after the file is written."""
        self.selected = selection
        self._done.set()


class _BoardServer(ThreadingHTTPServer):
    """Threading server carrying its board for the handler."""

    daemon_threads = True
    board: ChoiceBoard


class _Handler(BaseHTTPRequestHandler):
    """Static page, manifest JSON, images, and one choose endpoint."""

    server_version = "lpui-choose/1"
    server: _BoardServer

    def log_message(self, format: str, *args: object) -> None:
        """Stay quiet; the CLI owns the terminal."""

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(int(status))
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: object) -> None:
        self._send(
            status,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _token(self) -> str:
        header = self.headers.get(TOKEN_HEADER, "")
        query = parse_qs(urlparse(self.path).query).get("t", [""])[0]
        return header or query

    def _authorized(self) -> bool:
        if secrets.compare_digest(self._token(), self.server.board.token):
            return True
        self._json(HTTPStatus.FORBIDDEN, {"error": "missing or invalid token"})
        return False

    def _route(self) -> str:
        return unquote(urlparse(self.path).path) or "/"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler naming
        """Serve the page, the manifest, or one image."""
        if not self._authorized():
            return
        path = self._route()
        board = self.server.board
        if path == "/":
            self._send(
                HTTPStatus.OK,
                board.page.encode("utf-8"),
                "text/html; charset=utf-8",
            )
            return
        if path == "/api/manifest":
            options = [
                {
                    "id": option.id,
                    "label": option.label,
                    "description": option.description,
                    "image": quote(option.relative, safe="/"),
                }
                for option in board.manifest.options
            ]
            self._json(
                HTTPStatus.OK,
                {
                    "title": board.manifest.title,
                    "prompt": board.manifest.prompt,
                    "allow_notes": board.manifest.allow_notes,
                    "options": options,
                },
            )
            return
        if path.startswith("/image/"):
            relative = path[len("/image/") :]
            try:
                body = choices.image_bytes(board.manifest, relative)
            except choices.ChoiceError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "image not found"})
                return
            content_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
            self._send(HTTPStatus.OK, body, content_type)
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler naming
        """Accept one choice and write the selection file."""
        if self._route() != "/api/choose":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not self._authorized():
            return
        if self.server.board.selected is not None:
            self._json(HTTPStatus.CONFLICT, {"error": "a choice is already recorded"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid body size"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON"})
            return
        if not isinstance(payload, dict):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "body must be an object"})
            return
        board = self.server.board
        try:
            selection = choices.select(
                board.manifest, payload.get("option"), payload.get("notes", "")
            )
            choices.write_selection(board.selection_path, selection, force=board.force)
        except choices.ChoiceError as exc:
            status = HTTPStatus.CONFLICT if "already exists" in str(exc) else HTTPStatus.BAD_REQUEST
            self._json(status, {"error": str(exc)})
            return
        board.record(selection)
        self._json(
            HTTPStatus.OK,
            {
                "ok": True,
                "option": selection.option,
                "label": selection.label,
                "notes": selection.notes,
            },
        )


__all__ = ["ChoiceBoard"]
