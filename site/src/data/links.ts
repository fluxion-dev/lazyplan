export const VERSION = "0.39.0"
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
  { href: "#story", label: "Story" },
  { href: "#features", label: "Features" },
  { href: "#proof", label: "Proof" },
  { href: "#screens", label: "Screenshots" },
  { href: "#faq", label: "FAQ" },
  { href: DOCS_URL, label: "Docs", external: true },
]
