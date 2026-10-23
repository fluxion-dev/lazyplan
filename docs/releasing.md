# Releasing lazyplan

`pyproject.toml` is the single source of truth for the version. README, the man
page, `site/index.html`, and `site/package.json` mirror it; `tools/bump.sh`
updates all of them and `tests/test_version.py` fails on drift.

## Before tagging

1. Run `./tools/check.sh`. It must print `ALL GATES GREEN` on both
   interpreters.
2. Run `python3 tools/gen-man.py --check`.
3. Build a wheel and inspect the contents when the release changes packaging:

   ```bash
   python3 -m build --outdir /tmp/lazyplan-dist
   ```

4. Confirm the version is already correct everywhere:

   ```bash
   grep -n '^version = ' pyproject.toml
   head -1 README.md
   grep -n '"version"' site/index.html site/package.json
   ```

5. Commit in reviewable slices, then push `main`. Do not tag a red commit.

## Publish

```bash
git push origin main
gh run watch            # ci + pages must be green
git tag -a vX.Y.Z -m "lazyplan vX.Y.Z"
git push origin vX.Y.Z
gh run watch            # release.yml builds assets, GitHub release, PyPI
```

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

Also check that the deployed site shows the new version, the new copy, and
working screenshots:

```bash
curl -fsSL https://fluxion-dev.github.io/lazyplan/ | grep -E '0\.X\.Y|init --check|doctor'
```

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
