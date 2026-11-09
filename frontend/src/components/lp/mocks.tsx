import React from "react";
import { motion } from "framer-motion";
import {
  ArrowRight,
  Camera,
  Check,
  CircleCheck,
  FileCheck2,
  HandHeart,
  HardHat,
  LayoutGrid,
  Link2,
  Lock,
  Plus,
  Repeat,
  RotateCcw,
  Shuffle,
  Users,
  Vote,
} from "lucide-react";
import { Count, useCount, useInOnce } from "./primitives";
import { PROJECTS, totals } from "@/data/projects";
import { fmtCount, manat } from "@/lib/money";

/* ============================================================
   The landing page's product mocks — hand-drawn in CSS and SVG rather than
   screenshotted (MuhAI's rule): a capture goes stale the moment the app
   changes. Same `.lp-app`, `.lp-panel` and `.lp-tag` vocabulary, with
   Veritas's money in it: what was raised, what waits in escrow, what was
   released on proof. The figures are the sample project's, and every one
   adds up (36,420 = 9,500 released + 26,920 in escrow).
   ============================================================ */

/* Cumulative money raised by the sample school roof, week by week: the curve
   only ever goes up. */
const RAISED = [2.1, 4.4, 6.0, 8.9, 11.2, 13.0, 15.8, 18.3, 20.1, 22.9, 25.2, 27.4, 30.1, 32.2, 34.5, 36.42];

