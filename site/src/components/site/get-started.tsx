import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { REPO_URL } from "@/data/site"

import { Section } from "./section"

export function GetStarted() {
  return (
    <Section id="get-started" padded={false} className="max-w-5xl pb-20 md:pb-28">
      <Card className="border-border bg-card/70 px-6 py-12 text-center shadow-xl shadow-black/30 md:px-12">
        <CardContent>
          <h2 className="mb-3 text-2xl font-bold tracking-tight text-balance text-foreground md:text-3xl">
            Bring your plan into focus.
          </h2>
          <p className="mx-auto mb-8 max-w-xl text-lg text-pretty text-muted-foreground">
            Give your agent the same plan you see.
          </p>
          <div className="flex flex-col items-center justify-center gap-2.5 sm:flex-row">
            <Button asChild size="lg">
              <a href="#install">Install</a>
            </Button>
            <Button asChild size="lg" variant="outline">
              <a href={REPO_URL}>GitHub</a>
            </Button>
          </div>
        </CardContent>
      </Card>
    </Section>
  )
}
