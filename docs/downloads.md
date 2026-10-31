# Download counts

The landing page shows real download counts from two owners: PyPI and GitHub
releases. Each channel is labeled and rendered on its own. Nothing is estimated,
adjusted, or added across channels.

## Channels

| Channel | Source | Meaning |
| --- | --- | --- |
| PyPI downloads | pypistats `with_mirrors` | Package downloads across PyPI and its mirrors |
| Direct from PyPI | pypistats `without_mirrors` | Downloads served directly by PyPI |
| GitHub release assets | GitHub releases API | Downloads of `install.sh`, deb, rpm, wheel, and sdist assets |

The headline is the mirror-inclusive PyPI total because it is the broadest real
number we can source. The direct figure is shown beside it so the mirror share
is visible. GitHub asset downloads are a separate distribution channel and are
not added to either PyPI figure.

## Why the channels are not summed

PyPI and GitHub count different things. A person can install from PyPI and also
download a release asset, a mirror can serve the same file more than once, and
CI can install repeatedly. Adding the channels would produce a bigger number
with no honest meaning, so the page keeps them separate.

## Limits

- Counts include mirrors, CI, and repeat installs.
- Counts are not unique users or unique installs.
- Mirror aggregation depends on pypistats and can lag the PyPI index.
- GitHub asset counts include every asset type, including the wheel and sdist,
  not just `install.sh`.

These limits stay visible next to the strip and are the reason the page does not
print a single combined "installs" figure.

## How the snapshot is built

`tools/fetch-downloads.py` fetches both pypistats series and every GitHub release
page, then writes a versioned JSON snapshot:

```json
{
  "available": true,
  "schema": 2,
  "generated_at": "2026-10-31T00:00:00Z",
  "channels": {
    "pypi_with_mirrors": {"available": true, "total": 10004, "last_7_days": 3777, "source": "pypistats.org", "metric": "with_mirrors"},
    "pypi_direct": {"available": true, "total": 3252, "last_7_days": 1244, "source": "pypistats.org", "metric": "without_mirrors"},
    "github_assets": {"available": true, "total": 43, "artifacts": {}, "source": "api.github.com", "metric": "release_assets"}
  }
}
```

The Pages workflow runs the script before every build and on a daily schedule.
The snapshot is gitignored, so the deployed page always reflects the build that
produced it. If one channel fails, the others still render; if the snapshot is
missing, stale, malformed, or a different schema, the strip hides.

## Verify a number

```bash
python3 tools/fetch-downloads.py --out /tmp/downloads.json
curl -fsSL https://pypistats.org/api/packages/lazyplan-tui/overall
gh api repos/fluxion-dev/lazyplan/releases --paginate \
  --jq '[.[].assets[].download_count] | add'
```

Compare each channel with the matching source on the same date. Do not compare
the PyPI total with the GitHub total, and do not present their sum as installs.

## Policy

Counts are never inflated, estimated, or backfilled. If a source is unavailable,
the channel is marked unavailable and the page shows what it can prove. Caveats
are part of the feature, not copy to remove for a launch.
