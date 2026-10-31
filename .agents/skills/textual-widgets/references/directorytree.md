# DirectoryTree

**Textual:** 8.2.8 · **Import:** `from textual.widgets import DirectoryTree`
**Official:** https://textual.textualize.io/widgets/directorytree/

A Tree subclass that lazily lists a filesystem directory.

## Constructor

```python
DirectoryTree(path: 'str | Path', *, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False) -> 'None'
```

## Key properties and methods

- path
- show_root
- dir_excluded

## Messages

- FileSelected — emitted when a file is activated.
- DirectorySelected — emitted for directories.

## CSS

- DirectoryTree — inherits Tree parts; tree--cursor and tree--guides apply.

## Example

```python
yield DirectoryTree("./src", id="files")
```

## Pitfalls

- Large directories are lazy; do not assume all nodes are loaded.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.DirectoryTree)`
