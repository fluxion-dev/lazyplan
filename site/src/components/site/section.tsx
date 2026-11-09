import type { ReactNode } from "react"
import { cn } from "cn"

type SectionProps = Readonly<{
  id?: string
  className?: string
  padded?: boolean
  children: ReactNode
}>

export function Section({
  id,
  className,
  padded = true,
  children,
}: SectionProps) {
  return (
    <section
      id={id}
      className={cn(
        "mx-auto w-full max-w-6xl scroll-mt-24 px-6",
        padded && "py-20 md:py-28",
        className
      )}
    >
      {children}
    </section>
  )
}

type SectionHeadingProps = Readonly<{
  eyebrow: string
  title: string
  intro?: string
  className?: string
}>

export function SectionHeading({
  eyebrow,
  title,
  intro,
  className,
}: SectionHeadingProps) {
  return (
    <div className={cn("mb-10 max-w-2xl md:mb-14", className)}>
      <p className="mb-3 text-sm font-semibold tracking-[0.18em] text-brand-cyan uppercase">
        {eyebrow}
      </p>
      <h2 className="mb-4 text-2xl font-bold tracking-tight text-balance text-foreground md:text-3xl">
        {title}
      </h2>
      {intro ? (
        <p className="text-lg text-pretty text-muted-foreground">{intro}</p>
      ) : null}
    </div>
  )
}
