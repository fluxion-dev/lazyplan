# Select

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Select`
**Official:** https://textual.textualize.io/widgets/select/

A dropdown that selects one value from a list.

## Constructor

```python
Select(options: 'Iterable[tuple[RenderableType, SelectType]]', *, prompt: 'str' = 'Select', allow_blank: 'bool' = True, value: 'SelectType | NoSelection' = Select.NULL, type_to_search: 'bool' = True, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, tooltip: 'RenderableType | None' = None, compact: 'bool' = False)
```

## Key properties and methods

- value
- options
- prompt
- allow_blank

## Messages

- Changed — emitted when the value changes.

## CSS

- Select — field.
- select--overlay, select--option-list — parts.

## Example

```python
yield Select([("One", 1), ("Two", 2)], prompt="Pick one")
```

## Pitfalls

- Option values are arbitrary objects; compare by value, not label.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Select)`
