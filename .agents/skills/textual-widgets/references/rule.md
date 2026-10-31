# Rule

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Rule`
**Official:** https://textual.textualize.io/widgets/rule/

A horizontal or vertical divider.

## Constructor

```python
Rule(orientation: 'RuleOrientation' = 'horizontal', line_style: 'LineStyle' = 'solid', *, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False) -> 'None'
```

## Key properties and methods

- orientation

## Messages

- None.

## CSS

- Rule — line; rule--horizontal, rule--vertical — variants.

## Example

```python
yield Rule(orientation="horizontal")
```

## Pitfalls

- Use CSS margin for spacing; Rule is only the line.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Rule)`
