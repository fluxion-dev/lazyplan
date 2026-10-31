# Toast

**Textual:** 8.2.8 · **Import:** `from textual.widgets._toast import Toast`
**Official:** https://textual.textualize.io/widgets/toast/

A transient notification card managed by the app.

## Constructor

```python
Toast(notification: 'Notification') -> 'None'
```

## Key properties and methods

- message
- title
- severity
- timeout

## Messages

- None.

## CSS

- Toast — card.
- toast--title, toast--message — parts.

## Example

```python
self.notify("Saved", title="Plan", timeout=3)
```

## Pitfalls

- Use App.notify rather than mounting Toast directly.

## See also

- [Widgets index](../SKILL.md)
- self.notify(...) is the public API
