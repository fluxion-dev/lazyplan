# OptionList

**Textual:** 8.2.8 · **Import:** `from textual.widgets import OptionList`
**Official:** https://textual.textualize.io/widgets/optionlist/

A compact single-choice list of Option entries with filtering support.

## Constructor

```python
OptionList(*content: 'OptionListContent', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, markup: 'bool' = True, compact: 'bool' = False)
```

## Key properties and methods

- highlighted
- compact
- option_count

## Messages

- OptionHighlighted — emitted on cursor movement.
- OptionSelected — emitted on activation.

## CSS

- OptionList — list.
- option-list--option, option-list--option-highlighted — parts.

## Example

```python
yield OptionList(Option("Open", id="open"), Option("Quit", id="quit"))
```

## Pitfalls

- Option ids are the stable handle; use clear_options/add_options for dynamic lists.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.OptionList)`
