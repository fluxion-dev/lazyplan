import {
  Activity,
  CircleHelp,
  ListChecks,
  Lock,
  ShieldCheck,
  Terminal as TerminalIcon,
} from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"
import { COPY, STORY_SCREENS } from "@/data/site"

import { Reveal } from "./reveal"
import { Section, SectionHeading } from "./section"

const PROOF_SCREEN =
  STORY_SCREENS.find((screen) => screen.name === "control-room") ?? STORY_SCREENS[0]

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
      "Read-only until you arm override; every write lands in the feed.",
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
          <figure className="relative m-0">
            <div
              aria-hidden="true"
              className="absolute -inset-6 rounded-[2rem] bg-brand-cyan/10 blur-3xl"
            />
            <div className="relative overflow-hidden rounded-2xl border border-border bg-card/70 p-1.5 shadow-cinema">
              <img
                data-proof
                src={`./screens/${PROOF_SCREEN.file}.png`}
                width={PROOF_SCREEN.width}
                height={PROOF_SCREEN.height}
                loading="lazy"
                decoding="async"
                alt={PROOF_SCREEN.alt}
                className="block h-auto w-full rounded-xl"
              />
            </div>
            <figcaption className="mt-3 text-sm text-muted-foreground">
              {PROOF_SCREEN.caption}
            </figcaption>
          </figure>
        </Reveal>
      </div>
    </Section>
  )
}
