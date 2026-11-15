import {
  Activity,
  CircleHelp,
  ListChecks,
  Lock,
  ShieldCheck,
  Terminal as TerminalIcon,
} from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"
import { COPY, screen } from "@/data/site"

import { Reveal } from "./reveal"
import { ScreenshotFigure } from "./screenshot-figure"
import { Section, SectionHeading } from "./section"

const PROOF_SCREEN = screen("control-room")

const TRUST = [
  {
    icon: Activity,
    title: "Needs",
    description:
      "Drift, open questions, claims, and overlaps surface before they block the loop.",
  },
  {
    icon: ShieldCheck,
    title: "Approvals",
    description:
      "Scope changes are deliberate. The diff shows what moved before it lands.",
  },
  {
    icon: ListChecks,
    title: "Criteria",
    description:
      "Acceptance criteria live on the row, with a task that proves each one.",
  },
  {
    icon: TerminalIcon,
    title: "Evidence",
    description: "Record the command, exit code, commit, and proving task.",
  },
  {
    icon: CircleHelp,
    title: "Questions",
    description:
      "Open questions block readiness until someone resolves them.",
  },
  {
    icon: Lock,
    title: "Auditability",
    description:
      "Writes go straight to the plan; every change lands in the feed.",
  },
] as const

export function ProofSection() {
  return (
    <Section id="proof" className="max-w-7xl">
      <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Reveal>
          <SectionHeading
            eyebrow={COPY.proof.eyebrow}
            title={COPY.proof.title}
            intro={COPY.proof.intro}
            className="mb-8"
          />
          <Card className="border-border bg-card/60">
            <CardContent className="grid gap-5 p-5 sm:grid-cols-2">
              {TRUST.map((item) => (
                <div key={item.title} className="flex gap-3">
                  <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-brand-cyan">
                    <item.icon className="size-4" aria-hidden="true" />
                  </div>
                  <div>
                    <p className="mb-1 font-semibold text-foreground">
                      {item.title}
                    </p>
                    <p className="m-0 text-[0.9rem] text-muted-foreground">
                      {item.description}
                    </p>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </Reveal>

        <Reveal delay={100}>
          <ScreenshotFigure screen={PROOF_SCREEN} glow="cyan" marker="proof" />
        </Reveal>
      </div>
    </Section>
  )
}
