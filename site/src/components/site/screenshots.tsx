"use client"

import { useState } from "react"

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { SCREENS, type Screen } from "@/data/site"

import { Section, SectionHeading } from "./section"

export function Screenshots() {
  const [active, setActive] = useState<Screen | null>(null)

  return (
    <Section id="screens">
      <SectionHeading
        eyebrow="Screenshots"
        title="See it in action."
        intro="Three themes, git context, one plan."
      />

      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        {SCREENS.map((screen) => (
          <figure key={screen.name} className="m-0">
            <button
              type="button"
              data-zoom
              aria-haspopup="dialog"
              aria-label={`Open the ${screen.name.replaceAll("-", " ")} screenshot`}
              onClick={() => setActive(screen)}
              className="group block w-full cursor-zoom-in rounded-xl text-left"
            >
              <picture>
                <source
                  srcSet={`./screens/${screen.file}.webp`}
                  type="image/webp"
                />
                <img
                  src={`./screens/${screen.file}.png`}
                  width={screen.width}
                  height={screen.height}
                  loading="lazy"
                  decoding="async"
                  alt={screen.alt}
                  className="block h-auto w-full rounded-xl border border-border transition duration-150 group-hover:brightness-110 group-focus-visible:brightness-110"
                />
              </picture>
            </button>
            <figcaption className="mt-2 text-sm text-muted-foreground">
              {screen.mono ? (
                <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[0.9em] text-foreground">
                  {screen.caption}
                </code>
              ) : (
                screen.caption
              )}
            </figcaption>
          </figure>
        ))}
      </div>

      <Dialog
        open={active !== null}
        onOpenChange={(open) => {
          if (!open) {
            setActive(null)
          }
        }}
      >
        <DialogContent className="max-h-[92vh] max-w-[min(96vw,1100px)] overflow-auto p-3 sm:max-w-[min(96vw,1100px)]">
          <DialogHeader>
            <DialogTitle className="sr-only">
              {active?.caption ?? "Screenshot preview"}
            </DialogTitle>
            <DialogDescription className="sr-only">
              Full-size screenshot preview.
            </DialogDescription>
          </DialogHeader>
          {active ? (
            <>
              <img
                src={`./screens/${active.file}.png`}
                width={active.width}
                height={active.height}
                alt={active.alt}
                className="block h-auto w-full rounded-lg border border-border"
              />
              <p className="m-0 text-center text-sm text-muted-foreground">
                {active.caption}
              </p>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </Section>
  )
}
