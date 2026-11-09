import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Leaf } from "lucide-react";

/* ============================================================
   The landing page's primitives — the arrow, the chip button, the
   eyebrow pill, the reveal and the count-up.

   Ported from MuhAI's `components/ui/lp.jsx` and `pages/Landing.jsx`.
   They live here rather than inside the landing page because the auth
   screens, About, Pricing and the legal pages render the same design
   language, and a second copy of the chip button would drift from the
   first the first time either was touched. Every rule they read is in
   `styles/landing.css`, so anything rendering them sits inside `.lp`.
   ============================================================ */

/** The arrow drawn across the whole 24 grid — x 3 to 21, 1.5 stroke. Lucide's
 *  ArrowRight is inset to 5 → 19 and reads stubby beside the chip. */
export function Arrow(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      className="lucide"
      viewBox="0 0 24 24"
      width="24"
      height="24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M3 12h18m0 0-7-7m7 7-7 7" />
    </svg>
  );
}

type BtnProps = {
  to?: string;
  href?: string;
  type?: "submit" | "button";
  label: React.ReactNode;
  variant?: "" | "lime" | "quiet" | "ghost";
  size?: "" | "sm" | "lg" | "wide";
  icon?: React.ElementType;
  onClick?: (e: React.MouseEvent) => void;
  className?: string;
  disabled?: boolean;
} & Omit<React.HTMLAttributes<HTMLElement>, "onClick" | "className">;

/**
 * The signature control: a pill with a lime chip pinned inside it that sweeps
 * the label into view on hover. A `<Link>` by default, an `<a>` with `href`, a
 * real `<button>` with `type` — a form submit must stay a button or Enter does
 * nothing.
 */
export function Btn({
  to,
  href,
  type,
  label,
  variant = "",
  size = "",
  icon: Icon = Arrow,
  onClick,
  className = "",
  ...rest
}: BtnProps) {
  const cls = ["lp-btn", variant && "lp-btn--" + variant, size && "lp-btn--" + size, className]
    .filter(Boolean)
    .join(" ");

  /* The label renders twice on purpose: the copy inside the chip is what the
     sweep reveals, the outer one fades out under it. The duplicate is hidden
     from assistive tech. */
  const inner = (
    <>
      <span className="lp-btn__chip" aria-hidden="true">
        <span>{label}</span>
        <i className="lp-btn__ico">
          <Icon />
        </i>
      </span>
      <span className="lp-btn__ghost" aria-hidden="true" />
      <span className="lp-btn__label">{label}</span>
    </>
  );

  if (type) {
    return (
      <button className={cls} type={type} onClick={onClick} {...(rest as React.ButtonHTMLAttributes<HTMLButtonElement>)}>
        {inner}
      </button>
    );
  }
  if (href) {
    return (
      <a className={cls} href={href} onClick={onClick} {...(rest as React.AnchorHTMLAttributes<HTMLAnchorElement>)}>
        {inner}
      </a>
    );
  }
  return (
    <Link className={cls} to={to || "/signup"} onClick={onClick} {...(rest as React.AnchorHTMLAttributes<HTMLAnchorElement>)}>
      {inner}
    </Link>
  );
}

export function Eyebrow({
  icon: Icon = Leaf,
  tone = "",
  children,
}: {
  icon?: React.ElementType;
  tone?: "" | "flat" | "dark";
  children: React.ReactNode;
}) {
  return (
    <span className={"lp-eyebrow" + (tone ? " lp-eyebrow--" + tone : "")}>
      <span className="lp-eyebrow__ico">
        <Icon />
      </span>
      {children}
    </span>
  );
}

/* ============================================================
   Reveal.

   One IntersectionObserver for the whole page, opening each element once.
   Every revealed element starts at opacity 0, so the open state lives in
   React (a class the observer wrote onto the node would be wiped by the
   next render of a parent, and the element would fade back out for good).
   Opens immediately when the API is missing or the element is already on
   screen.
   ============================================================ */
const REVEAL_MARGIN: IntersectionObserverInit = { rootMargin: "0px 0px -12% 0px", threshold: 0.01 };
let revealIO: IntersectionObserver | null = null;
const revealJobs = new WeakMap<Element, () => void>();

export function onReveal(el: Element, fire: () => void) {
  if (typeof IntersectionObserver === "undefined") {
    fire();
    return undefined;
  }
  if (!revealIO) {
    revealIO = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return;
        const job = revealJobs.get(e.target);
        revealIO!.unobserve(e.target);
        revealJobs.delete(e.target);
        job?.();
      });
    }, REVEAL_MARGIN);
  }
  revealJobs.set(el, fire);
  revealIO.observe(el);
  return () => {
    revealIO?.unobserve(el);
    revealJobs.delete(el);
  };
}

