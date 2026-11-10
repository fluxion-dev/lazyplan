import { Maximize2 } from "lucide-react"
import { cn } from "cn"

import type { Screen } from "@/data/site"

type ScreenshotFrameProps = Readonly<{
  screen: Screen
  onOpen: () => void
  className?: string
}>

export function ScreenshotFrame({
  screen,
  onOpen,
  className,
}: ScreenshotFrameProps) {
  return (
    <figure className={cn("m-0", className)}>
      <button
        type="button"
        data-zoom
        aria-haspopup="dialog"
        aria-label={`Open the ${screen.name.replaceAll("-", " ")} screenshot`}
        onClick={onOpen}
        className="group relative block w-full cursor-zoom-in rounded-xl text-left"
      >
        <picture>
          <source srcSet={`./screens/${screen.file}.webp`} type="image/webp" />
          <img
            src={`./screens/${screen.file}.png`}
            width={screen.width}
            height={screen.height}
            loading="lazy"
            decoding="async"
            alt={screen.alt}
            className="block h-auto w-full rounded-xl border border-border transition duration-150 group-hover:brightness-110 group-focus-visible:brightness-110"
          />
        </picture>
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 flex items-end justify-end rounded-xl bg-gradient-to-t from-black/40 via-transparent to-transparent p-3 opacity-0 transition duration-200 group-hover:opacity-100 group-focus-visible:opacity-100"
        >
          <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-background/80 px-2.5 py-1 text-xs font-medium text-foreground backdrop-blur">
            <Maximize2 className="size-3" />
            Open
          </span>
        </div>
      </button>
      <figcaption className="mt-2 text-sm text-muted-foreground">
        {screen.caption}
      </figcaption>
    </figure>
  )
}
