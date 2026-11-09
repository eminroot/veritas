import React from "react";
import { motion } from "framer-motion";
import {
  Bell,
  Building2,
  Camera,
  Check,
  Compass,
  HandHeart,
  LayoutDashboard,
  LayoutGrid,
  Layers,
  Lock,
  Map as MapIcon,
  MessagesSquare,
  Receipt,
  Rocket,
  Search,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { Arrow } from "@/components/lp/primitives";
import { useAuth } from "@/contexts/AuthContext";
import { sumDonations, useMyDonations } from "@/hooks/useAccount";
import { manat } from "@/lib/money";
import { DESTINATIONS, SETTINGS, isLive } from "@/components/layout/nav";
import type { IntroControls, TourDef } from "./Tour";

const EASE = [0.16, 1, 0.3, 1] as const;

/** Focus the primary button once, without scrolling to it: `autoFocus` scrolled a tall
 *  splash down and hid its top behind the window edge. */
const focusOnce = (el: HTMLButtonElement | null) => {
  if (el && !el.dataset.focused) {
    el.dataset.focused = "1";
    el.focus({ preventScroll: true });
  }
};

/* ============================================================
   The landing splash — the animated welcome a first-time visitor sees.

   The wordmark assembles letter by letter, one line says what Veritas is,
   and three cards rise to say how — each with a small drawing that moves
   once: gifts stack up, the escrow fills, the checks tick. Then the two
   choices. Entrance only; nothing loops.
   ============================================================ */

function LandingIntro({ next, skip, total }: IntroControls) {
  const word = "Veritas".split("");
  const cards = [
    {
      icon: HandHeart,
      title: "Give",
      body: "To a verified organisation's project: a school roof, a well, a shelter.",
      art: (
        <>
          {[30, 44, 52, 66, 72, 88, 96].map((h, i) => (
            <motion.i
              key={i}
              className={"tsp__bar" + (i === 6 ? " is-hi" : "")}
              initial={{ height: "8%" }}
              animate={{ height: `${h}%` }}
              transition={{ duration: 0.9, ease: EASE, delay: 1.55 + i * 0.05 }}
            />
          ))}
        </>
      ),
    },
    {
      icon: Lock,
      title: "Held in escrow",
      body: "Your money waits, split across the project's milestones, until the work is done.",
      art: (
        <div className="tsp__meter">
          {[
            [100, "#9db45f"],
            [100, "#6aa5e0"],
            [46, "#c9d3e0"],
          ].map(([w, c], i) => (
            <span key={i}>
              <motion.i
                style={{ background: c as string }}
                initial={{ width: "0%" }}
                animate={{ width: `${w}%` }}
                transition={{ duration: 1.1, ease: EASE, delay: 1.7 + i * 0.12 }}
              />
            </span>
          ))}
        </div>
      ),
    },
    {
      icon: Camera,
      lime: true,
      title: "Released on proof",
      body: "Photos from the site are checked before a single manat reaches the builder.",
      art: (
        <div className="tsp__lines">
          {[64, 92, 78].map((w, i) => (
            <motion.i
              key={i}
              initial={{ width: "0%" }}
              animate={{ width: `${w}%` }}
              transition={{ duration: 0.7, ease: "easeOut", delay: 1.85 + i * 0.22 }}
            />
          ))}
        </div>
      ),
    },
  ];

  return (
    <div className="tsp">
      <motion.span
        className="tsp__eyebrow"
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EASE, delay: 0.1 }}
      >
        <i />
        Welcome, it's your first visit
      </motion.span>

      <h1 className="tsp__word" aria-label="Veritas">
        {word.map((ch, i) => (
          <motion.span
            key={i}
            aria-hidden="true"
            initial={{ opacity: 0, y: "55%", rotate: 8, filter: "blur(10px)" }}
            animate={{ opacity: 1, y: "0%", rotate: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.8, ease: EASE, delay: 0.25 + i * 0.055 }}
          >
            {ch}
          </motion.span>
        ))}
      </h1>

      <motion.p
        className="tsp__lead"
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: EASE, delay: 0.95 }}
      >
        Giving you can see through: every donation waits in escrow and is released only when the work is proven.
      </motion.p>

      <div className="tsp__cards">
        {cards.map((c, i) => (
          <motion.div
            key={c.title}
            className="tsp__card"
            initial={{ opacity: 0, y: 34, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.8, ease: EASE, delay: 1.25 + i * 0.12 }}
          >
            <div className="tsp__card-top">
              <span className={"tsp__card-icon" + (c.lime ? " is-lime" : "")}>
                <c.icon size={17} />
              </span>
              <span className="tsp__card-step">0{i + 1}</span>
            </div>
            <b>{c.title}</b>
            <p>{c.body}</p>
            <div className="tsp__card-art" aria-hidden="true">
              {c.art}
            </div>
          </motion.div>
        ))}
      </div>

      <motion.div
        className="tsp__acts"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: EASE, delay: 2.15 }}
      >
        <button className="tour-btn" style={{ height: 48, padding: "0 20px", fontSize: 15 }} onClick={next} ref={focusOnce}>
          <span>Show me around</span>
          <Arrow width={16} height={16} />
        </button>
        <button className="tsp__skip" onClick={skip}>
          Skip, I'll explore myself
        </button>
      </motion.div>
      <motion.p
        className="tsp__hint"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6, delay: 2.5 }}
      >
        {total} quick stops · about a minute · press Esc to leave
      </motion.p>
    </div>
  );
}