export function SparkLine({ data = RAISED, area = false }: { data?: number[]; area?: boolean }) {
  const w = 100;
  const h = 100;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const pts = data.map((v, i) => [(i / (data.length - 1)) * w, h - ((v - min) / (max - min || 1)) * (h - 12) - 6]);
  const d = pts
    .map(([x, y], i) => {
      if (i === 0) return `M${x} ${y}`;
      const [px, py] = pts[i - 1];
      const cx = (px + x) / 2;
      return `C${cx} ${py} ${cx} ${y} ${x} ${y}`;
    })
    .join(" ");
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      {data.map((_, i) => (
        <line
          key={i}
          x1={(i / (data.length - 1)) * w}
          y1="0"
          x2={(i / (data.length - 1)) * w}
          y2="100"
          stroke="rgba(36,36,38,.1)"
          strokeWidth="0.5"
          vectorEffect="non-scaling-stroke"
        />
      ))}
      {area ? <path d={`${d} L100 100 L0 100 Z`} fill="rgba(217,255,92,.55)" /> : null}
      <path d={d} fill="none" stroke="#242426" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/* Start poses for the four cards that assemble into the grid as the hero
   scrolls (measured off MuhAI's reference), interpolated in CSS against --p. */
const POSE = [
  { tx: -55, ty: -55, rx: -12.1, ry: 2.2, rz: -8.4, sc: 0.9 },
  { tx: -74, ty: -172, rx: -5.6, ry: 8.8, rz: -10.7, sc: 0.9 },
  { tx: 122, ty: -333, rx: -0.9, ry: -9.1, rz: 10.2, sc: 1.1 },
  { tx: 36, ty: -24, rx: 0, ry: 0, rz: 3, sc: 1.1 },
];

const poseVars = (i: number, live: boolean): React.CSSProperties | undefined =>
  live
    ? ({
        "--tx": POSE[i].tx,
        "--ty": POSE[i].ty,
        "--rx": POSE[i].rx,
        "--ry": POSE[i].ry,
        "--rz": POSE[i].rz,
        "--sc": POSE[i].sc,
      } as React.CSSProperties)
    : undefined;

/** Released (slate), in escrow (lime), still needed (mist): the colours every money bar uses. */
export const MONEY = ["#35363b", "#c7f03f", "#c9d3e0"];

const ROOF: [string, string, string, string][] = [
  ["1 · Scaffolding, old roof off", "Paid", "dark", "₼9,500"],
  ["2 · New roof frame", "Checked", "warn", "₼18,200"],
  ["3 · Roofing sheets, gutters", "Raising", "lime", "₼8,720"],
  ["4 · Ceilings and paint", "Next", "", "₼0"],
];

export function AppMock({ live = false }: { live?: boolean }) {
  return (
    <div className="lp-app">
      <div className="lp-app__rail" aria-hidden="true">
        <i className="on">
          <LayoutGrid />
        </i>
        <i>
          <Lock />
        </i>
        <i>
          <Camera />
        </i>
        <i>
          <HandHeart />
        </i>
        <span className="sp" />
        <span className="lp-app__me" />
      </div>

      <div className="lp-app__main">
        <div className="lp-app__bar">
          <div>
            <div className="lp-app__ttl">Project escrow</div>
            <div className="lp-app__sub">A new roof for School No. 3 · Şəki</div>
          </div>
          <span className="lp-app__pick">
            Sample project
            <Plus style={{ width: 13, height: 13, opacity: 0.4 }} />
          </span>
          <span className="lp-app__plus" aria-hidden="true">
            <Plus />
          </span>
        </div>

        <div className="lp-app__grid">
          <div className="lp-hcard lp-hcard--tall" style={poseVars(0, live)}>
            <div className="lp-panel">
              <div className="lp-panel__top">
                <div className="lp-panel__k">Raised</div>
                <span className="lp-tag lp-tag--lime" style={{ marginLeft: "auto" }}>
                  +₼9,840 this month
                </span>
              </div>
              <div className="lp-panel__big">
                36,420<small>₼</small>
              </div>
              <div className="lp-spark">
                <SparkLine area />
                <div className="lp-spark__x">
                  <span>Aug</span>
                  <span>Sep</span>
                  <span>Nov</span>
                </div>
              </div>
              <div className="lp-panel__foot" style={{ paddingTop: 14 }}>
                <div className="lp-panel__cell">
                  <b>412</b>
                  <span>Donors</span>
                </div>
                <div className="lp-panel__cell">
                  <b>₼88</b>
                  <span>Average gift</span>
                </div>
              </div>
            </div>
          </div>

          <div className="lp-hcard" style={poseVars(1, live)}>
            <div className="lp-panel">
              <div className="lp-panel__top">
                <div>
                  <div className="lp-panel__k">In escrow</div>
                  <div className="lp-panel__d">Waiting for proof</div>
                </div>
                <span className="lp-tag lp-tag--dark" style={{ marginLeft: "auto" }}>
                  <Lock style={{ width: 11, height: 11, marginRight: 4, verticalAlign: -1 }} />
                  Held
                </span>
              </div>
              <div className="lp-panel__big" style={{ marginTop: "auto" }}>
                26,920<small>₼</small>
              </div>
            </div>
          </div>

          <div className="lp-hcard" style={poseVars(2, live)}>
            <div className="lp-panel">
              <div className="lp-panel__top">
                <div className="lp-panel__k">Released on proof</div>
                <span className="lp-tag lp-tag--ok" style={{ marginLeft: "auto" }}>
                  1 of 4
                </span>
              </div>
              <div className="lp-days">
                <i className="on">
                  <b>✓</b>
                  Paid
                </i>
                <i>
                  <b>2</b>
                  Checked
                </i>
                <i>
                  <b>3</b>
                  Raising
                </i>
              </div>
              <div className="lp-panel__big" style={{ marginTop: "auto" }}>
                9,500<small>₼</small>
              </div>
            </div>
          </div>

          <div className="lp-hcard lp-hcard--wide" style={poseVars(3, live)}>
            <div className="lp-panel">
              <div className="lp-panel__top">
                <div>
                  <div className="lp-panel__k">Where each manat is</div>
                  <div className="lp-panel__d">Released · in escrow · still needed</div>
                </div>
                <span className="lp-tag" style={{ marginLeft: "auto" }}>
                  4 milestones
                </span>
              </div>
              <div className="lp-bars" aria-hidden="true">
                {[9500, 26920, 11580].map((n, i) => (
                  <i key={i} style={{ flex: n, background: MONEY[i] }} />
                ))}
              </div>
              <div className="lp-brk">
                {ROOF.map(([k, s, tone, v]) => (
                  <div className="lp-brk__row" key={k}>
                    <span>{k}</span>
                    <em className={"lp-tag" + (tone ? ` lp-tag--${tone}` : "")} style={{ marginLeft: "auto", fontStyle: "normal" }}>
                      {s}
                    </em>
                    <b>{v}</b>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------- slab visuals: floating panels on the photograph ---------- */

export function Float({
  className = "",
  style,
  children,
}: {
  className?: string;
  style?: React.CSSProperties;
  children: React.ReactNode;
}) {
  return (
    <div
      className={"lp-panel " + className}
      style={{ boxShadow: "0 2px 4px rgba(36,36,38,.05), 0 16px 40px rgba(36,36,38,.12)", ...style }}
    >
      {children}
    </div>
  );
}

export function GiveMock() {
  return (
    <Float>
      <div className="lp-panel__top">
        <div className="lp-panel__k">Your gift</div>
        <span className="lp-tag lp-tag--lime" style={{ marginLeft: "auto" }}>
          Verified
        </span>
      </div>
      <div className="v-mseg" aria-hidden="true">
        <span className="on">
          <Lock /> Give once
        </span>
        <span>
          <Repeat /> Pay on proof
        </span>
      </div>
      <div className="v-mchips" aria-hidden="true">
        {["₼10", "₼25", "₼50", "₼100"].map((c) => (
          <span key={c} className={c === "₼50" ? "on" : ""}>
            {c}
          </span>
        ))}
      </div>
      <div className="lp-brk" style={{ paddingTop: 12 }}>
        <div className="lp-brk__row">
          <span style={{ color: "var(--ink-75)" }}>Waits for · Roofing sheets</span>
          <b style={{ marginLeft: "auto" }}>₼50</b>
        </div>
      </div>
    </Float>
  );
}

/** Money moving: a gift travels into escrow, and stops there until the proof arrives. */
export function EscrowMock() {
  const [ref, on] = useInOnce<HTMLDivElement>();
  return (
    <div ref={ref} style={{ width: "100%" }}>
      <Float>
        <div className="lp-panel__top">
          <div className="lp-panel__k">Escrow, on-chain</div>
          <span className="lp-tag lp-tag--dark" style={{ marginLeft: "auto" }}>
            Locked
          </span>
        </div>
        <div className={"v-flow" + (on ? " is-on" : "")} aria-hidden="true">
          <span className="v-flow__node">
            <HandHeart />
            <em>You</em>
          </span>
          <span className="v-flow__wire">
            <i />
            <i />
            <i />
          </span>
          <span className="v-flow__node v-flow__node--lock">
            <Lock />
            <em>Escrow</em>
          </span>
          <span className="v-flow__wire v-flow__wire--held" />
          <span className="v-flow__node v-flow__node--off">
            <HardHat />
            <em>Builder</em>
          </span>
        </div>
        <div className="lp-panel__foot" style={{ paddingTop: 12 }}>
          <div className="lp-panel__cell">
            <b>₼50 in</b>
            <span>Held for milestone 3</span>
          </div>
          <div className="lp-panel__cell">
            <b>₼0 out</b>
            <span>Until it is proven</span>
          </div>
        </div>
      </Float>
    </div>
  );
}

const CHECKS = [
  "Taken on the site",
  "Taken during the session",
  "Not reused from elsewhere",
  "Everything on the checklist",
  "Files unchanged since capture",
];

export function ChecksMock() {
  const [ref, on] = useInOnce<HTMLDivElement>();
  return (
    <div ref={ref} style={{ width: "100%" }}>
      <Float>
        <div className="lp-panel__top">
          <div className="lp-panel__k">Evidence check · roof frame</div>
          <span className="lp-tag lp-tag--ok" style={{ marginLeft: "auto" }}>
            <Count to={5} on={on} ms={1400} />/5
          </span>
        </div>
        <div className="lp-brk" style={{ paddingTop: 12 }}>
          {CHECKS.map((c, i) => (
            <motion.div
              className="lp-brk__row"
              key={c}
              initial={{ opacity: 0.35 }}
              animate={on ? { opacity: 1 } : undefined}
              transition={{ delay: 0.25 + i * 0.22 }}
            >
              <motion.span
                className="v-tick"
                initial={{ scale: 0 }}
                animate={on ? { scale: 1 } : undefined}
                transition={{ type: "spring", stiffness: 400, damping: 18, delay: 0.25 + i * 0.22 }}
              >
                <Check />
              </motion.span>
              <span>{c}</span>
            </motion.div>
          ))}
        </div>
      </Float>
    </div>
  );
}

export function ReleaseMock() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "100%" }}>
      <Float>
        <div className="lp-panel__top">
          <div className="lp-panel__k">Milestone approved</div>
          <span className="lp-tag lp-tag--ok" style={{ marginLeft: "auto" }}>
            Released
          </span>
        </div>
        <div style={{ fontSize: 22, letterSpacing: "-0.02em", paddingTop: 8 }}>₼18,200 to Qala Construction</div>
        <div className="lp-brk__row" style={{ paddingTop: 8 }}>
          <Link2 style={{ width: 14, height: 14, color: "var(--ink-50)" }} />
          <span style={{ fontSize: 13, color: "var(--ink-75)" }}>Recorded on-chain · 0x8f3a…41c2</span>
        </div>
      </Float>
      <Float style={{ padding: "12px 16px" }}>
        <div className="lp-brk__row">
          <RotateCcw style={{ width: 14, height: 14 }} />
          <span style={{ fontSize: 13 }}>If a project stops, your share comes back to your card</span>
        </div>
      </Float>
    </div>
  );
}

/* ---------- bento visuals ---------- */

/** Fundraising, in the open: money raised across every project this month, drawn as it grew. */
export function GrowthMock() {
  const [ref, on] = useInOnce<HTMLDivElement>();
  const raised = totals().recentRaised;
  return (
    <div ref={ref} style={{ width: "100%", paddingBottom: 22 }}>
      <Float>
        <div className="lp-panel__top">
          <span className="lp-tag lp-tag--lime">This month</span>
          <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--ink-75)" }}>all projects</span>
        </div>
        <div className="lp-panel__big" style={{ paddingTop: 8 }}>
          <Count to={Math.round(raised / 100)} on={on} pre="₼" />
        </div>
        <div className="lp-spark" style={{ height: 96, flex: "none" }}>
          <SparkLine area data={[3, 5, 9, 12, 18, 22, 29, 33, 41, 47, 54, 60, 68, 73, 81, 88, 96, 100]} />
        </div>
      </Float>
    </div>
  );
}

const CROWD = ["Aysel", "Kamran", "Leyla", "Tural", "Nigar", "Elvin", "Səbinə", "Rauf", "Günay", "Orxan", "Fidan", "Murad"];

export function CrowdMock() {
  const [ref, on] = useInOnce<HTMLDivElement>();
  const donors = PROJECTS.reduce((s, p) => s + p.recent.donations, 0);
  return (
    <div ref={ref} style={{ width: "100%", paddingBottom: 24 }}>
      <div className="v-crowd" aria-hidden="true">
        {CROWD.map((n, i) => (
          <motion.span
            key={n}
            initial={{ scale: 0, opacity: 0 }}
            animate={on ? { scale: 1, opacity: 1 } : undefined}
            transition={{ type: "spring", stiffness: 380, damping: 20, delay: 0.1 + i * 0.06 }}
            style={{ background: `hsl(${(i * 47) % 360} 30% 86%)`, color: `hsl(${(i * 47) % 360} 32% 28%)` }}
          >
            {n[0]}
          </motion.span>
        ))}
      </div>
      <div style={{ fontSize: 15, paddingTop: 14 }}>
        <b style={{ fontWeight: 500 }}>
          <Count to={donors} on={on} />
        </b>{" "}
        <span style={{ color: "var(--ink-75)" }}>gifts this month, most under ₼50</span>
      </div>
    </div>
  );
}

export function ProofMock() {
  return (
    <div style={{ width: "100%", paddingBottom: 24 }}>
      <Float style={{ borderColor: "rgba(36,36,38,.1)", padding: 0, overflow: "hidden" }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center", padding: 16 }}>
          <span className="v-mico">
            <FileCheck2 />
          </span>
          <div style={{ minWidth: 0, textAlign: "left" }}>
            <div style={{ fontSize: 14 }}>Receipt 0x5c09…b3e8</div>
            <div style={{ fontSize: 12, color: "var(--ink-75)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              ₼100 · Sabirabad homes · 3 milestones
            </div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", background: "var(--pg)", fontSize: 13, color: "var(--ink-75)" }}>
          Your proof checks out on-chain
          <span style={{ marginLeft: "auto", display: "grid", placeItems: "center", width: 24, height: 24, borderRadius: 8, background: "var(--lime)", color: "#242426" }}>
            <CircleCheck style={{ width: 13, height: 13 }} />
          </span>
        </div>
      </Float>
    </div>
  );
}

export function VoteMock() {
  const [ref, on] = useInOnce<HTMLDivElement>();
  const yes = useCount(78, on, 1300);
  return (
    <div ref={ref} style={{ width: "100%", paddingBottom: 24 }}>
      <Float>
        <div className="lp-panel__top">
          <span className="v-mico v-mico--sm">
            <Vote />
          </span>
          <div className="lp-panel__k" style={{ alignSelf: "center" }}>
            Donor vote · new contractor
          </div>
        </div>
        <div className="v-vote" aria-hidden="true">
          <span className="v-vote__yes" style={{ width: `${yes}%` }}>
            Approve {Math.round(yes)}%
          </span>
          <span className="v-vote__no">{100 - Math.round(yes)}%</span>
        </div>
        <div style={{ fontSize: 12, color: "var(--ink-75)", paddingTop: 10 }}>
          <Users style={{ width: 12, height: 12, verticalAlign: -2, marginRight: 4 }} />
          One receipt, one vote
        </div>
      </Float>
    </div>
  );
}

export function RefundMock() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, width: "100%", paddingBottom: 24 }}>
      <Float style={{ padding: "12px 16px" }}>
        <div className="lp-brk__row">
          <span className="v-radio on" />
          <span>Refund to my card</span>
          <RotateCcw style={{ marginLeft: "auto", width: 14, height: 14, color: "var(--ink-50)" }} />
        </div>
      </Float>
      <Float style={{ padding: "12px 16px", opacity: 0.7 }}>
        <div className="lp-brk__row">
          <span className="v-radio" />
          <span>Move it to a similar project</span>
          <Shuffle style={{ marginLeft: "auto", width: 14, height: 14, color: "var(--ink-50)" }} />
        </div>
      </Float>
    </div>
  );
}

