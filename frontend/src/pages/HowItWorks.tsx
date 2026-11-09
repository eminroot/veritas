import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { MotionConfig, motion } from "framer-motion";
import {
  Banknote,
  BadgeCheck,
  Bot,
  Building2,
  Camera,
  Check,
  Copy,
  Database,
  Eye,
  FileCheck2,
  FileText,
  Fingerprint,
  Globe,
  HardHat,
  Hash,
  IdCard,
  Landmark,
  Link2,
  ListChecks,
  Lock,
  MapPin,
  Receipt,
  RotateCcw,
  ServerOff,
  ShieldCheck,
  Timer,
  Users,
  Vote,
} from "lucide-react";
import { LpHero, LpPage } from "@/components/lp/LpChrome";
import { EscrowMock, Float, RefundMock } from "@/components/lp/mocks";
import { Btn, Count, Eyebrow, Rv, useCount, useInOnce } from "@/components/lp/primitives";
import { SHOWCASE } from "@/data/sample-proof";
import "@/styles/how.css";

/**
 * How Veritas keeps a donation safe, as one flow: eight steps between a gift and a paid
 * builder, zig-zagging down the page and joined by arrows that draw themselves, each with a
 * visual that plays out what the step checks. Few words: the pictures carry it.
 */

/** Count up 1..n once `on`, one step every `every` ms: the visuals' sequences. */
function useSequence(on: boolean, n: number, every: number, start = 300): number {
  const [done, setDone] = useState(0);
  useEffect(() => {
    if (!on) return undefined;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setDone(n);
      return undefined;
    }
    const timers = Array.from({ length: n }, (_, i) => window.setTimeout(() => setDone(i + 1), start + every * i));
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [on, n, every, start]);
  return done;
}

const pop = { type: "spring" as const, stiffness: 380, damping: 20 };

type Item = { icon: React.ElementType; label: string };

/** Icon tiles in a row, lit one after another: the shape every checklist takes here. */
function Tiles({ items, done }: { items: Item[]; done: number }) {
  return (
    <div className={"hw-tiles" + (items.length > 4 ? " hw-tiles--many" : "")} style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}>
      {items.map((it, i) => (
        <div key={it.label} className={"hw-tile" + (i < done ? " is-done" : i === done ? " is-now" : "")}>
          <span className="hw-tile__ico">
            <it.icon />
            <i className="hw-tile__ok">
              <Check />
            </i>
          </span>
          <span className="hw-tile__t">{it.label}</span>
        </div>
      ))}
    </div>
  );
}

function Progress({ value }: { value: number }) {
  return (
    <span className="hw-progress" aria-hidden="true">
      <i style={{ width: `${Math.round(value * 100)}%` }} />
    </span>
  );
}

/** A short arrow down, with a dot running along it once `on`. */
function Down({ on }: { on: boolean }) {
  return (
    <span className={"hw-down" + (on ? " is-on" : "")} aria-hidden="true">
      <i />
    </span>
  );
}

/* ------------------------------------------------------------------ 1. the organisation */

const ORG: Item[] = [
  { icon: Landmark, label: "Registration" },
  { icon: Receipt, label: "VÖEN" },
  { icon: IdCard, label: "Director's ID" },
  { icon: Banknote, label: "Bank account" },
];

function OrgVisual() {
  const [ref, on] = useInOnce<HTMLDivElement>();
  const done = useSequence(on, ORG.length + 1, 600);
  const verified = done > ORG.length;
  return (
    <div ref={ref} className="hw-vis">
      <Float>
        <div className="lp-panel__top">
          <span className="v-mico v-mico--sm">
            <Building2 />
          </span>
          <div className="lp-panel__k" style={{ alignSelf: "center" }}>
            Organisation check
          </div>
          <span className={"lp-tag " + (verified ? "lp-tag--ok" : "lp-tag--warn")} style={{ marginLeft: "auto" }}>
            {verified ? "Verified" : "Checking"}
          </span>
        </div>
        <Tiles items={ORG} done={done} />
        <Progress value={Math.min(done, ORG.length) / ORG.length} />
        <motion.div
          className="hw-stamp"
          initial={{ opacity: 0, scale: 1.5, rotate: -16 }}
          animate={verified ? { opacity: 1, scale: 1, rotate: -6 } : { opacity: 0, scale: 1.5, rotate: -16 }}
          transition={pop}
        >
          <BadgeCheck /> Verified
        </motion.div>
      </Float>
    </div>
  );
}

