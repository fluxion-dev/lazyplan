#!/usr/bin/env python3
"""Generate and check the repo-local Textual skill suite.

Usage:
  python3 tools/gen_textual_skills.py            # write the skill tree
  python3 tools/gen_textual_skills.py --check    # validate coverage

The catalog is curated in tools/textual_catalog_*.py. Widget and container
constructor signatures come from the installed Textual package, so regenerate
after a pin bump. Official pages are linked, never copied.
"""

from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".agents" / "skills"
PIN = "8.2.8"

sys.path.insert(0, str(ROOT / "tools"))
from textual_catalog_events import EVENTS  # noqa: E402
from textual_catalog_guides import GUIDES  # noqa: E402
from textual_catalog_layout import LAYOUT  # noqa: E402
from textual_catalog_styles import STYLES  # noqa: E402
from textual_catalog_types import CSS_TYPES  # noqa: E402
from textual_catalog_widgets import WIDGETS  # noqa: E402

CATEGORIES: dict[str, dict[str, Any]] = {
    "widgets": {
        "skill": "textual-widgets",
        "title": "Textual widgets",
        "description": "Every Textual 8.2.8 widget: constructor, key APIs, messages, CSS hooks, examples, and pitfalls. Use when choosing or wiring any built-in widget.",
        "source": "https://textual.textualize.io/widgets/{id}/",
        "kind": "widget",
        "items": WIDGETS,
    },
    "styles": {
        "skill": "textual-styles",
        "title": "Textual styles",
        "description": "Every Textual 8.2.8 style property: accepted values, defaults, applicable widgets, examples, and related properties. Use when styling or debugging CSS.",
        "source": "https://textual.textualize.io/{path}/",
        "kind": "style",
        "items": STYLES,
    },
    "events": {
        "skill": "textual-events",
        "title": "Textual events",
        "description": "Every Textual 8.2.8 event: handler name, bubbling, cancelability, attributes, and examples. Use when handling input, focus, mouse, lifecycle, or screen events.",
        "source": "https://textual.textualize.io/events/{id}/",
        "kind": "event",
        "items": EVENTS,
    },
    "css-types": {
        "skill": "textual-css-types",
        "title": "Textual CSS types",
        "description": "Every Textual 8.2.8 CSS type: grammar, examples, and which styles consume it. Use when a style value is rejected or its syntax is unclear.",
        "source": "https://textual.textualize.io/css_types/{id}/",
        "kind": "type",
        "items": CSS_TYPES,
    },
    "layout": {
        "skill": "textual-layout",
        "title": "Textual layout, containers, and screens",
        "description": "Textual 8.2.8 containers, screens, composition, sizing, docking, grids, scrolling, and lifecycle. Use when structuring a screen or debugging layout and navigation.",
        "source": "https://textual.textualize.io/guide/layout/",
        "kind": "layout",
        "items": LAYOUT,
    },
    "guides": {
        "skill": "textual-guides",
        "title": "Textual guides",
        "description": "Every Textual 8.2.8 guide: the problem it solves, core concepts, APIs, links to the reference files it uses, examples, and pitfalls.",
        "source": "https://textual.textualize.io/guide/{id}/",
        "kind": "guide",
        "items": GUIDES,
    },
}

HEADINGS = {
    "widget": ("## Constructor", "## Key properties and methods", "## Messages", "## CSS", "## Example", "## Pitfalls"),
    "style": ("## Values", "## Default and inheritance", "## Applies to", "## Example", "## Related"),
    "event": ("## Handler", "## Bubbling and cancelability", "## Attributes", "## Example"),
    "type": ("## Grammar", "## Consumers", "## Example"),
    "layout": ("## Constructor and usage", "## Key behavior", "## Example", "## Pitfalls"),
    "guide": ("## What it covers", "## Core concepts", "## APIs", "## Related references", "## Example", "## Pitfalls"),
}


def _widget_class(name: str):
    """Resolve a widget class, including the non-exported Toast."""
    if name == "Toast":
        from textual.widgets._toast import Toast

        return Toast
    import textual.widgets as widgets

    return getattr(widgets, name)


def _signature(name: str, category: str) -> str:
    """Return a constructor signature, or a usage line for non-class entries."""
    if category == "layout":
        if name in ("Screen", "ModalScreen"):
            from textual.screen import ModalScreen, Screen

            cls = ModalScreen if name == "ModalScreen" else Screen
        elif name == "Composition":
            return "def compose(self) -> ComposeResult: ..."
        else:
            import textual.containers as containers

            cls = getattr(containers, name.replace(" ", "").replace("-", ""))
        return f"{name}{inspect.signature(cls)}"
    if category == "widgets":
        cls = _widget_class(name)
        return f"{name}{inspect.signature(cls)}"
    return ""


