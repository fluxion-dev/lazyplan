# Markdown

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Markdown`
**Official:** https://textual.textualize.io/widgets/markdown/

A scrollable Markdown renderer with links and headings.

## Constructor

```python
Markdown(markdown: 'str | None' = None, *, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, parser_factory: 'Callable[[], MarkdownIt] | None' = None, open_links: 'bool' = True)
```

## Key properties and methods

- markdown

## Messages

- LinkClicked — emitted when a link is followed.

## CSS

- Markdown — document.
- markdown--heading, markdown--code, markdown--link — parts.

## Example

```python
yield Markdown("# Release notes\n\n- fixed")
```

## Pitfalls

- Markdown is read-only; use MarkdownViewer for a TOC.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Markdown)`
