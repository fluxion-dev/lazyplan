"""Choice manifests: validation, the pick, and the atomic selection file."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan.services import choices

PNG = b"\x89PNG\r\n\x1a\n"


def write_manifest(root: Path, payload: object, *, name: str = "choices.json") -> Path:
    """Write one manifest file and return its path."""
    path = root / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def option(option_id: str = "a", image: str = "a.png", **extra: object) -> dict:
    """One valid option, with overrides."""
    row = {"id": option_id, "label": f"Option {option_id}", "image": image}
    row.update(extra)
    return row


def payload(*options: dict, **extra: object) -> dict:
    """One valid manifest, with overrides."""
    body = {
        "title": "Empty state",
        "prompt": "Which one should ship?",
        "options": list(options) or [option(), option("b", "b.png")],
    }
    body.update(extra)
    return body


class ManifestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ("a.png", "b.png"):
            (self.root / name).write_bytes(PNG)

    def load(self, body: object) -> choices.ChoiceManifest:
        return choices.load_manifest(write_manifest(self.root, body))

    def assert_error(self, body: object, needle: str) -> None:
        with self.assertRaises(choices.ChoiceError) as raised:
            self.load(body)
        self.assertIn(needle, str(raised.exception))


class LoadManifestTest(ManifestCase):
    def test_valid_manifest_keeps_every_option(self) -> None:
        manifest = self.load(
            payload(
                option("a", description="Compact card"),
                option("b", "b.png"),
                allow_notes=False,
            )
        )

        self.assertEqual(manifest.title, "Empty state")
        self.assertEqual(manifest.prompt, "Which one should ship?")
        self.assertEqual([row.id for row in manifest.options], ["a", "b"])
        self.assertEqual(manifest.options[0].description, "Compact card")
        self.assertEqual(manifest.options[1].description, "")
        self.assertEqual(manifest.options[0].relative, "a.png")
        self.assertEqual(manifest.options[0].image, (self.root / "a.png").resolve())
        self.assertFalse(manifest.allow_notes)
        self.assertEqual(manifest.root, self.root.resolve())

    def test_notes_are_allowed_by_default(self) -> None:
        self.assertTrue(self.load(payload()).allow_notes)

    def test_missing_file_and_bad_json(self) -> None:
        with self.assertRaises(choices.ChoiceError):
            choices.load_manifest(self.root / "missing.json")
        self.assert_error("{", "not valid JSON")
        self.assert_error("[]", "JSON object")

    def test_title_and_prompt_are_required(self) -> None:
        self.assert_error(payload(title=""), "title")
        self.assert_error(payload(prompt=None), "prompt")
        self.assert_error(payload(title="x" * 121), "title")

    def test_options_need_two_to_twelve(self) -> None:
        self.assert_error(payload(option()), "options needs 2")
        many = [option(f"o{index}", "a.png") for index in range(13)]
        self.assert_error(payload(*many), "options needs 2")
        self.assert_error(payload(options="a.png"), "options must be a list")
        self.assert_error(payload(options=[option(), "x"]), "options[1] must be an object")

    def test_ids_are_lowercase_and_unique(self) -> None:
        self.assert_error(payload(option("A"), option("b", "b.png")), "options[0].id")
        self.assert_error(payload(option("a"), option("a", "b.png")), "duplicated")

    def test_labels_and_descriptions_are_bounded(self) -> None:
        self.assert_error(payload(option(label=""), option("b", "b.png")), "label")
        self.assert_error(
            payload(option(label="x" * 81), option("b", "b.png")),
            "label",
        )
        self.assert_error(
            payload(option(description="x" * 501), option("b", "b.png")),
            "description",
        )

    def test_allow_notes_must_be_boolean(self) -> None:
        self.assert_error(payload(allow_notes="yes"), "allow_notes")

    def test_images_must_stay_inside_the_manifest_directory(self) -> None:
        self.assert_error(payload(option(image="/etc/passwd"), option("b", "b.png")), "relative")
        self.assert_error(payload(option(image="..\\a.png"), option("b", "b.png")), "relative")
        self.assert_error(payload(option(image="../a.png"), option("b", "b.png")), "inside")

    def test_images_need_a_supported_suffix_and_a_file(self) -> None:
        (self.root / "notes.txt").write_text("x", encoding="utf-8")
        self.assert_error(payload(option(image="notes.txt"), option("b", "b.png")), "must end in")
        self.assert_error(payload(option(image="gone.png"), option("b", "b.png")), "does not exist")

    def test_a_symlink_escape_is_refused(self) -> None:
        outside = Path(self.tmp.name).parent / f"{Path(self.tmp.name).name}-outside.png"
        outside.write_bytes(PNG)
        self.addCleanup(outside.unlink)
        try:
            (self.root / "link.png").symlink_to(outside)
        except (OSError, NotImplementedError):  # Windows without the symlink privilege
            self.skipTest("symlinks are unavailable")

        self.assert_error(payload(option(image="link.png"), option("b", "b.png")), "inside")

    def test_an_oversized_image_is_refused(self) -> None:
        with mock.patch.object(choices, "MAX_IMAGE_BYTES", 2):
            self.assert_error(payload(option(), option("b", "b.png")), "larger than")

    def test_unknown_options_fail_to_select(self) -> None:
        manifest = self.load(payload())

        with self.assertRaises(choices.ChoiceError) as raised:
            choices.select(manifest, "zzz")
        self.assertIn("unknown option", str(raised.exception))
        with self.assertRaises(choices.ChoiceError):
            choices.select(manifest, 3)  # type: ignore[arg-type]


class SelectionTest(ManifestCase):
    def setUp(self) -> None:
        super().setUp()
        self.manifest = self.load(payload())

    def test_select_records_the_option_label_and_time(self) -> None:
        selection = choices.select(self.manifest, "a", notes="  the compact one  ")

        self.assertEqual(selection.option, "a")
        self.assertEqual(selection.label, "Option a")
        self.assertEqual(selection.notes, "the compact one")
        self.assertRegex(selection.at, r"^\d{4}-\d{2}-\d{2}T")

    def test_notes_are_bounded(self) -> None:
        with self.assertRaises(choices.ChoiceError):
            choices.select(self.manifest, "a", notes="x" * 2001)

    def test_write_is_atomic_and_refuses_to_replace(self) -> None:
        target = self.root / "out" / "selection.json"
        selection = choices.select(self.manifest, "a")

        written = choices.write_selection(target, selection)

        self.assertEqual(written, target)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), selection.as_dict())
        self.assertEqual(
            [path.name for path in target.parent.iterdir()],
            ["selection.json"],
        )
        with self.assertRaises(choices.ChoiceError) as raised:
            choices.write_selection(target, choices.select(self.manifest, "b"))
        self.assertIn("already exists", str(raised.exception))

    def test_force_replaces_the_selection(self) -> None:
        target = self.root / "selection.json"
        choices.write_selection(target, choices.select(self.manifest, "a"))

        choices.write_selection(target, choices.select(self.manifest, "b"), force=True)

        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["option"], "b")

    def test_image_bytes_reads_a_known_image(self) -> None:
        self.assertEqual(
            choices.image_bytes(self.manifest, self.manifest.options[0].relative),
            PNG,
        )
        with self.assertRaises(choices.ChoiceError):
            choices.image_bytes(self.manifest, "../a.png")


if __name__ == "__main__":
    unittest.main()
