import React, { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { MoreHorizontal } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { SETTINGS, destinationsFor, isLive } from "./nav";
import { RailItem } from "./SideRail";

/**
 * Below 860px the rail is gone and navigation moves to the foot of the window: four
 * destinations in a row and "More" for the rest, as a sheet. The tiles are the rail's
 * own, so the lime "you are here" mark looks and behaves identically on a phone.
 */
const PRIMARY = ["/dashboard", "/donations", "/donate", "/map"];

export default function MobileBar() {
  const { pathname } = useLocation();
  const { accountType } = useAuth();
  const [sheet, setSheet] = useState(false);

  useEffect(() => setSheet(false), [pathname]);

  const all = destinationsFor(accountType);
  const primary = all.filter((d) => PRIMARY.includes(d.to));
  const rest = [...all.filter((d) => !PRIMARY.includes(d.to)), SETTINGS];
  const moreLive = rest.some((d) => isLive(pathname, d));

  return (
    <>
      <nav className="mobilebar" aria-label="Primary" data-tour="nav">
        <div className="mobilebar__row">
          {primary.map((d) => (
            <RailItem key={d.to} d={d} live={isLive(pathname, d)} layoutId="mobile-live" />
          ))}
          <button className={`rail__item${moreLive ? " is-live" : ""}`} onClick={() => setSheet(true)} aria-label="More destinations">
            <span className="rail__tile">
              {moreLive && <motion.span layoutId="mobile-live" className="rail__fill" aria-hidden="true" />}
              <MoreHorizontal size={19} strokeWidth={1.5} />
            </span>
            <span className="rail__label">More</span>
          </button>
        </div>
      </nav>

      <AnimatePresence>
        {sheet && (
          <>
            <motion.div
              className="sheet-scrim"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, pointerEvents: "none" }}
              onClick={() => setSheet(false)}
            />
            <motion.div
              className="sheet"
              role="dialog"
              aria-label="All destinations"
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={{ type: "spring", stiffness: 420, damping: 40 }}
            >
              <div className="sheet__grip" />
              <div className="sheet__grid">
                {rest.map((d) => (
                  <RailItem key={d.to} d={d} live={isLive(pathname, d)} layoutId="sheet-live" onClick={() => setSheet(false)} />
                ))}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
