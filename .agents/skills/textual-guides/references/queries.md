# DOM Queries

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/queries/

Find widgets with query, query_one, and typed selectors.

## What it covers

- query
- query_one
- CSS selectors
- NoMatches
- TooManyMatches

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- DOMNode.query
- DOMNode.query_one
- DOMNode.query_children

## Related references

Guides:

- [css](css.md)
- [widgets](widgets.md)

Reference files:

- [widgets](../../textual-widgets/SKILL.md)

## Example

```python
self.query_one("#status", Label).update("ready")
```

## Pitfalls

- Do not query before mount; handle NoMatches explicitly.
