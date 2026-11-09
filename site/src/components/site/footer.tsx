import { DOCS_URL, LICENSE_URL, REPO_URL, RELEASES_URL } from "@/data/site"

const LINKS = [
  { href: DOCS_URL, label: "Docs" },
  { href: `${DOCS_URL}#setup-and-scope`, label: "Setup" },
  { href: REPO_URL, label: "GitHub" },
  { href: RELEASES_URL, label: "Releases" },
  { href: LICENSE_URL, label: "License" },
] as const

export function Footer() {
  return (
    <footer className="border-t border-border bg-card/60 px-6 py-12 text-center text-[0.92rem] text-muted-foreground backdrop-blur">
      <p className="m-0">
        <a
          href={REPO_URL}
          className="text-brand-cyan underline-offset-4 hover:text-foreground hover:underline"
        >
          lazyplan
        </a>{" "}
        — one plan for you and your agent.
      </p>
      <ul className="mt-6 flex list-none flex-wrap items-center justify-center gap-x-6 gap-y-2 p-0">
        {LINKS.map((link) => (
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
    </footer>
  )
}
