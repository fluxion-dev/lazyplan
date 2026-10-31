# App Basics

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/app/

The App lifecycle, compose, screens, CSS, and the message loop.

## What it covers

- App class
- compose()
- on_mount
- run()
- screen stack

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- App
- ComposeResult
- Screen

## Related references

Guides:

- [screens](screens.md)
- [css](css.md)
- [events](events.md)

Reference files:

- [widgets](../../textual-widgets/SKILL.md)
- [events](../../textual-events/SKILL.md)

## Example

```python
class MyApp(App):
    def compose(self):
        yield Header()
        yield Footer()
```

## Pitfalls

- Mount widgets in compose; do not query before mount.
