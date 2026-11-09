import { readFile, writeFile } from "node:fs/promises"

import { render } from "../.ssr/entry-server.js"

const marker = '<div id="root"></div>'
const file = new URL("../dist/index.html", import.meta.url)
const html = await readFile(file, "utf8")

if (!html.includes(marker)) {
  throw new Error("dist/index.html has no empty #root to prerender into")
}

await writeFile(file, html.replace(marker, `<div id="root">${render()}</div>`))
