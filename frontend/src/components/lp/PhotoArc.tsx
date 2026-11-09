import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { MapPin } from "lucide-react";
import { causeOf } from "@/data/causes";
import { PROJECTS, goalOf, raisedOf, type Project } from "@/data/projects";
import { manat, percentOf } from "@/lib/money";

/**
 * The curved photo strip: real-world causes on cards that bend away from the middle, as
 * if laid around the inside of a cylinder. The strip drifts slowly sideways, wrapping
 * round, and stops while a card is hovered or focused; under reduced motion it stays
 * still. Each card is a sample project and opens it.
 *
 * Positions are written straight onto each card's style from one animation frame loop:
 * no React render per frame.
 */
const PICK = ["absheron-trees", "baku-shelter", "sabirabad-homes", "agdash-water", "ganja-day-centre", "guba-recycling", "shaki-school-roof"];

const SPEED = 0.045; // cards per second
const SPREAD = 1.02; // card widths between card centres: a sliver of space between cards

export default function PhotoArc() {
  const items: Project[] = PICK.map((id) => PROJECTS.find((p) => p.id === id)).filter(Boolean) as Project[];
  const n = items.length;
  const strip = useRef<HTMLDivElement>(null);
  const cards = useRef<(HTMLAnchorElement | null)[]>([]);
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    const el = strip.current;
    if (!el) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    let phase = 0;
    let last = performance.now();
    let raf = 0;

    const place = () => {
      const w = el.clientWidth;
      // Card width follows the strip: larger cards on wide screens, about 70% of a phone.
      const card = Math.min(420, Math.max(220, w * (w < 640 ? 0.66 : 0.3)));
      cards.current.forEach((c, i) => {
        if (!c) return;
        // Offset from the middle, wrapped into -n/2..n/2 so the strip loops.
        let o = (((i - phase) % n) + n) % n;
        if (o > n / 2) o -= n;
        const x = o * card * SPREAD;
        // Laid round the outside of a drum: a card's outer edge turns away from the
        // viewer, so the cards left of the middle turn one way and those right the other.
        const rot = Math.max(-50, Math.min(50, o * 17));
        const z = -Math.abs(o) * Math.abs(o) * 30;
        const fade = Math.max(0, 1 - Math.max(0, Math.abs(o) - 1.6) * 0.9);
        c.style.width = `${card}px`;
        c.style.transform = `translate3d(calc(-50% + ${x}px), -50%, ${z}px) rotateY(${rot}deg)`;
        c.style.opacity = String(fade);
        c.style.zIndex = String(100 - Math.round(Math.abs(o) * 10));
        c.style.pointerEvents = fade < 0.35 ? "none" : "auto";
        c.tabIndex = fade < 0.35 ? -1 : 0;
      });
    };

    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (!pausedRef.current) phase = (phase + dt * SPEED * 2) % n;
      place();
      raf = requestAnimationFrame(tick);
    };

    place();
    if (!reduce) raf = requestAnimationFrame(tick);
    const onResize = () => place();
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
    };
  }, [n]);

  return (
    <div
      className="v-arc"
      ref={strip}
      onPointerEnter={() => setPaused(true)}
      onPointerLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      data-tour="lp-arc"
      aria-label="Projects being funded now"
      role="region"
    >
      {items.map((p, i) => {
        const cause = causeOf(p.cause);
        const goal = goalOf(p);
        const raised = raisedOf(p);
        return (
          <Link
            key={p.id}
            to={`/projects/${p.id}`}
            className="v-arc__card"
            ref={(el) => (cards.current[i] = el)}
            aria-label={`${p.title}, ${manat(raised)} raised of ${manat(goal)}`}
          >
            <img src={p.photo} alt="" loading={i < 3 ? "eager" : "lazy"} draggable={false} />
            <span className="v-arc__shade" aria-hidden="true" />
            <span className="v-arc__info" aria-hidden="true">
              {cause ? (
                <span className="v-arc__cause">
                  <cause.icon />
                  {cause.label}
                </span>
              ) : null}
              <span className="v-arc__title">{p.title}</span>
              <span className="v-arc__meta">
                <MapPin />
                {p.place} · {manat(raised)} raised
              </span>
              <span className="v-arc__bar">
                <i style={{ width: `${percentOf(raised, goal)}%` }} />
              </span>
            </span>
          </Link>
        );
      })}
    </div>
  );
}
