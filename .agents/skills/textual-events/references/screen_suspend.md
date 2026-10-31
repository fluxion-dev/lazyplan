# ScreenSuspend

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/screen_suspend/

A screen was suspended by another screen.

## Handler

`def on_screen_suspend(self, event: events.ScreenSuspend) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: no. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`none`

## Example

```python
def on_screen_suspend(self) -> None:
    self.pause_updates()
```

## See also

- [Events index](../SKILL.md)
- `textual.events.ScreenSuspend` docstring
