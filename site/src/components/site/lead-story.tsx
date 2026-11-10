import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { COPY, LEAD_FEATURES } from "@/data/site"

import { FeatureIcon } from "./feature-icon"
import { Reveal } from "./reveal"
import { Section, SectionHeading } from "./section"

const GROUP_LABEL = {
  plan: "Plan",
  agents: "Agents",
  proof: "Proof",
  product: "Product",
} as const

export function LeadStory() {
  return (
    <Section id="story">
      <SectionHeading
        eyebrow={COPY.story.eyebrow}
        title={COPY.story.title}
        intro={COPY.story.intro}
        className="max-w-3xl"
      />
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        {LEAD_FEATURES.map((feature, index) => (
          <Reveal
            key={feature.id}
            delay={index * 80}
            className="h-full"
          >
            <Card className="relative h-full overflow-hidden border-border bg-card/70 shadow-cinema">
              <div
                aria-hidden="true"
                className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand-gold/60 to-transparent"
              />
              <span
                aria-hidden="true"
                className="absolute top-2 right-4 font-mono text-6xl font-black text-foreground/5"
              >
                {String(index + 1).padStart(2, "0")}
              </span>
              <CardHeader>
                <Badge
                  variant="outline"
                  className="mb-3 w-fit gap-1.5 border-border text-[0.68rem] font-semibold tracking-[0.14em] text-brand-cyan uppercase"
                >
                  <span
                    aria-hidden="true"
                    className="size-1.5 rounded-full bg-brand-gold"
                  />
                  {GROUP_LABEL[feature.group]}
                </Badge>
                <div className="mb-3 flex size-11 items-center justify-center rounded-xl bg-secondary text-brand-cyan">
                  <FeatureIcon name={feature.icon} className="size-5" />
                </div>
                <CardTitle className="text-xl md:text-2xl">
                  {feature.title}
                </CardTitle>
                <CardDescription className="text-[0.95rem] leading-relaxed">
                  {feature.description}
                </CardDescription>
              </CardHeader>
            </Card>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}
