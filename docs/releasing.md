# Releasing lazyplan

`pyproject.toml` is the single source of truth for the version. README, the man
page, `site/index.html`, and `site/package.json` mirror it; `tools/bump.sh`
updates all of them and `tests/test_version.py` fails on drift.

## Before tagging

1. Run `./tools/check.sh`. It must print `ALL GATES GREEN` on both
   interpreters.
2. Run `python3 tools/gen-man.py --check`.
3. Run `python3 tools/check-site.py` and, after `npm run build` in `site/`,
   `python3 tools/check-site.py --dist site/dist`. The Pages workflow runs the
   dist check before deploy; do not bypass it.
4. Build a wheel and inspect the contents when the release changes packaging:

   ```bash
   python3 -m build --outdir /tmp/lazyplan-dist
   ```

5. Confirm the version is already correct everywhere:

   ```bash
   grep -n '^version = ' pyproject.toml
   head -1 README.md
   grep -n '"version"' site/index.html site/package.json
   ```

6. Commit in reviewable slices and open a pull request against `main`.
   Do not tag a red commit.

## Publish

Run the **bump** workflow from the Actions tab and choose `patch`, `minor`, or
`major`. It commits the version bump on `release/vX.Y.Z`, opens a pull request,
and enables auto-merge. When `gates` passes, the PR merges; `tag-release` then
creates `vX.Y.Z` and dispatches `release.yml` against that tag.

Auto-merge merges with `GITHUB_TOKEN`, and GitHub does not start push-event
workflows for those pushes. The bump workflow therefore has a `publish` job
that waits for the release PR to merge, then dispatches `tag-release.yml` and
`pages.yml` explicitly. The job checks out the repository so `gh pr view` can
resolve it. Both dispatched workflows are idempotent: `tag-release` exits when
the tag already exists, and Pages redeploys the same source. A bot-created
release PR can also leave its `ci` run in `action_required`; approve that run
as an admin so `gates` can start. Approve promptly: the `publish` job waits 20
minutes for the release PR to merge. If approval runs past that window, the
job times out and auto-merge may not fire; merge the PR by hand, then dispatch
the tag and Pages workflows and record the outcome.

If the post-merge job still fails, dispatch both workflows by hand and record
the failing run URL before the next release:

```bash
gh workflow run tag-release.yml --ref main
gh workflow run pages.yml --ref main
```

```bash
gh run list --workflow bump.yml
gh run watch <bump-run-id>   # stays open until the release PR merges
```

Admins can still release locally through the ruleset bypass:

```bash
./tools/bump.sh patch --push
```

That pushes `main` and the tag directly, so prefer the workflow when the bump
should be reviewed. Do not push a tag before its version commit is on `main`.

`release.yml` builds sdist/wheel, `.deb` and `.rpm` for amd64/arm64, creates the
GitHub release, and publishes to PyPI through trusted publishing. GitHub
generates placeholder release notes; replace them with the curated summary:

```bash
gh release edit vX.Y.Z --notes-file /tmp/release-notes-vX.Y.Z.md
```

## Verify

```bash
python3 - <<'PY'
import json, urllib.request
with urllib.request.urlopen("https://pypi.org/pypi/lazyplan-tui/json") as r:
    print(json.load(r)["info"]["version"])
PY
pipx install "lazyplan-tui==X.Y.Z"
curl -fsSL https://github.com/fluxion-dev/lazyplan/releases/latest/download/install.sh | head
gh release view vX.Y.Z
```

A just-published version can take a minute to appear in the simple index, and
pip caches the miss in that window. Use `pip install --no-cache-dir` (or
`pipx --pip-args=--no-cache-dir`) when verifying immediately after the upload.

Also check that the deployed site shows the new version, the new copy, and
working screenshots:

