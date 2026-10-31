# ListView

**Textual:** 8.2.8 · **Import:** `from textual.widgets import ListView`
**Official:** https://textual.textualize.io/widgets/listview/

A vertical list of ListItem children with a highlight cursor.

## Constructor

```python
ListView(*children: 'ListItem', initial_index: 'int | None' = 0, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False) -> 'None'
```

## Key properties and methods

- index
- initial_index

## Messages

- Highlighted — emitted when the cursor moves.
- Selected — emitted when an item is activated.

## CSS

- ListView — list.
- listview--item, listview--highlight — parts.

## Example

```python
yield ListView(ListItem(Label("One")), ListItem(Label("Two")))
```

## Pitfalls

- Children must be ListItem; use append/extend for dynamic rows.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.ListView)`
