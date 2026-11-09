import React from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { EASE_OUT, RISE } from '@/lib/motion'

/**
 * Scroll-triggered reveal primitives.
 *
 * Two deliberate constraints here, both learned the hard way on this codebase:
 *
 * 1. No `whileInView`, and no variant-name propagation from parent to child. Both were
 *    tried and both left real copy stranded at opacity 0 — the parent never resolved
 *    its variant, so every child inherited `hidden` forever and the page rendered
 *    blank. Everything below animates with explicit object values and an explicit
 *    delay, which is the form that behaves consistently.
 *
 * 2. Reveals fail OPEN. `useReveal` shows content if the element is on screen at mount,
 *    if the observer fires, or if a short backstop timer elapses. Copy becoming visible
 *    is never contingent on animation machinery working.
 *
 * Reduced motion reduces rather than removes: opacity still transitions, positional
 * travel is dropped. `prefers-reduced-motion` is a common default (Windows "Show
 * animations" off, VMs, headless browsers), so that path must look finished, not inert.
 */

const REVEAL_FALLBACK_MS = 900

/**
 * Reveals replay every time an element enters the viewport, in either direction.
 *
 * The earlier version latched `shown` to true on first intersection and kept it there,
 * which meant a reveal fired once per mount and never again — scrolling back up and
 * down did nothing, and the page only looked animated straight after a refresh.
 * Tracking `isIntersecting` continuously makes the reveal symmetric: it plays coming
 * down the page and again coming back up.
 *
 * The observer is created once per element. `shown` is deliberately NOT a dependency:
 * including it would tear down and rebuild the observer on every intersection change,
 * which drops events mid-scroll.
 */
export function useReveal<T extends HTMLElement>(rootMargin = '-60px') {
  const ref = React.useRef<T>(null)
  const [shown, setShown] = React.useState(false)
  const observerFired = React.useRef(false)

  React.useEffect(() => {
    const node = ref.current

    if (!node || typeof IntersectionObserver === 'undefined') {
      setShown(true)
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        observerFired.current = true
        // Single observed node, so the last entry is the current state.
        setShown(entries[entries.length - 1].isIntersecting)
      },
      { rootMargin, threshold: 0 }
    )
    observer.observe(node)

    // Fail open: if the observer never reports at all, show the content rather than
    // leaving real copy stranded at opacity 0. Only applies when nothing has fired,
    // so it never fights a legitimate "scrolled out of view" state.
    const timer = window.setTimeout(() => {
      if (!observerFired.current) setShown(true)
    }, REVEAL_FALLBACK_MS)

    return () => {
      observer.disconnect()
      window.clearTimeout(timer)
    }
  }, [rootMargin])

  return { ref, shown }
}

interface RevealProps {
  children: React.ReactNode
  className?: string
  delay?: number
  /** Vertical travel in px. Ignored under reduced motion. */
  distance?: number
  as?: 'div' | 'section' | 'span'
}

export function Reveal({
  children,
  className,
  delay = 0,
  distance = RISE,
  as = 'div',
}: RevealProps) {
  const reduce = useReducedMotion()
  const { ref, shown } = useReveal<HTMLDivElement>()
  const Component = (as === 'span' ? motion.span : as === 'section' ? motion.section : motion.div) as typeof motion.div

  const from = { opacity: 0, y: reduce ? 0 : distance }
  const to = { opacity: 1, y: 0 }

  return (
    <Component
      ref={ref}
      className={className}
      initial={from}
      animate={shown ? to : from}
      transition={{
        duration: reduce ? 0.45 : 0.7,
        ease: EASE_OUT,
        delay: reduce ? Math.min(delay, 0.12) : delay,
      }}
    >
      {children}
    </Component>
  )
}

/** Injected by StaggerGroup so each item knows its position in the cascade. */
const StaggerContext = React.createContext<{ gap: number; delay: number; shown: boolean }>({
  gap: 0.08,
  delay: 0,
  shown: true,
})
const IndexContext = React.createContext(0)

interface StaggerGroupProps {
  children: React.ReactNode
  className?: string
  gap?: number
  delay?: number
  as?: 'div' | 'section'
}