type RvProps = {
  as?: React.ElementType;
  y?: number;
  delay?: number;
  now?: boolean;
  className?: string;
  children?: React.ReactNode;
  style?: React.CSSProperties;
} & Omit<React.HTMLAttributes<HTMLElement>, "className" | "style">;

export function Rv({ as: As = "div", y, delay = 0, now = false, className = "", children, style, ...rest }: RvProps) {
  const ref = useRef<HTMLElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (shown) return undefined;
    if (now) {
      setShown(true);
      return undefined;
    }
    const el = ref.current;
    if (!el) return undefined;
    const r = el.getBoundingClientRect();
    if (r.top < window.innerHeight && r.bottom > 0) {
      setShown(true);
      return undefined;
    }
    // Fail open: an observer that never fires must not leave a blank section.
    const backstop = window.setTimeout(() => setShown(true), 4000);
    const off = onReveal(el, () => setShown(true));
    return () => {
      window.clearTimeout(backstop);
      off?.();
    };
  }, [shown, now]);

  // The reveal's delay and distance ride in as CSS custom properties.
  const s: Record<string, string | number> = { ...((style as Record<string, string | number>) || {}) };
  if (delay) s["--rv-d"] = delay + "ms";
  if (y != null) s["--rv-y"] = y + "px";

  return (
    <As {...rest} ref={ref} style={s as React.CSSProperties} className={"lp-rv " + className + (shown ? " is-in" : "")}>
      {children}
    </As>
  );
}

/* ============================================================
   Scroll progress, written into a CSS variable rather than React state,
   so the scroll handler never renders and transforms stay on the
   compositor. Custom properties inherit, so descendants read the same --p.
   ============================================================ */
export const clamp01 = (n: number) => (n < 0 ? 0 : n > 1 ? 1 : n);
export const smooth = (n: number) => n * n * (3 - 2 * n);

export function useScrollVar(
  ref: React.RefObject<HTMLElement>,
  map: (rect: DOMRect, vh: number) => number,
  name = "--p"
) {
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof window === "undefined") return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      el.style.setProperty(name, "1");
      return;
    }
    let raf = 0;
    const write = () => {
      raf = 0;
      el.style.setProperty(name, map(el.getBoundingClientRect(), window.innerHeight).toFixed(4));
    };
    const onScroll = () => {
      if (!raf) raf = window.requestAnimationFrame(write);
    };
    write();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      if (raf) window.cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [ref, map, name]);
}

/** The nav pill inverts over the dark bands, switching at the band edge rather
 *  than at a scroll offset, so resizing a section cannot desynchronise it. */
export function useNavTone(rootRef: React.RefObject<HTMLElement>, setDark: (v: boolean) => void) {
  useEffect(() => {
    const root = rootRef.current;
    if (!root || typeof window === "undefined") return;
    const bands = [...root.querySelectorAll(".lp-dark")];
    if (!bands.length) return;
    let raf = 0;
    let last: boolean | null = null;
    const line = 40;
    const read = () => {
      raf = 0;
      const over = bands.some((b) => {
        const r = b.getBoundingClientRect();
        return r.top <= line && r.bottom >= line;
      });
      if (over !== last) {
        last = over;
        setDark(over);
      }
    };
    const onScroll = () => {
      if (!raf) raf = window.requestAnimationFrame(read);
    };
    read();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      if (raf) window.cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [rootRef, setDark]);
}

/* ============================================================
   Count-up. A figure already at its final value when it scrolls into
   frame is just text; these arrive. Under reduced motion the value is
   simply there — never a frozen zero.
   ============================================================ */
const still = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function useInOnce<T extends HTMLElement = HTMLDivElement>(): [React.RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (on) return undefined;
    const el = ref.current;
    if (!el) return undefined;
    const r = el.getBoundingClientRect();
    if (r.top < window.innerHeight && r.bottom > 0) {
      setOn(true);
      return undefined;
    }
    return onReveal(el, () => setOn(true));
  }, [on]);
  return [ref, on];
}

const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

export function useCount(to: number, on: boolean, ms = 1100) {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!on) return undefined;
    if (still()) {
      setN(to);
      return undefined;
    }
    let raf = 0;
    const t0 = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - t0) / ms);
      setN(to * easeOut(t));
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    // A tab that is not painting never runs a frame; land on the value anyway.
    const settle = window.setTimeout(() => setN(to), ms + 80);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(settle);
    };
  }, [to, on, ms]);
  return n;
}

const nf = new Intl.NumberFormat("en-US");

export function Count({ to, on, pre = "", post = "", ms }: { to: number; on: boolean; pre?: string; post?: string; ms?: number }) {
  const n = useCount(to, on, ms);
  return (
    <span style={{ fontVariantNumeric: "tabular-nums" }}>
      {pre}
      {nf.format(Math.round(n))}
      {post}
    </span>
  );
}
