#!/usr/bin/env python3
"""Snapshot PyPI downloads for the site.

Usage:
  python3 tools/fetch-downloads.py [--out PATH] [--package NAME] [--timeout SECONDS]

Reads pypistats `overall`, sums the `without_mirrors` series, and writes a
same-origin JSON snapshot for the landing page. Any network, parsing, or
validation failure writes {"available": false} and exits 0 so a Pages deploy is
never blocked by an analytics endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "site" / "public" / "downloads.json"
PACKAGE = "lazyplan-tui"
SOURCE = "pypistats.org"
METRIC = "without_mirrors"
URL = "https://pypistats.org/api/packages/{package}/overall"
USER_AGENT = "lazyplan-site/1.0 (+https://github.com/fluxion-dev/lazyplan)"
TIMEOUT = 20.0


class StatsError(Exception):
    """The download payload is missing or malformed."""


def fetch_payload(
    package: str = PACKAGE,
    timeout: float = TIMEOUT,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Fetch the pypistats overall response for one package."""
    request = urllib.request.Request(
        URL.format(package=package),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with opener(request, timeout=timeout) as response:
        raw = response.read()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise StatsError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise StatsError("payload is not an object")
    return payload


def _timestamp(now: datetime | None) -> str:
    stamp = now or datetime.now(UTC)
    return stamp.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def summarize(payload: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Total and last-seven-day downloads from the without_mirrors series."""
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise StatsError("payload missing data list")
    daily: list[tuple[str, int]] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("category") != METRIC:
            continue
        date = row.get("date")
        downloads = row.get("downloads")
        if not isinstance(date, str) or not date:
            raise StatsError("download row missing date")
        if isinstance(downloads, bool) or not isinstance(downloads, int) or downloads < 0:
            raise StatsError(f"invalid download count for {date}")
        daily.append((date, downloads))
    if not daily:
        raise StatsError("no without_mirrors rows")
    daily.sort()
    total = sum(count for _, count in daily)
    last_seven = sum(count for _, count in daily[-7:])
    if total < last_seven:
        raise StatsError("total is smaller than the last seven days")
    return {
        "available": True,
        "total": total,
        "last_7_days": last_seven,
        "generated_at": _timestamp(now),
        "source": SOURCE,
        "metric": METRIC,
    }


def failure_snapshot(now: datetime | None = None) -> dict[str, Any]:
    """The shape the page receives when stats cannot be trusted."""
    return {
        "available": False,
        "generated_at": _timestamp(now),
        "source": SOURCE,
        "metric": METRIC,
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


def run(
    out: Path = DEFAULT_OUT,
    package: str = PACKAGE,
    timeout: float = TIMEOUT,
    opener: Callable[..., Any] = urllib.request.urlopen,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fetch, summarize, and write one snapshot; fall back to unavailable."""
    try:
        snapshot = summarize(fetch_payload(package, timeout, opener), now)
    except Exception as exc:  # noqa: BLE001 - never block a deploy for stats
        print(f"warning: download stats unavailable: {exc}", file=sys.stderr)
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
    parser.add_argument("--timeout", type=float, default=TIMEOUT, help="network timeout")
    args = parser.parse_args(argv)
    snapshot = run(args.out.resolve(), args.package, args.timeout)
    state = "ok" if snapshot["available"] else "unavailable"
    print(f"download stats {state}: {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
