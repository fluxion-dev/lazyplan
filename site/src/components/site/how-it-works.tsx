import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { COPY } from "@/data/site"

import { Section, SectionHeading } from "./section"

export function HowItWorks() {
  return (
    <Section id="how" className="max-w-5xl">
      <SectionHeading
        eyebrow={COPY.workflow.eyebrow}
        title={COPY.workflow.title}
      />
      <ol className="grid list-none grid-cols-1 gap-6 p-0 md:grid-cols-3">
        {COPY.workflow.steps.map((step) => (
          <li key={step.number}>
            <Card className="h-full border-border bg-card/70">
              <CardHeader>
                <span className="text-sm font-bold text-brand-gold">
                  {step.number}
                </span>
                <CardTitle className="mt-2 text-lg">{step.title}</CardTitle>
                <CardDescription className="text-[0.95rem]">
                  {step.description}
                </CardDescription>
              </CardHeader>
            </Card>
          </li>
        ))}
      </ol>
    </Section>
  )
}
