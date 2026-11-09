import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, X } from "lucide-react";
import { Arrow } from "@/components/lp/primitives";

/* ============================================================
   The guided tour.

   The first time someone opens the site — and again the first time they
   land in the console — an animated welcome plays and then a spotlight
   walks them through what is what: the page dims, a lime ring settles on
   one thing at a time, and a card beside it says what it is for.

   A tour is a list of steps. A step either has an `intro` (a full-screen
   splash, the animated part) or a `target`: a CSS selector, resolved to the
   first *visible* match so the same step can point at the rail on a laptop
   and at the bottom bar on a phone. A target that cannot be found shows the
   card centred over a plain dim rather than failing.

   "Done" is remembered per tour in localStorage, so it plays once; a skip
   counts as done. Every entry point that replays it (the console's help
   button, the landing footer) calls `start()` directly and ignores that.

   Motion is the console's: a short entrance, then stillness. The ring and
   the hole move on one spring so they never drift apart, and everything
   honours reduced motion through the app's MotionConfig.
   ============================================================ */

export type TourStep = {
  id: string;
  /** CSS selector; the first visible match is spotlit. */
  target?: string;
  title: string;
  body: React.ReactNode;
  icon?: React.ElementType;
  placement?: "top" | "bottom" | "left" | "right" | "auto";
  /** A full-screen animated splash instead of a spotlight. */
  intro?: (controls: IntroControls) => React.ReactNode;
  /** "console" lays the splash over a frosted app instead of the page ground. */
  splash?: "page" | "console";
  /** Extra room around the target, in px. */
  pad?: number;
  radius?: number;
  /** Label for the primary button on this step. */
  next?: string;
};

export type IntroControls = { next: () => void; skip: () => void; total: number };

export type TourDef = {
  id: string;
  version: number;
  steps: TourStep[];
  /** The pages the tour belongs to. The provider lives above the router's
   *  pages, so without this a tour started in the console kept playing over
   *  /onboarding (the redirect a new account gets) or the landing page after
   *  signing out. Leaving the scope closes it without marking it seen. */
  scope?: (pathname: string) => boolean;
};

type Ctx = { start: (tour: TourDef) => void; active: boolean };
const TourContext = createContext<Ctx>({ start: () => {}, active: false });
export const useTour = () => useContext(TourContext);

const storageKey = (t: TourDef) => `bb.tour.${t.id}.v${t.version}`;

export function tourDone(t: TourDef): boolean {
  try {
    return window.localStorage.getItem(storageKey(t)) === "done";
  } catch {
    // Storage blocked (private mode, a sandboxed preview): play nothing
    // automatically rather than ambushing every page load.
    return true;
  }
}

function markDone(t: TourDef) {
  try {
    window.localStorage.setItem(storageKey(t), "done");
  } catch {
    /* nothing to remember it in */
  }
}

/** Plays `tour` once, `delay` ms after mount, unless it has been seen. */
export function useFirstVisitTour(tour: TourDef, delay = 900, enabled = true) {
  const { start } = useTour();
  useEffect(() => {
    if (!enabled || tourDone(tour)) return;
    const timer = window.setTimeout(() => start(tour), delay);
    return () => window.clearTimeout(timer);
  }, [tour, delay, enabled, start]);
}

export function TourProvider({ children }: { children: React.ReactNode }) {
  const [tour, setTour] = useState<TourDef | null>(null);
  const [index, setIndex] = useState(0);
  const { pathname } = useLocation();
  const path = useRef(pathname);
  path.current = pathname;

  const start = useCallback((t: TourDef) => {
    // A delayed first-visit start can fire after a redirect has already
    // moved the user somewhere the tour has nothing to point at.
    if (t.scope && !t.scope(path.current)) return;
    setIndex(0);
    setTour(t);
  }, []);

  useEffect(() => {
    if (tour?.scope && !tour.scope(pathname)) setTour(null);
  }, [pathname, tour]);

  const finish = useCallback(() => {
    setTour((t) => {
      if (t) markDone(t);
      return null;
    });
  }, []);

  const value = useMemo(() => ({ start, active: !!tour }), [start, tour]);

  return (
    <TourContext.Provider value={value}>
      {children}
      {typeof document !== "undefined" &&
        createPortal(
          <AnimatePresence>
            {tour && (
              <TourLayer
                key={tour.id}
                tour={tour}
                index={index}
                setIndex={setIndex}
                onFinish={finish}
              />
            )}
          </AnimatePresence>,
          document.body
        )}
    </TourContext.Provider>
  );
}

/* ---------------------------------------------------------- geometry -- */

type Box = { x: number; y: number; w: number; h: number };

function visibleMatch(selector: string): HTMLElement | null {
  const all = document.querySelectorAll<HTMLElement>(selector);
  for (const el of all) {
    const r = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    if (r.width > 0 && r.height > 0 && style.visibility !== "hidden" && style.display !== "none") return el;
  }
  return null;
}

