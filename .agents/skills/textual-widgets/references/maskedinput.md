# MaskedInput

**Textual:** 8.2.8 · **Import:** `from textual.widgets import MaskedInput`
**Official:** https://textual.textualize.io/widgets/maskedinput/

An Input that enforces a fixed character mask such as a date or phone number.

## Constructor

```python
MaskedInput(template: 'str', value: 'str | None' = None, placeholder: 'str' = '', *, validators: 'Validator | Iterable[Validator] | None' = None, validate_on: 'Iterable[InputValidationOn] | None' = None, valid_empty: 'bool' = False, select_on_focus: 'bool' = True, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, tooltip: 'RenderableType | None' = None, compact: 'bool' = False) -> 'None'
```

## Key properties and methods

- value
- template
- placeholder
- validators

## Messages

- Changed — emitted on edit.
- Submitted — emitted on Enter.

## CSS

- MaskedInput — inherits Input parts.

## Example

```python
yield MaskedInput(template="99/99/9999", id="date")
```

## Pitfalls

- The template characters are literal anchors; test paste and deletion paths.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.MaskedInput)`
