import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { COPY, DOCS_URL, FAQ, REPO_URL } from "@/data/site"

import { Section, SectionHeading } from "./section"

export function Faq() {
  return (
    <Section id="faq" className="max-w-6xl">
      <div className="grid gap-10 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <div>
          <SectionHeading
            eyebrow={COPY.faq.eyebrow}
            title={COPY.faq.title}
            intro={COPY.faq.intro}
            className="mb-6"
          />
          <div className="flex flex-col gap-3 text-sm">
            <a
              href={DOCS_URL}
              className="text-brand-cyan underline-offset-4 hover:text-foreground hover:underline"
            >
              Read the usage guide
            </a>
            <a
              href={`${REPO_URL}/issues`}
              className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
            >
              Open an issue
            </a>
          </div>
        </div>
        <Accordion
          type="single"
          collapsible
          className="w-full rounded-2xl border border-border bg-card/60 px-6"
        >
          {FAQ.map((item) => (
            <AccordionItem key={item.question} value={item.question}>
              <AccordionTrigger className="text-left font-semibold text-foreground">
                {item.question}
              </AccordionTrigger>
              <AccordionContent
                forceMount
                className="text-muted-foreground"
              >
                {item.answer}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </Section>
  )
}
