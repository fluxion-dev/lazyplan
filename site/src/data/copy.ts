export const COPY = {
  hero: {
    badge: "The terminal plan tracker",
    title: ["Plan it.", "Dispatch it.", "Prove it."],
    intro:
      "One local plan you and your agents share. First run sets it up, lanes carry it out, and every criterion keeps its proof.",
  },
  story: {
    eyebrow: "The loop",
    title: "One plan. Many lanes. Proof attached.",
    intro:
      "You and your agent share the same rows: plans, milestones, tasks, and acceptance criteria. Dispatch turns milestones into lanes, and every lane ends with evidence on the criterion it proves.",
  },
  features: {
    eyebrow: "What you get",
    title: "Every row is a workspace.",
    intro:
      "The plan tree is the spine. Lanes, claims, sessions, evidence, and git proof hang off it, so the work stays in one place.",
  },
  firstRun: {
    eyebrow: "First run",
    title: "A wizard, not a config file.",
    intro:
      "The first launch offers setup. Choose where plans live, which agents receive the skill, and how hooks behave. Nothing is written until you review and apply.",
    points: [
      {
        title: "Placement",
        description:
          "The home database follows every checkout. Repo placement keeps the journal with the work and ignores the database file.",
      },
      {
        title: "Agents and hooks",
        description:
          "Detected hosts get the skill and managed profiles. Hooks record sessions, inject the active plan, and check commits and stops.",
      },
      {
        title: "Models and effort",
        description:
          "Each host maps fast, standard, and deep tiers to its own models. Roles can add an effort level where the host exposes one.",
      },
      {
        title: "Review, then apply",
        description:
          "The last step lists every file setup writes, refreshes, or removes. Apply runs the same writer as lpui setup.",
      },
    ],
  },
  practice: {
    eyebrow: "Ways to work",
    title: "Solo, paired, or parallel.",
    intro:
      "Start with one agent and one task. Add lanes when the work can run side by side, and give each role the model it needs.",
  },
  dispatch: {
    eyebrow: "Lanes and dispatch",
    title: "Milestones are lanes. Lanes run in waves.",
    intro:
      "lpui dispatch --plan P prints the waves, the capacity, the worktree command for each lane, and one prompt per ready task. You run the commands; lazyplan keeps the journal.",
    beats: [
      {
        title: "Declare the shape",
        description:
          "A plan sets its dispatch mode and agent cap. Each milestone names a wave and a role; tasks inherit the lane's work.",
      },
      {
        title: "Register the worktrees",
        description:
          "Dispatch prints one git worktree command per lane and the matching register call. lazyplan never creates or removes a checkout itself.",
      },
      {
        title: "Start one worker per task",
        description:
          "A lane holds one doing task, so parallel agents cannot race the same row. Claims, touch-points, and expiry guard the files.",
      },
      {
        title: "Integrate in a later wave",
        description:
          "The integrator lane merges the finished work and runs the combined gates before the plan closes.",
      },
    ],
  },
  proof: {
    eyebrow: "Proof, not promises",
    title: "The work leaves a trail.",
    intro:
      "Criteria, evidence, questions, and approvals live beside the work, not in a chat log. Follow a task into the commit, the file, and the pull request.",
  },
  gallery: {
    eyebrow: "See the loop",
    title: "The app, in use.",
    intro:
      "Deterministic captures from fixture plans: first run, the shell, dispatch, and the proof trail.",
  },
  workflow: {
    eyebrow: "How it works",
    title: "Plan, dispatch, prove.",
    steps: [
      {
        number: "01",
        title: "Plan with an agent",
        description:
          "Interview the work in words: why, scope, acceptance criteria, and the ordered slices. Your agent writes the rows; you edit them.",
      },
      {
        number: "02",
        title: "Dispatch the lanes",
        description:
          "Milestones become lanes in waves. Dispatch prints the capacity, the worktree command, and one prompt per ready task.",
      },
      {
        number: "03",
        title: "Keep the proof",
        description:
          "Evidence, commits, and pull requests attach to the criterion they prove. Finish with trace, lint, and audit.",
      },
    ],
  },
  faq: {
    eyebrow: "FAQ",
    title: "Questions, answered.",
    intro: "Setup, agents, lanes, and where your data lives.",
  },
  install: {
    eyebrow: "Install",
    title: "Get the plan into your terminal.",
    intro: "Python 3.11+. Linux, macOS, Windows.",
  },
  cta: {
    title: "Bring your plan into focus.",
    intro: "One plan for you and your agents, with the proof attached.",
  },
} as const
