import { COPY, SUPPORT_FEATURES } from "@/data/site"

import { FeatureCard } from "./feature-card"
import { Reveal } from "./reveal"
import { Section, SectionHeading } from "./section"

export function FeatureMatrix() {
  return (
    <Section id="features" className="max-w-7xl">
      <SectionHeading
        eyebrow={COPY.features.eyebrow}
        title={COPY.features.title}
        intro={COPY.features.intro}
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {SUPPORT_FEATURES.map((feature, index) => (
          <Reveal
            key={feature.id}
            delay={(index % 3) * 60}
            className="h-full"
          >
            <FeatureCard
              icon={feature.icon}
              title={feature.title}
              description={feature.description}
            />
          </Reveal>
        ))}
      </div>
    </Section>
  )
}
