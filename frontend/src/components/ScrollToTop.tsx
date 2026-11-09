import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { DESTINATIONS, SETTINGS } from "@/components/layout/nav";

/** Pages drawn inside the console frame (AppLayout). Give and the map are in the console's
 *  navigation too, but they are public pages in the site's own frame. */
const CONSOLE = [...DESTINATIONS, SETTINGS].filter((d) => !d.publicPage).map((d) => d.to);
const inConsole = (pathname: string) => CONSOLE.some((p) => pathname === p || pathname.startsWith(p + "/"));

/**
 * Every page opens at the top. Without this, a page opened from far down another one keeps
 * that scroll position, cut to its own height: a shorter page opens at its footer.
 *
 * Between two console pages AppLayout does it instead, once the old page has faded out;
 * doing it here as well would jump the page that is still on screen.
 */
export default function ScrollToTop() {
  const { pathname } = useLocation();
  const previous = useRef(pathname);

  useEffect(() => {
    const from = previous.current;
    previous.current = pathname;
    if (from !== pathname && inConsole(from) && inConsole(pathname)) return;
    window.scrollTo({ top: 0, left: 0, behavior: "instant" as ScrollBehavior });
  }, [pathname]);

  return null;
}
