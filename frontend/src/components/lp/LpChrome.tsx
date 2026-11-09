import React, { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Menu, Play, X } from "lucide-react";
import { Btn, Rv, useNavTone } from "./primitives";
import { useTour } from "@/components/tour/Tour";
import { LANDING_TOUR } from "@/components/tour/tours";
import { useAuth } from "@/contexts/AuthContext";

/* ============================================================
   The public pages' frame — MuhAI's nav pill and footer, through BestByte.

   The pill floats over the page, turns white once the page moves and dark
   over the dark bands (the `.lp-dark` sections, read live by `useNavTone`).
   The footer ends in the oversized wordmark, clipped by the page edge.
   Every public page renders inside `LpPage`, so the landing, the causes,
   projects, the map and the legal pages share one frame.
   ============================================================ */

type NavLink = [href: string, label: string];

const SITE_LINKS: NavLink[] = [
  ["/donate", "Causes"],
  ["/how-it-works", "How it works"],
  ["/map", "Map"],
  ["/organisations", "For organisations"],
  ["/about", "About"],
];

const FOOT = [
  {
    h: "Give",
    items: [
      ["All causes", "/donate"],
      ["Donation map", "/map"],
      ["How it works", "/how-it-works"],
    ],
  },
  {
    h: "Organisations",
    items: [
      ["Register an organisation", "/signup?as=organisation"],
      ["How verification works", "/organisations"],
    ],
  },
  {
    h: "Veritas",
    items: [
      ["About", "/about"],
    ],
  },
  {
    h: "Legal",
    items: [
      ["Terms", "/terms"],
      ["Privacy", "/privacy"],
    ],
  },
];

function NavAnchor({ href, label, onClick }: { href: string; label: string; onClick?: () => void }) {
  // In-page anchors stay anchors (smooth scroll); routes go through the router.
  if (href.startsWith("#") || href.startsWith("mailto:")) {
    return (
      <a href={href} onClick={onClick}>
        {label}
      </a>
    );
  }
  return (
    <Link to={href} onClick={onClick}>
      {label}
    </Link>
  );
}

export function useReplayLandingTour() {
  const { start } = useTour();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  return () => {
    if (pathname !== "/") navigate("/");
    window.scrollTo({ top: 0, behavior: "smooth" });
    window.setTimeout(() => start(LANDING_TOUR), pathname === "/" ? 350 : 700);
  };
}

export function LpPage({
  children,
  links = SITE_LINKS,
}: {
  children: React.ReactNode;
  links?: NavLink[];
}) {
  const page = useRef<HTMLDivElement>(null);
  const [stuck, setStuck] = useState(false);
  const [navDark, setNavDark] = useState(false);
  const [menu, setMenu] = useState(false);
  const replay = useReplayLandingTour();
  const { user } = useAuth();

  useNavTone(page, setNavDark);

  useEffect(() => {
    const onScroll = () => setStuck(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // The drawer owns the scroll lock while it is open.
  useEffect(() => {
    if (!menu) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [menu]);

  const account = user ? (["/dashboard", "Dashboard"] as const) : (["/login", "Log in"] as const);

  return (
    <div className="lp" ref={page}>
      <div className={"lp-navwrap" + (stuck ? " is-stuck" : "") + (navDark ? " is-dark" : "")}>
        <Rv as="nav" y={-56} now className="lp-nav" data-tour="lp-nav">
          <Link className="lp-nav__brand" to="/">
            Veritas
          </Link>
          <div className="lp-nav__links">
            {links.map(([href, label]) => (
              <NavAnchor key={href} href={href} label={label} />
            ))}
          </div>
          <div className="lp-nav__right">
            <button className="lp-burger" onClick={() => setMenu(true)} aria-label="Open menu">
              <Menu style={{ width: 18, height: 18 }} />
            </button>
            <Link className="lp-nav__login" to={account[0]}>
              {account[1]}
            </Link>
            <span data-tour="lp-nav-start" style={{ display: "inline-flex" }}>
              <Btn to="/donate" label="Donate" size="sm" />
            </span>
          </div>
        </Rv>
      </div>

      <div className={"lp-drawer" + (menu ? " is-open" : "")} aria-hidden={!menu}>
        <div className="lp-drawer__top">
          <Link className="lp-nav__brand" to="/" onClick={() => setMenu(false)}>
            Veritas
          </Link>
          <button className="lp-burger" onClick={() => setMenu(false)} aria-label="Close menu">
            <X style={{ width: 18, height: 18 }} />
          </button>
        </div>
        <div className="lp-drawer__body">
          {links.map(([href, label]) => (
            <NavAnchor key={href} href={href} label={label} onClick={() => setMenu(false)} />
          ))}
          <Link to={account[0]} onClick={() => setMenu(false)}>
            {account[1]}
          </Link>
          <div className="lp-drawer__foot">
            <Btn to="/donate" label="Donate" onClick={() => setMenu(false)} />
          </div>
        </div>
      </div>

      {children}

      <footer className="lp-foot">
        <div className="lp-shell">
          <div className="lp-foot__grid">
            <div className="lp-foot__brand">
              <Link className="lp-nav__brand" to="/">
                Veritas
              </Link>
              <p>Giving you can see through. Every donation waits in escrow until photos from the site prove the work is done.</p>
              <button className="lp-tourlink" onClick={replay} style={{ alignSelf: "flex-start" }}>
                <i>
                  <Play />
                </i>
                Replay the tour
              </button>
            </div>
            {FOOT.map((c) => (
              <div className="lp-foot__col" key={c.h}>
                <h4>{c.h}</h4>
                {c.items.map(([label, href]) => (
                  <Link key={label} to={href}>
                    {label}
                  </Link>
                ))}
              </div>
            ))}
          </div>
          <div className="lp-foot__mark" aria-hidden="true">
            <span>Veritas</span>
          </div>
          <div className="lp-foot__bar">
            <p>© {new Date().getFullYear()} Veritas. The organisations and projects shown before launch are samples.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}

/** The tinted band at the top of a public subpage: eyebrow, title, lead. */
export function LpHero({
  eyebrow,
  title,
  lead,
  children,
  wide = false,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  lead?: React.ReactNode;
  children?: React.ReactNode;
  /** Let the title run wider than 16 characters. */
  wide?: boolean;
}) {
  return (
    <header className="lp-hero" style={{ paddingBottom: 96 }}>
      <div className="lp-shell">
        <div className="lp-hero__head">
          {eyebrow ? <Rv y={30}>{eyebrow}</Rv> : null}
          <Rv as="h1" y={48} delay={60} className="lp-d1 lp-hero__title" style={{ maxWidth: wide ? "22ch" : "16ch" }}>
            {title}
          </Rv>
          {lead ? (
            <Rv as="p" y={60} delay={120} className="lp-lead lp-hero__lead">
              {lead}
            </Rv>
          ) : null}
          {children ? (
            <Rv y={70} delay={180} className="lp-hero__cta">
              {children}
            </Rv>
          ) : null}
        </div>
      </div>
    </header>
  );
}
