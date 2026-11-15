export type FaqItem = Readonly<{ question: string; answer: string }>

export const FAQ: readonly FaqItem[] = [
  {
    question: "What is lazyplan?",
    answer:
      "A local plan your coding agents can read and write. Plans, milestones, tasks, and acceptance criteria live in one SQLite journal, and the read-only trail from each criterion to its commits and pull requests stays attached.",
  },
  {
    question: "What happens on first run?",
    answer:
      "lpui detects your agents, offers the setup wizard, and creates the plan store. The wizard asks where plans live, which agents receive the skill, how hooks behave, and which models each role uses. It lists every file it will write before anything is applied. Reopen it with lpui setup or by pressing S in the screen.",
  },
  {
    question: "Do I need more than one agent?",
    answer:
      "No. One agent can plan and execute. When you add workers, milestones become lanes and lpui dispatch --plan P prints the waves, the worktree commands, and one prompt per ready task.",
  },
  {
    question: "How do parallel lanes avoid collisions?",
    answer:
      "A lane holds one doing task at a time, claims carry a lease with an expiry, and touch-points name the files a task expects. Parallel plans also require a lane cap and an integrator lane in a later wave.",
  },
  {
    question: "Does it work with my coding agent?",
    answer:
      "Yes. Setup detects OpenCode, Claude Code, Codex, Cursor, Gemini CLI, and Copilot, and any agent that can run a command can use the CLI or the MCP server.",
  },
  {
    question: "Where is my data stored?",
    answer:
      "In a local SQLite database: your home directory by default, or inside the repo when setup chooses repo placement. There is no account and no cloud dependency, and you can export or import everything at any time.",
  },
  {
    question: "How do updates work?",
    answer:
      "The taskbar shows the running version. When the update cache knows a newer release it adds an arrow; click the badge or press U to download and verify a wheel that applies on the next launch. lpui upgrade does the same from the shell.",
  },
  {
    question: "Does it run on Windows, macOS, and Linux?",
    answer: "Yes. Linux, macOS, and Windows; the plan stays local on all three.",
  },
]
