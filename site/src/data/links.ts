export const VERSION = "0.49.0"
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

export type SectionId =
  | "first-run"
  | "story"
  | "dispatch"
  | "proof"
  | "screens"
  | "faq"

export type SectionLink = Readonly<{
  id: SectionId
  href: `#${SectionId}`
  label: string
}>

export const SECTION_LINKS: readonly SectionLink[] = [
  { id: "first-run", href: "#first-run", label: "First run" },
  { id: "story", href: "#story", label: "Plan" },
  { id: "dispatch", href: "#dispatch", label: "Dispatch" },
  { id: "proof", href: "#proof", label: "Proof" },
  { id: "screens", href: "#screens", label: "Screenshots" },
  { id: "faq", href: "#faq", label: "FAQ" },
]

export const NAV_LINKS: readonly NavLink[] = [
  ...SECTION_LINKS,
  { href: DOCS_URL, label: "Docs", external: true },
]
