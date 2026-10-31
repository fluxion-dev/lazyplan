# Focus

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/focus/

A widget gained keyboard focus.

## Handler

`def on_focus(self, event: events.Focus) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`none`

## Example

```python
def on_focus(self) -> None:
    self.add_class("active")
```

## See also

- [Events index](../SKILL.md)
- `textual.events.Focus` docstring