```bash
curl -fsSL https://fluxion-dev.github.io/lazyplan/ | grep -E '0\.X\.Y|lpui-source-trail'
curl -fsI https://fluxion-dev.github.io/lazyplan/screens/lpui-source-trail.webp | head -1
```

The second command catches a missing or unreadable source-trail image; regenerate
it with `tools/capture-screens.py` rather than editing either format by hand.

Run the discoverability post-deploy checklist in `docs/seo.md`: canonical,
FAQ/JSON-LD, sitemap, robots, social preview, and version badges. Search engine
submission is human-only; document what was submitted.

## If something fails

Never force-push `main` or rewrite release history.

- **CI or Pages red before the tag:** fix on a new commit, push, and wait for
  green. No release exists yet, so nothing to undo.
- **Pages only:** rerun the workflow with `gh workflow run pages.yml`. The
  previous site stays live until the deploy succeeds.
- **Release workflow red after the tag:** inspect the failed job first. If the
  release must be recreated, delete the GitHub release and tag, fix the commit,
  and tag again:

  ```bash
  gh release delete vX.Y.Z --yes
  git push origin :refs/tags/vX.Y.Z
  git tag -d vX.Y.Z
  ```

- **PyPI already accepted the version:** PyPI versions are immutable. Yank the
  release from the project's PyPI release page, then publish a patch version.
  Do not try to overwrite the version.
- **Asset or install problem after publish:** leave the release visible and
  publish a patch with the fix. Add a short note to the broken release pointing
  at the patch.

Record the failing run URL and the recovery command used in the release notes
or the next plan row so the next release has the context.

## Release log

### v0.22.0 (2026-10-24)

- Minor bump from 0.21.0 with `./tools/bump.sh minor`: release commit
  `b56345d`, annotated tag `v0.22.0`.
