import React, { useEffect } from "react";
import { useLocation, useOutlet } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import SideRail from "./SideRail";
import Topbar from "./Topbar";
import MobileBar from "./MobileBar";
import { useFirstVisitTour } from "@/components/tour/Tour";
import { APP_TOUR } from "@/components/tour/tours";

// The document is what scrolls, so without this a new page opened at the
// previous page's scroll position. Called once the old page has faded and
// before the new one appears; "instant" because html scrolls smoothly.
const toTop = () => window.scrollTo({ top: 0, left: 0, behavior: "instant" as ScrollBehavior });

/**
 * The console frame — MuhAI's: the rail on the left, a flush top bar, and
 * the page under it with a short fade between pages. Pages render only
 * their content (`.page`), never their own navigation.
 *
 * The transition is keyed on the path, so every page fades and opens at the
 * top, the organisation's profile and its projects included.
 */
export default function AppLayout() {
  const location = useLocation();
  // The outlet element captured at this render. The page fading out keeps
  // the element it was rendered with; a live <Outlet/> inside it would
  // swap to the *new* page for the length of the exit animation.
  const outlet = useOutlet();

  useFirstVisitTour(APP_TOUR, 1300);

  // Back and forward too: left to the browser, it restores the old position
  // on the page that is still fading out — a visible jump before ours.
  useEffect(() => {
    const previous = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";
    return () => {
      window.history.scrollRestoration = previous;
    };
  }, []);

  return (
    <div className="app-shell">
      <SideRail />
      <div className="main-col">
        <Topbar />
        <AnimatePresence mode="wait" onExitComplete={toTop}>
          <motion.main
            key={location.pathname}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.18, ease: [0.22, 0.8, 0.3, 1] }}
          >
            {outlet}
          </motion.main>
        </AnimatePresence>
      </div>
      <MobileBar />
    </div>
  );
}