/* ------------------------------------------------------------------ 2. the plan, sealed */

const PLAN: [string, number][] = [
  ["Old roof", 8_600],
  ["New roof", 24_400],
  ["Windows", 17_800],
  ["Heating", 12_200],
];
const HASH = "0x7c2f9a41e0b6d83c5f1a";

function SealVisual() {
  const [ref, on] = useInOnce<HTMLDivElement>();
  const stage = useSequence(on, 3, 1000, 200);
  const typed = Math.round(useCount(HASH.length, stage >= 2, 900));
  return (
    <div ref={ref} className="hw-vis">
      <Float>
        <div className="lp-panel__top">
          <span className="v-mico v-mico--sm">
            <FileCheck2 />
          </span>
          <div className="lp-panel__k" style={{ alignSelf: "center" }}>
            Project plan
          </div>
          <span className="lp-tag" style={{ marginLeft: "auto" }}>
            ₼63,000
          </span>
        </div>
        <div className="hw-budget">
          {PLAN.map(([t, amount], i) => (
            <motion.div
              key={t}
              className="hw-budget__seg"
              style={{ flexGrow: amount }}
              initial={{ opacity: 0, y: 8 }}
              animate={stage >= 1 ? { opacity: 1, y: 0 } : { opacity: 0, y: 8 }}
              transition={{ duration: 0.35, delay: i * 0.14 }}
            >
              <span className="hw-budget__bar" />
              <b>{t}</b>
              <em>₼{(amount / 1000).toFixed(1)}k</em>
            </motion.div>
          ))}
        </div>
        <Down on={stage >= 2} />
        <div className={"hw-hash" + (stage >= 2 ? " is-on" : "")}>
          <Fingerprint />
          <code>{stage >= 2 ? HASH.slice(0, typed) : "fingerprint"}</code>
        </div>
        <Down on={stage >= 3} />
        <div className="hw-chain">
          <span className="hw-block">#1041</span>
          <span className="hw-link" />
          <span className="hw-block">#1042</span>
          <span className="hw-link" />
          <motion.span
            className="hw-block hw-block--new"
            initial={{ opacity: 0, x: 30 }}
            animate={stage >= 3 ? { opacity: 1, x: 0 } : { opacity: 0, x: 30 }}
            transition={pop}
          >
            <Lock /> Sealed
          </motion.span>
        </div>
      </Float>
    </div>
  );
}

/* ------------------------------------------------------------------ 3. escrow */

const HOLD: [string, number][] = [
  ["Old roof", 100],
  ["New roof", 100],
  ["Windows", 64],
  ["Heating", 0],
];

function EscrowVisual() {
  const [ref, on] = useInOnce<HTMLDivElement>();
  return (
    <div ref={ref} className="hw-vis hw-stack">
      <EscrowMock />
      <Float>
        <div className="lp-panel__top">
          <div className="lp-panel__k">Held per milestone</div>
          <span className="lp-tag lp-tag--dark" style={{ marginLeft: "auto" }}>
            <Lock style={{ width: 12, height: 12 }} /> Locked
          </span>
        </div>
        <div className="hw-jars">
          {HOLD.map(([t, pct], i) => (
            <div key={t} className="hw-jar">
              <span className="hw-jar__glass">
                <motion.i initial={{ height: 0 }} animate={{ height: on ? `${pct}%` : 0 }} transition={{ duration: 1.1, delay: 0.3 + i * 0.15, ease: [0.16, 1, 0.3, 1] }} />
              </span>
              <b>{t}</b>
              <em>{pct === 100 ? "Full" : pct ? `${pct}%` : "Next"}</em>
            </div>
          ))}
        </div>
      </Float>
    </div>
  );
}

