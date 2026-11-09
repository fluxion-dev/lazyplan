import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

import { Section, SectionHeading } from "./section"

const STEPS = [
  {
    number: "01",
    title: "Create a plan",
    description: "Give it a title, a reason, and a scope.",
  },
  {
    number: "02",
    title: "Bring in your agent",
    description: "Your agent reads and updates the same plan.",
  },
  {
    number: "03",
    title: "Keep work moving",
    description: "Review progress, clear blockers, and finish.",
  },
] as const

export function HowItWorks() {
  return (
    <Section id="how" className="max-w-5xl">
      <SectionHeading
        eyebrow="How it works"
        title="Start in three steps."
      />
      <ol className="grid list-none grid-cols-1 gap-6 p-0 md:grid-cols-3">
        {STEPS.map((step) => (
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
