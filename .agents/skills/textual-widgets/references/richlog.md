# RichLog

**Textual:** 8.2.8 · **Import:** `from textual.widgets import RichLog`
**Official:** https://textual.textualize.io/widgets/richlog/

A scrollable log that accepts Rich renderables.

## Constructor

```python
RichLog(*, max_lines: 'int | None' = None, min_width: 'int' = 78, wrap: 'bool' = False, highlight: 'bool' = False, markup: 'bool' = False, auto_scroll: 'bool' = True, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False) -> 'None'
```

## Key properties and methods

- max_lines
- auto_scroll
- wrap
- markup

## Messages

- None.

## CSS

- RichLog — scrollable log.

## Example

```python
log = RichLog(); log.write(Text("done", style="green"))
```

## Pitfalls

- Rich renderables are retained; bound max_lines for streaming logs.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.RichLog)`