/** The daily reconciliation: the bank, the ledger and the chain hold the same total, or
 *  releases freeze until they do. */
export function ReconcileMock() {
  const [ref, on] = useInOnce<HTMLDivElement>();
  const rows: [string, string][] = [
    ["Bank account", "Held by the bank"],
    ["Veritas ledger", "Every recorded gift"],
    ["Escrow contracts", "vAZN on-chain"],
  ];
  return (
    <div ref={ref} style={{ width: "100%", paddingBottom: 24 }}>
      <Float>
        <div className="lp-panel__top">
          <div className="lp-panel__k">Daily reconciliation</div>
          <span className="lp-tag lp-tag--ok" style={{ marginLeft: "auto" }}>
            Balanced
          </span>
        </div>
        <div className="lp-brk" style={{ paddingTop: 12 }}>
          {rows.map(([k, s]) => (
            <div className="lp-brk__row" key={k}>
              <span>
                {k}
                <span style={{ display: "block", fontSize: 11, color: "var(--ink-50)" }}>{s}</span>
              </span>
              <b style={{ marginLeft: "auto" }}>
                <Count to={1_204_880} on={on} pre="₼" />
              </b>
            </div>
          ))}
        </div>
      </Float>
    </div>
  );
}

/* ---------- the dark showcase: proof from the site ---------- */