/* ============================================================
   The console welcome — the first time someone signs in.

   A dark panel with where the person's money is, drawn as three arcs
   (released, in escrow, refunded) that sweep in and count up, and on the
   right what the tour will cover.
   ============================================================ */

const SHARES = [
  { key: "released", label: "Released", color: "#9db45f" },
  { key: "inEscrow", label: "In escrow", color: "#6aa5e0" },
  { key: "refunded", label: "Refunded", color: "#e0c5b6" },
] as const;

function MoneyRing() {
  const { rows } = useMyDonations();
  const t = sumDonations(rows);
  const r = 78;
  const c = 2 * Math.PI * r;
  const gap = t.given > 0 ? 8 : 0;
  let offset = 0;
  const [shown, setShown] = React.useState(0);

  React.useEffect(() => {
    let raf = 0;
    const t0 = performance.now();
    const step = (now: number) => {
      const k = Math.min(1, (now - t0) / 1400);
      setShown(t.given * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(step);
    };
    const start = window.setTimeout(() => (raf = requestAnimationFrame(step)), 450);
    const settle = window.setTimeout(() => setShown(t.given), 2000);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(start);
      window.clearTimeout(settle);
    };
  }, [t.given]);

  return (
    <div className="tsc__ringwrap">
      <svg viewBox="0 0 200 200" width="220" height="220" aria-hidden="true">
        <circle cx="100" cy="100" r={r} fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="12" />
        {SHARES.map((s, i) => {
          const part = t[s.key];
          if (!t.given || !part) return null;
          // Each share owns its part of the circle: the ring never shows money that is not there.
          const len = Math.max(0, (c * part) / t.given - gap);
          const rot = (offset / c) * 360 - 90;
          offset += (c * part) / t.given;
          return (
            <g key={s.key} transform={`rotate(${rot} 100 100)`}>
              <motion.circle
                cx="100"
                cy="100"
                r={r}
                fill="none"
                stroke={s.color}
                strokeWidth="12"
                strokeLinecap="round"
                initial={{ strokeDasharray: `0 ${c}` }}
                animate={{ strokeDasharray: `${len} ${c}` }}
                transition={{ duration: 1.2, ease: EASE, delay: 0.45 + i * 0.18 }}
              />
            </g>
          );
        })}
      </svg>
      <div className="tsc__ringval">
        <b>{manat(Math.round(shown / 100) * 100)}</b>
        <span>{t.given ? "Given so far" : "Nothing given yet"}</span>
      </div>
    </div>
  );
}

