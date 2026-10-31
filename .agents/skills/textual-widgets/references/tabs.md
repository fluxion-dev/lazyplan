# Tabs

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Tabs`
**Official:** https://textual.textualize.io/widgets/tabs/

A horizontal tab bar with active-tab state.

## Constructor

```python
Tabs(*tabs: 'Tab | ContentText', active: 'str | None' = None, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False)
```

## Key properties and methods

- active
- tab_count

## Messages

- TabActivated — emitted when a tab is activated.

## CSS

- Tabs — bar.
- tabs--tab, tabs--active, tabs--underline — parts.

## Example

```python
yield Tabs("One", "Two", active="one")
```

## Pitfalls

- Tab ids are the stable handle; add tabs with add_tab.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Tabs)`
