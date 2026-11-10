import {
  Activity,
  Bot,
  Database,
  GitBranch,
  Keyboard,
  ListChecks,
  Lock,
  MessagesSquare,
  Monitor,
  Network,
  Palette,
  Route,
  Search,
  ShieldCheck,
  Timer,
  type LucideIcon,
} from "lucide-react"

import type { FeatureIcon as FeatureIconName } from "@/data/site"

const ICONS: Record<FeatureIconName, LucideIcon> = {
  activity: Activity,
  bot: Bot,
  database: Database,
  "git-branch": GitBranch,
  keyboard: Keyboard,
  "list-checks": ListChecks,
  lock: Lock,
  "messages-square": MessagesSquare,
  monitor: Monitor,
  network: Network,
  palette: Palette,
  route: Route,
  search: Search,
  "shield-check": ShieldCheck,
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
