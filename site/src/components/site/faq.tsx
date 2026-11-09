import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { FAQ } from "@/data/site"

import { Section, SectionHeading } from "./section"

export function Faq() {
  return (
    <Section id="faq" className="max-w-3xl">
      <SectionHeading eyebrow="FAQ" title="Questions, answered." />
      <Accordion
        type="single"
        collapsible
        className="w-full rounded-xl border border-border bg-card/70 px-6"
      >
        {FAQ.map((item) => (
          <AccordionItem key={item.question} value={item.question}>
            <AccordionTrigger className="text-left font-semibold text-foreground">
              {item.question}
            </AccordionTrigger>
            <AccordionContent forceMount className="text-muted-foreground">
              {item.answer}
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </Section>
  )
}
