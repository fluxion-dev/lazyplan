# Tree

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Tree`
**Official:** https://textual.textualize.io/widgets/tree/

A hierarchical outline with cursors, folding, and node data.

## Constructor

```python
Tree(label: 'TextType', data: 'TreeDataType | None' = None, *, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False) -> 'None'
```

## Key properties and methods

- root
- show_root
- guides
- auto_expand

## Messages

- NodeHighlighted — emitted on cursor movement.
- NodeSelected — emitted on activation.
- NodeCollapsed / NodeExpanded — emitted on fold changes.

## CSS

- Tree — outline.
- tree--cursor, tree--guides, tree--highlight — parts.

## Example

```python
tree = Tree("root"); node = tree.root.add("child", data={"id": 1}); tree.root.expand()
```

## Pitfalls

- Store model ids in TreeNode.data; never parse labels.
- Use select_node/scroll_to_node for programmatic movement.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Tree)`