/* ------------------------------------------------------------------ 4. proof from the site */

const CAPTURED: Item[] = [
  { icon: MapPin, label: "In the site" },
  { icon: Hash, label: "Today's code" },
  { icon: Fingerprint, label: "Signed" },
];

function CaptureVisual() {
  const [ref, on] = useInOnce<HTMLDivElement>();
  const stage = useSequence(on, 4, 750, 350);
  return (
    <div ref={ref} className="hw-vis hw-capture">
      <div className="hw-phone" aria-hidden="true">
        <div className="hw-phone__screen">
          <img src="/img/proof/ganja-school/m2-shingles.jpg" alt="" loading="lazy" />
          <span className={"hw-flash" + (stage >= 1 ? " is-on" : "")} />
          <motion.span className="hw-code" initial={{ opacity: 0, y: 14, rotate: -2 }} animate={stage >= 2 ? { opacity: 1, y: 0, rotate: -5 } : { opacity: 0, y: 14, rotate: -2 }} transition={pop}>
            <small>Today's code</small>K7-4Q2
          </motion.span>
          <span className="hw-phone__bar">
            <Camera /> 09:41 · 40.68282, 46.36061
          </span>
        </div>
      </div>
      <Float className="hw-geo">
        <div className="lp-panel__top">
          <span className="v-mico v-mico--sm">
            <MapPin />
          </span>
          <div className="lp-panel__k" style={{ alignSelf: "center" }}>
            Site boundary
          </div>
        </div>
        <svg className="hw-geo__map" viewBox="0 0 200 120" aria-hidden="true">
          <defs>
            <pattern id="hw-grid" width="12" height="12" patternUnits="userSpaceOnUse">
              <path d="M12 0H0V12" fill="none" stroke="rgba(36,36,38,.07)" strokeWidth="1" />
            </pattern>
          </defs>
          <rect width="200" height="120" rx="10" fill="url(#hw-grid)" />
          <polygon points="46,22 150,16 172,74 120,104 38,92" className="hw-geo__fence" />
          <motion.g initial={{ opacity: 0, y: -24 }} animate={stage >= 3 ? { opacity: 1, y: 0 } : { opacity: 0, y: -24 }} transition={pop}>
            <circle cx="104" cy="60" r="14" className="hw-geo__acc" />
            <path d="M104 62c-6-8-9-12-9-16a9 9 0 0 1 18 0c0 4-3 8-9 16z" className="hw-geo__pin" />
            <circle cx="104" cy="46" r="3.2" fill="#fff" />
          </motion.g>
        </svg>
        <Tiles items={CAPTURED} done={Math.max(0, stage - 1)} />
      </Float>
    </div>
  );
}

/* ------------------------------------------------------------------ 5. eleven checks */

const AUTOMATIC: Item[] = [
  { icon: Fingerprint, label: "Untouched" },
  { icon: MapPin, label: "In the site" },
  { icon: Timer, label: "On time" },
  { icon: Copy, label: "Never used" },
  { icon: ListChecks, label: "Checklist" },
];
const BY_AI: Item[] = [
  { icon: Hash, label: "Code" },
  { icon: Bot, label: "Not AI-made" },
  { icon: Eye, label: "Shows work" },
  { icon: FileText, label: "Invoice" },
  { icon: Receipt, label: "Receipt" },
  { icon: HardHat, label: "Contractor" },
];

