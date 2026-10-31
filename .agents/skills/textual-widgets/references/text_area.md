# TextArea

**Textual:** 8.2.8 · **Import:** `from textual.widgets import TextArea`
**Official:** https://textual.textualize.io/widgets/text_area/

A multi-line editor with syntax highlighting, selections, and undo.

## Constructor

```python
TextArea(text: 'str' = '', *, language: 'str | None' = None, theme: 'str' = 'css', soft_wrap: 'bool' = True, tab_behavior: "Literal['focus', 'indent']" = 'focus', read_only: 'bool' = False, show_cursor: 'bool' = True, show_line_numbers: 'bool' = False, line_number_start: 'int' = 1, max_checkpoints: 'int' = 50, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, tooltip: 'RenderableType | None' = None, compact: 'bool' = False, highlight_cursor_line: 'bool' = True, placeholder: 'str | Content' = '') -> 'None'
```

## Key properties and methods

- text
- language
- theme
- soft_wrap
- read_only
- show_line_numbers
- tab_behavior

## Messages

- Changed — emitted on edit.
- SelectionChanged — emitted on selection change.

## CSS

- TextArea — editor.
- text-area--gutter, text-area--cursor, text-area--selection — parts.

## Example

```python
yield TextArea("hello", language="python", show_line_numbers=True)
```

## Pitfalls

- Many TextAreas are heavy; prefer one editor pane over a list of editors.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.TextArea)`