- `ci.yml` and `pages.yml` green on `b56345d`:
  [ci](https://github.com/fluxion-dev/lazyplan/actions/runs/40127821060),
  [pages](https://github.com/fluxion-dev/lazyplan/actions/runs/40127821062).
- `release.yml` green for the tag, with both the `release` and `publish-pypi`
  jobs succeeding:
  [run](https://github.com/fluxion-dev/lazyplan/actions/runs/40128048379).
- PyPI lagged about two minutes behind the upload, and pip cached the miss; an
  isolated `pip install --no-cache-dir lazyplan-tui==0.22.0` then printed
  `0.22.0`. The tip above came from this run.
- Verified: PyPI JSON 0.22.0, all seven release assets, `install.sh`, the
  deployed site showing 0.22.0 and the diff copy, canonical/FAQ/JSON-LD,
  sitemap, robots, social preview asset, and the release badge.
- No deviations from the runbook and no fix-forward commits.

### v0.23.0 (2026-10-25)

- Minor bump from 0.22.0 with the **bump** workflow (`part=minor`), 70 commits
  after `v0.22.0`: [run](https://github.com/fluxion-dev/lazyplan/actions/runs/40199102285).
- Release PR [#4](https://github.com/fluxion-dev/lazyplan/pull/4) changed only
  the version mirrors. Its `gates` run was left in `action_required` by GitHub
  because the PR came from `GITHUB_TOKEN`; an admin approved it, then it passed:
  [run](https://github.com/fluxion-dev/lazyplan/actions/runs/40199121137).
- Auto-merge produced merge commit `bd865ad` with the same tree as the gated
  commit `d9f27a0`.
- **Deviation:** the auto-merge push did not trigger `tag-release.yml`, `ci.yml`,
  or `pages.yml`, because GitHub suppresses push-event workflows for
  `GITHUB_TOKEN` pushes. The annotated tag was created locally on `bd865ad`
  with `git tag -a v0.23.0 -m "lazyplan v0.23.0"` and pushed; that tag push
  started the release. Pages was dispatched with
  `gh workflow run pages.yml --ref main`
  ([run](https://github.com/fluxion-dev/lazyplan/actions/runs/40199772230)).
- `release.yml` green for the tag, with both `release` and `publish-pypi`
  succeeding:
  [run](https://github.com/fluxion-dev/lazyplan/actions/runs/40199626042).
- PyPI JSON served 0.23.0 immediately, but the simple index lagged: the first
  isolated install missed and a `--no-cache-dir` retry about two minutes later
  printed `0.23.0`.
- Verified: seven release assets including `install.sh`, the isolated install,
  the deployed site showing 0.23.0, the source-trail WebP, canonical/FAQ/JSON-LD,
  sitemap (lastmod 2026-10-25), and robots.
- Fix forward in the same docs PR: `bump.yml` now has a `publish` job that waits
  for the release PR and dispatches `tag-release.yml` and `pages.yml`, and
  `tag-release.yml` accepts `workflow_dispatch`. The next release proves it.

### v0.24.0 (2026-10-25)

- Minor bump from 0.23.0 with the **bump** workflow (`part=minor`):
  [run](https://github.com/fluxion-dev/lazyplan/actions/runs/40209172641). The
  `bump` job created `release/v0.24.0` and enabled auto-merge.
- Release PR [#9](https://github.com/fluxion-dev/lazyplan/pull/9) changed only
  the version mirrors. Its `gates` run was left in `action_required` by GitHub;
  an admin approved it, then it passed:
  [run](https://github.com/fluxion-dev/lazyplan/actions/runs/40209185702).
  Auto-merge produced merge commit `49a7a12`.
- **Deviation:** the new post-merge `publish` job failed in three seconds with
  `fatal: not a git repository`. It had no checkout, so `gh pr view` could not
  resolve the PR before it ever waited. The documented fallback was used:
  `gh workflow run tag-release.yml --ref main`
  ([run](https://github.com/fluxion-dev/lazyplan/actions/runs/40209660006)) and
  `gh workflow run pages.yml --ref main`
  ([run](https://github.com/fluxion-dev/lazyplan/actions/runs/40209684224)).
- `tag-release` created annotated tag `v0.24.0` on `49a7a12` and dispatched
  `release.yml`; both the `release` and `publish-pypi` jobs succeeded:
  [run](https://github.com/fluxion-dev/lazyplan/actions/runs/40209672733).
- Fix forward before recording this entry: PR
  [#10](https://github.com/fluxion-dev/lazyplan/pull/10) added the checkout to
  the `publish` job, tolerated a transient `gh pr view` failure inside the
  wait loop, and documented the manual fallback. `gates` passed
  ([run](https://github.com/fluxion-dev/lazyplan/actions/runs/40210099506)) and
  it merged as `1f3a45d`.
- PyPI JSON lagged one poll of about 15 seconds; the simple index missed the
  first isolated install, then `pip install --no-cache-dir lazyplan-tui==0.24.0`
  printed `0.24.0`.
- Verified: seven release assets including `install.sh`, the isolated install,
  the deployed site showing 0.24.0 and the spinner copy, the source-trail WebP,
  canonical/FAQ/JSON-LD, sitemap (lastmod 2026-10-25), robots, and the release
  badge.
- The next release must prove the repaired `publish` job dispatches the tag and
  Pages without the manual fallback.

### v0.25.0 (2026-10-25)

- Minor bump from 0.24.0 with the **bump** workflow (`part=minor`):
  [run](https://github.com/fluxion-dev/lazyplan/actions/runs/40223852371).
  Porcelain mode is a user-visible agent feature, so this is a minor release.
- The release PR [#14](https://github.com/fluxion-dev/lazyplan/pull/14)
  changed only the version mirrors. GitHub left its `gates` run in
  `action_required`; the run was approved through the Actions API and passed:
  [run](https://github.com/fluxion-dev/lazyplan/actions/runs/40223863850).
  Auto-merge produced merge commit `e6dd3b9` and the `publish` job dispatched
  both `tag-release` and Pages without a manual fallback.
- `tag-release` created annotated tag `v0.25.0` on `e6dd3b9` and dispatched
  `release.yml` with no manual action:
  [tag-release](https://github.com/fluxion-dev/lazyplan/actions/runs/40225447378),
  [pages](https://github.com/fluxion-dev/lazyplan/actions/runs/40225448792).
  Both `release` and `publish-pypi` jobs succeeded:
  [run](https://github.com/fluxion-dev/lazyplan/actions/runs/40225459158).
- Local site verification used `bun install && bun run build` because this
  machine has no `npm`; the Pages workflow used its normal npm build and passed.
- PyPI JSON served 0.25.0 immediately, while the simple index missed two
  isolated installs before `pip install --no-cache-dir lazyplan-tui==0.25.0`
  printed `0.25.0` roughly two minutes after publish. That lag is expected.
- Verified: seven release assets including `install.sh`, the isolated install,
  the installed CLI exposing `--porcelain`, the deployed site showing 0.25.0
  and the porcelain copy, the source-trail WebP, canonical/FAQ/JSON-LD,
  sitemap (lastmod 2026-10-25), robots, and the social preview asset.
- No deviations from the release flow and no fix-forward commits.

### v0.26.0 (2026-10-26)

- Minor bump from 0.25.0 with the **bump** workflow (`part=minor`):
  [run](https://github.com/fluxion-dev/lazyplan/actions/runs/40345429021).
  This release shipped P87-P94: coordination, trace/lint, MCP, flow health,
  collaboration, gates, issue imports, and TUI search/bulk.
- The release PR [#27](https://github.com/fluxion-dev/lazyplan/pull/27)
  changed only the version mirrors. GitHub left its `ci` run in
  `action_required`; it was approved through the Actions API and `gates`
  passed: [run](https://github.com/fluxion-dev/lazyplan/actions/runs/40345466711).
- **Deviation:** auto-merge did not merge after approval, and the `publish` job
  timed out at 15:23:42 waiting for the PR
  ([run](https://github.com/fluxion-dev/lazyplan/actions/runs/40345429021)).
  The manual fallback merged PR #27 as `b1d92ee`. That human merge push started
  `tag-release` ([run](https://github.com/fluxion-dev/lazyplan/actions/runs/40350692192))
  and Pages ([run](https://github.com/fluxion-dev/lazyplan/actions/runs/40350692422));
  both succeeded. Duplicate manual dispatches of `tag-release`
  ([run](https://github.com/fluxion-dev/lazyplan/actions/runs/40350756178)) and
  Pages ([run](https://github.com/fluxion-dev/lazyplan/actions/runs/40350761134))
  were idempotent.
- `tag-release` created annotated tag `v0.26.0` on `b1d92ee` and dispatched
  `release.yml`; both `release` and `publish-pypi` jobs succeeded:
  [run](https://github.com/fluxion-dev/lazyplan/actions/runs/40350712250).
- PyPI JSON served 0.26.0 immediately. An isolated
  `pip install --no-cache-dir lazyplan-tui==0.26.0` printed `0.26.0`; smoke
  tests covered `next`, `stats`, an MCP initialize/tools-list session,
  `share`, `sync --help`, and `issue import --help`.
- Verified: seven release assets including `install.sh`, the isolated install,
  the deployed site showing 0.26.0, the new What's new and capability sections,
  all 11 new screenshots plus the refreshed hero and social card, canonical,
  FAQ/JSON-LD, sitemap (lastmod 2026-10-26), robots, and the curated release
  notes. Lighthouse on the built site scored 99 performance and 100 for
  accessibility, best practices, and SEO; Playwright confirmed no horizontal
  overflow at 360, 768, and 1440 widths.
- Follow-up for the next release: approve the release PR within the 20-minute
  publish window, or expect to merge and dispatch manually. No other
  deviations and no fix-forward commits.
