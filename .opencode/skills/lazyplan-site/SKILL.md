---
name: lazyplan-site
description: Use when editing the lazyplan marketing site in site/ — React 19, TypeScript, Vite, Tailwind v4, and shadcn/ui. Covers the brand theme, page sections, shadcn component conventions, prerendering, and the build and deploy loop.
---

# lazyplan marketing site

The site is a single landing page at `site/`. It is a React app that is
prerendered to static HTML at build time, so crawlers and the discoverability
gate see full markup before JavaScript runs.

## Stack

- React 19 + TypeScript, built by Vite.
- Tailwind CSS v4 through `@tailwindcss/vite`.
- shadcn/ui, `radix-nova` style, Radix base.
- Self-hosted Plus Jakarta Sans and JetBrains Mono.
- GitHub Pages, served from `site/dist` under `/lazyplan/`.

## Layout

| Path | Purpose |
| --- | --- |
| `site/index.html` | Vite entry. Keeps the head metadata, JSON-LD, `<div id="root">`, and the module script. |
| `site/src/main.tsx` | Hydrates the prerendered root, or mounts fresh in dev. |
| `site/src/App.tsx` | Section order for the page. |
| `site/src/index.css` | Tailwind, shadcn tokens, brand tokens, fonts, base layer. |
| `site/src/data/site.ts` | Version, links, nav, FAQ, screenshots, and other page content. |
| `site/src/components/ui/` | shadcn components. Generated; prefer adding over hand-editing. |
| `site/src/components/site/` | Page sections composed from shadcn primitives. |
| `site/src/entry-server.tsx` | Renders the app to a string for prerendering. |
| `site/scripts/prerender.mjs` | Injects the rendered markup into `dist/index.html`. |
| `site/public/` | Screenshots, logo, robots, sitemap, downloads snapshot. |

## Commands

```bash
cd site
npm install
npm run dev        # http://127.0.0.1:5173/lazyplan/
npm run build      # tsc, client build, SSR build, prerender
npm run preview    # serve dist at the configured base
npm run typecheck
npx shadcn@latest add <component>
python3 tools/check-site.py --dist site/dist
```

`npm run build` is the source of truth. It must leave `site/dist/index.html`
with the full rendered body; otherwise SEO and `check-site.py` fail.

## Brand tokens

Set once in `site/src/index.css`, used semantically everywhere else.

| Token | Value | Use |
| --- | --- | --- |
| `--background` | `#09090B` | Page canvas |
| `--card` | `#131316` | Elevated surfaces |
| `--border` | `#27272A` | Borders, separators |
| `--primary` | `#2563EB` | Primary actions |
| `--ring` | `#06B6D4` | Focus rings |
| `--brand-gold` | `#F59E0B` | Brand dot, timeline accents |
| `--brand-cyan` | `#06B6D4` | Eyebrows, links |
| `--brand-green` | `#10B981` | Success and execution states |
| `--radius` | `0.75rem` | Base radius |

Never hard-code raw palette classes such as `text-zinc-400` or
`bg-blue-500` in page code. Use `text-muted-foreground`, `bg-primary`,
`border-border`, or a `brand-*` token.

## shadcn rules

Install the official skill with `npx skills add shadcn/ui -g`; it has the full
guide. The project imports `cn` from the `cn` package directly. The essentials
for this site:

- Prefer `Button`, `Card`, `Badge`, `Accordion`, `Dialog`, `Sheet`,
  `Separator`, and `Kbd` over hand-rolled equivalents.
- Use built-in variants before adding classes. `className` is for layout only.
- Use full `Card` composition: `CardHeader`, `CardTitle`, `CardDescription`,
  `CardContent`, `CardFooter`.
- `Dialog` and `Sheet` always need a `Title`; hide it with `sr-only` when it is
  visual only.
- Use `flex` + `gap-*`, never `space-y-*`. Use `size-*` when width equals
  height, and `truncate` for single-line overflow.
- Use `cn()` for conditional classes.
- Do not add `z-*` to overlay components; they manage their own stacking.
- Add components with the CLI, not by copying random snippets.
- The FAQ force-mounts `AccordionContent` so every answer is in the static
  HTML, and `AccordionContent` carries `data-[state=closed]:hidden` so closed
  answers stay hidden. Keep both when re-adding the accordion.

## Page rules

- Exactly one `h1`, and headings must not skip levels.
- Every local image needs `alt`, `width`, and `height`; every screenshot has a
  matching `.webp` and a zoom trigger.
- Keep the head metadata, canonical URL, Open Graph, Twitter, and JSON-LD in
  `index.html` in sync with the visible copy. The FAQ JSON-LD answers must match
  the visible FAQ.
- Keep the word budget under 750 words and the screenshot figure count at ten.
- No browser APIs at module scope; use effects. The app must render on the
  server without `window` or `document`.
- Links to docs use
  `https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md` and its
  existing anchors.

## Version bumps

`tools/bump.sh` updates the version in `site/index.html` and
`site/src/data/site.ts`. When adding version-pinned links or badges, derive
them from `VERSION` in `site/src/data/site.ts` instead of repeating literals.

## Deploy loop

For rapid site iteration, use the opencode worktree and merge through a pull
request. Pages deploys on any `site/**` push to `main`; watch the `pages`
workflow and verify the live page before reporting done.

```bash
git switch -c site/my-change origin/main
# edit, build, check
git commit -am "site: ..."
git push -u origin site/my-change
gh pr create --base main --fill
gh pr merge --admin --squash --delete-branch
```