function sameBox(a: Box | null, b: Box | null) {
  if (!a || !b) return a === b;
  return Math.abs(a.x - b.x) < 0.5 && Math.abs(a.y - b.y) < 0.5 && Math.abs(a.w - b.w) < 0.5 && Math.abs(a.h - b.h) < 0.5;
}

const MARGIN = 14;
const GAP = 16;

function placeCard(
  hole: Box | null,
  card: { w: number; h: number },
  vw: number,
  vh: number,
  preferred: TourStep["placement"]
): { x: number; y: number; side: "top" | "bottom" | "left" | "right" | "center" } {
  if (!hole) return { x: (vw - card.w) / 2, y: (vh - card.h) / 2, side: "center" };

  const room = {
    bottom: vh - (hole.y + hole.h) - GAP - MARGIN,
    top: hole.y - GAP - MARGIN,
    right: vw - (hole.x + hole.w) - GAP - MARGIN,
    left: hole.x - GAP - MARGIN,
  };
  const fits = {
    bottom: room.bottom >= card.h,
    top: room.top >= card.h,
    right: room.right >= card.w,
    left: room.left >= card.w,
  };
  const order: ("bottom" | "top" | "right" | "left")[] =
    preferred && preferred !== "auto"
      ? [preferred, "bottom", "top", "right", "left"]
      : ["bottom", "top", "right", "left"];
  const side = order.find((s) => fits[s]);

  const clampX = (x: number) => Math.max(MARGIN, Math.min(x, vw - card.w - MARGIN));
  const clampY = (y: number) => Math.max(MARGIN, Math.min(y, vh - card.h - MARGIN));
  const cx = hole.x + hole.w / 2;
  const cy = hole.y + hole.h / 2;

  switch (side) {
    case "bottom":
      return { x: clampX(cx - card.w / 2), y: hole.y + hole.h + GAP, side };
    case "top":
      return { x: clampX(cx - card.w / 2), y: hole.y - GAP - card.h, side };
    case "right":
      return { x: hole.x + hole.w + GAP, y: clampY(cy - card.h / 2), side };
    case "left":
      return { x: hole.x - GAP - card.w, y: clampY(cy - card.h / 2), side };
    default:
      // Nothing fits beside it (a target taller than the window): sit over
      // the lower part of the screen, where a long target usually continues.
      return { x: clampX(cx - card.w / 2), y: clampY(vh - card.h - MARGIN * 2), side: "center" };
  }
}

/* ------------------------------------------------------------- layer -- */

const SPRING = { type: "spring", stiffness: 260, damping: 32, mass: 0.9 } as const;

