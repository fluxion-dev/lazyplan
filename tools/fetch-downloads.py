#!/usr/bin/env python3
"""Snapshot PyPI and GitHub download counts for the site.

Usage:
  python3 tools/fetch-downloads.py [--out PATH] [--package NAME]
                                   [--repo OWNER/NAME] [--timeout SECONDS]

Reads the pypistats `overall` response and sums both the with-mirrors and
without-mirrors series, then sums GitHub release asset downloads per artifact.
The snapshot keeps each channel separate: PyPI and GitHub counts are different
units and are never added together. Any network, parsing, or validation failure
writes an unavailable snapshot and exits 0 so a Pages deploy is never blocked
by an analytics endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "site" / "public" / "downloads.json"
PACKAGE = "lazyplan-tui"
REPO = "fluxion-dev/lazyplan"
SOURCE = "pypistats.org"
GITHUB_SOURCE = "api.github.com"
SCHEMA = 2
PYPI_SERIES = (
    ("with_mirrors", "pypi_with_mirrors"),
    ("without_mirrors", "pypi_direct"),
)
URL = "https://pypistats.org/api/packages/{package}/overall"
GITHUB_URL = "https://api.github.com/repos/{repo}/releases?per_page=100&page={page}"
USER_AGENT = "lazyplan-site/1.0 (+https://github.com/fluxion-dev/lazyplan)"
TIMEOUT = 20.0
PAGE_SIZE = 100
MAX_PAGES = 10


class StatsError(Exception):
    """The download payload is missing or malformed."""


def _request(url: str) -> urllib.request.Request:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def _read_json(request: urllib.request.Request, timeout: float, opener: Callable[..., Any]) -> Any:
    with opener(request, timeout=timeout) as response:
        raw = response.read()
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise StatsError(f"invalid JSON: {exc}") from exc


def fetch_payload(
    package: str = PACKAGE,
    timeout: float = TIMEOUT,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Fetch the pypistats overall response for one package."""
    payload = _read_json(_request(URL.format(package=package)), timeout, opener)
    if not isinstance(payload, dict):
        raise StatsError("payload is not an object")
    return payload


