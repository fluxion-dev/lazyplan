"""The generated OpenCode plugin loads under both OpenCode plugin APIs."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from lazyplan.infrastructure import hook_install

NODE = shutil.which("node")

PROBE = """
import { pathToFileURL } from "node:url"
const plugin = (await import(pathToFileURL(process.argv[2]).href)).default
const registered = []
const domain = (name) => ({ hook: async (hook) => registered.push(`${name}.${hook}`) })
await plugin.setup({
  location: { directory: process.cwd() },
  permission: domain("permission"),
  tool: domain("tool"),
  session: domain("session"),
})
const hooks = await plugin.server({ directory: process.cwd() })
console.log(JSON.stringify({
  id: plugin.id,
  setup: typeof plugin.setup,
  server: typeof plugin.server,
  tui: typeof plugin.tui,
  v2: registered.sort(),
  v1: Object.keys(hooks).sort(),
}))
"""


@unittest.skipIf(NODE is None, "node is not installed")
class OpenCodePluginCase(unittest.TestCase):
    def _load(self) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = Path(tmp) / "lazyplan.mjs"
            plugin.write_text(hook_install.plugin_text(), encoding="utf-8")
            probe = Path(tmp) / "probe.mjs"
            probe.write_text(PROBE, encoding="utf-8")
            out = subprocess.run(
                [str(NODE), str(probe), str(plugin)],
                cwd=tmp,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
            )
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_the_default_export_satisfies_both_loaders(self):
        shape = self._load()
        self.assertEqual(shape["id"], "lazyplan")
        self.assertEqual(shape["setup"], "function")
        self.assertEqual(shape["server"], "function")
        self.assertEqual(shape["tui"], "undefined")

    def test_both_apis_register_every_lifecycle_hook(self):
        shape = self._load()
        self.assertEqual(
            shape["v2"],
            ["permission.evaluate", "session.compaction", "session.context", "tool.execute.after"],
        )
        self.assertEqual(
            shape["v1"],
            [
                "chat.message",
                "event",
                "experimental.chat.system.transform",
                "experimental.session.compacting",
                "tool.execute.after",
                "tool.execute.before",
            ],
        )


if __name__ == "__main__":
    unittest.main()