function TourLayer({
  tour,
  index,
  setIndex,
  onFinish,
}: {
  tour: TourDef;
  index: number;
  setIndex: (n: number) => void;
  onFinish: () => void;
}) {
  const step = tour.steps[index];
  const total = tour.steps.length;
  const isLast = index === total - 1;
  const spotSteps = tour.steps.filter((s) => !s.intro);
  const spotIndex = spotSteps.indexOf(step);

  const [hole, setHole] = useState<Box | null>(null);
  const [vp, setVp] = useState({ w: window.innerWidth, h: window.innerHeight });
  const [cardSize, setCardSize] = useState({ w: 360, h: 220 });
  const [ready, setReady] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);

  const next = useCallback(() => (isLast ? onFinish() : setIndex(index + 1)), [isLast, onFinish, setIndex, index]);
  const back = useCallback(() => index > 0 && setIndex(index - 1), [index, setIndex]);

  // Resolve, scroll to, then follow the target every frame. Following is
  // what keeps the ring on a sticky header or a card that is still
  // assembling from its scroll animation.
  useLayoutEffect(() => {
    setReady(false);
    if (step.intro) {
      setHole(null);
      return;
    }
    let raf = 0;
    let settleTimer = 0;
    let last: Box | null = null;
    const pad = step.pad ?? 8;

    const el = step.target ? visibleMatch(step.target) : null;
    if (el) {
      const r = el.getBoundingClientRect();
      const offscreen = r.top < 76 || r.bottom > window.innerHeight - 24;
      if (offscreen) el.scrollIntoView({ behavior: "smooth", block: r.height > window.innerHeight * 0.7 ? "start" : "center" });
    }

    const tick = () => {
      const target = step.target ? visibleMatch(step.target) : null;
      let box: Box | null = null;
      if (target) {
        const r = target.getBoundingClientRect();
        box = { x: r.left - pad, y: r.top - pad, w: r.width + pad * 2, h: r.height + pad * 2 };
      }
      if (!sameBox(box, last)) {
        last = box;
        setHole(box);
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
    // Let a smooth scroll get most of the way before the card commits to a
    // side; it repositions anyway, but a card that jumps sides mid-scroll
    // reads as broken.
    settleTimer = window.setTimeout(() => setReady(true), el ? 380 : 60);

    const onResize = () => setVp({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(settleTimer);
      window.removeEventListener("resize", onResize);
    };
  }, [step]);

  useLayoutEffect(() => {
    const el = cardRef.current;
    if (!el) return;
    const measure = () => setCardSize({ w: el.offsetWidth, h: el.offsetHeight });
    measure();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    ro?.observe(el);
    return () => ro?.disconnect();
  }, [step]);

  useEffect(() => {
    if (ready) nextRef.current?.focus({ preventScroll: true });
  }, [ready, index]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onFinish();
      else if (!step.intro && (e.key === "ArrowRight" || e.key === "Enter")) {
        e.preventDefault();
        next();
      } else if (!step.intro && e.key === "ArrowLeft") back();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, next, back, onFinish]);

  const narrow = vp.w < 640;
  const placed = placeCard(hole, cardSize, vp.w, vp.h, step.placement);
  const radius = step.radius ?? 16;
  const Icon = step.icon;

  if (step.intro) {
    return (
      <motion.div
        className={"tour-splash" + (step.splash === "console" ? " tour-splash--console" : "")}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0, transition: { duration: 0.25 } }}
        transition={{ duration: 0.35 }}
        role="dialog"
        aria-modal="true"
        aria-label="Welcome"
      >
        {step.intro({ next, skip: onFinish, total: spotSteps.length })}
      </motion.div>
    );
  }

  return (
    <motion.div
      className="tour-layer"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.2 } }}
      transition={{ duration: 0.25 }}
    >
      {/* The dim, with a hole where the target is. */}
      <svg className="tour-dim" width="100%" height="100%" aria-hidden="true">
        <defs>
          <mask id="bb-tour-hole">
            <rect x="0" y="0" width="100%" height="100%" fill="white" />
            {hole && (
              <motion.rect
                initial={false}
                animate={{ x: hole.x, y: hole.y, width: hole.w, height: hole.h }}
                transition={SPRING}
                rx={radius}
                ry={radius}
                fill="black"
              />
            )}
          </mask>
        </defs>
        <rect x="0" y="0" width="100%" height="100%" fill="rgba(28, 28, 31, 0.56)" mask="url(#bb-tour-hole)" />
      </svg>

      {hole && (
        <motion.div
          className="tour-ring"
          initial={false}
          animate={{ left: hole.x, top: hole.y, width: hole.w, height: hole.h }}
          transition={SPRING}
          style={{ borderRadius: radius }}
        >
          <span key={step.id} className="tour-ring__pulse" style={{ borderRadius: radius }} />
        </motion.div>
      )}

      <motion.div
        ref={cardRef}
        className={"tour-card" + (narrow ? " is-docked" : "")}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        initial={narrow ? { opacity: 0, y: 10 } : { opacity: 0, x: placed.x, y: placed.y + 10, scale: 0.98 }}
        animate={
          narrow
            ? { opacity: ready ? 1 : 0, y: ready ? 0 : 10, scale: 1 }
            : { opacity: ready ? 1 : 0, x: placed.x, y: placed.y, scale: ready ? 1 : 0.98 }
        }
        transition={{ ...SPRING, opacity: { duration: 0.2 } }}
        style={narrow ? undefined : { left: 0, top: 0 }}
      >
        <div className="tour-card__top">
          {Icon ? (
            <span className="tour-card__icon">
              <Icon size={16} strokeWidth={1.6} />
            </span>
          ) : null}
          <span className="tour-card__count">
            {spotIndex + 1} of {spotSteps.length}
          </span>
          <button className="tour-card__close" onClick={onFinish} aria-label="Close the tour">
            <X size={15} />
          </button>
        </div>

        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={step.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.18 }}
          >
            <h2 id="tour-title" className="tour-card__title">
              {step.title}
            </h2>
            <div className="tour-card__body">{step.body}</div>
          </motion.div>
        </AnimatePresence>

        <div className="tour-card__dots" aria-hidden="true">
          {spotSteps.map((s, i) => (
            <i key={s.id} className={i === spotIndex ? "on" : i < spotIndex ? "done" : ""} />
          ))}
        </div>

        <div className="tour-card__acts">
          <button className="tour-card__skip" onClick={onFinish}>
            Skip tour
          </button>
          <span className="tour-card__gap" />
          {spotIndex > 0 && (
            <button className="tour-btn tour-btn--quiet" onClick={back} aria-label="Previous step">
              <ArrowLeft size={15} />
            </button>
          )}
          <button ref={nextRef} className="tour-btn" onClick={next}>
            <span>{step.next || (isLast ? "Finish" : "Next")}</span>
            <Arrow width={15} height={15} />
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
