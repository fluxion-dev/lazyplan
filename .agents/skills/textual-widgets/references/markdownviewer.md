# MarkdownViewer

**Textual:** 8.2.8 · **Import:** `from textual.widgets import MarkdownViewer`
**Official:** https://textual.textualize.io/widgets/markdownviewer/

A Markdown document with a table-of-contents pane.

## Constructor

```python
MarkdownViewer(markdown: 'str | None' = None, *, show_table_of_contents: 'bool' = True, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, parser_factory: 'Callable[[], MarkdownIt] | None' = None, open_links: 'bool' = True)
```

## Key properties and methods

- show_table_of_contents
- markdown

## Messages

- None.

## CSS

- MarkdownViewer — split view.
- MarkdownViewer--contents, MarkdownViewer--document — parts.

## Example

```python
yield MarkdownViewer("# Title\n\nBody", show_table_of_contents=True)
```

## Pitfalls

- The document pane is a Markdown widget; style it through the viewer.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.MarkdownViewer)`