function ChecksVisual() {
  const [ref, on] = useInOnce<HTMLDivElement>();
  const total = AUTOMATIC.length + BY_AI.length;
  const done = useSequence(on, total, 260, 300);
  return (
    <div ref={ref} className="hw-vis">
      <Float>
        <div className="lp-panel__top">
          <span className="v-mico v-mico--sm">
            <ShieldCheck />
          </span>
          <div className="lp-panel__k" style={{ alignSelf: "center" }}>
            Check report
          </div>
          <span className={"lp-tag " + (done === total ? "lp-tag--ok" : "lp-tag--lime")} style={{ marginLeft: "auto" }}>
            {done}/{total}
          </span>
        </div>
        <p className="hw-group">Automatic</p>
        <Tiles items={AUTOMATIC} done={Math.min(done, AUTOMATIC.length)} />
        <p className="hw-group">
          <Bot /> AI, then the officer
        </p>
        <Tiles items={BY_AI} done={Math.max(0, done - AUTOMATIC.length)} />
        <Progress value={done / total} />
      </Float>
    </div>
  );
}

/* ------------------------------------------------------------------ 6. people decide */

function DecideVisual() {
  const [ref, on] = useInOnce<HTMLDivElement>();
  const stage = useSequence(on, 3, 1100, 300);
  const yes = useCount(91, stage >= 3, 1300);
  return (
    <div ref={ref} className="hw-vis">
      <Float>
        <div className="lp-panel__top">
          <span className="v-mico v-mico--sm">
            <BadgeCheck />
          </span>
          <div className="lp-panel__k" style={{ alignSelf: "center" }}>
            Independent officer
          </div>
          <span className={"lp-tag " + (stage >= 2 ? "lp-tag--ok" : "")} style={{ marginLeft: "auto" }}>
            {stage >= 2 ? "Approved" : "Reading"}
          </span>
        </div>
        <div className="hw-report">
          <Bot />
          <span>AI report: 11/11 passed</span>
        </div>
        <svg className="hw-sign" viewBox="0 0 260 60" aria-hidden="true">
          <motion.path
            d="M6 44c18-30 30-34 30-16 0 14-10 18-4 2 6-16 18-22 22-8 3 10-6 16 2 8 12-12 20-24 28-10 6 10 10 4 18-6 10-12 16-2 22 6 8 10 16-8 24-14 10-8 14 10 22 8s14-14 24-12c8 2 6 12 14 10 10-2 18-10 30-10"
            fill="none"
            stroke="#2b4ca0"
            strokeWidth="2.4"
            strokeLinecap="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: stage >= 2 ? 1 : 0 }}
            transition={{ duration: 1.1, ease: "easeInOut" }}
          />
          <line x1="4" y1="54" x2="256" y2="54" stroke="rgba(36,36,38,.15)" strokeDasharray="3 4" />
        </svg>
      </Float>
      <Down on={stage >= 3} />
      <Float>
        <div className="lp-panel__top">
          <span className="v-mico v-mico--sm">
            <Vote />
          </span>
          <div className="lp-panel__k" style={{ alignSelf: "center" }}>
            Donors vote, 72 hours
          </div>
        </div>
        <div className="v-vote" aria-hidden="true">
          <span className="v-vote__yes" style={{ width: `${yes}%` }}>
            Yes {Math.round(yes)}%
          </span>
          <span className="v-vote__no">{100 - Math.round(yes)}%</span>
        </div>
        <div className="hw-note">
          <Users /> One receipt, one vote
        </div>
      </Float>
    </div>
  );
}

/* ------------------------------------------------------------------ 7. paid, and on the record */

const LEDGER = ["Plan", "Proof", "Approval", "Vote", "Payment"];

