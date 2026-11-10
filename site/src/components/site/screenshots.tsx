"use client"

import { useState } from "react"

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { COPY, SCREENS, type Screen } from "@/data/site"

import { ScreenshotFrame } from "./screenshot-frame"
import { Section, SectionHeading } from "./section"

export function Screenshots() {
  const [active, setActive] = useState<Screen | null>(null)

  return (
    <Section id="screens">
      <SectionHeading
        eyebrow={COPY.gallery.eyebrow}
        title={COPY.gallery.title}
        intro={COPY.gallery.intro}
      />

      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        {SCREENS.map((screen) => (
          <ScreenshotFrame
            key={screen.name}
            screen={screen}
            onOpen={setActive}
          />
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