const SHOTS = [
  { src: "/img/builder-frame.jpg", tag: "Roof frame · photo 7 of 19" },
  { src: "/img/builders-smiling.jpg", tag: "Faces blurred before publishing" },
  { src: "/img/children-listening.jpg", tag: "Inside the site boundary" },
];

export function EvidenceShowcase() {
  return (
    <div className="v-evid" aria-hidden="true">
      <div className="v-evid__shots">
        {SHOTS.map((s, i) => (
          <figure key={s.src} className={`v-evid__shot v-evid__shot--${i}`}>
            <img src={s.src} alt="" loading="lazy" />
            <figcaption>{s.tag}</figcaption>
          </figure>
        ))}
      </div>
      <div className="v-evid__report">
        <div className="v-evid__head">
          <span className="v-mico v-mico--lime">
            <Camera />
          </span>
          <div>
            <b>Check report</b>
            <span>Milestone 2 · New roof frame</span>
          </div>
        </div>
        {CHECKS.map((c) => (
          <div className="v-evid__row" key={c}>
            <i>
              <Check />
            </i>
            {c}
          </div>
        ))}
        <div className="v-evid__foot">
          <span>
            <Link2 /> Anchored on-chain · 2 Nov
          </span>
          <span className="v-evid__go">
            Officer review <ArrowRight />
          </span>
        </div>
      </div>
    </div>
  );
}

export const sampleTotals = () => {
  const t = totals();
  return { raised: manat(t.raised), donors: fmtCount(t.donors) };
};
