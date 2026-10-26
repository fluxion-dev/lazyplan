"""Text file I/O: encodings, BOMs, and line endings behave the same on every OS."""

import ast
import codecs
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import textfile  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCANNED = (ROOT / "src" / "lazyplan", ROOT / "tests", ROOT / "tools")


class TextFileCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "f.md"

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_file_is_utf8_with_lf(self):
        textfile.write(self.path, "café ✓\nnext\n")
        self.assertEqual(self.path.read_bytes(), "café ✓\nnext\n".encode())

    def test_existing_crlf_file_keeps_crlf(self):
        self.path.write_bytes(b"one\r\ntwo\r\n")
        textfile.write(self.path, "one\ntwo\nthree\n")
        self.assertEqual(self.path.read_bytes(), b"one\r\ntwo\r\nthree\r\n")

    def test_existing_lf_file_keeps_lf(self):
        self.path.write_bytes(b"one\n")
        textfile.write(self.path, "one\ntwo\n")
        self.assertEqual(self.path.read_bytes(), b"one\ntwo\n")

    def test_read_strips_utf8_bom_and_crlf(self):
        self.path.write_bytes(codecs.BOM_UTF8 + '{\r\n  "a": "é"\r\n}\r\n'.encode())
        self.assertEqual(textfile.read(self.path), '{\n  "a": "é"\n}\n')

    def test_read_decodes_utf16_with_bom(self):
        for bom, codec in ((codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be")):
            with self.subTest(codec=codec):
                self.path.write_bytes(bom + '[1, "✓"]\r\n'.encode(codec))
                self.assertEqual(textfile.read(self.path), '[1, "✓"]\n')

    def test_read_rejects_invalid_utf8(self):
        self.path.write_bytes(b"ok \x81")
        with self.assertRaises(UnicodeDecodeError):
            textfile.read(self.path)

    def test_append_matches_existing_crlf(self):
        self.path.write_bytes(b"a\r\n")
        textfile.append(self.path, "b\n")
        self.assertEqual(self.path.read_bytes(), b"a\r\nb\r\n")

    def test_append_creates_lf_file(self):
        textfile.append(self.path, "a\n")
        self.assertEqual(self.path.read_bytes(), b"a\n")


def _open_mode(node: ast.Call) -> str:
    args = [*node.args[1:2], *(kw.value for kw in node.keywords if kw.arg == "mode")]
    return next((arg.value for arg in args if isinstance(arg, ast.Constant)), "r")


def _platform_text_calls(tree: ast.AST) -> list[int]:
    """Lines that read or write text with the platform's default encoding."""
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        keywords = {kw.arg for kw in node.keywords}
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in ("read_text", "write_text") and "encoding" not in keywords:
            if not (isinstance(func, ast.Attribute) and getattr(func.value, "id", "") == "dist"):
                found.append(node.lineno)
        if name == "open" and isinstance(func, ast.Name) and "encoding" not in keywords:
            if "b" not in _open_mode(node):
                found.append(node.lineno)
        is_subprocess = isinstance(func, ast.Attribute) and getattr(func.value, "id", "") == (
            "subprocess"
        )
        if is_subprocess and {"text", "universal_newlines"} & keywords:
            if "encoding" not in keywords:
                found.append(node.lineno)
    return found


class PlatformEncodingGuard(unittest.TestCase):
    def test_code_never_relies_on_the_platform_encoding(self):
        offenders = []
        for folder in SCANNED:
            for path in sorted(folder.glob("*.py")):
                if path.name == "textfile.py":
                    continue
                tree = ast.parse(path.read_text(encoding="utf-8"))
                offenders += [f"{path.name}:{line}" for line in _platform_text_calls(tree)]
        self.assertEqual(offenders, [], "use lazyplan.textfile or an explicit encoding")


if __name__ == "__main__":
    unittest.main()
