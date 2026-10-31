# Actions

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/actions/

Named app/screen actions, bindings, and dynamic enablement.

## What it covers

- action_*
- Binding
- check_action
- priority
- show

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- App.BINDINGS
- Screen.BINDINGS
- Widget.action_*

## Related references

Guides:

- [input](input.md)
- [command_palette](command_palette.md)

Reference files:

- [events](../../textual-events/SKILL.md)

## Example

```python
BINDINGS = [Binding("q", "quit", "Quit")]
```

## Pitfalls

- Return False from check_action to disable a binding dynamically.
