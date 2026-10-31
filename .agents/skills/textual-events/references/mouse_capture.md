# MouseCapture

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/mouse_capture/

A widget captured the mouse.

## Handler

`def on_mouse_capture(self, event: events.MouseCapture) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`mouse_event`

## Example

```python
def on_mouse_capture(self, event: events.MouseCapture) -> None:
    self.add_class("dragging")
```

## See also

- [Events index](../SKILL.md)
- `textual.events.MouseCapture` docstring
