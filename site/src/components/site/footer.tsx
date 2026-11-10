import {
  DOCS_URL,
  LICENSE_URL,
  REPO_URL,
  RELEASES_URL,
  VERSION,
} from "@/data/site"

const GROUPS = [
  {
    title: "Product",
    links: [
      { href: "#story", label: "Story" },
      { href: "#features", label: "Features" },
      { href: "#proof", label: "Proof" },
      { href: "#screens", label: "Screenshots" },
    ],
  },
  {
    title: "Docs",
    links: [
      { href: DOCS_URL, label: "Usage" },
      { href: `${DOCS_URL}#setup-and-scope`, label: "Setup" },
      { href: REPO_URL, label: "GitHub" },
      { href: RELEASES_URL, label: "Releases" },
      { href: LICENSE_URL, label: "License" },
    ],
  },
] as const

export function Footer() {
  return (
    <footer className="relative overflow-hidden border-t border-border bg-card/40 px-6 py-16">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 cinema-grid opacity-30"
      />
      <div className="relative mx-auto max-w-6xl">
        <div className="grid gap-10 md:grid-cols-[1.2fr_1fr_1fr]">
          <div>
            <a
              href="#top"
              className="inline-flex items-center gap-2 text-xl font-extrabold tracking-tight text-foreground no-underline"
            >
              <img
                src="./logo.svg"
                alt=""
                width={32}
                height={32}
                className="size-8"
                aria-hidden="true"
              />
              <span>
                lazyplan<span className="text-brand-gold">.</span>
              </span>
            </a>
            <p className="mt-4 max-w-sm text-sm text-pretty text-muted-foreground">
              One plan for you and your agent. Plan locally. Ship with proof.
            </p>
            <p className="mt-4 font-mono text-xs text-muted-foreground">
              v{VERSION} · MIT
            </p>
          </div>
          {GROUPS.map((group) => (
            <div key={group.title}>
              <p className="mb-3 text-xs font-semibold tracking-[0.16em] text-brand-cyan uppercase">
                {group.title}
              </p>
              <ul className="m-0 flex list-none flex-col gap-2 p-0 text-sm">
                {group.links.map((link) => (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-12 flex flex-col gap-2 border-t border-border/60 pt-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p className="m-0">MIT licensed. Built for the terminal.</p>
          <p className="m-0">Local-first by default. No account, no cloud.</p>
        </div>
      </div>
    </footer>
  )
}