export function StaggerGroup({
  children,
  className,
  gap = 0.08,
  delay = 0,
  as = 'div',
}: StaggerGroupProps) {
  const reduce = useReducedMotion()
  const { ref, shown } = useReveal<HTMLDivElement>()
  const Component = (as === 'section' ? motion.section : motion.div) as typeof motion.div

  // Index is handed down explicitly rather than relying on variant orchestration.
  const items = React.Children.map(children, (child, i) => (
    <IndexContext.Provider value={i}>{child}</IndexContext.Provider>
  ))

  return (
    <StaggerContext.Provider
      value={{ gap: reduce ? Math.min(gap, 0.04) : gap, delay: reduce ? 0 : delay, shown }}
    >
      <Component ref={ref} className={className}>
        {items}
      </Component>
    </StaggerContext.Provider>
  )
}

export function StaggerItem({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  const reduce = useReducedMotion()
  const { gap, delay, shown } = React.useContext(StaggerContext)
  const index = React.useContext(IndexContext)

  const from = { opacity: 0, y: reduce ? 0 : RISE }
  const to = { opacity: 1, y: 0 }

  return (
    <motion.div
      className={className}
      initial={from}
      animate={shown ? to : from}
      transition={{
        duration: reduce ? 0.4 : 0.65,
        ease: EASE_OUT,
        delay: delay + index * gap,
      }}
    >
      {children}
    </motion.div>
  )
}

/**
 * Display heading whose words rise out of the baseline. Under reduced motion the words
 * fade in place — no travel, and no clipping mask (the mask exists only to hide travel,
 * and would clip descenders without it).
 */
export function RisingWords({
  text,
  className,
  wordClassName,
  delay = 0,
}: {
  text: string
  className?: string
  wordClassName?: string
  delay?: number
}) {
  const reduce = useReducedMotion()
  const { ref, shown } = useReveal<HTMLSpanElement>()
  const words = text.split(' ')
  const gap = reduce ? 0.03 : 0.055

  return (
    <span ref={ref} className={className} aria-label={text}>
      {words.map((word, i) => (
        <span
          key={`${word}-${i}`}
          className={reduce ? 'inline-block' : 'inline-block overflow-hidden align-bottom'}
          aria-hidden="true"
        >
          <motion.span
            className={`inline-block ${wordClassName ?? ''}`}
            initial={reduce ? { opacity: 0 } : { y: '110%' }}
            animate={shown ? (reduce ? { opacity: 1 } : { y: 0 }) : reduce ? { opacity: 0 } : { y: '110%' }}
            transition={{
              duration: reduce ? 0.4 : 0.8,
              ease: EASE_OUT,
              delay: delay + i * gap,
            }}
          >
            {word}
            {i < words.length - 1 ? ' ' : ''}
          </motion.span>
        </span>
      ))}
    </span>
  )
}

/**
 * Counts to `value` once on screen. Counting digits are not positional motion, so this
 * runs under reduced motion too, just quicker.
 */
export function CountUp({
  value,
  decimals = 0,
  suffix = '',
  prefix = '',
  duration = 1.6,
  className,
}: {
  value: number
  decimals?: number
  suffix?: string
  prefix?: string
  duration?: number
  className?: string
}) {
  const reduce = useReducedMotion()
  const { ref, shown } = useReveal<HTMLSpanElement>('0px')
  const [display, setDisplay] = React.useState(0)
  const runDuration = reduce ? Math.min(duration, 0.8) : duration

  React.useEffect(() => {
    if (!shown) return
    let frame = 0
    let settled = false
    const t0 = performance.now()

    const tick = (now: number) => {
      const progress = Math.min((now - t0) / (runDuration * 1000), 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplay(value * eased)
      if (progress < 1) {
        frame = requestAnimationFrame(tick)
      } else {
        settled = true
      }
    }
    frame = requestAnimationFrame(tick)

    /**
     * Snap to the true figure if the ramp has not finished in time. This component
     * renders prices and emissions totals, and requestAnimationFrame is suspended in
     * background tabs, so without this the number can sit at 0 indefinitely and
     * advertise the wrong value. setTimeout still fires where rAF does not.
     */
    const settle = window.setTimeout(
      () => {
        if (!settled) setDisplay(value)
      },
      runDuration * 1000 + 400
    )

    return () => {
      cancelAnimationFrame(frame)
      window.clearTimeout(settle)
    }
  }, [shown, value, runDuration])

  return (
    <span ref={ref} className={className}>
      {prefix}
      {display.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
      {suffix}
    </span>
  )
}

export { EASE_OUT }
