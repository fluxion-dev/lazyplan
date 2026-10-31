# DescendantFocus

**Textual:** 8.2.8 · **Import:** `from textual import events`
**Official:** https://textual.textualize.io/events/descendant_focus/

A descendant gained focus; the event bubbles through ancestors.

## Handler

`def on_descendant_focus(self, event: events.DescendantFocus) -> None`

Use the `@on` decorator when the handler name would collide with another event.

## Bubbling and cancelability

Bubbles: yes. Cancelable: no. Call
`event.stop()` to stop propagation, and `event.prevent_default()` only when the
event is cancelable.

## Attributes

`widget`

## Example

```python
def on_descendant_focus(self, event: events.DescendantFocus) -> None:
    self.refresh()
```

## See also

- [Events index](../SKILL.md)
- `textual.events.DescendantFocus` docstring
