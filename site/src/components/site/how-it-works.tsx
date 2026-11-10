import { COPY } from "@/data/site"

import { Reveal } from "./reveal"
import { Section, SectionHeading } from "./section"

export function HowItWorks() {
  return (
    <Section id="how" className="max-w-6xl">
      <SectionHeading
        eyebrow={COPY.workflow.eyebrow}
        title={COPY.workflow.title}
      />
      <div className="relative">
        <div
          aria-hidden="true"
          className="absolute top-6 right-0 left-0 hidden h-px bg-gradient-to-r from-transparent via-brand-gold/40 to-transparent md:block"
        />
        <ol className="relative grid list-none grid-cols-1 gap-8 p-0 md:grid-cols-3">
          {COPY.workflow.steps.map((step, index) => (
            <li key={step.number}>
              <Reveal delay={index * 80}>
                <div className="flex flex-col items-start gap-3">
                  <span className="relative flex size-12 items-center justify-center rounded-full border border-border bg-background font-mono text-sm font-bold text-brand-gold shadow-glow">
                    {step.number}
                  </span>
                  <h3 className="m-0 text-xl font-semibold tracking-headline text-foreground">
                    {step.title}
                  </h3>
                  <p className="m-0 text-[0.95rem] text-muted-foreground">
                    {step.description}
                  </p>
                </div>
              </Reveal>
            </li>
          ))}
        </ol>
      </div>
    </Section>
  )
}
