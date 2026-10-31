# ModalScreen

**Textual:** 8.2.8 · **Import:** `from textual.screen import ModalScreen`
**Official:** https://textual.textualize.io/guide/screens/

A screen that blocks interaction with the screen below.

## Constructor and usage

```python
ModalScreen(name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None) -> 'None'
```

## Key behavior

- dismiss
- BINDINGS
- compose

## Example

```python
class Confirm(ModalScreen[bool]):
    def compose(self):
        yield Button("OK", id="ok")
```

## Pitfalls

- Dismiss with a typed payload; Esc should cancel.

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
