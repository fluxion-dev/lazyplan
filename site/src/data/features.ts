import features from "./features.json"

export type FeatureGroup = "plan" | "agents" | "proof" | "product"

export type FeatureIcon =
  | "activity"
  | "bot"
  | "database"
  | "git-branch"
  | "keyboard"
  | "list-checks"
  | "lock"
  | "messages-square"
  | "monitor"
  | "network"
  | "palette"
  | "route"
  | "search"
  | "shield-check"
  | "timer"

export type Feature = Readonly<{
  id: string
  title: string
  description: string
  icon: FeatureIcon
  group: FeatureGroup
}>

export const LEAD_FEATURES = features.lead as readonly Feature[]
export const SUPPORT_FEATURES = features.support as readonly Feature[]
