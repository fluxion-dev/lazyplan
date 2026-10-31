# Header

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Header`
**Official:** https://textual.textualize.io/widgets/header/

A top bar showing the app or screen title and clock.

## Constructor

```python
Header(show_clock: 'bool' = False, *, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, icon: 'str | None' = None, time_format: 'str | None' = None)
```

## Key properties and methods

- show_clock

## Messages

- None.

## CSS

- Header — bar.
- header--title, header--clock — parts.

## Example

```python
yield Header(show_clock=True)
```

## Pitfalls

- Use Screen.TITLE / SUB_TITLE for per-screen titles.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Header)`
