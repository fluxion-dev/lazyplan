# Site discoverability and SEO

The site is `https://fluxion-dev.github.io/lazyplan/`. Curl it before assuming
a deploy landed.

## Automated gate

```bash
python3 tools/check-site.py                 # source page, sitemap, robots, assets
python3 tools/check-site.py --dist site/dist # built page after npm run build
```

`tools/check.sh` runs the source check. The Pages workflow runs the dist check
after `npm run build` and before upload, so a malformed canonical, missing alt
text, broken anchor, bad heading order, missing sitemap entry, or invalid
JSON-LD blocks the deploy.

The gate deliberately checks both plain metadata and the structured data that
search engines actually consume. Do not weaken it to make a copy change pass;
fix the page.

## Current content targets

- Primary phrase: terminal plan tracker.
- Secondary: plan tracker for coding agents, agent planning, local plan
  database, git provenance, pull request tracking.
- The provenance section and FAQ exist to cover those intents without keyword
  stuffing. Keep answers specific and matched to shipped behavior.

## Google Search Console

1. Open <https://search.google.com/search-console>.
2. Add a **URL-prefix** property for `https://fluxion-dev.github.io/lazyplan/`
   (not a domain property; GitHub Pages does not let us add DNS records).
3. Verify with the HTML tag method: copy the `google-site-verification` meta
   tag into `site/index.html` `<head>`, deploy, then click Verify. Keep the tag
   in the page after verification.
4. Submit `https://fluxion-dev.github.io/lazyplan/sitemap.xml` under
   **Indexing → Sitemaps**.
5. Use **URL Inspection** on the canonical URL after each deploy and request
   indexing once the page is live.

This is a human-only step: the agent can prepare the meta tag and the deploy,
but only the account owner can verify ownership and submit.

## Bing Webmaster Tools

1. Open <https://www.bing.com/webmasters>.
2. Add `https://fluxion-dev.github.io/lazyplan/`.
3. Prefer **Import from Google Search Console** if the Google property is
   verified; otherwise use the meta-tag method.
4. Submit the same sitemap.
5. Optional: enable IndexNow if a stable key file is added to `site/public/`.
   Only claim IndexNow if it is actually configured.

## Off-site discoverability checklist

- GitHub repository **About**: one-sentence description and topics
  `terminal`, `tui`, `planning`, `coding-agents`, `developer-tools`, `git`,
  `pull-requests`, `python`, `textual`.
- PyPI project summary, keywords, classifiers, and long description match the
  site's positioning.
- README first screen names the product, the problem, and the install command.
- Release notes summarize user-facing outcomes, not just commit titles.
- Link the live site from the GitHub release and README.

## Performance and accessibility baseline

The page is deliberately dependency-light for a marketing page:

- self-hosted variable fonts with `font-display: swap`;
- hero screenshot preloaded and `fetchpriority="high"`;
- below-fold screenshots `loading="lazy"` with explicit dimensions;
- WebP sources with PNG fallbacks;
- reduced-motion media query disables smooth scroll and transitions;
- visible focus rings, skip link, labelled tabs, and keyboard tab behavior;
- no third-party analytics or tag manager by default.

Record a Lighthouse or PageSpeed Insights result after deploy. Target 90+ for
Performance, Accessibility, Best Practices, and SEO on mobile. Check 360px,
768px, and desktop widths for horizontal overflow.

### v0.21.0 pass (2026-10-24)

Before: the hero image was eager but not preloaded, below-fold screenshots were
also eager, the page had no provenance/FAQ content, and no SEO gate existed.

After: the hero is preloaded with `fetchpriority="high"`, below-fold screenshots
are lazy with explicit dimensions, provenance and FAQ content cover the target
intents, FAQPage/SoftwareApplication structured data validate, and
`tools/check-site.py` runs in the normal gates and again against `site/dist`
before Pages deploy. Live Lighthouse and mobile-width checks run immediately
after deploy; record the scores in the release notes if they miss the target.

### v0.22.0 pass (2026-10-24)

After: the provenance copy names live in-place diffs in the Source trail card,
the visible FAQ, and the FAQPage JSON-LD. Version pins, release asset URLs, and
the sitemap moved to 0.22.0; canonical, robots, structured data, and the social
preview asset are unchanged and serve cleanly.

Verified live with the commands below plus the release badge endpoint: the page
contains 0.22.0 and the diff copy, `sitemap.xml` is current, and
`screens/og-lpui-and-agent.png` returns 200.

Human-only follow-ups: submit the updated URL to search engines, record
Lighthouse/mobile scores, and confirm the social card in a real client.

## Post-deploy verification

Run after Pages is green:

```bash
curl -fsSL https://fluxion-dev.github.io/lazyplan/ -o /tmp/lazyplan-site.html
grep -E 'canonical|FAQPage|0\.[0-9]+\.[0-9]+|provenance' /tmp/lazyplan-site.html | head
curl -fsSL https://fluxion-dev.github.io/lazyplan/sitemap.xml
curl -fsSL https://fluxion-dev.github.io/lazyplan/robots.txt
python3 - <<'PY'
import json, urllib.request
with urllib.request.urlopen("https://pypi.org/pypi/lazyplan-tui/json") as r:
    print(json.load(r)["info"]["version"])
PY
```

Then check the live page in a private window and confirm the canonical URL,
FAQ rich-result eligibility, social preview image, and version badges.
