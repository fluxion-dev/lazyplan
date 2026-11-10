import { cn } from "cn"

import type { Screen } from "@/data/site"

type ScreenshotFrameProps = Readonly<{
  screen: Screen
  onOpen: (screen: Screen) => void
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
        onClick={() => onOpen(screen)}
        className="group block w-full cursor-zoom-in rounded-xl text-left"
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
      </button>
      <figcaption className="mt-2 text-sm text-muted-foreground">
        {screen.mono ? (
          <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[0.9em] text-foreground">
            {screen.caption}
          </code>
        ) : (
          screen.caption
        )}
      </figcaption>
    </figure>
  )
}
