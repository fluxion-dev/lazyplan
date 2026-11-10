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

export const HERO_COMPOSITE: Screen = {
  name: "hero",
  file: "lpui-hero",
  width: 2400,
  height: 1200,
  alt: "Wide lazyplan scene with the plan tree on the left, an agent workbench in the middle, and a source trail with commits and a pull request on the right.",
  caption: "One shared plan, one agent loop, one proof trail.",
}

export const STORY_SCREENS: readonly Screen[] = [
  {
    name: "control-room",
    file: "lpui-control-room",
    width: 1604,
    height: 904,
    alt: "Control room with the health and needs strip, active session, attention tasks, open question, claims, and approval drift.",
    caption: "What needs you, before it blocks the loop.",
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
    caption: "Claims, blockers, and attention in one tree.",
  },
  {
    name: "workbench",
    file: "lpui-workbench",
    width: 1604,
    height: 904,
    alt: "lazyplan agent workbench with a task prompt, a streaming agent response, a tool approval card, and the plan beside it.",
    caption: "Run the agent beside the plan.",
  },
  {
    name: "trust-evidence",
    file: "lpui-trace",
    width: 1482,
    height: 587,
    alt: "lazyplan trace output linking acceptance criteria to tasks, commits, and pull requests, with a lint finding for a missing proving task.",
    caption: "Every criterion keeps its proof.",
  },
  {
    name: "source-trail",
    file: "lpui-source-trail",
    width: 1604,
    height: 904,
    alt: "Source trail for a task with a repository, commits, changed files, pull requests, and a selected file diff.",
    caption: "Follow a task into the commit and the code.",
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
    name: "timeline",
    file: "lpui-timeline",
    width: 1604,
    height: 904,
    alt: "Main shell with the timeline open, showing plan and milestone traces at distinct start positions and one never-started lane.",
    caption: "Plans and milestones across lanes.",
  },
]
