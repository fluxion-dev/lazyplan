import { cn } from "cn"

import type { Screen } from "@/data/site"

type ScreenshotFigureProps = Readonly<{
  screen: Screen
  glow?: "gold" | "cyan"
  captionAlign?: "start" | "center"
  eager?: boolean
  marker?: "hero" | "proof"
  className?: string
}>

const GLOW = {
  gold: "bg-brand-gold/10",
  cyan: "bg-brand-cyan/10",
} as const

const MARKER = {
  hero: { "data-hero": true },
  proof: { "data-proof": true },
} as const

export function ScreenshotFigure({
  screen,
  glow,
  captionAlign = "start",
  eager = false,
  marker,
  className,
}: ScreenshotFigureProps) {
  return (
    <figure className={cn("relative m-0", className)}>
      {glow ? (
        <div
          aria-hidden="true"
          className={cn(
            "absolute -inset-6 rounded-[2rem] blur-3xl",
            GLOW[glow]
          )}
        />
      ) : null}
      <div className="relative overflow-hidden rounded-2xl border border-border bg-card/70 p-1.5 shadow-cinema">
        <picture>
          <source srcSet={`./screens/${screen.file}.webp`} type="image/webp" />
          <img
            {...(marker ? MARKER[marker] : {})}
            src={`./screens/${screen.file}.png`}
            width={screen.width}
            height={screen.height}
            loading={eager ? "eager" : "lazy"}
            decoding="async"
            alt={screen.alt}
            className="block h-auto w-full rounded-xl"
          />
        </picture>
      </div>
      <figcaption
        className={cn(
          "mt-3 text-sm text-muted-foreground",
          captionAlign === "center" && "text-center"
        )}
      >
        {screen.caption}
      </figcaption>
    </figure>
  )
}
