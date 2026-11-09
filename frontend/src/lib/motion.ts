import type { Variants, Transition } from 'framer-motion'

/**
 * Shared motion language for the marketing surfaces.
 *
 * One easing curve and one distance scale everywhere — the thing that makes a site
 * feel authored rather than assembled is that everything moves the *same way*.
 * Components should import these rather than inventing per-section timings.
 */

/** Slight overshoot on the way out, hard settle. Reads as intentional, not springy. */
export const EASE_OUT: Transition['ease'] = [0.16, 1, 0.3, 1]
export const EASE_IN_OUT: Transition['ease'] = [0.65, 0, 0.35, 1]

/** Travel distances. Anything past ~32px starts to feel like the page is broken. */
export const RISE = 28

export const fadeRise: Variants = {
  hidden: { opacity: 0, y: RISE },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.7, ease: EASE_OUT },
  },
}

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.9, ease: EASE_OUT } },
}

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.94 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.8, ease: EASE_OUT },
  },
}

/**
 * Parent for staggered groups. Children must use `fadeRise` (or any variant keyed
 * hidden/visible) — the parent drives them, so children need no transition of their own.
 */
export function stagger(childDelay = 0.08, initialDelay = 0): Variants {
  return {
    hidden: {},
    visible: {
      transition: { staggerChildren: childDelay, delayChildren: initialDelay },
    },
  }
}

/** Standard viewport config: fire a bit before the element is fully on screen, once only. */
export const viewportOnce = { once: true, margin: '-80px' } as const

/**
 * Word-by-word reveal for display headings. Returns per-word variants; the caller
 * splits the string and renders each word in its own overflow-hidden span so the
 * words appear to rise out of the line rather than fade in place.
 */
export const wordRise: Variants = {
  hidden: { y: '110%' },
  visible: {
    y: 0,
    transition: { duration: 0.8, ease: EASE_OUT },
  },
}