def fetch_releases(
    repo: str = REPO,
    timeout: float = TIMEOUT,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> list[dict[str, Any]]:
    """Fetch every release page for *repo*."""
    releases: list[dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        payload = _read_json(_request(GITHUB_URL.format(repo=repo, page=page)), timeout, opener)
        if not isinstance(payload, list):
            raise StatsError("release payload is not a list")
        releases.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < PAGE_SIZE:
            return releases
    raise StatsError("release pagination did not finish")


def _timestamp(now: datetime | None) -> str:
    stamp = now or datetime.now(UTC)
    return stamp.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _daily_series(rows: Sequence[Any], metric: str) -> list[tuple[str, int]]:
    daily: list[tuple[str, int]] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("category") != metric:
            continue
        date = row.get("date")
        downloads = row.get("downloads")
        if not isinstance(date, str) or not date:
            raise StatsError(f"{metric} row missing date")
        if isinstance(downloads, bool) or not isinstance(downloads, int) or downloads < 0:
            raise StatsError(f"invalid {metric} count for {date}")
        daily.append((date, downloads))
    if not daily:
        raise StatsError(f"no {metric} rows")
    daily.sort()
    return daily


def _pypi_channel(metric: str, daily: Sequence[tuple[str, int]]) -> dict[str, Any]:
    total = sum(count for _, count in daily)
    last_seven = sum(count for _, count in daily[-7:])
    if total < last_seven:
        raise StatsError(f"{metric} total is smaller than the last seven days")
    return {
        "available": True,
        "total": total,
        "last_7_days": last_seven,
        "source": SOURCE,
        "metric": metric,
    }


def _unavailable(metric: str, source: str) -> dict[str, Any]:
    return {"available": False, "source": source, "metric": metric}


def summarize(payload: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Both PyPI series as separate channels; raise when neither is usable."""
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise StatsError("payload missing data list")
    channels: dict[str, Any] = {}
    for metric, key in PYPI_SERIES:
        try:
            channels[key] = _pypi_channel(metric, _daily_series(rows, metric))
        except StatsError:
            channels[key] = _unavailable(metric, SOURCE)
    if not any(channel["available"] for channel in channels.values()):
        raise StatsError("no usable PyPI series")
    return {
        "available": True,
        "schema": SCHEMA,
        "generated_at": _timestamp(now),
        "source": SOURCE,
        "channels": channels,
    }


def summarize_github(payload: Sequence[Any]) -> dict[str, Any]:
    """Sum release asset downloads per artifact name."""
    artifacts: dict[str, int] = {}
    for release in payload:
        if not isinstance(release, dict):
            continue
        assets = release.get("assets")
        if not isinstance(assets, list):
            continue
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = asset.get("name")
            count = asset.get("download_count")
            if not isinstance(name, str) or not name:
                raise StatsError("asset missing name")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise StatsError(f"invalid asset count for {name}")
            artifacts[name] = artifacts.get(name, 0) + count
    return {
        "available": True,
        "total": sum(artifacts.values()),
        "artifacts": dict(sorted(artifacts.items())),
        "source": GITHUB_SOURCE,
        "metric": "release_assets",
    }


def failure_snapshot(now: datetime | None = None) -> dict[str, Any]:
    """The shape the page receives when stats cannot be trusted."""
    return {
        "available": False,
        "schema": SCHEMA,
        "generated_at": _timestamp(now),
        "channels": {},
    }


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    """Write JSON atomically so the page never reads a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _build_snapshot(
    package: str,
    repo: str,
    timeout: float,
    opener: Callable[..., Any],
    github_opener: Callable[..., Any],
    now: datetime | None,
) -> dict[str, Any]:
    channels: dict[str, Any] = {}
    try:
        pypi = summarize(fetch_payload(package, timeout, opener), now)
        channels.update(pypi["channels"])
    except Exception:  # noqa: BLE001 - one channel must not hide the others
        for metric, key in PYPI_SERIES:
            channels[key] = _unavailable(metric, SOURCE)
    try:
        channels["github_assets"] = summarize_github(fetch_releases(repo, timeout, github_opener))
    except Exception:  # noqa: BLE001 - one channel must not hide the others
        channels["github_assets"] = _unavailable("release_assets", GITHUB_SOURCE)
    return {
        "available": any(channel["available"] for channel in channels.values()),
        "schema": SCHEMA,
        "generated_at": _timestamp(now),
        "channels": channels,
    }


def run(
    out: Path = DEFAULT_OUT,
    package: str = PACKAGE,
    timeout: float = TIMEOUT,
    opener: Callable[..., Any] = urllib.request.urlopen,
    now: datetime | None = None,
    repo: str = REPO,
    github_opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Fetch, summarize, and write one snapshot; fall back per channel."""
    snapshot = _build_snapshot(
        package,
        repo,
        timeout,
        opener,
        github_opener or opener,
        now,
    )
    if not snapshot["available"]:
        print("warning: download stats unavailable", file=sys.stderr)
        snapshot = failure_snapshot(now)
    try:
        write_snapshot(out, snapshot)
    except OSError as exc:
        print(f"warning: cannot write {out}: {exc}", file=sys.stderr)
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output JSON path")
    parser.add_argument("--package", default=PACKAGE, help="PyPI package name")
    parser.add_argument("--repo", default=REPO, help="GitHub owner/name")
    parser.add_argument("--timeout", type=float, default=TIMEOUT, help="network timeout")
    args = parser.parse_args(argv)
    snapshot = run(args.out.resolve(), args.package, args.timeout, repo=args.repo)
    state = "ok" if snapshot["available"] else "unavailable"
    print(f"download stats {state}: {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
