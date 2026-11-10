"use client"

import { useEffect, useRef, type ReactNode } from "react"
import { cn } from "cn"

type RevealProps = Readonly<{
  children: ReactNode
  className?: string
  delay?: number
}>

const VIEWPORT_MARGIN = 0.12
const CLEANUP_MS = 800

export function Reveal({ children, className, delay = 0 }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const node = ref.current
    if (!node) {
      return
    }
    node.style.setProperty("--reveal-delay", `${delay}ms`)
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return
    }
    if (node.getBoundingClientRect().top <= window.innerHeight * (1 - VIEWPORT_MARGIN)) {
      return
    }

    node.setAttribute("data-reveal", "pending")
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) {
            continue
          }
          node.classList.add("is-visible")
          observer.disconnect()
          window.setTimeout(() => {
            node.removeAttribute("data-reveal")
            node.classList.remove("is-visible")
          }, CLEANUP_MS)
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.12 }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [delay])

  return (
    <div ref={ref} className={cn(className)}>
      {children}
    </div>
  )
}