function ConsoleIntro({ next, skip, total }: IntroControls) {
  const { user } = useAuth();
  const name = user?.firstName || user?.email?.split("@")[0] || "there";
  const items = [
    "Where every donation of yours is now",
    "How escrow, release and refunds work",
    "Finding a cause and the donation map",
    "Search, updates and this tour",
  ];
  return (
    <motion.div
      className="tsc"
      initial={{ opacity: 0, y: 24, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.6, ease: EASE }}
    >
      <div className="tsc__art">
        <MoneyRing />
        <div className="tsc__legend">
          {SHARES.map((s) => (
            <span key={s.key}>
              <i style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      </div>
      <div className="tsc__body">
        <motion.span className="tsc__hello" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
          Welcome, {name}
        </motion.span>
        <motion.h2
          className="tsc__title"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EASE, delay: 0.25 }}
        >
          This is your Veritas account.
        </motion.h2>
        <motion.p
          className="tsc__sub"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EASE, delay: 0.35 }}
        >
          A {total}-step tour of what is where, about a minute. Every manat you give is tracked here, from escrow to the
          builder.
        </motion.p>
        <ul className="tsc__list">
          {items.map((t, i) => (
            <motion.li
              key={t}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.45, ease: EASE, delay: 0.55 + i * 0.1 }}
            >
              <i>
                <Check strokeWidth={2.4} />
              </i>
              {t}
            </motion.li>
          ))}
        </ul>
        <motion.div
          className="tsc__acts"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 1.0 }}
        >
          <button className="tour-btn" style={{ height: 44 }} onClick={next} ref={focusOnce}>
            <span>Start the tour</span>
            <Arrow width={15} height={15} />
          </button>
          <button className="tsp__skip" onClick={skip}>
            I'll explore on my own
          </button>
        </motion.div>
      </div>
    </motion.div>
  );
}

/* ============================================================
   The tours.
   ============================================================ */

export const LANDING_TOUR: TourDef = {
  id: "landing",
  version: 1,
  scope: (path) => path === "/",
  steps: [
    { id: "intro", title: "Welcome", body: null, intro: (c) => <LandingIntro {...c} /> },
    {
      id: "nav",
      target: '[data-tour="lp-nav"]',
      icon: Compass,
      title: "Find your way",
      body: "Jump to how Veritas works, the donation map, organisations and the FAQ. The bar follows you and turns dark over dark sections.",
      radius: 24,
    },
    {
      id: "cta",
      target: '[data-tour="lp-cta"]',
      icon: HandHeart,
      title: "Give in a minute",
      body: "Pick a cause, pick a project, choose an amount. Every organisation you can give to has been checked by Veritas first.",
      radius: 20,
    },
    {
      id: "stage",
      target: '[data-tour="lp-stage"]',
      icon: LayoutDashboard,
      title: "Where the money is, at a glance",
      body: "Raised, in escrow and released, the donors behind it and every milestone's status. Keep scrolling and the cards assemble into place.",
      placement: "top",
      radius: 24,
      pad: 6,
    },
    {
      id: "arc",
      target: '[data-tour="lp-arc"]',
      icon: Layers,
      title: "Real places, real work",
      body: "Schools, wells, shelters and homes being built right now. Each one is split into milestones you can follow.",
      radius: 24,
    },
    {
      id: "how",
      target: '[data-tour="lp-how"]',
      icon: Workflow,
      title: "How it works, in three moves",
      body: "You give, the money waits in escrow, and photos from the site release it. The sentence lights up as you scroll.",
      radius: 20,
    },
    {
      id: "slabs",
      target: '[data-tour="lp-slab"]',
      icon: ShieldCheck,
      title: "Each step, up close",
      body: "Giving, escrow, the evidence checks and the release or refund. Four cards that stack as you scroll.",
      radius: 24,
    },
    {
      id: "bento",
      target: '[data-tour="lp-bento"]',
      icon: LayoutGrid,
      title: "Everything in the open",
      body: "Fundraising in real time, thousands of small gifts, on-chain proof, votes and refunds: nothing is hidden from donors.",
      radius: 24,
    },
    {
      id: "map",
      target: '[data-tour="lp-map"]',
      icon: MapIcon,
      title: "See where the money goes",
      body: "Every region of Azerbaijan, shaded by what donors gave there in the last 30 days. Hover a region, or click a pin to open its project.",
      radius: 24,
    },
    {
      id: "orgs",
      target: '[data-tour="lp-orgs"]',
      icon: Building2,
      title: "Raising money for a project?",
      body: "Registered organisations apply, get verified and publish projects. Individuals cannot fundraise on Veritas.",
      radius: 20,
    },
    {
      id: "faq",
      target: '[data-tour="lp-faq"]',
      icon: MessagesSquare,
      title: "Questions, answered",
      body: "Donating, escrow and refunds, organisations and payments, grouped by topic on the left.",
      radius: 24,
    },
    {
      id: "start",
      target: '[data-tour="lp-nav-start"]',
      icon: Rocket,
      title: "Ready when you are",
      body: "Donate from here. You can replay this tour any time from the link in the footer.",
      radius: 14,
      next: "Finish",
    },
  ],
};

