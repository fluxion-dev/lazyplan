import type { ReactNode } from "react"
import { Activity, Layers, ShieldCheck, Users } from "lucide-react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Kbd } from "@/components/ui/kbd"

import { Section, SectionHeading } from "./section"

const ITEMS = [
  {
    icon: Activity,
    title: "Health and needs",
    description: "Drift, questions, claims, overlaps.",
  },
  {
    icon: ShieldCheck,
    title: "Manual override",
    description: "Read-only until armed; writes audited.",
  },
  {
    icon: Layers,
    title: "Trust hubs",
    description: "Criteria, evidence, questions, and references are selectable.",
  },
  {
    icon: Users,
    title: "Agents pane",
    description: "Who is working; click for sessions, handoffs, and comments.",
  },
] as const

export function WhatsNew() {
  return (
    <Section id="new">
      <div className="overflow-hidden rounded-2xl border border-border bg-card/70 shadow-xl shadow-black/30">
        <div className="grid gap-6 p-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1.7fr)] md:p-8">
          <div>
            <p className="mb-3 text-sm font-semibold tracking-[0.18em] text-brand-cyan uppercase">
              What&apos;s new
            </p>
            <h2 className="mb-3 text-2xl font-bold tracking-tight text-balance text-foreground md:text-3xl">
              One control room for the loop.
            </h2>
            <p className="m-0 text-[0.95rem] text-pretty text-muted-foreground">
              See what needs you, correct it, and ship with proof.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {ITEMS.map((item) => (
              <Card
                key={item.title}
                size="sm"
                className="border-border bg-background/60"
              >
                <CardHeader>
                  <div className="mb-1 flex size-8 items-center justify-center rounded-lg bg-secondary text-brand-cyan">
                    <item.icon className="size-4" aria-hidden="true" />
                  </div>
                  <CardTitle>{item.title}</CardTitle>
                  <CardDescription>{item.description}</CardDescription>
                </CardHeader>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </Section>
  )
}

export function Features() {
  return (
    <Section id="features" className="max-w-7xl">
      <SectionHeading
        eyebrow="Why lazyplan"
        title="Less chat. More done."
        intro="The plan you and your agent both see."
      />
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <FeatureCard
          icon={Layers}
          title="One source of truth"
          description="Plans, milestones, and tasks live in one place. You and your agent read the same plan."
        />
        <FeatureCard
          icon={Activity}
          title="Built for focus"
          description="A fast keyboard screen keeps plans short until you open them."
          hint={
            <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="inline-flex items-center gap-1">
                <Kbd>c</Kbd> palette
              </span>
              <span className="inline-flex items-center gap-1">
                <Kbd>?</Kbd> help
              </span>
              <span className="inline-flex items-center gap-1">
                <Kbd>[</Kbd>
                <Kbd>]</Kbd> history
              </span>
              <span className="inline-flex items-center gap-1">
                <Kbd>q</Kbd> quit anywhere
              </span>
            </span>
          }
        />
        <FeatureCard
          icon={ShieldCheck}
          title="Proof you can see"
          description="Follow plan, commit, PR, and activity."
        />
        <FeatureCard
          icon={Users}
          title="Yours to keep"
          description="Local-first and private. Export any time. No cloud, no lock-in."
        />
      </div>
    </Section>
  )
}

type FeatureCardProps = Readonly<{
  icon: typeof Layers
  title: string
  description: string
  hint?: ReactNode
}>

function FeatureCard({
  icon: Icon,
  title,
  description,
  hint,
}: FeatureCardProps) {
  return (
    <Card className="border-border bg-card/70 shadow-lg shadow-black/30">
      <CardHeader>
        <div className="mb-2 flex size-9 items-center justify-center rounded-lg bg-secondary text-brand-cyan">
          <Icon className="size-4" aria-hidden="true" />
        </div>
        <CardTitle className="text-lg">{title}</CardTitle>
        <CardDescription className="text-[0.95rem]">
          {description}
        </CardDescription>
      </CardHeader>
      {hint ? (
        <CardContent className="pt-0 font-mono text-[0.85rem] text-muted-foreground">
          {hint}
        </CardContent>
      ) : null}
    </Card>
  )
}
