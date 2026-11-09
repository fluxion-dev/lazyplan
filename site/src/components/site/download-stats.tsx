import { useEffect, useState } from "react"
import { cn } from "cn"

import { Card, CardContent } from "@/components/ui/card"

type Snapshot = Readonly<{
  available: boolean
  schema: number
  generated_at: string
  channels?: Readonly<{
    pypi_with_mirrors?: Readonly<{
      available: boolean
      total: number
    }>
  }>
}>

type Stats = Readonly<{ downloads: string; updated: string }>

const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000
const DOWNLOADS_URL = `${import.meta.env.BASE_URL}downloads.json`

function readStats(data: Snapshot | null): Stats | null {
  if (!data || data.available !== true || data.schema !== 2) {
    return null
  }
  const stamp = Date.parse(data.generated_at)
  if (!Number.isFinite(stamp)) {
    return null
  }
  const age = Date.now() - stamp
  if (age < 0 || age > MAX_AGE_MS) {
    return null
  }
  const pypi = data.channels?.pypi_with_mirrors
  if (!pypi || pypi.available !== true || !Number.isInteger(pypi.total) || pypi.total < 0) {
    return null
  }
  return {
    downloads: new Intl.NumberFormat("en-US").format(pypi.total),
    updated: new Date(stamp).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }),
  }
}

export function DownloadStats() {
  const [stats, setStats] = useState<Stats | null>(null)

  useEffect(() => {
    let active = true
    fetch(DOWNLOADS_URL, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) {
          throw new Error("missing downloads snapshot")
        }
        return response.json() as Promise<Snapshot>
      })
      .then((data) => {
        if (active) {
          setStats(readStats(data))
        }
      })
      .catch(() => {
        if (active) {
          setStats(null)
        }
      })
    return () => {
      active = false
    }
  }, [])

  return (
    <Card
      id="download-stats"
      aria-label="Downloads"
      className={cn(
        "mx-auto mt-8 max-w-md border-border bg-card/60",
        !stats && "hidden"
      )}
    >
      <CardContent className="text-center">
        <p className="mb-0 text-xs font-semibold tracking-[0.14em] text-muted-foreground uppercase">
          Downloads
        </p>
        <p className="mt-1 mb-0 text-3xl font-bold text-foreground">
          <span id="stats-downloads">{stats?.downloads ?? "—"}</span>
        </p>
        <p className="mt-2 mb-0 text-xs text-muted-foreground">
          Updated <span id="stats-updated">{stats?.updated ?? "—"}</span> · How we
          count: channels are reported separately, never added.
        </p>
      </CardContent>
    </Card>
  )
}
