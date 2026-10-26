"""Text file I/O that behaves the same on posix and Windows. Stdlib only.

Reads honor a UTF-8 or UTF-16 byte-order mark (Windows PowerShell 5 writes
both); everything else is UTF-8. Writes are UTF-8 without a BOM and keep an
existing file's CRLF line endings; new files get LF.
"""

from __future__ import annotations

import codecs
from pathlib import Path

_UTF16_BOMS = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)


def decode(raw: bytes) -> str:
    """Decode file bytes by BOM, defaulting to UTF-8; newlines become LF."""
    encoding = "utf-16" if raw.startswith(_UTF16_BOMS) else "utf-8-sig"
    return raw.decode(encoding).replace("\r\n", "\n")


def read(path: str | Path) -> str:
    """Whole file as text with LF newlines."""
    return decode(Path(path).read_bytes())


def _uses_crlf(path: Path) -> bool:
    try:
        return b"\r\n" in path.read_bytes()
    except OSError:
        return False


def write(path: str | Path, text: str) -> None:
    """Replace the file's text, keeping CRLF when the file already used it."""
    target = Path(path)
    newline = "\r\n" if _uses_crlf(target) else "\n"
    target.write_text(text, encoding="utf-8", newline=newline)


def append(path: str | Path, text: str) -> None:
    """Append text, matching the file's existing line endings."""
    target = Path(path)
    newline = "\r\n" if _uses_crlf(target) else "\n"
    with target.open("a", encoding="utf-8", newline=newline) as fh:
        fh.write(text)
