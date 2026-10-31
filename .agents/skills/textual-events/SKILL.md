---
name: textual-events
description: Every Textual 8.2.8 event: handler name, bubbling, cancelability, attributes, and examples. Use when handling input, focus, mouse, lifecycle, or screen events.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# Textual events — Textual 8.2.8

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
| [AppBlur](references/app_blur.md) | `app_blur` |
| [AppFocus](references/app_focus.md) | `app_focus` |
| [Blur](references/blur.md) | `blur` |
| [Click](references/click.md) | `click` |
| [DescendantBlur](references/descendant_blur.md) | `descendant_blur` |
| [DescendantFocus](references/descendant_focus.md) | `descendant_focus` |
| [Enter](references/enter.md) | `enter` |
| [Focus](references/focus.md) | `focus` |
| [Hide](references/hide.md) | `hide` |
| [Key](references/key.md) | `key` |
| [Leave](references/leave.md) | `leave` |
| [Load](references/load.md) | `load` |
| [Mount](references/mount.md) | `mount` |
| [MouseCapture](references/mouse_capture.md) | `mouse_capture` |
| [MouseDown](references/mouse_down.md) | `mouse_down` |
| [MouseMove](references/mouse_move.md) | `mouse_move` |
| [MouseRelease](references/mouse_release.md) | `mouse_release` |
| [MouseScrollDown](references/mouse_scroll_down.md) | `mouse_scroll_down` |
| [MouseScrollUp](references/mouse_scroll_up.md) | `mouse_scroll_up` |
| [MouseUp](references/mouse_up.md) | `mouse_up` |
| [Paste](references/paste.md) | `paste` |
| [Print](references/print.md) | `print` |
| [Resize](references/resize.md) | `resize` |
| [ScreenResume](references/screen_resume.md) | `screen_resume` |
| [ScreenSuspend](references/screen_suspend.md) | `screen_suspend` |
| [Show](references/show.md) | `show` |
| [Unmount](references/unmount.md) | `unmount` |

## See also

- [Textual router](../textual/SKILL.md)
- [Coverage manifest](../textual/references/_manifest.json)
