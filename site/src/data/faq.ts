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
