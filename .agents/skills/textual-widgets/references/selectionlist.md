# SelectionList

**Textual:** 8.2.8 · **Import:** `from textual.widgets import SelectionList`
**Official:** https://textual.textualize.io/widgets/selectionlist/

A multi-select list of labelled values.

## Constructor

```python
SelectionList(*selections: 'Selection[SelectionType] | tuple[ContentText, SelectionType] | tuple[ContentText, SelectionType, bool]', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, compact: 'bool' = False)
```

## Key properties and methods

- selected
- compact

## Messages

- SelectedChanged — emitted when the selected set changes.

## CSS

- SelectionList — list.
- selection-list--button, selection-list--label — parts.

## Example

```python
yield SelectionList(("One", 1), ("Two", 2))
```

## Pitfalls

- Selection is keyed by value; duplicate values are ambiguous.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.SelectionList)`
