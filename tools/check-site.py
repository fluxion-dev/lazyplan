#!/usr/bin/env python3
"""Site discoverability gate: metadata, structured data, links, and assets.

Usage:
  python3 tools/check-site.py                 # check site/ source
  python3 tools/check-site.py --dist site/dist # also check the built site

Stdlib only. Fails with a readable list so Pages and local gates stop before
shipping a page that can't be crawled or shared correctly.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://fluxion-dev.github.io/lazyplan/"


class PageParser(HTMLParser):
    """Collect the HTML facts the gate checks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.ids: list[str] = []
        self.json_ld: list[str] = []
        self._in_script = False
        self._script_type = ""
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {k: v or "" for k, v in attrs}
        self.tags.append((tag, data))
        if data.get("id"):
            self.ids.append(data["id"])
        if tag == "script" and data.get("type") == "application/ld+json":
            self._in_script = True
            self._script_type = data.get("type", "")
            self._script_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_script:
            self.json_ld.append("".join(self._script_parts))
            self._in_script = False
            self._script_type = ""


def _tag(page: PageParser, tag_name: str, **match: str) -> dict[str, str] | None:
    for tag, attrs in page.tags:
        if tag != tag_name:
            continue
        if all(attrs.get(key) == value for key, value in match.items()):
            return attrs
    return None


def _meta(page: PageParser, name: str) -> str:
    item = _tag(page, "meta", name=name)
    if item is None:
        item = _tag(page, "meta", property=name)
    return item.get("content", "") if item else ""


def _local_path(root: Path, value: str) -> Path | None:
    text = value.strip()
    if not text or text.startswith(("http://", "https://", "//", "data:")):
        return None
    parsed = urlparse(text)
    if parsed.scheme or parsed.netloc:
        return None
    path = parsed.path.lstrip("/")
    return root / path if path else None


def _check_metadata(page: PageParser, errors: list[str]) -> None:
    desc = _meta(page, "description")
    if not (20 <= len(desc) <= 170):
        errors.append(f"meta description must be 20-170 chars, got {len(desc)}")
    canonical = _tag(page, "link", rel="canonical")
    if canonical is None or canonical.get("href") != BASE_URL:
        errors.append(f"canonical must be {BASE_URL}")
    robots = _meta(page, "robots")
    if "index" not in robots or "follow" not in robots:
        errors.append("meta robots must allow index,follow")
    for name in ("og:title", "og:description", "og:type", "og:url", "og:image"):
        if not _meta(page, name):
            errors.append(f"missing {name}")
    if _meta(page, "og:url") != BASE_URL:
        errors.append("og:url must match the canonical")
    for name in ("twitter:card", "twitter:title", "twitter:description", "twitter:image"):
        if not _meta(page, name):
            errors.append(f"missing {name}")


def _check_headings(page: PageParser, errors: list[str]) -> None:
    levels = [int(tag[1]) for tag, _ in page.tags if re.fullmatch(r"h[1-6]", tag)]
    if levels.count(1) != 1:
        errors.append(f"expected exactly one h1, found {levels.count(1)}")
    if levels and levels[0] != 1:
        errors.append("first heading must be h1")
    previous = 0
    for level in levels:
        if previous and level > previous + 1:
            errors.append(f"heading order skips from h{previous} to h{level}")
            break
        previous = level


def _asset_path(root: Path, value: str) -> Path | None:
    """Resolve a local asset at the site root, falling back to public/."""
    path = _local_path(root, value)
    if path is None or path.is_file():
        return path
    try:
        relative = path.relative_to(root)
    except ValueError:
        return path
    public = root / "public" / relative
    return public if public.is_file() else path


def _check_assets(page: PageParser, root: Path, errors: list[str]) -> None:
    for tag, attrs in page.tags:
        if tag == "img":
            src = attrs.get("src", "")
            if not attrs.get("alt") and attrs.get("alt") != "":
                errors.append(f"image missing alt: {src or '(empty src)'}")
            path = _asset_path(root, src)
            if path is not None:
                for attr in ("width", "height"):
                    if not attrs.get(attr):
                        errors.append(f"local image missing {attr}: {src}")
                if not path.is_file():
                    errors.append(f"missing image: {path.relative_to(ROOT)}")
        elif tag == "source":
            for candidate in attrs.get("srcset", "").split(","):
                value = candidate.strip().split(" ")[0]
                path = _asset_path(root, value)
                if path is not None and not path.is_file():
                    errors.append(f"missing source asset: {path.relative_to(ROOT)}")


