import type { ReactNode } from "react"
import { cn } from "cn"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type { FeatureIcon as FeatureIconName } from "@/data/site"

import { FeatureIcon } from "./feature-icon"

type FeatureCardProps = Readonly<{
  icon: FeatureIconName
  title: string
  description: string
  hint?: ReactNode
  className?: string
}>

export function FeatureCard({
  icon,
  title,
  description,
  hint,
  className,
}: FeatureCardProps) {
  return (
    <Card
      className={cn(
        "h-full border-border bg-card/70 shadow-lg shadow-black/30",
        className
      )}
    >
      <CardHeader>
        <div className="mb-2 flex size-9 items-center justify-center rounded-lg bg-secondary text-brand-cyan">
          <FeatureIcon name={icon} className="size-4" />
        </div>
        <CardTitle className="text-lg">{title}</CardTitle>
        <CardDescription className="text-[0.95rem]">
          {description}
        </CardDescription>
      </CardHeader>
      {hint ? (
        <CardContent className="pt-0 font-mono text-[0.85rem] text-muted-foreground">
          {hint}
        </CardContent>
      ) : null}
    </Card>
  )
}
