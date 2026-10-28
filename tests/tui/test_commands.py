"""One command registry: palette, keymap, help, and CLI aliases agree."""

import argparse
import unittest

from lazyplan import palette
from lazyplan.cli.parser import build_parser


def _subcommands() -> dict[str, argparse.ArgumentParser]:
    parser = build_parser()
    subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return dict(subs.choices)


class TestCommandRegistry(unittest.TestCase):
    def test_ids_and_labels_are_unique(self):
        ids = [cmd.id for cmd in palette.COMMANDS]
        labels = [cmd.label for cmd in palette.COMMANDS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(labels), len(set(labels)))

    def test_every_command_has_a_known_section(self):
        for cmd in palette.COMMANDS:
            self.assertIn(cmd.section, palette.SECTIONS, cmd.id)
            self.assertTrue(cmd.label.strip(), cmd.id)
            self.assertTrue(cmd.handler.strip(), cmd.id)

    def test_palette_sections_cover_commands_once(self):
        ids = [cmd.id for cmd in palette.palette_commands()]
        sectioned = [cid for _, section in palette.palette_sections() for cid in section]
        self.assertEqual(sectioned, ids)
        self.assertEqual(len(sectioned), len(set(sectioned)))
        self.assertEqual([name for name, _ in palette.palette_sections()], list(palette.SECTIONS))

    def test_data_commands_use_the_glossary(self):
        for cmd in palette.COMMANDS:
            if cmd.tui_only:
                self.assertEqual(cmd.verb, "", cmd.id)
                continue
            self.assertIn(cmd.verb, palette.VERBS, cmd.id)
            for noun in cmd.nouns:
                self.assertIn(noun, palette.NOUNS, cmd.id)
            self.assertTrue(cmd.verb, cmd.id)

    def test_every_data_command_maps_to_a_legacy_cli_verb(self):
        parser = _subcommands()
        for cmd in palette.COMMANDS:
            if cmd.tui_only:
                continue
            for noun in cmd.nouns or ("",):
                key = (noun, cmd.verb)
                legacy = palette.LEGACY_COMMANDS.get(key)
                self.assertIsNotNone(legacy, f"{key} has no legacy CLI alias")
                for name in legacy or ():
                    self.assertIn(name, parser, f"lpui {name} is missing")

    def test_legacy_aliases_are_documented(self):
        parser = _subcommands()
        for names in palette.LEGACY_COMMANDS.values():
            for name in names:
                self.assertIn(name, parser, f"lpui {name} is missing")

    def test_matching_finds_labels_aliases_and_verbs(self):
        def ids(query: str) -> list[str]:
            return [cmd.id for _, cmds in palette.matching(query) for cmd in cmds]

        self.assertIn("create-task", ids("add task"))
        self.assertIn("create-task", ids("Create task"))
        self.assertIn("move-done", ids("complete"))
        self.assertIn("tick-criterion", ids("check"))
        self.assertIn("open-detail", ids("show"))
        self.assertEqual(ids("zzz-no-such-command"), [])

    def test_help_shows_every_keymap_key(self):
        table = " ".join(key for key, _action, _surface in palette.KEYMAP)
        for key, _hint, _surface in palette.KEYMAP:
            first = key.split(",")[0].split()[0]
            self.assertIn(first, palette.HELP_TEXT, key)
            self.assertIn(first, table, key)

    def test_help_has_no_stale_claims(self):
        self.assertNotIn("press n to seed", palette.HELP_TEXT)
        self.assertNotIn("c ticks", palette.HELP_TEXT)
        self.assertIn("n", palette.HELP_TEXT)
        self.assertIn("s", palette.HELP_TEXT)
        self.assertIn("?", palette.HELP_TEXT)

    def test_labels_avoid_mechanism_jargon(self):
        banned = ("with confirm", "capped", "create…", "cycle status", "show all /")
        for cmd in palette.palette_commands():
            for word in banned:
                self.assertNotIn(word, cmd.label.lower(), cmd.id)

    def test_help_and_palette_are_importable_without_textual(self):
        # The registry must stay stdlib-only: the CLI and stdlib tests use it.
        with open(palette.__file__, encoding="utf-8") as fh:
            source = fh.read().lower()
        self.assertNotIn("import textual", source)
        self.assertNotIn("from textual", source)
        self.assertTrue(palette.HELP_TEXT)


if __name__ == "__main__":
    unittest.main()