def _check_links(page: PageParser, errors: list[str]) -> None:
    ids = set(page.ids)
    if len(page.ids) != len(ids):
        errors.append("duplicate ids found")
    for tag, attrs in page.tags:
        if tag != "a":
            continue
        href = attrs.get("href", "").strip()
        if href.startswith("#") and len(href) > 1 and href[1:] not in ids:
            errors.append(f"broken internal anchor: {href}")


def _check_json_ld(page: PageParser, version: str, errors: list[str]) -> None:
    if not page.json_ld:
        errors.append("missing JSON-LD")
        return
    types: set[str] = set()
    for raw in page.json_ld:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON-LD: {exc}")
            continue
        blocks = data if isinstance(data, list) else [data]
        for block in blocks:
            if not isinstance(block, dict):
                continue
            kind = str(block.get("@type", ""))
            types.add(kind)
            if kind == "SoftwareApplication":
                for key in ("name", "url", "applicationCategory"):
                    if not block.get(key):
                        errors.append(f"SoftwareApplication missing {key}")
                if str(block.get("softwareVersion", block.get("version", ""))) != version:
                    errors.append("SoftwareApplication version must match pyproject")
            if kind == "FAQPage":
                questions = block.get("mainEntity", [])
                if not isinstance(questions, list) or len(questions) < 3:
                    errors.append("FAQPage needs at least three questions")
                    continue
                for item in questions:
                    if not isinstance(item, dict) or not item.get("name"):
                        errors.append("FAQPage question missing name")
                        continue
                    answer = item.get("acceptedAnswer", {})
                    if not isinstance(answer, dict) or not answer.get("text"):
                        errors.append("FAQPage question missing acceptedAnswer.text")
    for required in ("SoftwareApplication", "FAQPage"):
        if required not in types:
            errors.append(f"missing {required} JSON-LD")


def _check_sitemap(root: Path, errors: list[str]) -> None:
    sitemap = root / "sitemap.xml"
    if not sitemap.is_file():
        sitemap = root / "public/sitemap.xml"
    robots = root / "robots.txt"
    if not robots.is_file():
        robots = root / "public/robots.txt"
    if not sitemap.is_file():
        errors.append("missing sitemap.xml")
    else:
        text = sitemap.read_text()
        if BASE_URL not in text:
            errors.append("sitemap does not include the canonical URL")
        if not re.search(r"<lastmod>\d{4}-\d{2}-\d{2}</lastmod>", text):
            errors.append("sitemap needs an ISO lastmod")
    if not robots.is_file():
        errors.append("missing robots.txt")
    elif "Sitemap:" not in robots.read_text():
        errors.append("robots.txt must advertise the sitemap")


def _check_page(root: Path, version: str) -> list[str]:
    errors: list[str] = []
    index = root / "index.html"
    if not index.is_file():
        return [f"missing {index}"]
    source = index.read_text()
    page = PageParser()
    page.feed(source)
    title_match = re.search(r"<title>(.*?)</title>", source, re.S | re.I)
    title = title_match.group(1).strip() if title_match else ""
    if not (20 <= len(title) <= 65):
        errors.append(f"title must be 20-65 chars, got {len(title)}")
    _check_metadata(page, errors)
    _check_headings(page, errors)
    _check_assets(page, root, errors)
    _check_links(page, errors)
    _check_json_ld(page, version, errors)
    _check_sitemap(root, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", default="", metavar="PATH", help="also check a built site")
    args = parser.parse_args()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    failures: list[str] = []
    roots = [("site", ROOT / "site")]
    if args.dist:
        dist = (ROOT / args.dist).resolve()
        if not dist.is_dir():
            failures.append(f"missing dist directory: {dist}")
        else:
            roots.append(("dist", dist))
    for label, root in roots:
        for error in _check_page(root, version):
            failures.append(f"{label}: {error}")
    if failures:
        print("site check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"site ok: {', '.join(label for label, _root in roots)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
