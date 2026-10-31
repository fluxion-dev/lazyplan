# Collapsible

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Collapsible`
**Official:** https://textual.textualize.io/widgets/collapsible/

A titled section that expands or collapses its children.

## Constructor

```python
Collapsible(*children: 'Widget', title: 'str' = 'Toggle', collapsed: 'bool' = True, collapsed_symbol: 'str' = '▶', expanded_symbol: 'str' = '▼', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False) -> 'None'
```

## Key properties and methods

- title
- collapsed
- collapsed_symbol
- expanded_symbol

## Messages

- Toggled — emitted when the section opens or closes.

## CSS

- Collapsible — frame.
- collapsible--title, collapsible--contents — parts.

## Example

```python
yield Collapsible(Static("Body"), title="Details")
```

## Pitfalls

- Constructor children are placed in the body; post-mount children are not.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Collapsible)`
