"""Visual choice manifests for the planning interview.

A manifest names a question and two to twelve image options. The
``lpui choose`` command serves those images on a loopback page and writes the
one option the reader picks. This module owns the file format and validation;
it imports no presentation or database code.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

MIN_OPTIONS = 2
MAX_OPTIONS = 12
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_TITLE = 120
MAX_PROMPT = 300
MAX_LABEL = 80
MAX_DESCRIPTION = 500
MAX_NOTES = 2000
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"})
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


class ChoiceError(ValueError):
    """A manifest or selection that cannot be used."""


@dataclass(frozen=True)
class ChoiceOption:
    """One image the reader may pick."""

    id: str
    label: str
    image: Path
    relative: str
    description: str = ""


@dataclass(frozen=True)
class ChoiceManifest:
    """A validated manifest rooted at its own directory."""

    title: str
    prompt: str
    options: tuple[ChoiceOption, ...]
    root: Path
    allow_notes: bool = True
    source: Path = field(default=Path("."))

    def option(self, option_id: str) -> ChoiceOption:
        """One option by id, or a ChoiceError naming the unknown id."""
        for option in self.options:
            if option.id == option_id:
                return option
        raise ChoiceError(f"unknown option: {option_id}")


@dataclass(frozen=True)
class Selection:
    """The reader's pick, ready to write as JSON."""

    option: str
    label: str
    notes: str
    at: str

    def as_dict(self) -> dict[str, str]:
        """The stable JSON shape the agent reads."""
        return {
            "option": self.option,
            "label": self.label,
            "notes": self.notes,
            "at": self.at,
        }


def _text(raw: object, where: str, limit: int, *, allow_empty: bool = False) -> str:
    """One manifest string with a field name in every error."""
    if not isinstance(raw, str):
        raise ChoiceError(f"{where} must be a string")
    value = raw.strip()
    if not value and not allow_empty:
        raise ChoiceError(f"{where} must not be empty")
    if len(value) > limit:
        raise ChoiceError(f"{where} is longer than {limit} characters")
    return value


def _resolve_image(root: Path, raw: object, where: str) -> tuple[Path, str]:
    """One image path under *root*; refuse escapes, missing files, and large files."""
    value = _text(raw, where, 500)
    if value.startswith(("/", "\\")) or "\\" in value:
        raise ChoiceError(f"{where} must be a relative path")
    parts = Path(value).parts
    if ".." in parts:
        raise ChoiceError(f"{where} must stay inside the manifest directory")
    suffix = Path(value).suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        allowed = ", ".join(sorted(IMAGE_SUFFIXES))
        raise ChoiceError(f"{where} must end in one of {allowed}")
    base = root.resolve()
    candidate = (base / value).resolve()
    if not candidate.is_relative_to(base):
        raise ChoiceError(f"{where} must stay inside the manifest directory")
    if not candidate.is_file():
        raise ChoiceError(f"{where} does not exist: {value}")
    if candidate.stat().st_size > MAX_IMAGE_BYTES:
        raise ChoiceError(f"{where} is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
    return candidate, Path(value).as_posix()


def _parse_options(root: Path, raw: object) -> tuple[ChoiceOption, ...]:
    if not isinstance(raw, list):
        raise ChoiceError("options must be a list")
    if not MIN_OPTIONS <= len(raw) <= MAX_OPTIONS:
        raise ChoiceError(f"options needs {MIN_OPTIONS}–{MAX_OPTIONS} entries")
    options: list[ChoiceOption] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        where = f"options[{index}]"
        if not isinstance(entry, dict):
            raise ChoiceError(f"{where} must be an object")
        option_id = _text(entry.get("id"), f"{where}.id", 40)
        if not _ID.match(option_id):
            raise ChoiceError(f"{where}.id must be lowercase letters, digits, - or _")
        if option_id in seen:
            raise ChoiceError(f"{where}.id is duplicated: {option_id}")
        seen.add(option_id)
        label = _text(entry.get("label"), f"{where}.label", MAX_LABEL)
        description = _text(
            entry.get("description", ""), f"{where}.description", MAX_DESCRIPTION, allow_empty=True
        )
        image, relative = _resolve_image(root, entry.get("image"), f"{where}.image")
        options.append(
            ChoiceOption(
                id=option_id,
                label=label,
                image=image,
                relative=relative,
                description=description,
            )
        )
    return tuple(options)


def load_manifest(path: str | Path) -> ChoiceManifest:
    """Parse and validate one choices file; every failure is a ChoiceError."""
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ChoiceError(f"cannot read manifest: {exc}") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ChoiceError(f"manifest is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ChoiceError("manifest must be a JSON object")
    root = source.resolve().parent
    title = _text(raw.get("title"), "title", MAX_TITLE)
    prompt = _text(raw.get("prompt"), "prompt", MAX_PROMPT)
    allow_notes = raw.get("allow_notes", True)
    if not isinstance(allow_notes, bool):
        raise ChoiceError("allow_notes must be true or false")
    options = _parse_options(root, raw.get("options"))
    return ChoiceManifest(
        title=title,
        prompt=prompt,
        options=options,
        root=root,
        allow_notes=allow_notes,
        source=source.resolve(),
    )


def select(manifest: ChoiceManifest, option_id: object, notes: object = "") -> Selection:
    """Validate one pick and build the selection record."""
    if not isinstance(option_id, str) or not option_id:
        raise ChoiceError("option must be an option id")
    option = manifest.option(option_id)
    text = _text(notes, "notes", MAX_NOTES, allow_empty=True) if notes is not None else ""
    return Selection(
        option=option.id,
        label=option.label,
        notes=text,
        at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def write_selection(path: str | Path, selection: Selection, *, force: bool = False) -> Path:
    """Write the selection atomically; refuse to replace one without *force*."""
    target = Path(path)
    if target.exists() and not force:
        raise ChoiceError(f"selection already exists: {target} (use --force to replace it)")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.tmp")
    temp.write_text(
        json.dumps(selection.as_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, target)
    return target


def image_bytes(manifest: ChoiceManifest, relative: str) -> bytes:
    """Read one image that a validated manifest already points at."""
    resolved, _ = _resolve_image(manifest.root, relative, "image")
    return resolved.read_bytes()