def _bullet(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None."


def _fence(code: str, language: str = "python") -> str:
    return f"```{language}\n{code.strip()}\n```"


def render_widget(item_id: str, data: dict[str, Any]) -> str:
    signature = _signature(data["name"], "widgets")
    if data["name"] == "Toast":
        import_line = "from textual.widgets._toast import Toast"
        doc_line = "self.notify(...) is the public API"
    else:
        import_line = f"from textual.widgets import {data['name']}"
        doc_line = f"`help(textual.widgets.{data['name']})`"
    return f"""# {data["name"]}

**Textual:** {PIN} · **Import:** `{import_line}`
**Official:** https://textual.textualize.io/widgets/{item_id}/

{data["summary"]}

## Constructor

```python
{signature}
```

## Key properties and methods

{_bullet(data["props"])}

## Messages

{_bullet(data["messages"])}

## CSS

{_bullet(data["css"])}

## Example

{_fence(data["example"])}

## Pitfalls

{_bullet(data["pitfalls"])}

## See also

- [Widgets index](../SKILL.md)
- {doc_line}
"""


def _style_example(data: dict[str, Any]) -> str:
    if "example" in data:
        return str(data["example"])
    values = str(data["values"])
    token = values.split("|")[0].split(",")[0].strip()
    if token in {"colour", "color"}:
        return "$primary"
    if token.startswith("scalar"):
        return "1fr"
    if token == "integer":
        return "1"
    if token == "0-1":
        return "0.8"
    if token in {"one to four scalars", "cells, %, fr, auto"}:
        return "1"
    if token.startswith("edge"):
        return "solid $primary"
    if token.startswith("horizontal vertical"):
        return "1 2"
    if token.startswith("space-separated track"):
        return "1fr 2fr"
    if token.startswith("space-separated layer"):
        return "base overlay"
    if token.startswith("scrollbar"):
        return "$scrollbar"
    return "inherit"


def render_style(item_id: str, data: dict[str, Any]) -> str:
    example = _style_example(data)
    return f"""# {data["name"]}

**Textual:** {PIN}
**Official:** https://textual.textualize.io/{data["path"]}/

{data["summary"]}

## Values

`{data["values"]}`

## Default and inheritance

Default: {data["default"]}. Textual resolves the final value from the widget, its
classes, the app CSS, and the active theme. Use `styles.get_rule()` or the
devtools CSS inspector when the cascade is unclear.

## Applies to

{data["applies"]}.

## Example

```css
{data["name"]}: {example};
```

## Related

- `{data["related"]}`

## See also

- [Styles index](../SKILL.md)
- [CSS types index](../../textual-css-types/SKILL.md)
"""


def render_event(item_id: str, data: dict[str, Any]) -> str:
    return f"""# {data["name"]}

**Textual:** {PIN} · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/{item_id}/

{data["summary"]}

## Handler

`def {data["handler"]}(self, event: events.{data["name"]}) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: {data["bubbles"]}. Cancelable: {data["cancelable"]}. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`{data["attrs"]}`

## Example

{_fence(data["example"])}

## See also

- [Events index](../SKILL.md)
- `textual.events.{data["name"]}` docstring
"""


def render_type(item_id: str, data: dict[str, Any]) -> str:
    return f"""# {data["name"]}

**Textual:** {PIN}
**Official:** https://textual.textualize.io/css_types/{item_id}/

{data["summary"]}

## Grammar

`{data["grammar"]}`

## Consumers

{data["consumers"]}.

## Example

```css
{data["example"]}
```

## See also

- [CSS types index](../SKILL.md)
"""


def _layout_source(item_id: str) -> str:
    if item_id in ("screen", "modal_screen", "composition"):
        return "https://textual.textualize.io/guide/screens/"
    return "https://textual.textualize.io/guide/layout/"


def render_layout(item_id: str, data: dict[str, Any]) -> str:
    if data["name"] == "Composition and lifecycle":
        signature = "def compose(self) -> ComposeResult: ..."
        import_line = "from textual.app import ComposeResult"
    elif item_id in ("screen", "modal_screen"):
        import_line = f"from textual.screen import {data['name']}"
        signature = _signature(data["name"], "layout")
    else:
        import_line = f"from textual.containers import {data['name']}"
        signature = _signature(data["name"], "layout")
    return f"""# {data["name"]}

**Textual:** {PIN} · **Import:** `{import_line}`
**Official:** {_layout_source(item_id)}

{data["summary"]}

## Constructor and usage

```python
{signature}
```

## Key behavior

{_bullet(data["props"])}

## Example

{_fence(data["example"])}

## Pitfalls

{_bullet(data["pitfalls"])}

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
"""


GUIDE_REFS: dict[str, tuple[str, ...]] = {
    "devtools": ("widgets",),
    "app": ("widgets", "events"),
    "styles": ("styles", "css-types"),
    "css": ("styles", "css-types", "layout"),
    "queries": ("widgets",),
    "layout": ("layout", "styles"),
    "events": ("events", "widgets"),
    "input": ("events", "widgets"),
    "actions": ("events",),
    "reactivity": ("events", "widgets"),
    "design": ("styles", "css-types"),
    "widgets": ("widgets", "events"),
    "content": ("widgets", "styles"),
    "animation": ("styles",),
    "screens": ("layout", "events"),
    "workers": ("events",),
    "command_palette": ("widgets", "events"),
    "testing": ("widgets", "layout"),
}


def _guide_link(link: str) -> str:
    """Resolve a guide's related link to a sibling guide or a category skill."""
    if link in GUIDES:
        return f"{link}.md"
    return f"../../textual-{link}/SKILL.md"


def render_guide(item_id: str, data: dict[str, Any]) -> str:
    source_id = "CSS" if item_id == "css" else item_id
    links = "\n".join(f"- [{link}]({_guide_link(link)})" for link in data["links"])
    refs = "\n".join(
        f"- [{ref}](../../textual-{ref}/SKILL.md)" for ref in GUIDE_REFS.get(item_id, ())
    )
    return f"""# {data["title"]}

**Textual:** {PIN}
**Official:** https://textual.textualize.io/guide/{source_id}/

{data["summary"]}

## What it covers

{_bullet(data["concepts"])}

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

{_bullet(data["apis"])}

## Related references

Guides:

{links}

Reference files:

{refs}

## Example

{_fence(data["example"])}

## Pitfalls

{_bullet(data["pitfalls"])}
"""


RENDERERS = {
    "widget": render_widget,
    "style": render_style,
    "event": render_event,
    "type": render_type,
    "layout": render_layout,
    "guide": render_guide,
}


def reference_name(item_id: str) -> str:
    return item_id.replace("/", "__") + ".md"


def skill_md(category: str, config: dict[str, Any]) -> str:
    rows = []
    for item_id, data in config["items"].items():
        name = data.get("name") or data.get("title")
        rows.append(f"| [{name}](references/{reference_name(item_id)}) | `{item_id}` |")
    table = "\n".join(rows)
    return f"""---
name: {config["skill"]}
description: {config["description"]}
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# {config["title"]} — Textual {PIN}

Read the matching reference before writing or changing this part of a Textual
app. Every entry links the official page and the pinned API.

## Rules

- Pin all advice to Textual {PIN}; check the installed version when a symbol is missing.
- Prefer composition and classes over inline styles and deep inheritance.
- Never copy long passages from the official docs; summarize and link.
- After a Textual upgrade, run `python3 tools/gen_textual_skills.py --check`.

## Index

| Item | Id |
| --- | --- |
{table}

## See also

- [Textual router](../textual/SKILL.md)
- [Coverage manifest](../textual/references/_manifest.json)
"""


def router_md() -> str:
    rows = "\n".join(
        f"| [`{config['skill']}`](../{config['skill']}/SKILL.md) | {config['title']} |"
        for config in CATEGORIES.values()
    )
    return f"""---
name: textual
description: Router for the complete Textual {PIN} skill suite. Use for any Textual widget, style, event, CSS type, container, screen, or guide question; choose the category skill and read the matching reference.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# Textual {PIN} skill suite

This suite covers the Textual reference and guide at {PIN}. Start here, then
open the category skill and the one reference file you need.

## Choose a skill

| Skill | Use for |
| --- | --- |
{rows}

## Routing rules

- A concrete class, control, or display element → `textual-widgets`.
- A CSS property, value, or cascade question → `textual-styles`; follow a value
  question to `textual-css-types`.
- A handler, key, mouse, focus, lifecycle, or custom message → `textual-events`.
- A container, screen, modal, sizing, docking, grid, or scroll layout → `textual-layout`.
- A workflow or concept ("how do I test this?", "how do screens work?") →
  `textual-guides`, then the linked category reference.

## Coverage

The manifest at `references/_manifest.json` is the source of truth for the
suite. It records the pinned version, every item, its category, its reference
file, and the official URL. `python3 tools/gen_textual_skills.py --check`
fails on a missing file, missing heading, duplicate id, or version drift.

## Official sources

- Reference: https://textual.textualize.io/reference/
- Guide: https://textual.textualize.io/guide/
- API: https://textual.textualize.io/api/

The suite is a distilled index, not a substitute for the official pages. Read
the linked page when behavior or version support is uncertain.
"""


def manifest() -> dict[str, Any]:
    items = []
    for category, config in CATEGORIES.items():
        for item_id, data in config["items"].items():
            if category == "styles":
                source = config["source"].format(path=data["path"])
            elif category == "guides":
                source_id = "CSS" if item_id == "css" else item_id
                source = config["source"].format(id=source_id)
            elif category == "layout":
                source = _layout_source(item_id)
            else:
                source = config["source"].format(id=item_id)
            items.append(
                {
                    "category": category,
                    "id": item_id,
                    "name": data.get("name") or data.get("title"),
                    "file": f".agents/skills/{config['skill']}/references/{reference_name(item_id)}",
                    "source": source,
                }
            )
    return {
        "version": PIN,
        "categories": {
            category: {
                "skill": config["skill"],
                "title": config["title"],
                "count": len(config["items"]),
            }
            for category, config in CATEGORIES.items()
        },
        "items": items,
    }


def write_tree() -> None:
    for category, config in CATEGORIES.items():
        skill_dir = SKILLS / config["skill"]
        refs = skill_dir / "references"
        refs.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(skill_md(category, config), encoding="utf-8")
        renderer = RENDERERS[config["kind"]]
        for item_id, data in config["items"].items():
            (refs / reference_name(item_id)).write_text(
                renderer(item_id, data), encoding="utf-8"
            )
    router = SKILLS / "textual"
    (router / "references").mkdir(parents=True, exist_ok=True)
    (router / "SKILL.md").write_text(router_md(), encoding="utf-8")
    data = manifest()
    (router / "references" / "_manifest.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(data['items'])} references across {len(CATEGORIES)} categories")


def check() -> int:
    problems: list[str] = []
    try:
        from textual import __version__ as textual_version
    except ImportError:
        textual_version = ""
    if textual_version != PIN:
        problems.append(f"installed Textual {textual_version or 'missing'} != pin {PIN}")
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'textual\s*>=\s*([0-9.]+)', text)
    if not m or m.group(1) != PIN:
        problems.append(f"pyproject Textual lower bound {m.group(1) if m else 'missing'} != {PIN}")

    path = SKILLS / "textual" / "references" / "_manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"error: cannot read manifest: {exc}", file=sys.stderr)
        return 1
    if data.get("version") != PIN:
        problems.append(f"manifest version {data.get('version')} != {PIN}")
    seen: set[tuple[str, str]] = set()
    for item in data.get("items", []):
        key = (item.get("category", ""), item.get("id", ""))
        if key in seen:
            problems.append(f"duplicate item {key}")
        seen.add(key)
        file = ROOT / item["file"]
        if not file.is_file():
            problems.append(f"missing {item['file']}")
            continue
        body = file.read_text(encoding="utf-8")
        kind = CATEGORIES.get(item["category"], {}).get("kind")
        if kind is None:
            problems.append(f"unknown category {item['category']}")
            continue
        for heading in HEADINGS[kind]:
            if heading not in body:
                problems.append(f"{item['file']} missing {heading}")
        if item.get("source") not in body:
            problems.append(f"{item['file']} missing official URL")
    for config in CATEGORIES.values():
        if not (SKILLS / config["skill"] / "SKILL.md").is_file():
            problems.append(f"missing {config['skill']}/SKILL.md")
    if not (SKILLS / "textual" / "SKILL.md").is_file():
        problems.append("missing textual/SKILL.md")

    link_re = re.compile(r"\]\(([^)]+)\)")
    for page in sorted(SKILLS.glob("textual*/**/*.md")):
        body = page.read_text(encoding="utf-8")
        for target in link_re.findall(body):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = (page.parent / target).resolve()
            if not resolved.exists():
                problems.append(f"{page.relative_to(ROOT)} has dead link {target}")

    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 1
    print(f"ok: {len(data['items'])} references at Textual {PIN}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate instead of writing")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    write_tree()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
