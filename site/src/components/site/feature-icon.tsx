import {
  Activity,
  Database,
  Download,
  GitBranch,
  Keyboard,
  Layers,
  ListChecks,
  Lock,
  MessagesSquare,
  Network,
  Palette,
  Route,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  type LucideIcon,
} from "lucide-react"

import type { FeatureIcon as FeatureIconName } from "@/data/site"

const ICONS: Record<FeatureIconName, LucideIcon> = {
  activity: Activity,
  database: Database,
  download: Download,
  "git-branch": GitBranch,
  keyboard: Keyboard,
  layers: Layers,
  "list-checks": ListChecks,
  lock: Lock,
  "messages-square": MessagesSquare,
  network: Network,
  palette: Palette,
  route: Route,
  "shield-check": ShieldCheck,
  sliders: SlidersHorizontal,
  sparkles: Sparkles,
}

type FeatureIconProps = Readonly<{
  name: FeatureIconName
  className?: string
}>

export function FeatureIcon({ name, className }: FeatureIconProps) {
  const Icon = ICONS[name]
  return <Icon className={className} aria-hidden="true" />
}
