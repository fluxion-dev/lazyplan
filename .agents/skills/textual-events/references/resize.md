# Resize

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/resize/

The app or widget was resized.

## Handler

`def on_resize(self, event: events.Resize) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: no. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`size, virtual_size`

## Example

```python
def on_resize(self, event: events.Resize) -> None:
    self.narrow = event.size.width < 100
```

## See also

- [Events index](../SKILL.md)
- `textual.events.Resize` docstring
