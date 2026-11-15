import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { COPY, SCREENS } from "@/data/site"

import { Reveal } from "./reveal"
import { Section, SectionHeading } from "./section"

const SETUP_STEPS = [
  "Welcome",
  "Where plans live",
  "Your agents",
  "Hooks and the pointer",
  "Model targets",
  "Role tiers and effort",
  "New integrations",
  "Appearance and checks",
  "Review and apply",
] as const

const SETUP = SCREENS.setup

export function FirstRun() {
  return (
    <Section id="first-run" className="max-w-7xl">
      <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
        <Reveal>
          <figure className="relative m-0">
            <div
              aria-hidden="true"
              className="absolute -inset-6 rounded-[2rem] bg-brand-gold/10 blur-3xl"
            />
            <div className="relative overflow-hidden rounded-2xl border border-border bg-card/70 p-1.5 shadow-cinema">
              <picture>
                <source
                  srcSet={`./screens/${SETUP.file}.webp`}
                  type="image/webp"
                />
                <img
                  src={`./screens/${SETUP.file}.png`}
                  width={SETUP.width}
                  height={SETUP.height}
                  loading="lazy"
                  decoding="async"
                  alt={SETUP.alt}
                  className="block h-auto w-full rounded-xl"
                />
              </picture>
            </div>
            <figcaption className="mt-3 text-sm text-muted-foreground">
              {SETUP.caption}
            </figcaption>
          </figure>
        </Reveal>

        <Reveal delay={100}>
          <SectionHeading
            eyebrow={COPY.firstRun.eyebrow}
            title={COPY.firstRun.title}
            intro={COPY.firstRun.intro}
            className="mb-8"
          />
          <Card className="border-border bg-card/60">
            <CardContent className="grid gap-5 p-5 sm:grid-cols-2">
              {COPY.firstRun.points.map((point) => (
                <div key={point.title}>
                  <p className="mb-1 font-semibold text-foreground">
                    {point.title}
                  </p>
                  <p className="m-0 text-[0.9rem] text-muted-foreground">
                    {point.description}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
          <div className="mt-5 flex flex-wrap gap-1.5">
            {SETUP_STEPS.map((step) => (
              <Badge
                key={step}
                variant="outline"
                className="border-border/80 bg-secondary/40 text-[0.7rem] font-medium text-muted-foreground"
              >
                {step}
              </Badge>
            ))}
          </div>
          <p className="mt-4 text-sm text-muted-foreground">
            Reopen it with <code className="font-mono text-foreground">lpui setup</code>{" "}
            or press <code className="font-mono text-foreground">S</code> in the
            screen.
          </p>
        </Reveal>
      </div>
    </Section>
  )
}
