"use client"

import { useState } from "react"
import { Check, Copy, Terminal } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { COPY, INSTALL_COMMAND } from "@/data/site"

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
        {COPY.install.eyebrow}
      </p>
      <h2 className="mb-4 text-3xl leading-headline font-bold tracking-headline text-foreground md:text-4xl">
        {COPY.install.title}
      </h2>
      <p className="mb-8 text-lg text-muted-foreground">
        {COPY.install.intro}
      </p>

      <Card className="relative mx-auto max-w-md overflow-hidden border-border bg-card/70 text-left shadow-cinema">
        <div
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand-gold/60 to-transparent"
        />
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
            size="default"
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
