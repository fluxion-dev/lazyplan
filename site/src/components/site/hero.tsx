import { ArrowRight } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  HERO_COMPOSITE,
  LICENSE_BADGE,
  PYPI_BADGE,
  PYPI_URL,
  RELEASE_BADGE,
  REPO_URL,
  RELEASES_URL,
} from "@/data/site"

import { DownloadStats } from "./download-stats"

export function Hero() {
  return (
    <section
      aria-labelledby="hero-title"
      className="relative overflow-hidden px-6 pt-24 pb-20 text-center md:pt-32 md:pb-24"
    >
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 cinema-grid opacity-70" />
        <div className="absolute inset-0 cinema-vignette" />
        <div className="absolute inset-x-0 bottom-0 h-48 bg-gradient-to-b from-transparent to-background" />
      </div>

      <div className="relative mx-auto max-w-4xl">
        <Badge
          variant="outline"
          className="mb-5 h-auto gap-2 border-border bg-card/60 px-3 py-1 text-[0.7rem] font-semibold tracking-[0.16em] text-brand-cyan uppercase shadow-glow"
        >
          <span
            aria-hidden="true"
            className="size-1.5 rounded-full bg-brand-gold"
          />
          The terminal plan tracker
        </Badge>

        <h1
          id="hero-title"
          className="m-0 text-display leading-display font-extrabold tracking-display text-balance text-foreground"
        >
          Your master plan(s), laid bare.
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lead text-pretty text-muted-foreground">
          Agent compatible long context planning and control
        </p>

        <div className="mt-8 flex flex-col items-center justify-center gap-2.5 sm:flex-row">
          <Button asChild size="lg">
            <a href="#install">Install</a>
          </Button>
          <Button asChild size="lg" variant="outline">
            <a href="#screens">
              See it in action
              <ArrowRight />
            </a>
          </Button>
        </div>

        <div className="mt-8 flex flex-wrap items-center justify-center gap-2">
          <a href={RELEASES_URL} aria-label="Release">
            <img
              src={RELEASE_BADGE}
              alt="Release"
              width={102}
              height={20}
              className="h-5 w-auto"
            />
          </a>
          <a href={PYPI_URL} aria-label="PyPI">
            <img
              src={PYPI_BADGE}
              alt="PyPI"
              width={86}
              height={20}
              className="h-5 w-auto"
            />
          </a>
          <a href={REPO_URL} aria-label="License">
            <img
              src={LICENSE_BADGE}
              alt="License"
              width={78}
              height={20}
              className="h-5 w-auto"
            />
          </a>
        </div>

        <DownloadStats />
      </div>

      <figure className="relative mx-auto mt-14 max-w-5xl">
        <div
          aria-hidden="true"
          className="absolute -inset-6 rounded-[2rem] bg-brand-gold/10 blur-3xl"
        />
        <div className="relative overflow-hidden rounded-2xl border border-border bg-card/70 p-1.5 shadow-cinema">
          <picture>
            <source
              srcSet={`./screens/${HERO_COMPOSITE.file}.webp`}
              type="image/webp"
            />
            <img
              data-hero
              src={`./screens/${HERO_COMPOSITE.file}.png`}
              width={HERO_COMPOSITE.width}
              height={HERO_COMPOSITE.height}
              loading="eager"
              decoding="async"
              alt={HERO_COMPOSITE.alt}
              className="block h-auto w-full rounded-xl"
            />
          </picture>
        </div>
        <figcaption className="mt-3 text-center text-sm text-muted-foreground">
          {HERO_COMPOSITE.caption}
        </figcaption>
      </figure>
    </section>
  )
}
