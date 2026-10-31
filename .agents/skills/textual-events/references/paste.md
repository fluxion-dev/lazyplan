# Paste

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/paste/

Text was pasted into the app.

## Handler

`def on_paste(self, event: events.Paste) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: yes. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`text`

## Example

```python
def on_paste(self, event: events.Paste) -> None:
    self.insert(event.text)
```

## See also

- [Events index](../SKILL.md)
- `textual.events.Paste` docstring