function ReleaseVisual() {
  const [ref, on] = useInOnce<HTMLDivElement>();
  const stage = useSequence(on, LEDGER.length, 420, 900);
  return (
    <div ref={ref} className="hw-vis hw-stack">
      <Float>
        <div className="lp-panel__top">
          <div className="lp-panel__k" style={{ alignSelf: "center" }}>
            Released to the builder
          </div>
          <span className={"lp-tag " + (stage >= LEDGER.length ? "lp-tag--ok" : "lp-tag--dark")} style={{ marginLeft: "auto" }}>
            {stage >= LEDGER.length ? "Paid" : "Releasing"}
          </span>
        </div>
        <div className={"hw-pay" + (on ? " is-on" : "")} aria-hidden="true">
          <span className="hw-pay__node hw-pay__node--lock">
            <Lock />
            <em>Escrow</em>
          </span>
          <span className="hw-pay__wire">
            <i />
          </span>
          <span className="hw-pay__node">
            <HardHat />
            <em>Builder</em>
          </span>
        </div>
        <div className="lp-panel__big" style={{ paddingTop: 2 }}>
          <Count to={24_400} on={on} pre="₼" ms={1400} />
        </div>
      </Float>
      <div className="hw-ledger" aria-hidden="true">
        {LEDGER.map((l, i) => (
          <React.Fragment key={l}>
            {i ? <span className={"hw-link" + (i < stage ? " is-on" : "")} /> : null}
            <span className={"hw-block hw-block--sm" + (i < stage ? " is-on" : "")}>
              <Link2 />
              {l}
            </span>
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ 8. no single server */

const RING = Array.from({ length: 10 }, (_, i) => {
  const a = (i / 10) * Math.PI * 2 - Math.PI / 2;
  return { x: 100 + Math.cos(a) * 68, y: 78 + Math.sin(a) * 56 };
});

function NetworkVisual() {
  const [ref, on] = useInOnce<HTMLDivElement>();
  const stage = useSequence(on, 2, 1500, 900);
  const off = stage >= 1;
  return (
    <div ref={ref} className="hw-vis hw-net">
      <Float className={"hw-net__card" + (off ? " is-off" : "")}>
        <div className="lp-panel__k">One server</div>
        <svg viewBox="0 0 200 156" className="hw-net__svg" aria-hidden="true">
          <rect x="70" y="44" width="60" height="70" rx="10" className="hw-net__server" />
          <line x1="82" y1="64" x2="118" y2="64" className="hw-net__slot" />
          <line x1="82" y1="78" x2="118" y2="78" className="hw-net__slot" />
          <line x1="82" y1="92" x2="118" y2="92" className="hw-net__slot" />
          <motion.g initial={{ scale: 0, opacity: 0 }} animate={off ? { scale: 1, opacity: 1 } : { scale: 0, opacity: 0 }} transition={pop} style={{ transformOrigin: "100px 79px" }}>
            <circle cx="100" cy="79" r="20" fill="#a4433a" />
            <path d="M92 71l16 16M108 71l-16 16" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
          </motion.g>
        </svg>
        <div className={"hw-net__say" + (off ? " is-bad" : "")}>
          {off ? <ServerOff /> : <Database />}
          {off ? "Gone, or quietly changed" : "Switched off…"}
        </div>
      </Float>
      <Float className="hw-net__card hw-net__card--good">
        <div className="lp-panel__k">Many copies</div>
        <svg viewBox="0 0 200 156" className="hw-net__svg" aria-hidden="true">
          {RING.map((p, i) => {
            const q = RING[(i + 1) % RING.length];
            return <line key={`l${i}`} x1={p.x} y1={p.y} x2={q.x} y2={q.y} className="hw-net__edge" />;
          })}
          {RING.map((p, i) => (
            <line key={`c${i}`} x1={p.x} y1={p.y} x2={100} y2={78} className="hw-net__edge hw-net__edge--in" />
          ))}
          <circle cx="100" cy="78" r="15" className={"hw-net__core" + (off ? " is-off" : "")} />
          <text x="100" y="82" textAnchor="middle" className="hw-net__label">
            {off ? "off" : "us"}
          </text>
          {RING.map((p, i) => (
            <circle key={`n${i}`} cx={p.x} cy={p.y} r="9" className="hw-net__node" style={{ animationDelay: `${i * 0.18}s` }} />
          ))}
        </svg>
        <div className="hw-net__say is-good">
          <Globe />
          {off ? "Still there, still checkable" : "Veritas offline…"}
        </div>
      </Float>
    </div>
  );
}

/* ------------------------------------------------------------------ the arrows between steps */

/** The width of an element, kept up to date. */
function useWidth<T extends HTMLElement>(): [React.RefObject<T>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    setWidth(el.clientWidth);
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

/** Whether the window is as narrow as the one-column layout in how.css. */
function useNarrow(query = "(max-width: 960px)"): boolean {
  const [narrow, setNarrow] = useState(() => typeof window !== "undefined" && Boolean(window.matchMedia?.(query).matches));
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return undefined;
    const update = () => setNarrow(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [query]);
  return narrow;
}

const GAP = 56;
const RISE = 132;

/**
 * An arrow from one step's picture to the next: down from the side it is on, across, and
 * down into the other side, drawn as it comes into view, with a dot that keeps running along
 * it and, halfway, what one step hands to the next. Straight down when the steps stack.
 */
function Connector({ from, icon: Icon }: { from: "left" | "right"; icon: React.ElementType }) {
  const [seen, on] = useInOnce<HTMLDivElement>();
  const [box, w] = useWidth<HTMLDivElement>();
  const stacked = useNarrow();
  const centre = (side: "left" | "right") => (side === "left" ? (w - GAP) / 4 : w - (w - GAP) / 4);
  const x1 = stacked ? 26 : centre(from);
  const x2 = stacked ? 26 : centre(from === "left" ? "right" : "left");
  const rise = stacked ? 96 : RISE;
  const mid = rise / 2;
  const r = 26;
  const dir = x2 < x1 ? -1 : 1;
  const d = stacked
    ? `M ${x1} 0 V ${rise - 6}`
    : `M ${x1} 0 V ${mid - r} Q ${x1} ${mid} ${x1 + dir * r} ${mid} H ${x2 - dir * r} Q ${x2} ${mid} ${x2} ${mid + r} V ${rise - 6}`;
  return (
    <div ref={seen} className={"hw-conn" + (on ? " is-on" : "")} aria-hidden="true">
      <div ref={box} className="hw-conn__box">
        {w ? (
          <svg width={w} height={rise} viewBox={`0 0 ${w} ${rise}`}>
            <path d={d} className="hw-conn__base" />
            <path d={d} className="hw-conn__draw" pathLength={1} />
            <path d={`M ${x2 - 7} ${rise - 14} L ${x2} ${rise - 5} L ${x2 + 7} ${rise - 14}`} className="hw-conn__head" />
            <circle r="6" className="hw-conn__dot">
              <animateMotion dur="2.6s" repeatCount="indefinite" path={d} />
            </circle>
          </svg>
        ) : null}
        {w ? (
          <span className="hw-conn__chip" style={{ left: stacked ? x1 : (x1 + x2) / 2, top: mid }}>
            <Icon />
          </span>
        ) : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ the flow */

type StepData = {
  id: string;
  short: string;
  title: string;
  line: string;
  Visual: () => React.ReactElement;
  /** What this step hands to the next one, on the arrow between them. */
  hands: React.ElementType;
};

const STEPS: StepData[] = [
  { id: "verify", short: "Organisation checked", title: "The organisation is checked", line: "Registered charities only, checked by a person first.", Visual: OrgVisual, hands: BadgeCheck },
  { id: "seal", short: "Plan sealed", title: "The plan is sealed", line: "Milestones, budget and builder, fixed on the blockchain.", Visual: SealVisual, hands: FileCheck2 },
  { id: "escrow", short: "Money in escrow", title: "Your money waits in escrow", line: "Not with the charity, not with us.", Visual: EscrowVisual, hands: Lock },
  { id: "capture", short: "Proof from the site", title: "Proof comes from the site", line: "Photos with today's code, place and time, signed on the phone.", Visual: CaptureVisual, hands: Camera },
  { id: "checks", short: "11 checks", title: "Eleven checks run", line: "One failed check stops the money.", Visual: ChecksVisual, hands: ShieldCheck },
  { id: "decide", short: "People decide", title: "People decide", line: "AI advises. An officer signs, then donors vote.", Visual: DecideVisual, hands: Vote },
  { id: "release", short: "Paid and recorded", title: "The builder is paid", line: "Straight from escrow, and on the record for good.", Visual: ReleaseVisual, hands: Link2 },
  { id: "chain", short: "No single server", title: "No single server", line: "If Veritas vanished, the record would still be there.", Visual: NetworkVisual, hands: Globe },
];

function Step({ n, step, flip }: { n: number; step: StepData; flip: boolean }) {
  const [ref, on] = useInOnce<HTMLElement>();
  const Visual = step.Visual;
  return (
    <article id={step.id} ref={ref} className={"hw-step" + (flip ? " hw-step--flip" : "") + (on ? " is-on" : "")}>
      <div className="hw-step__text">
        <span className="hw-step__num" aria-hidden="true">
          {String(n).padStart(2, "0")}
        </span>
        <Rv as="h2" className="lp-d4 hw-step__title">
          {step.title}
        </Rv>
        <Rv as="p" delay={80} className="lp-lead hw-step__body">
          {step.line}
        </Rv>
      </div>
      <div className="hw-step__vis">
        <Visual />
      </div>
    </article>
  );
}

export default function HowItWorks() {
  return (
    <MotionConfig reducedMotion="user">
      <LpPage>
        <LpHero
          eyebrow={<Eyebrow icon={ShieldCheck}>How it works</Eyebrow>}
          title="Don't take our word for it. Check every step."
          lead="Eight steps from your card to a finished roof. Each one is checked."
          wide
        >
          <Btn to={`/projects/${SHOWCASE}`} label="See a finished project's proof" variant="lime" size="lg" />
          <Btn href="#verify" label="Follow the steps" variant="quiet" size="lg" />
        </LpHero>

        <section className="lp-sec hw-pipewrap">
          <div className="lp-shell">
            <Rv as="nav" className="hw-pipe" aria-label="The eight steps">
              {STEPS.map((s, i) => (
                <a key={s.id} href={`#${s.id}`} className="hw-pipe__step" style={{ "--i": i } as React.CSSProperties}>
                  <b>{i + 1}</b>
                  <span>{s.short}</span>
                </a>
              ))}
            </Rv>
          </div>
        </section>

        <section className="lp-sec hw-flow">
          <div className="lp-shell">
            {STEPS.map((s, i) => (
              <React.Fragment key={s.id}>
                <Step n={i + 1} step={s} flip={i % 2 === 1} />
                {i < STEPS.length - 1 ? <Connector from={i % 2 === 0 ? "right" : "left"} icon={s.hands} /> : null}
              </React.Fragment>
            ))}
          </div>
        </section>

        <section className="lp-sec lp-sec--tight">
          <div className="lp-shell hw-stop">
            <div>
              <Rv>
                <Eyebrow icon={RotateCcw} tone="flat">
                  If a project stops
                </Eyebrow>
              </Rv>
              <Rv as="h2" delay={60} className="lp-d4">
                Your money comes back
              </Rv>
              <Rv as="p" delay={110} className="lp-lead">
                To your card, or to a similar project. You choose.
              </Rv>
            </div>
            <Rv delay={140} className="hw-stop__vis">
              <RefundMock />
            </Rv>
          </div>
        </section>

        <div className="lp-closewrap lp-closewrap--gap">
          <section className="lp-close lp-dark">
            <div className="lp-close__head">
              <Rv as="h2" className="lp-d2">
                See it on a finished project.
              </Rv>
              <Rv as="p" delay={60} className="lp-lead lp-lead--dark">
                Every photo, document and vote, open to read.
              </Rv>
              <Rv delay={120} className="hw-close__cta">
                <Btn to={`/projects/${SHOWCASE}`} label="Open its proof" variant="lime" size="lg" />
                <Btn to="/donate" label="Browse causes" variant="ghost" size="lg" />
              </Rv>
            </div>
            <Rv delay={160} className="lp-close__stage hw-close__stage">
              <img src="/img/proof/ganja-school/m4-first-lessons.jpg" alt="" loading="lazy" />
              <span className="hw-close__chip">
                <BadgeCheck /> 4 of 4 milestones proven
              </span>
            </Rv>
          </section>
        </div>
      </LpPage>
    </MotionConfig>
  );
}
