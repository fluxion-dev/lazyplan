# ScreenResume

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/screen_resume/

A screen became active again after being suspended.

## Handler

`def on_screen_resume(self, event: events.ScreenResume) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: no. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`none`

## Example

```python
def on_screen_resume(self) -> None:
    self.refresh_data()
```

## See also

- [Events index](../SKILL.md)
- `textual.events.ScreenResume` docstring
