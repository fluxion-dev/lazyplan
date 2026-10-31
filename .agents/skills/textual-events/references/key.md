# Key

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/key/

A key was pressed while the widget had focus.

## Handler

`def on_key(self, event: events.Key) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: yes. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`key, character, name, is_printable, modifiers`

## Example

```python
def on_key(self, event: events.Key) -> None:
    if event.key == "escape":
        self.dismiss()
```

## See also

- [Events index](../SKILL.md)
- `textual.events.Key` docstring
