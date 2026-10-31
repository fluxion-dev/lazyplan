# Screen

**Textual:** 8.2.8 · **Import:** `from textual.screen import Screen`
**Official:** https://textual.textualize.io/guide/screens/

A full-screen surface with its own bindings, title, and lifecycle.

## Constructor and usage

```python
Screen(name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None) -> 'None'
```

## Key behavior

- TITLE
- SUB_TITLE
- BINDINGS
- compose

## Example

```python
class DetailScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]
```

## Pitfalls

- Screens are pushed/popped, not mounted as children.

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
