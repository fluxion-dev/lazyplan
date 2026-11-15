import { Card, CardContent } from "@/components/ui/card"
import { COPY, SCREENS } from "@/data/site"

import { Reveal } from "./reveal"
import { Section, SectionHeading } from "./section"

const DISPATCH = SCREENS.dispatch

export function Dispatch() {
  return (
    <Section id="dispatch" className="max-w-7xl">
      <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Reveal>
          <SectionHeading
            eyebrow={COPY.dispatch.eyebrow}
            title={COPY.dispatch.title}
            intro={COPY.dispatch.intro}
            className="mb-6"
          />
          <p className="mb-6 w-fit rounded-lg border border-border bg-card/70 px-3 py-2 font-mono text-sm text-foreground shadow-glow">
            <span className="text-brand-cyan">$</span> lpui dispatch --plan 23
          </p>
          <Card className="border-border bg-card/60">
            <CardContent className="grid gap-5 p-5 sm:grid-cols-2">
              {COPY.dispatch.beats.map((beat) => (
                <div key={beat.title}>
                  <p className="mb-1 font-semibold text-foreground">
                    {beat.title}
                  </p>
                  <p className="m-0 text-[0.9rem] text-muted-foreground">
                    {beat.description}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        </Reveal>

        <Reveal delay={100}>
          <figure className="relative m-0">
            <div
              aria-hidden="true"
              className="absolute -inset-6 rounded-[2rem] bg-brand-cyan/10 blur-3xl"
            />
            <div className="relative overflow-hidden rounded-2xl border border-border bg-card/70 p-1.5 shadow-cinema">
              <picture>
                <source
                  srcSet={`./screens/${DISPATCH.file}.webp`}
                  type="image/webp"
                />
                <img
                  src={`./screens/${DISPATCH.file}.png`}
                  width={DISPATCH.width}
                  height={DISPATCH.height}
                  loading="lazy"
                  decoding="async"
                  alt={DISPATCH.alt}
                  className="block h-auto w-full rounded-xl"
                />
              </picture>
            </div>
            <figcaption className="mt-3 text-sm text-muted-foreground">
              {DISPATCH.caption}
            </figcaption>
          </figure>
        </Reveal>
      </div>
    </Section>
  )
}
