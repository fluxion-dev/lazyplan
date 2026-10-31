# DescendantBlur

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/descendant_blur/

A descendant lost focus; the event bubbles through ancestors.

## Handler

`def on_descendant_blur(self, event: events.DescendantBlur) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`widget`

## Example

```python
def on_descendant_blur(self, event: events.DescendantBlur) -> None:
    self.refresh()
```

## See also

- [Events index](../SKILL.md)
- `textual.events.DescendantBlur` docstring
