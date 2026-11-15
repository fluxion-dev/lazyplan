import { Bot, Layers, UserRound } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { COPY } from "@/data/site"

import { Section, SectionHeading } from "./section"
import { Terminal } from "./terminal"

export function WaysToWork() {
  return (
    <Section id="ways-to-work">
      <SectionHeading
        eyebrow={COPY.practice.eyebrow}
        title={COPY.practice.title}
        intro={COPY.practice.intro}
        className="max-w-3xl"
      />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="border-border bg-card/70 shadow-lg shadow-black/30 md:p-2">
          <CardHeader className="px-4 pt-4 md:px-6 md:pt-6">
            <Badge variant="secondary" className="mb-2 w-fit gap-1.5">
              <UserRound aria-hidden="true" />
              Solo
            </Badge>
            <CardTitle className="text-lg">Ask for a plan.</CardTitle>
          </CardHeader>
          <div className="flex flex-col gap-4 px-4 pb-4 md:px-6 md:pb-6">
            <blockquote className="m-0 rounded-lg border-l-2 border-brand-gold/70 bg-secondary/50 px-4 py-3 text-[0.95rem] text-muted-foreground">
              <span className="font-semibold text-foreground">You:</span> Add a
              plan for passwordless sign-in. Cover magic links, passkeys, and the
              migration. Break it into reviewable tasks.
            </blockquote>
            <Terminal title="plan">
              {`$ lpui plan recipe feature > plan.json
$ lpui plan apply --file plan.json
created P1 'Passwordless sign-in':
  3 milestones, 9 tasks, 4 criteria`}
            </Terminal>
            <CardDescription className="text-[0.95rem]">
              Your planner agent writes the rows. Edit what does not fit.
            </CardDescription>
          </div>
        </Card>

        <Card className="border-border bg-card/70 shadow-lg shadow-black/30 md:p-2">
          <CardHeader className="px-4 pt-4 md:px-6 md:pt-6">
            <Badge variant="secondary" className="mb-2 w-fit gap-1.5">
              <Bot aria-hidden="true" />
              Paired
            </Badge>
            <CardTitle className="text-lg">Hand off one task.</CardTitle>
          </CardHeader>
          <div className="flex flex-col gap-4 px-4 pb-4 md:px-6 md:pb-6">
            <blockquote className="m-0 rounded-lg border-l-2 border-brand-green/70 bg-secondary/50 px-4 py-3 text-[0.95rem] text-muted-foreground">
              <span className="font-semibold text-foreground">
                Executor subagent:
              </span>{" "}
              Claiming “Add the token model”. I&apos;ll add the model, migration,
              and tests, and link the commit.
            </blockquote>
            <Terminal title="execution">
              {`$ lpui --actor helper --porcelain next
task  4  doing  Add the token model  milestone:1
$ lpui --actor helper task finish --id 4
linked 1 commit(s) on feat/tokens from a1b2c3d
T4 done`}
            </Terminal>
            <CardDescription className="text-[0.95rem]">
              The executor works one task at a time. Take over or do it
              yourself.
            </CardDescription>
          </div>
        </Card>

        <Card className="border-border bg-card/70 shadow-lg shadow-black/30 md:p-2">
          <CardHeader className="px-4 pt-4 md:px-6 md:pt-6">
            <Badge variant="secondary" className="mb-2 w-fit gap-1.5">
              <Layers aria-hidden="true" />
              Parallel
            </Badge>
            <CardTitle className="text-lg">Run the lanes.</CardTitle>
          </CardHeader>
          <div className="flex flex-col gap-4 px-4 pb-4 md:px-6 md:pb-6">
            <blockquote className="m-0 rounded-lg border-l-2 border-brand-cyan/70 bg-secondary/50 px-4 py-3 text-[0.95rem] text-muted-foreground">
              <span className="font-semibold text-foreground">You:</span> Two
              lanes can run at once. Implement the read path while a docs lane
              writes the guide, then integrate both.
            </blockquote>
            <Terminal title="dispatch">
              {`$ lpui dispatch --plan 7
P7 API v2 · parallel · max 2
now      wave 1 · capacity 0/2 active
lanes:
  M1 Read path [ready] w1 implementer
  M2 Write path [ready] w1 docs
  M3 Integration [waiting] w2 integrator`}
            </Terminal>
            <CardDescription className="text-[0.95rem]">
              Waves run in order; lanes in a wave run side by side up to the
              cap.
            </CardDescription>
          </div>
        </Card>
      </div>
      <p className="mx-auto mt-8 max-w-2xl text-center text-[0.95rem] text-muted-foreground">
        Swap roles, add a lane, or do the work yourself.
      </p>
    </Section>
  )
}
