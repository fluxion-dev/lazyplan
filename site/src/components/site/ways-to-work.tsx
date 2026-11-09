import { Bot, UserRound } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import { Section, SectionHeading } from "./section"

export function WaysToWork() {
  return (
    <Section id="ways-to-work">
      <SectionHeading
        eyebrow="Ways to work"
        title="One agent plans. Another builds. You stay in control."
        intro="Every plan row lives in lazyplan. Edit any row yourself; your agents see every change."
        className="max-w-3xl"
      />
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <Card className="border-border bg-card/70 shadow-lg shadow-black/30 md:p-2">
          <CardHeader className="px-4 pt-4 md:px-6 md:pt-6">
            <Badge variant="secondary" className="mb-2 w-fit gap-1.5">
              <UserRound aria-hidden="true" />
              Planning
            </Badge>
            <CardTitle className="text-lg">Ask for a plan.</CardTitle>
          </CardHeader>
          <div className="flex flex-col gap-4 px-4 pb-4 md:px-6 md:pb-6">
            <blockquote className="m-0 rounded-lg border-l-2 border-brand-gold/70 bg-secondary/50 px-4 py-3 text-[0.95rem] text-muted-foreground">
              <span className="font-semibold text-foreground">You:</span> Add a
              plan for passwordless sign-in. Cover magic links, passkeys, and the
              migration. Break it into reviewable tasks.
            </blockquote>
            <pre className="m-0 overflow-x-auto rounded-lg border border-border bg-background p-4 font-mono text-[0.82rem] leading-relaxed text-foreground">
              {`Plan · Passwordless sign-in
  Milestone · Magic links
    Task · Add the token model
    Task · Wire the callback
  Milestone · Passkeys
    Task · Enroll a passkey
  Milestone · Migration
    Task · Keep passwords as a fallback`}
            </pre>
            <CardDescription className="text-[0.95rem]">
              Your planner agent writes the rows. Edit what does not fit.
            </CardDescription>
          </div>
        </Card>

        <Card className="border-border bg-card/70 shadow-lg shadow-black/30 md:p-2">
          <CardHeader className="px-4 pt-4 md:px-6 md:pt-6">
            <Badge variant="secondary" className="mb-2 w-fit gap-1.5">
              <Bot aria-hidden="true" />
              Execution
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
            <pre className="m-0 overflow-x-auto rounded-lg border border-border bg-background p-4 font-mono text-[0.82rem] leading-relaxed text-foreground">
              {`Task · Add the token model        doing
  Claimed by executor · expires in 30m
  Commit · a1b2c3d · tests passing
Task · Add the token model        done`}
            </pre>
            <CardDescription className="text-[0.95rem]">
              The executor works one task at a time. Take over or do it
              yourself.
            </CardDescription>
          </div>
        </Card>
      </div>
      <p className="mx-auto mt-8 max-w-2xl text-center text-[0.95rem] text-muted-foreground">
        Swap roles or do the work yourself.
      </p>
    </Section>
  )
}
