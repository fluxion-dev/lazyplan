# Screens

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/screens/

Push, pop, switch, and modal screens with their own bindings and lifecycle.

## What it covers

- Screen
- ModalScreen
- push_screen
- pop_screen
- switch_screen
- screen stack

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- Screen
- ModalScreen
- App.push_screen

## Related references

Guides:

- [app](app.md)
- [events](events.md)

Reference files:

- [layout](../../textual-layout/SKILL.md)
- [events](../../textual-events/SKILL.md)

## Example

```python
self.push_screen(ConfirmScreen("Delete?"))
```

## Pitfalls

- Dismiss before popping; never stack the same modal twice.
