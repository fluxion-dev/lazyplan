# Composition and lifecycle

**Textual:** 8.2.8 · **Import:** `from textual.app import ComposeResult`
**Official:** https://textual.textualize.io/guide/screens/

How compose, mount, suspend, resume, and unmount fit together.

## Constructor and usage

```python
def compose(self) -> ComposeResult: ...
```

## Key behavior

- compose
- on_mount
- on_unmount
- on_screen_suspend
- on_screen_resume

## Example

```python
def compose(self):
    yield Header()
    with Container():
        yield Static("body")
```

## Pitfalls

- Query widgets after mount; async work belongs in workers.

## See also

- [Layout index](../SKILL.md)
- [Screens guide](../../textual-guides/references/screens.md) for navigation and modality
