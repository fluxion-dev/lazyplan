# Devtools

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/devtools/

Debug a running app with the Textual devtools server, console, and live CSS editing.

## What it covers

- textual run --dev
- devtools console
- live CSS reload
- log inspection

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- App.run
- App.log
- textual console

## Related references

Guides:

- [app](app.md)
- [testing](testing.md)

Reference files:

- [widgets](../../textual-widgets/SKILL.md)

## Example

```python
textual run --dev app.py
```

## Pitfalls

- Devtools adds overhead; do not benchmark with it attached.
