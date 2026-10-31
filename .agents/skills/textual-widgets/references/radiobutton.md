# RadioButton

**Textual:** 8.2.8 · **Import:** `from textual.widgets import RadioButton`
**Official:** https://textual.textualize.io/widgets/radiobutton/

One choice in a RadioSet.

## Constructor

```python
RadioButton(label: 'ContentText' = '', value: 'bool' = False, button_first: 'bool' = True, *, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, tooltip: 'RenderableType | None' = None, compact: 'bool' = False) -> 'None'
```

## Key properties and methods

- value
- label
- disabled

## Messages

- Changed — emitted when selected.

## CSS

- RadioButton — row.
- toggle--button, toggle--label — parts.

## Example

```python
yield RadioButton("Fast", value=True)
```

## Pitfalls

- Group choices in RadioSet so only one stays selected.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.RadioButton)`
