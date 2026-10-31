# Digits

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Digits`
**Official:** https://textual.textualize.io/widgets/digits/

Large seven-segment style digits for counters and dashboards.

## Constructor

```python
Digits(value: 'str' = '', *, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False) -> 'None'
```

## Key properties and methods

- value
- digits

## Messages

- None.

## CSS

- Digits — the digit strip.

## Example

```python
yield Digits("42", id="count")
```

## Pitfalls

- Non-digit characters are ignored; width follows the string.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Digits)`
