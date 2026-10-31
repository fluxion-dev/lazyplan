# Blur

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/blur/

A widget lost keyboard focus.

## Handler

`def on_blur(self, event: events.Blur) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`none`

## Example

```python
def on_blur(self) -> None:
    self.add_class("idle")
```

## See also

- [Events index](../SKILL.md)
- `textual.events.Blur` docstring
