# MouseRelease

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/mouse_release/

A captured mouse button was released.

## Handler

`def on_mouse_release(self, event: events.MouseRelease) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: yes. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`x, y, delta_x, delta_y, button`

## Example

```python
def on_mouse_release(self) -> None:
    self.remove_class("dragging")
```

## See also

- [Events index](../SKILL.md)
- `textual.events.MouseRelease` docstring
