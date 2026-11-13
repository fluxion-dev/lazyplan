"""Per-file commit statistics parsed from git `--name-status` and `--numstat`."""

from __future__ import annotations

from dataclasses import dataclass

_STATUS_WORDS = {
    "A": "add",
    "D": "delete",
    "R": "rename",
    "C": "add",
}


@dataclass(frozen=True)
class FileStat:
    """One changed path in a commit, with its change kind and line counts."""

    path: str
    old_path: str = ""
    status: str = "modify"
    additions: int = 0
    deletions: int = 0
    binary: bool = False


@dataclass(frozen=True)
class CommitStats:
    """Per-file change summary for one commit.

    `state` is ok, missing, or error. A commit with no textual changes still
    reports `ok` with an empty file list.
    """

    state: str = "ok"
    detail: str = ""
    files: tuple[FileStat, ...] = ()

    @property
    def additions(self) -> int:
        """Total added lines across every non-binary file."""
        return sum(item.additions for item in self.files)

    @property
    def deletions(self) -> int:
        """Total removed lines across every non-binary file."""
        return sum(item.deletions for item in self.files)


def _parse_name_status(text: str) -> list[tuple[str, str, str]]:
    """One (status, old_path, path) tuple per `git --name-status` row."""
    rows: list[tuple[str, str, str]] = []
    for raw in text.splitlines():
        parts = raw.split("\t")
        if len(parts) < 2:
            continue
        code = parts[0][:1]
        if code in ("R", "C"):
            if len(parts) < 3:
                continue
            rows.append((code, parts[1], parts[2]))
        else:
            rows.append((code, "", parts[1]))
    return rows


def _parse_numstat(text: str) -> list[tuple[int, int, bool]]:
    """One (additions, deletions, binary) tuple per `git --numstat` row."""
    rows: list[tuple[int, int, bool]] = []
    for raw in text.splitlines():
        parts = raw.split("\t")
        if len(parts) < 3:
            continue
        added, removed = parts[0], parts[1]
        binary = added == "-" or removed == "-"
        rows.append(
            (
                0 if binary else int(added),
                0 if binary else int(removed),
                binary,
            )
        )
    return rows


def merge_file_stats(status_text: str, numstat_text: str) -> tuple[FileStat, ...]:
    """Join name-status and numstat rows by position."""
    statuses = _parse_name_status(status_text)
    counts = _parse_numstat(numstat_text)
    files: list[FileStat] = []
    for index, (code, old_path, path) in enumerate(statuses):
        additions, deletions, binary = counts[index] if index < len(counts) else (0, 0, False)
        status = _STATUS_WORDS.get(code, "modify")
        files.append(
            FileStat(
                path=path,
                old_path=old_path if status == "rename" else "",
                status=status,
                additions=additions,
                deletions=deletions,
                binary=binary,
            )
        )
    return tuple(files)
