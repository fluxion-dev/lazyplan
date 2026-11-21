"""Parse and render definition-only plan sketches as Markdown.

A sketch is the human review surface for a new plan: a title, why, what, and
acceptance criteria. It deliberately has no milestone or task grammar; the
agent derives that structure when the sketch is formalized.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_H1 = re.compile(r"^#\s+(.*)$")
_H2 = re.compile(r"^##\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_CHECKBOX = re.compile(r"^\[[ xX]\]\s*")

_WHY = frozenset({"why", "vision", "goal", "motivation"})
_WHAT = frozenset({"what", "scope", "approach", "plan", "deliverables"})
_DONE = frozenset({"done", "acceptance", "acceptance criteria", "success", "definition of done"})


class SketchDocumentError(ValueError):
    """A sketch is malformed or lacks a reviewable definition."""


@dataclass(frozen=True)
class SketchDocument:
    """One definition-only sketch: title, why, what, and criteria."""

    title: str
    why: str
    what: str
    criteria: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise SketchDocumentError("sketch title must not be empty")
        if not self.why.strip():
            raise SketchDocumentError("sketch why must not be empty")
        if not self.what.strip():
            raise SketchDocumentError("sketch what must not be empty")
        seen: set[str] = set()
        for criterion in self.criteria:
            if not criterion.strip():
                raise SketchDocumentError("sketch criterion must not be empty")
            if criterion in seen:
                raise SketchDocumentError(f"duplicate sketch criterion: {criterion}")
            seen.add(criterion)


def _heading_text(text: str) -> str:
    """Strip an ATX heading's optional closing hashes."""
    return text.strip().rstrip("#").strip()


def _section_key(text: str) -> str | None:
    """Map one H2 heading to a known section, or None for prose."""
    key = " ".join(_heading_text(text).lower().rstrip(":").split())
    for name, aliases in (("why", _WHY), ("what", _WHAT), ("done", _DONE)):
        if key in aliases:
            return name
    return None


def _join_lines(lines: list[str]) -> str:
    """Keep body text readable without trailing or repeated blank lines."""
    text = "\n".join(lines).strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def _criteria(lines: list[str]) -> tuple[str, ...]:
    """Read bullets and paragraphs under Done as ordered criteria."""
    out: list[str] = []
    current: list[str] = []
    for line in lines:
        bullet = _BULLET.match(line)
        if bullet:
            if current:
                out.append(" ".join(part.strip() for part in current))
            current = [_CHECKBOX.sub("", bullet.group(1)).strip()]
        elif not line.strip():
            if current:
                out.append(" ".join(part.strip() for part in current))
                current = []
        elif current:
            current.append(line)
        else:
            current = [line.strip()]
    if current:
        out.append(" ".join(part.strip() for part in current))
    deduped: list[str] = []
    seen: set[str] = set()
    for criterion in out:
        if criterion and criterion not in seen:
            seen.add(criterion)
            deduped.append(criterion)
    return tuple(deduped)


def parse_sketch(text: str) -> SketchDocument:
    """Read one sketch's title, sections, and criteria.

    Unknown H2 sections are kept in ``what`` so no prose is lost. The canonical
    headings are Why, What, and Done; common aliases are accepted.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    title = ""
    sections: dict[str, list[str]] = {"why": [], "what": [], "done": []}
    present: set[str] = set()
    current: str | None = None
    for line in lines:
        h1 = _H1.match(line)
        if h1 and not title:
            title = _heading_text(h1.group(1))
            continue
        h2 = _H2.match(line)
        if h2:
            key = _section_key(h2.group(1))
            if key is None or key in present:
                current = "what"
                sections["what"].append(f"## {_heading_text(h2.group(1))}")
                continue
            present.add(key)
            current = key
            continue
        if current is None:
            if line.strip():
                sections["what"].append(line)
            continue
        sections[current].append(line)

    if not title:
        raise SketchDocumentError("sketch needs a '# Title' heading")
    why = _join_lines(sections["why"])
    if not why:
        raise SketchDocumentError("sketch needs a '## Why' section")
    what = _join_lines(sections["what"])
    if not what:
        raise SketchDocumentError("sketch needs a '## What' section")
    return SketchDocument(title, why, what, _criteria(sections["done"]))


def render_sketch(document: SketchDocument) -> str:
    """Render one sketch in canonical Markdown."""
    lines = [
        f"# {document.title}",
        "",
        "## Why",
        document.why,
        "",
        "## What",
        document.what,
    ]
    if document.criteria:
        lines.extend(["", "## Done", *(f"- {criterion}" for criterion in document.criteria)])
    return "\n".join(lines).strip() + "\n"
