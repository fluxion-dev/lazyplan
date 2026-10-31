# Footer

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Footer`
**Official:** https://textual.textualize.io/widgets/footer/

A bar of the active screen's bindings.

## Constructor

```python
Footer(*children: 'Widget', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, show_command_palette: 'bool' = True, compact: 'bool' = False) -> 'None'
```

## Key properties and methods

- compact
- show_command_palette

## Messages

- None.

## CSS

- Footer — bar.
- footer--key, footer--description — parts.

## Example

```python
yield Footer(compact=True)
```

## Pitfalls

- Bindings come from the screen/app; hide the palette hint when the app disables it.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Footer)`
