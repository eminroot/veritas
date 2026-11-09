import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";
import { SETTINGS, destinationsFor, isLive, type Destination } from "./nav";

/**
 * The navigation rail — MuhAI's: a column of icons, each with its name underneath. The
 * live tile is one lime element that springs between destinations (shared layoutId), so
 * a click reads as travelling. Organisation pages appear only for organisation accounts.
 */
export function RailItem({
  d,
  live,
  badge,
  layoutId,
  onClick,
}: {
  d: Destination;
  live: boolean;
  badge?: number;
  layoutId: string;
  onClick?: () => void;
}) {
  const navigate = useNavigate();
  const Icon = d.icon;
  // A modified click stays with the browser, so any destination can still be opened in
  // a new tab.
  const follow = (event: React.MouseEvent) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    onClick?.();
    navigate(d.to);
  };
  return (
    <a
      href={d.to}
      onClick={follow}
      className={`rail__item${live ? " is-live" : ""}`}
      aria-current={live ? "page" : undefined}
      data-tour={d.tour}
    >
      <span className="rail__tile">
        {live && (
          <motion.span
            layoutId={layoutId}
            className="rail__fill"
            aria-hidden="true"
            transition={{ type: "spring", stiffness: 520, damping: 40, mass: 0.8 }}
          />
        )}
        <Icon size={19} strokeWidth={1.5} />
        {badge ? <span className="rail__badge tnum">{badge > 99 ? "99+" : badge}</span> : null}
      </span>
      <span className="rail__label">{d.short || d.label}</span>
    </a>
  );
}

export default function SideRail() {
  const { pathname } = useLocation();
  const { accountType } = useAuth();

  return (
    <nav className="rail" aria-label="Primary" data-tour="nav">
      <div className="rail__group">
        {destinationsFor(accountType).map((d) => (
          <RailItem key={d.to} d={d} live={isLive(pathname, d)} layoutId="rail-live" />
        ))}
      </div>
      <span className="rail__rule" aria-hidden="true" />
      <div className="rail__group rail__group--foot">
        <RailItem d={SETTINGS} live={isLive(pathname, SETTINGS)} layoutId="rail-live" />
      </div>
    </nav>
  );
}
