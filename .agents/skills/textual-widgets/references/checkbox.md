# Checkbox

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Checkbox`
**Official:** https://textual.textualize.io/widgets/checkbox/

A labelled boolean toggle with an optional indeterminate state.

## Constructor

```python
Checkbox(label: 'ContentText' = '', value: 'bool' = False, button_first: 'bool' = True, *, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, tooltip: 'RenderableType | None' = None, compact: 'bool' = False) -> 'None'
```

## Key properties and methods

- value
- label
- compact
- disabled

## Messages

- Changed — emitted when value changes; initial value is silent.

## CSS

- Checkbox — the row.
- toggle--button, toggle--label — parts.

## Example

```python
yield Checkbox("Enable hooks", value=True, id="hooks")
```

## Pitfalls

- Set value before mount when it represents saved state.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Checkbox)`
