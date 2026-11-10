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
export const FEATURES: readonly Feature[] = [...LEAD_FEATURES, ...SUPPORT_FEATURES]

export const COPY = {
  story: {
    eyebrow: "The loop",
    title: "One plan. Two workers. No lost context.",
    intro:
      "You and your agent share the same rows, the same acceptance criteria, and the same history. Edit any row yourself, hand off a task, and watch the proof land.",
  },
  features: {
    eyebrow: "What you get",
    title: "Every row is a workspace.",
    intro:
      "The plan tree is the spine. Claims, sessions, evidence, questions, and git proof hang off it, so the work stays in one place.",
  },
  proof: {
    eyebrow: "Proof, not promises",
    title: "The work leaves a trail.",
    intro:
      "Approvals, evidence, and questions live beside the work, not in a chat log. Follow a task into the commit, the file, and the pull request.",
  },
  gallery: {
    eyebrow: "See the loop",
    title: "The app, in use.",
    intro:
      "Real captures from a working plan: the control room, the tree, the agent, and the proof.",
  },
  workflow: {
    eyebrow: "How it works",
    title: "Start with a plan. Finish with proof.",
    steps: [
      {
        number: "01",
        title: "Write the plan",
        description:
          "Give it a reason, a scope, and acceptance criteria. You and your agent read the same rows.",
      },
      {
        number: "02",
        title: "Hand off the loop",
        description:
          "A planner writes the work. An executor claims a task, leaves a handoff, and links the commit.",
      },
      {
        number: "03",
        title: "Keep the proof",
        description:
          "Watch needs, claims, and checks. Finish with evidence, a pull request, and a clean trail.",
      },
    ],
  },
  install: {
    eyebrow: "Install",
    title: "Get the plan into your terminal.",
    intro: "Python 3.11+. Linux, macOS, Windows.",
  },
  cta: {
    title: "Bring your plan into focus.",
    intro: "Give your agent the same plan you see.",
  },
} as const

export const VERSION = "0.35.0"
export const REPO_URL = "https://github.com/fluxion-dev/lazyplan"
export const DOCS_URL = `${REPO_URL}/blob/main/docs/usage.md`
export const RELEASES_URL = `${REPO_URL}/releases`
export const PYPI_URL = "https://pypi.org/project/lazyplan-tui/"
export const LICENSE_URL = `${REPO_URL}/blob/main/LICENSE`
export const INSTALL_COMMAND = "pipx install lazyplan-tui"

export const RELEASE_BADGE = `https://img.shields.io/github/v/release/fluxion-dev/lazyplan?v=${VERSION}`
export const PYPI_BADGE = `https://img.shields.io/pypi/v/lazyplan-tui?v=${VERSION}`
export const LICENSE_BADGE = "https://img.shields.io/github/license/fluxion-dev/lazyplan"

export type NavLink = Readonly<{
  href: string
  label: string
  external?: boolean
}>

export const NAV_LINKS: readonly NavLink[] = [
  { href: "#new", label: "New" },
  { href: "#features", label: "Features" },
  { href: "#screens", label: "Screenshots" },
  { href: "#faq", label: "FAQ" },
  { href: DOCS_URL, label: "Docs", external: true },
]

export type Screen = Readonly<{
  name: string
  file: string
  width: number
  height: number
  alt: string
  caption: string
  mono?: boolean
}>

export const SCREENS: readonly Screen[] = [
  {
    name: "control-room",
    file: "lpui-control-room",
    width: 1604,
    height: 904,
    alt: "Control room with a manual override banner, health and needs strip, active session, attention tasks, and approval drift.",
    caption: "What needs you, in one audited control room.",
  },
  {
    name: "detail",
    file: "lpui-detail",
    width: 1604,
    height: 904,
    alt: "Read-only detail page showing a plan's reason, scope, acceptance criteria, and milestones.",
    caption: "The why, the what, and what done means.",
  },
  {
    name: "coordination",
    file: "lpui-coordination",
    width: 1604,
    height: 904,
    alt: "Plan tree with active and expired claims, blocked work, aging tasks, and a red check, with attention summarized in the control strip.",
    caption: "Active, blocked, and attention at a glance.",
  },
  {
    name: "git-pane",
    file: "lpui-git-pane",
    width: 1604,
    height: 904,
    alt: "Main shell with a linked task selected, showing the sticky preview above a GIT pane with the checkout, branch, commits, and pull requests.",
    caption: "Checkout, commits, and pull requests for the row.",
  },
  {
    name: "export",
    file: "lpui-export",
    width: 1604,
    height: 904,
    alt: "Markdown export picker showing the destination path, a Downloads folder tree, the filename, and Export and Cancel actions.",
    caption: "Pick a folder.",
  },
  {
    name: "timeline",
    file: "lpui-timeline",
    width: 1604,
    height: 904,
    alt: "Main shell with the timeline open, showing plan and milestone traces at distinct start positions and one never-started lane.",
    caption: "Every lane stays; the scoped plan names the card.",
  },
  {
    name: "source-trail",
    file: "lpui-source-trail",
    width: 1604,
    height: 904,
    alt: "Source trail for a task with a repository, commits, changed files, pull requests, and a selected file diff.",
    caption: "Follow the plan into the code.",
  },
  {
    name: "search-bulk",
    file: "lpui-search-bulk",
    width: 1604,
    height: 904,
    alt: "Plan tree with three marked tasks, checkmarks on each row, and a marked count in the status line.",
    caption: "Find, mark, edit once.",
  },
  {
    name: "theme-void",
    file: "lpui-theme-void",
    width: 1604,
    height: 904,
    alt: "lazyplan main shell in the OLED-black void theme, with the plan tree, sticky preview, and GIT pane.",
    caption: "void",
    mono: true,
  },
  {
    name: "theme-latte",
    file: "lpui-theme-latte",
    width: 1604,
    height: 904,
    alt: "lazyplan main shell in the light Latte theme, with the plan tree, sticky preview, and GIT pane.",
    caption: "latte",
    mono: true,
  },
]

export type FaqItem = Readonly<{ question: string; answer: string }>

export const FAQ: readonly FaqItem[] = [
  {
    question: "What is lazyplan?",
    answer:
      "A shared plan for you and your coding agent. Plans, milestones, tasks, and acceptance criteria live in one place, so the work, the handoffs, and the proof stay visible instead of disappearing into chat.",
  },
  {
    question: "Who is it for?",
    answer:
      "Developers and small teams who use coding agents and want one plan everyone can see.",
  },
  {
    question: "Does it work with my coding agent?",
    answer:
      "Yes. It works with OpenCode, Claude Code, Cursor, Codex, Gemini CLI, and any agent that can run a command.",
  },
  {
    question: "Does it run on Windows, macOS, and Linux?",
    answer: "Yes. Linux, macOS, and Windows; your plan stays local.",
  },
  {
    question: "Where is my data stored?",
    answer:
      "In a local SQLite database on your machine. There is no account and no cloud dependency, and you can export or back up everything at any time.",
  },
  {
    question: "Can I use one agent to plan and another to execute?",
    answer:
      "Yes. A planner agent can write the plan while an executor or subagent claims and completes individual tasks. You can change roles or run both at once; everyone reads the same plan.",
  },
]
