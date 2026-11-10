#!/usr/bin/env python3
"""Serve the UX review board and persist feedback to a JSON file.

Usage:
  cd site && bun run build
  python tools/ux-review-server.py [--site site/dist] [--data PATH] [--port 8765]

The page is served at http://127.0.0.1:8765/lazyplan/ux/ to match the Vite
base path. Feedback submitted while this server is running is written to
``.agents/ux-review/feedback.json`` (ignored by git); without the server the
page falls back to browser storage and export/import.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITE = ROOT / "site" / "dist"
DEFAULT_DATA = ROOT / ".agents" / "ux-review" / "feedback.json"
BASE = "/lazyplan"
API = "/ux/api"
LOCK = threading.Lock()
ENTRY_ID = "id"
VERDICTS = {"approve", "concern", "idea", "question"}


def load_feedback(path: Path) -> list[dict]:
    """Read the feedback file, tolerating a missing or empty file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("feedback") if isinstance(payload, dict) else payload
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def save_feedback(path: Path, rows: list[dict]) -> None:
    """Write atomically so a crash never leaves half a review behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(
        json.dumps({"feedback": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def valid_entry(raw: object) -> dict:
    """Keep only fields the site owns; reject a row without a scene or verdict."""
    if not isinstance(raw, dict):
        raise ValueError("entry must be an object")
    entry_id = str(raw.get(ENTRY_ID) or "").strip()
    scene = str(raw.get("scene") or "").strip()
    verdict = str(raw.get("verdict") or "").strip()
    if not entry_id or not scene or verdict not in VERDICTS:
        raise ValueError("entry needs id, scene, and a known verdict")
    return {
        "id": entry_id[:80],
        "scene": scene[:120],
        "verdict": verdict,
        "severity": str(raw.get("severity") or "medium")[:20],
        "tags": [str(tag)[:40] for tag in raw.get("tags", []) if isinstance(tag, str)],
        "text": str(raw.get("text") or "")[:8000],
        "reviewer": str(raw.get("reviewer") or "")[:80],
        "createdAt": str(raw.get("createdAt") or "")[:40],
        "updatedAt": str(raw.get("updatedAt") or "")[:40],
    }


class Handler(BaseHTTPRequestHandler):
    """Static files plus one small feedback API."""

    server_version = "lpui-ux-review/1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} {format % args}")

    @property
    def data_path(self) -> Path:
        return self.server.data_path  # type: ignore[attr-defined]

    @property
    def site_path(self) -> Path:
        return self.server.site_path  # type: ignore[attr-defined]

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: object) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _route(self) -> tuple[str, str]:
        path = unquote(urlparse(self.path).path)
        if path == "/":
            path = f"{BASE}/ux/"
        if path.startswith(BASE):
            path = path[len(BASE) :]
        return path or "/", path

    def _api(self, path: str, method: str) -> bool:
        """Handle one API path; return False when this is not an API request."""
        if path == f"{API}/health":
            self._json(
                HTTPStatus.OK,
                {
                    "service": "lpui-ux-review",
                    "data": str(self.data_path.relative_to(ROOT))
                    if self.data_path.is_relative_to(ROOT)
                    else str(self.data_path),
                },
            )
            return True
        if path == f"{API}/feedback":
            if method == "GET":
                with LOCK:
                    self._json(HTTPStatus.OK, {"feedback": load_feedback(self.data_path)})
                return True
            if method == "POST":
                try:
                    entry = valid_entry(self._read_json())
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return True
                with LOCK:
                    rows = load_feedback(self.data_path)
                    rows = [row for row in rows if row.get("id") != entry["id"]]
                    rows.append(entry)
                    save_feedback(self.data_path, rows)
                self._json(HTTPStatus.CREATED, {"entry": entry})
                return True
            self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"})
            return True
        prefix = f"{API}/feedback/"
        if path.startswith(prefix):
            entry_id = path[len(prefix) :]
            if method == "PATCH":
                try:
                    entry = valid_entry(self._read_json())
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return True
                entry["id"] = entry_id
                with LOCK:
                    rows = load_feedback(self.data_path)
                    if not any(row.get("id") == entry_id for row in rows):
                        self._json(HTTPStatus.NOT_FOUND, {"error": "entry not found"})
                        return True
                    rows = [row for row in rows if row.get("id") != entry_id]
                    rows.append(entry)
                    save_feedback(self.data_path, rows)
                self._json(HTTPStatus.OK, {"entry": entry})
                return True
            if method == "DELETE":
                with LOCK:
                    rows = load_feedback(self.data_path)
                    kept = [row for row in rows if row.get("id") != entry_id]
                    save_feedback(self.data_path, kept)
                self._json(HTTPStatus.OK, {"deleted": len(rows) - len(kept)})
                return True
            self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"})
            return True
        return False

    def _read_json(self) -> object:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 1_000_000:
            raise ValueError("missing or oversized body")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _static(self, path: str) -> None:
        if path == "/":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", f"{BASE}/ux/")
            self.end_headers()
            return
        relative = path.lstrip("/")
        if not relative or relative.endswith("/"):
            relative += "index.html"
        target = (self.site_path / relative).resolve()
        try:
            target.relative_to(self.site_path.resolve())
        except ValueError:
            self._send(HTTPStatus.FORBIDDEN, b"forbidden\n", "text/plain; charset=utf-8")
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            self._send(HTTPStatus.NOT_FOUND, b"not found\n", "text/plain; charset=utf-8")
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in (
            "application/javascript",
            "application/json",
            "image/svg+xml",
        ):
            content_type += "; charset=utf-8"
        self._send(HTTPStatus.OK, target.read_bytes(), content_type)

    def do_GET(self) -> None:
        path, _ = self._route()
        if self._api(path, "GET"):
            return
        self._static(path)

    def do_POST(self) -> None:
        path, _ = self._route()
        if self._api(path, "POST"):
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_PATCH(self) -> None:
        path, _ = self._route()
        if self._api(path, "PATCH"):
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_DELETE(self) -> None:
        path, _ = self._route()
        if self._api(path, "DELETE"):
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})


class ReviewServer(ThreadingHTTPServer):
    """HTTP server carrying the site root and feedback file."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], site: Path, data: Path) -> None:
        super().__init__(address, Handler)
        self.site_path = site
        self.data_path = data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", type=Path, default=DEFAULT_SITE, help="built site directory")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="feedback JSON path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="open the review page in a browser")
    args = parser.parse_args(argv)

    site = args.site.resolve()
    if not (site / "ux" / "index.html").is_file():
        raise SystemExit(
            f"error: {site} has no ux/index.html; run `cd site && bun run build` first"
        )
    data = args.data.resolve()
    data.parent.mkdir(parents=True, exist_ok=True)
    if not data.exists():
        save_feedback(data, [])

    server = ReviewServer((args.host, args.port), site, data)
    url = f"http://{args.host}:{args.port}/lazyplan/ux/"
    print(f"UX review: {url}")
    print(f"feedback:  {data}")
    print("Ctrl-C to stop")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
