# Unmount

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/unmount/

A widget is about to be removed.

## Handler

`def on_unmount(self, event: events.Unmount) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: no. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`none`

## Example

```python
def on_unmount(self) -> None:
    self.timer.stop()
```

## See also

- [Events index](../SKILL.md)
- `textual.events.Unmount` docstring
