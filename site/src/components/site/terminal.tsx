import type { ReactNode } from "react"
import { cn } from "cn"

type TerminalProps = Readonly<{
  title?: string
  children: ReactNode
  className?: string
}>

export function Terminal({
  title = "lazyplan",
  children,
  className,
}: TerminalProps) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border border-border bg-background shadow-cinema",
        className
      )}
    >
      <div
        aria-hidden="true"
        className="flex items-center gap-1.5 border-b border-border/70 bg-card/60 px-3 py-2"
      >
        <span className="size-2 rounded-full bg-[#ff5f57]" />
        <span className="size-2 rounded-full bg-[#febc2e]" />
        <span className="size-2 rounded-full bg-[#28c840]" />
        <span className="ml-2 font-mono text-[0.68rem] tracking-wide text-muted-foreground">
          {title}
        </span>
      </div>
      <pre className="m-0 overflow-x-auto p-4 font-mono text-[0.82rem] leading-relaxed text-foreground">
        {children}
      </pre>
    </div>
  )
}
