export type Screen = Readonly<{
  name: string
  file: string
  width: number
  height: number
  alt: string
  caption: string
}>

export const HERO_COMPOSITE: Screen = {
  name: "hero",
  file: "lpui-hero",
  width: 2400,
  height: 1200,
  alt: "Wide lazyplan scene: the plan tree and its overview on the left, a dispatch transcript with lanes and wave capacity at the top right, and a source trail with commits and a merged pull request below it.",
  caption: "Plan with an agent, dispatch the lanes, keep the proof.",
}

export const SCREENS = {
  setup: {
    name: "setup",
    file: "lpui-setup",
    width: 1604,
    height: 904,
    alt: "Setup wizard on its welcome step, with the step rail on the left and the resolved database, templates, config, pointer, and state paths in the panel.",
    caption: "First run asks where plans live and who they serve.",
  },
  "setup-review": {
    name: "setup-review",
    file: "lpui-setup-review",
    width: 1604,
    height: 904,
    alt: "Setup wizard on the review step, listing every database, config, skill, pointer, and agent profile file that Apply will write before anything changes.",
    caption: "Review lists every file before Apply writes a byte.",
  },
  update: {
    name: "update",
    file: "lpui-update",
    width: 1604,
    height: 904,
    alt: "Update dialog showing the installed version, the latest release, the install method, and Download, Restart, and Later buttons.",
    caption: "The taskbar badge opens a verified update.",
  },
  detail: {
    name: "detail",
    file: "lpui-detail",
    width: 1604,
    height: 904,
    alt: "Plan overview showing a plan's reason, scope, acceptance criteria, and milestones.",
    caption: "The why, the what, and what done means.",
  },
  dispatch: {
    name: "dispatch",
    file: "lpui-dispatch",
    width: 1604,
    height: 587,
    alt: "Terminal transcript of lpui dispatch showing waves, lane roles, registered worktrees, the capacity line, and the claim and worktree commands to run.",
    caption: "Waves, lane capacity, worktrees, and one prompt per task.",
  },
  worktrees: {
    name: "worktrees",
    file: "lpui-worktrees",
    width: 1604,
    height: 587,
    alt: "Terminal transcript of lpui plan worktree list and print showing the registered lane checkouts and the git worktree command for a new lane.",
    caption: "Every lane gets its own checkout, registered by you.",
  },
  "control-room": {
    name: "control-room",
    file: "lpui-control-room",
    width: 1604,
    height: 904,
    alt: "Control room with the plan tree, a compact agents row with two claims, the needs line, an open question, approval drift, and a failed check.",
    caption: "What needs you, before it blocks the loop.",
  },
  "git-pane": {
    name: "git-pane",
    file: "lpui-git-pane",
    width: 1604,
    height: 904,
    alt: "Main shell with a linked task selected: the plan tree and GIT pane with checkout, branch, commits, and pull requests on the left, and the task overview on the right.",
    caption: "Checkout, commits, and pull requests for the row.",
  },
  "source-trail": {
    name: "source-trail",
    file: "lpui-source-trail",
    width: 1604,
    height: 904,
    alt: "Source trail for a task with a repository, commits, changed files, pull requests, and a selected file diff.",
    caption: "Follow a task into the commit and the code.",
  },
  trace: {
    name: "trace",
    file: "lpui-trace",
    width: 1482,
    height: 587,
    alt: "Terminal transcript of lpui trace and lpui lint --strict linking acceptance criteria to tasks, commits, and pull requests, with a finding for a criterion that has no proving task.",
    caption: "Every criterion keeps its proof.",
  },
  timeline: {
    name: "timeline",
    file: "lpui-timeline",
    width: 1604,
    height: 904,
    alt: "Main shell with the timeline open under the plan tree, showing the selected milestone's task lanes with start positions and duration segments on a fixed time axis.",
    caption: "The selected milestone across time.",
  },
} as const satisfies Record<string, Screen>

export type ScreenName = keyof typeof SCREENS

export function screen(name: ScreenName): Screen {
  return SCREENS[name]
}

/** Gallery order: setup, updates, the plan, lanes, and the proof trail. */
export const GALLERY: readonly ScreenName[] = [
  "setup-review",
  "update",
  "detail",
  "worktrees",
  "git-pane",
  "source-trail",
  "trace",
  "timeline",
]
