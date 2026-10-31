# Input

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Input`
**Official:** https://textual.textualize.io/widgets/input/

A single-line text field with validation, suggestions, and submit.

## Constructor

```python
Input(value: 'str | None' = None, placeholder: 'str' = '', highlighter: 'Highlighter | None' = None, password: 'bool' = False, *, restrict: 'str | None' = None, type: 'InputType' = 'text', max_length: 'int' = 0, suggester: 'Suggester | None' = None, validators: 'Validator | Iterable[Validator] | None' = None, validate_on: 'Iterable[InputValidationOn] | None' = None, valid_empty: 'bool' = False, select_on_focus: 'bool' = True, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, tooltip: 'RenderableType | None' = None, compact: 'bool' = False) -> 'None'
```

## Key properties and methods

- value
- placeholder
- password
- type
- validators
- suggester
- compact

## Messages

- Changed — emitted on each edit.
- Submitted — emitted on Enter.
- Blurred — emitted when focus leaves.

## CSS

- Input — field.
- input--cursor, input--placeholder, input--suggestion — parts.

## Example

```python
yield Input(placeholder="Filter…", id="filter")
```

## Pitfalls

- Use type='integer'/'number' for numeric hints; validate explicitly when correctness matters.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Input)`
