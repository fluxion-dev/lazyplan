# Log

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Log`
**Official:** https://textual.textualize.io/widgets/log/

An auto-scrolling plain-text log with optional timestamps.

## Constructor

```python
Log(highlight: 'bool' = False, max_lines: 'int | None' = None, auto_scroll: 'bool' = True, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False) -> 'None'
```

## Key properties and methods

- max_lines
- auto_scroll

## Messages

- None.

## CSS

- Log — scrollable text.

## Example

```python
log = Log(); log.write_line("started")
```

## Pitfalls

- Bound max_lines for long-running logs; write_line is the append API.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Log)`
