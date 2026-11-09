import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { BadgeCheck, Camera, Check, Lock, MapPinned } from "lucide-react";
import { Btn } from "@/components/lp/primitives";

/**
 * The auth shell — the landing page's own language, one step in. Ported from MuhAI's
 * AuthShell through BestByte.
 *
 * The root is a `.lp` element on purpose: the wordmark, the nav pill, the chip button and
 * every token come from `styles/landing.css`. The card is the landing's slab geometry —
 * 8px of padding around two panels, dark on the left, the form on the right. Below 940px
 * the dark panel drops.
 */
const HIGHLIGHTS = [
  { icon: BadgeCheck, title: "Verified organisations", sub: "Every charity's registration, documents and director checked" },
  { icon: Lock, title: "Escrow, milestone by milestone", sub: "Your money waits until each part of the work is done" },
  { icon: Camera, title: "Paid on proof", sub: "Photos from the site, checked five ways, before a manat moves" },
  { icon: MapPinned, title: "Every gift on the map", sub: "Follow your projects, region by region" },
];

export default function AuthShell({
  title,
  subtitle,
  alt,
  solo = false,
  pitch,
  children,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  alt?: { to: string; quiet: string; cta: string };
  solo?: boolean;
  /** Replaces the dark panel's heading, e.g. for organisations. */
  pitch?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="lp lp-auth">
      <div className="lp-auth__nav">
        <nav className="lp-nav">
          <Link className="lp-nav__brand" to="/">
            Veritas
          </Link>
          <span className="lp-auth__gap" />
          <div className="lp-nav__right">
            {alt && (
              <>
                <Link className="lp-nav__login" to={alt.to}>
                  {alt.quiet}
                </Link>
                <Btn to={alt.to} label={alt.cta} size="sm" />
              </>
            )}
          </div>
        </nav>
      </div>

      <div className="lp-auth__body">
        <motion.div
          className={"lp-auth__card" + (solo ? " lp-auth__card--solo" : "")}
          initial={{ opacity: 0, y: 18, scale: 0.985 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
        >
          {!solo && (
            <aside className="lp-auth__pitch">
              <h2 className="lp-d5">{pitch ?? "Give where you can see every manat, from your card to the finished work."}</h2>
              <ul className="lp-auth__list">
                {HIGHLIGHTS.map((h, i) => (
                  <motion.li
                    key={h.title}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1], delay: 0.2 + i * 0.08 }}
                  >
                    <span className="lp-auth__mark">
                      <Check strokeWidth={2.2} />
                    </span>
                    <span>
                      <b>{h.title}</b>
                      <span>{h.sub}</span>
                    </span>
                  </motion.li>
                ))}
              </ul>
              <p className="lp-auth__foot">Veritas · transparent giving in Azerbaijan</p>
            </aside>
          )}

          <div className="lp-auth__form">
            <h1 className="lp-d4 lp-auth__title">{title}</h1>
            {subtitle ? <p className="lp-lead lp-auth__sub">{subtitle}</p> : null}
            {children}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
