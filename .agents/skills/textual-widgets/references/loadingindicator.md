# LoadingIndicator

**Textual:** 8.2.8 · **Import:** `from textual.widgets import LoadingIndicator`
**Official:** https://textual.textualize.io/widgets/loadingindicator/

An animated spinner for work in progress.

## Constructor

```python
LoadingIndicator(name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False)
```

## Key properties and methods

- speed

## Messages

- None.

## CSS

- LoadingIndicator — spinner area.

## Example

```python
yield LoadingIndicator()
```

## Pitfalls

- Remove or hide it when the work completes; it does not manage the task.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.LoadingIndicator)`
