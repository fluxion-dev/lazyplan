"use client"

import { useState } from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { COPY, STORY_SCREENS } from "@/data/site"

import { Reveal } from "./reveal"
import { ScreenshotFrame } from "./screenshot-frame"
import { Section, SectionHeading } from "./section"

export function Screenshots() {
  const [activeIndex, setActiveIndex] = useState<number | null>(null)
  const active = activeIndex === null ? null : STORY_SCREENS[activeIndex]
  const position = activeIndex === null ? 0 : activeIndex + 1

  function step(delta: number) {
    setActiveIndex((current) => {
      if (current === null) {
        return null
      }
      return (current + delta + STORY_SCREENS.length) % STORY_SCREENS.length
    })
  }

  return (
    <Section id="screens">
      <SectionHeading
        eyebrow={COPY.gallery.eyebrow}
        title={COPY.gallery.title}
        intro={COPY.gallery.intro}
      />

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:gap-8">
        {STORY_SCREENS.map((screen, index) => (
          <Reveal key={screen.name} delay={(index % 2) * 70}>
            <ScreenshotFrame
              screen={screen}
              onOpen={() => setActiveIndex(index)}
            />
          </Reveal>
        ))}
      </div>

      <Dialog
        open={active !== null}
        onOpenChange={(open) => {
          if (!open) {
            setActiveIndex(null)
          }
        }}
      >
        <DialogContent
          className="max-h-[92vh] max-w-[min(96vw,1100px)] overflow-auto p-3 sm:max-w-[min(96vw,1100px)]"
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") {
              event.preventDefault()
              step(-1)
            } else if (event.key === "ArrowRight") {
              event.preventDefault()
              step(1)
            }
          }}
        >
          <DialogHeader>
            <DialogTitle className="sr-only">
              {active?.caption ?? "Screenshot preview"}
            </DialogTitle>
            <DialogDescription className="sr-only">
              Full-size screenshot preview. Use the arrow keys to move through
              the gallery.
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
              <div className="flex flex-col items-center gap-3 sm:flex-row sm:justify-between">
                <Button
                  type="button"
                  variant="outline"
                  size="default"
                  onClick={() => step(-1)}
                  aria-label="Previous screenshot"
                  className="order-2 min-h-10 sm:order-none"
                >
                  <ChevronLeft />
                  Previous
                </Button>
                <p className="order-1 m-0 text-center text-sm text-muted-foreground sm:order-none">
                  <span className="font-mono text-xs text-muted-foreground">
                    {position} / {STORY_SCREENS.length}
                  </span>
                  <span className="mx-2 text-border">·</span>
                  {active.caption}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="default"
                  onClick={() => step(1)}
                  aria-label="Next screenshot"
                  className="order-2 min-h-10 sm:order-none"
                >
                  Next
                  <ChevronRight />
                </Button>
              </div>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </Section>
  )
}
