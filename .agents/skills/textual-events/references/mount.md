# Mount

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/mount/

A widget was mounted and can receive messages.

## Handler

`def on_mount(self, event: events.Mount) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: no. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`none`

## Example

```python
def on_mount(self) -> None:
    self.set_interval(1.0, self.tick)
```

## See also

- [Events index](../SKILL.md)
- `textual.events.Mount` docstring