export const APP_TOUR: TourDef = {
  id: "console",
  version: 1,
  scope: (path) => [...DESTINATIONS, SETTINGS].some((d) => isLive(path, { ...d, end: false })),
  steps: [
    { id: "intro", title: "Welcome", body: null, splash: "console", intro: (c) => <ConsoleIntro {...c} /> },
    {
      id: "nav",
      target: '[data-tour="nav"]',
      icon: Compass,
      title: "Your navigation",
      body: "Everything lives in this rail. The lime tile marks where you are, and slides with you as you move.",
      radius: 14,
      pad: 4,
      placement: "right",
    },
    {
      id: "nav-dashboard",
      target: '[data-tour="nav-dashboard"]',
      icon: LayoutGrid,
      title: "Dashboard",
      body: "What you have given, how much is still in escrow, how much has been released, and news from your projects.",
      placement: "right",
      pad: 4,
      radius: 14,
    },
    {
      id: "nav-donations",
      target: '[data-tour="nav-donations"]',
      icon: Receipt,
      title: "My donations",
      body: "Every gift with its receipt, split into released, in escrow and refunded, so you can see each manat's state.",
      placement: "right",
      pad: 4,
      radius: 14,
    },
    {
      id: "nav-give",
      target: '[data-tour="nav-give"]',
      icon: HandHeart,
      title: "Give",
      body: "Browse causes and verified organisations' projects, and give to the next milestone.",
      placement: "right",
      pad: 4,
      radius: 14,
    },
    {
      id: "nav-map",
      target: '[data-tour="nav-map"]',
      icon: MapIcon,
      title: "The donation map",
      body: "Every project on a map of Azerbaijan, region by region.",
      placement: "right",
      pad: 4,
      radius: 14,
    },
    {
      id: "search",
      target: '[data-tour="search"]',
      icon: Search,
      title: "Search everything",
      body: (
        <>
          Jump to any page, cause or project by name. Press <kbd>/</kbd> from anywhere to focus it.
        </>
      ),
      radius: 22,
      pad: 4,
    },
    {
      id: "escrow",
      target: '[data-tour="escrow"]',
      icon: Lock,
      title: "Your money in escrow",
      body: "What you have given that is still waiting for proof. It goes to the builder only when a milestone is approved, or back to you if the project stops.",
      radius: 20,
      pad: 4,
    },
    {
      id: "alerts",
      target: '[data-tour="alerts"]',
      icon: Bell,
      title: "Updates",
      body: "New evidence, approvals and payments on the projects you gave to land here.",
      radius: 22,
      pad: 4,
    },
    {
      id: "help",
      target: '[data-tour="help"]',
      icon: Compass,
      title: "Replay any time",
      body: "This tour lives here. That's everything. You're ready.",
      radius: 22,
      pad: 4,
      next: "Done",
    },
  ],
};
