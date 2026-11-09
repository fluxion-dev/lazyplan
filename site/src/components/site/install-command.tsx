"use client"

import { useState } from "react"
import { Check, Copy, Terminal } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { INSTALL_COMMAND } from "@/data/site"

import { Section } from "./section"

function legacyCopy(text: string): boolean {
  const area = document.createElement("textarea")
  area.value = text
  area.setAttribute("readonly", "")
  area.style.position = "absolute"
  area.style.left = "-9999px"
  document.body.appendChild(area)
  area.select()
  try {
    return document.execCommand("copy")
  } catch {
    return false
  } finally {
    document.body.removeChild(area)
  }
}

export function InstallCommand() {
  const [copied, setCopied] = useState(false)
  const [status, setStatus] = useState("")

  async function copyCommand() {
    let ok = false
    if (window.isSecureContext && navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(INSTALL_COMMAND)
        ok = true
      } catch {
        ok = legacyCopy(INSTALL_COMMAND)
      }
    } else {
      ok = legacyCopy(INSTALL_COMMAND)
    }

    setCopied(ok)
    setStatus(
      ok
        ? "Copied to clipboard."
        : "Copy failed — select the command and copy it manually."
    )
    window.setTimeout(() => {
      setCopied(false)
      setStatus("")
    }, 2000)
  }

  return (
    <Section
      id="install"
      padded={false}
      className="max-w-4xl pb-20 text-center md:pb-28"
    >
      <p className="mb-3 text-sm font-semibold tracking-[0.18em] text-brand-cyan uppercase">
        Install
      </p>
      <h2 className="mb-4 text-2xl font-bold tracking-tight text-foreground md:text-3xl">
        Get lazyplan in one command.
      </h2>
      <p className="mb-8 text-lg text-muted-foreground">
        Python 3.11+. Linux, macOS, Windows.
      </p>

      <Card className="mx-auto max-w-md text-left shadow-lg shadow-brand-blue/25">
        <CardContent className="flex items-center gap-2">
          <Terminal className="size-5 shrink-0 text-brand-cyan" aria-hidden="true" />
          <code
            id="install-cmd"
            className="min-w-0 flex-1 truncate font-mono text-sm text-foreground"
          >
            {INSTALL_COMMAND}
          </code>
          <Button
            id="install-copy"
            type="button"
            size="sm"
            onClick={copyCommand}
          >
            {copied ? <Check /> : <Copy />}
            {copied ? "Copied" : "Copy"}
          </Button>
        </CardContent>
      </Card>
      <span
        id="install-copy-status"
        role="status"
        aria-live="polite"
        className="mt-2 block min-h-5 text-sm text-brand-cyan"
      >
        {status}
      </span>
    </Section>
  )
}
