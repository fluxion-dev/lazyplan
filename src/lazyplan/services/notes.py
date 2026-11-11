"""Bundled release notes: parse CHANGELOG.md and track the last shown version."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..infrastructure.data_text import data_text
from ..infrastructure.repo import shared_home

MARKER_NAME = "notes-seen.json"
_HEADING = re.compile(
    r"^##\s+v?(\d+\.\d+\.\d+)\s+[—-]\s+(\d{4}-\d{2}-\d{2})\s*$",
    re.MULTILINE,
)
_PLAIN_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass(frozen=True)
class Release:
    """One versioned changelog section."""

    version: str
    date: str
    body: str

    def as_dict(self) -> dict[str, str]:
        """The JSON shape used by `lpui notes --json`."""
        return {"version": self.version, "date": self.date, "body": self.body}


def version_key(version: str) -> tuple[int, int, int]:
    """Turn `0.37.0` or `v0.37.0` into a comparable tuple."""
    text = version.strip()
    if text.startswith("v"):
        text = text[1:]
    if not _PLAIN_VERSION.fullmatch(text):
        raise ValueError(f"not a version: {version}")
    major, minor, patch = (int(part) for part in text.split("."))
    return major, minor, patch


def parse(text: str) -> tuple[Release, ...]:
    """Parse versioned `## vX.Y.Z — date` sections, newest first."""
    matches = list(_HEADING.finditer(text))
    releases: list[Release] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        releases.append(Release(match.group(1), match.group(2), body))
    return tuple(releases)


def bundled_text() -> str:
    """The changelog copied into the installed package."""
    return data_text("CHANGELOG.md")


def bundled_releases() -> tuple[Release, ...]:
    """Every release shipped with this build."""
    return parse(bundled_text())


def has_release(version: str, text: str | None = None) -> bool:
    """True when the bundled changelog carries the given version."""
    releases = parse(text) if text is not None else bundled_releases()
    target = version.lstrip("v")
    return any(release.version == target for release in releases)


def select(
    releases: tuple[Release, ...],
    installed: str,
    since: str | None = None,
    all_: bool = False,
) -> tuple[Release, ...]:
    """Pick the requested releases; ranges read oldest first, `--all` newest first."""
    if all_:
        return releases
    if since is not None:
        lower = version_key(since)
        upper = version_key(installed)
        chosen = [
            release
            for release in releases
            if lower < version_key(release.version) <= upper
        ]
        return tuple(sorted(chosen, key=lambda release: version_key(release.version)))
    target = installed.lstrip("v")
    return tuple(release for release in releases if release.version == target)


def render(releases: tuple[Release, ...]) -> str:
    """Render the selected sections as the Markdown a user reads."""
    blocks: list[str] = []
    for release in releases:
        body = release.body.strip()
        heading = f"## v{release.version} — {release.date}"
        blocks.append(f"{heading}\n\n{body}" if body else heading)
    if not blocks:
        return ""
    return "\n\n".join(blocks) + "\n"


def select_notes(
    installed: str,
    since: str | None = None,
    all_: bool = False,
    text: str | None = None,
) -> tuple[tuple[Release, ...], str]:
    """Return the selected sections and their rendered Markdown."""
    releases = parse(text) if text is not None else bundled_releases()
    chosen = select(releases, installed, since=since, all_=all_)
    return chosen, render(chosen)


def marker_path(home: str | Path | None = None) -> Path:
    """Where the last version whose notes were shown is recorded."""
    return shared_home(home) / MARKER_NAME


def read_seen(home: str | Path | None = None) -> str | None:
    """Return the recorded version; a missing or corrupt marker is None."""
    try:
        payload = json.loads(marker_path(home).read_text(encoding="utf-8"))
        value = str(payload["version"])
        version_key(value)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return value


def write_seen(version: str, home: str | Path | None = None) -> None:
    """Record the installed version atomically."""
    path = marker_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"version": version}) + "\n", encoding="utf-8")
    temporary.replace(path)


def seed_upgrade(installed: str, home: str | Path | None = None) -> None:
    """Record the old version before an upgrade so the next notice has a range."""
    if read_seen(home) is None:
        write_seen(installed, home)


def advance_notice(
    installed: str,
    text: str | None = None,
    home: str | Path | None = None,
) -> tuple[tuple[Release, ...], str]:
    """Advance the marker and return the notes for the unseen range.

    A missing or corrupt marker is a first install: record the version and show
    nothing. A downgrade or an unchanged version records the installed version
    and shows nothing. Otherwise the range from the recorded version through the
    installed version is returned once, oldest first.
    """
    releases = parse(text) if text is not None else bundled_releases()
    seen = read_seen(home)
    if seen is None:
        write_seen(installed, home)
        return (), ""
    if version_key(installed) <= version_key(seen):
        write_seen(installed, home)
        return (), ""
    chosen = select(releases, installed, since=seen)
    write_seen(installed, home)
    return chosen, render(chosen)
