---
name: textual-widgets
description: Every Textual 8.2.8 widget: constructor, key APIs, messages, CSS hooks, examples, and pitfalls. Use when choosing or wiring any built-in widget.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# Textual widgets — Textual 8.2.8

Read the matching reference before writing or changing this part of a Textual
app. Every entry links the official page and the pinned API.

## Rules

- Pin all advice to Textual 8.2.8; check the installed version when a symbol is missing.
- Prefer composition and classes over inline styles and deep inheritance.
- Never copy long passages from the official docs; summarize and link.
- After a Textual upgrade, run `python3 tools/gen_textual_skills.py --check`.

## Index

| Item | Id |
| --- | --- |
| [Button](references/button.md) | `button` |
| [Checkbox](references/checkbox.md) | `checkbox` |
| [Collapsible](references/collapsible.md) | `collapsible` |
| [ContentSwitcher](references/contentswitcher.md) | `contentswitcher` |
| [DataTable](references/datatable.md) | `datatable` |
| [Digits](references/digits.md) | `digits` |
| [DirectoryTree](references/directorytree.md) | `directorytree` |
| [Footer](references/footer.md) | `footer` |
| [Header](references/header.md) | `header` |
| [Input](references/input.md) | `input` |
| [Label](references/label.md) | `label` |
| [Link](references/link.md) | `link` |
| [ListItem](references/listitem.md) | `listitem` |
| [ListView](references/listview.md) | `listview` |
| [LoadingIndicator](references/loadingindicator.md) | `loadingindicator` |
| [Log](references/log.md) | `log` |
| [MarkdownViewer](references/markdownviewer.md) | `markdownviewer` |
| [Markdown](references/markdown.md) | `markdown` |
| [MaskedInput](references/maskedinput.md) | `maskedinput` |
| [OptionList](references/optionlist.md) | `optionlist` |
| [Placeholder](references/placeholder.md) | `placeholder` |
| [Pretty](references/pretty.md) | `pretty` |
| [ProgressBar](references/progressbar.md) | `progressbar` |
| [RadioButton](references/radiobutton.md) | `radiobutton` |
| [RadioSet](references/radioset.md) | `radioset` |
| [RichLog](references/richlog.md) | `richlog` |
| [Rule](references/rule.md) | `rule` |
| [Select](references/select.md) | `select` |
| [SelectionList](references/selectionlist.md) | `selectionlist` |
| [Sparkline](references/sparkline.md) | `sparkline` |
| [Static](references/static.md) | `static` |
| [Switch](references/switch.md) | `switch` |
| [TabbedContent](references/tabbedcontent.md) | `tabbedcontent` |
| [Tabs](references/tabs.md) | `tabs` |
| [TextArea](references/text_area.md) | `text_area` |
| [Toast](references/toast.md) | `toast` |
| [Tree](references/tree.md) | `tree` |

## See also

- [Textual router](../textual/SKILL.md)
- [Coverage manifest](../textual/references/_manifest.json)
