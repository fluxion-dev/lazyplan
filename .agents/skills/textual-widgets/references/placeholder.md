# Placeholder

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Placeholder`
**Official:** https://textual.textualize.io/widgets/placeholder/

A development-only block that stands in for an unfinished widget.

## Constructor

```python
Placeholder(label: 'str | None' = None, variant: 'PlaceholderVariant' = 'default', *, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False) -> 'None'
```

## Key properties and methods

- label
- variant

## Messages

- None.

## CSS

- Placeholder — dashed block.

## Example

```python
yield Placeholder("Chart goes here")
```

## Pitfalls

- Remove placeholders before shipping; they are intentionally plain.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Placeholder)`
