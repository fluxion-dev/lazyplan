import {
  Activity,
  Bot,
  Database,
  Download,
  GitBranch,
  Keyboard,
  Layers,
  ListChecks,
  Lock,
  MessagesSquare,
  Monitor,
  Network,
  Palette,
  Route,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Timer,
  type LucideIcon,
} from "lucide-react"

import type { FeatureIcon as FeatureIconName } from "@/data/site"

const ICONS: Record<FeatureIconName, LucideIcon> = {
  activity: Activity,
  bot: Bot,
  database: Database,
  download: Download,
  "git-branch": GitBranch,
  keyboard: Keyboard,
  layers: Layers,
  "list-checks": ListChecks,
  lock: Lock,
  "messages-square": MessagesSquare,
  monitor: Monitor,
  network: Network,
  palette: Palette,
  route: Route,
  search: Search,
  "shield-check": ShieldCheck,
  sliders: SlidersHorizontal,
  sparkles: Sparkles,
  timer: Timer,
}

type FeatureIconProps = Readonly<{
  name: FeatureIconName
  className?: string
}>

export function FeatureIcon({ name, className }: FeatureIconProps) {
  const Icon = ICONS[name]
  return <Icon className={className} aria-hidden="true" />
}
