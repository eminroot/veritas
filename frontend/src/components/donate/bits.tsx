import React from "react";
import { BadgeCheck, FlaskConical } from "lucide-react";
import type { Qapik } from "@/lib/money";
import { manat, percentOf } from "@/lib/money";
import type { MilestoneStatus } from "@/data/projects";

/**
 * Small pieces the donation pages share: the sample-data mark, the three-part funding
 * bar, the verified badge and the milestone status tag.
 */

/** Every page that shows sample organisations, projects or donations says so. */
export function SampleMark({ tone = "light", className = "" }: { tone?: "light" | "dark"; className?: string }) {
  return (
    <span
      className={`v-sample v-sample--${tone} ${className}`}
      title="The organisations, projects and figures shown here are illustrative samples until Veritas launches."
    >
      <FlaskConical aria-hidden="true" />
      Sample data
    </span>
  );
}

export function Verified({ label = "Verified" }: { label?: string }) {
  return (
    <span className="v-verified" title="Veritas checked this organisation's registration, documents and director">
      <BadgeCheck aria-hidden="true" />
      {label}
    </span>
  );
}

/**
 * Where a project's money is, in one bar: released to the contractor (dark), waiting in
 * escrow (lime) and still to raise (the track). Widths are shares of the goal.
 */
export function FundingBar({
  released,
  inEscrow,
  goal,
  size = "md",
  label,
}: {
  released: Qapik;
  inEscrow: Qapik;
  goal: Qapik;
  size?: "sm" | "md" | "lg";
  label?: string;
}) {
  const r = goal > 0 ? (released * 100) / goal : 0;
  const e = goal > 0 ? (inEscrow * 100) / goal : 0;
  return (
    <div
      className={`v-bar v-bar--${size}`}
      role="img"
      aria-label={
        label ??
        `${manat(released + inEscrow)} raised of ${manat(goal)} (${percentOf(released + inEscrow, goal)}%): ${manat(released)} released, ${manat(inEscrow)} in escrow`
      }
    >
      <i className="v-bar__rel" style={{ width: `${r}%` }} />
      <i className="v-bar__esc" style={{ width: `${e}%`, left: `${r}%` }} />
    </div>
  );
}

export function BarLegend({ released, inEscrow, toRaise }: { released: Qapik; inEscrow: Qapik; toRaise: Qapik }) {
  return (
    <div className="v-legend">
      <span>
        <i className="v-legend__rel" />
        Released <b>{manat(released)}</b>
      </span>
      <span>
        <i className="v-legend__esc" />
        In escrow <b>{manat(inEscrow)}</b>
      </span>
      <span>
        <i className="v-legend__need" />
        Still needed <b>{manat(Math.max(0, toRaise))}</b>
      </span>
    </div>
  );
}

export const STATUS: Record<MilestoneStatus, { label: string; tone: "" | "ok" | "warn" | "dark" | "lime"; say: string }> = {
  waiting: { label: "Next", tone: "", say: "Starts collecting once the milestone before it is funded." },
  funding: { label: "Raising", tone: "lime", say: "Collecting donations now. Gifts made today go here." },
  funded: { label: "Funded", tone: "", say: "Fully funded and held in escrow while the work is done." },
  evidence: { label: "Checking", tone: "warn", say: "Photos from the site are in; the automatic checks are running." },
  checked: { label: "Checked", tone: "warn", say: "Every check passed. Waiting for the officer's approval." },
  approved: { label: "Approved", tone: "ok", say: "Approved. The payment to the contractor is on its way." },
  paid: { label: "Paid", tone: "dark", say: "Released from escrow and paid to the contractor." },
  stopped: { label: "Stopped", tone: "", say: "The project stopped. What this milestone held went back to its donors, or to the projects they chose." },
};

export function StatusTag({ status }: { status: MilestoneStatus }) {
  const s = STATUS[status];
  return <span className={"lp-tag" + (s.tone ? ` lp-tag--${s.tone}` : "")}>{s.label}</span>;
}

export function fmtDate(iso: string, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }) {
  const d = new Date(iso + (iso.length === 10 ? "T12:00:00" : ""));
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-GB", opts);
}

export function Avatar({ name, size = 36 }: { name: string; size?: number }) {
  const letters = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
  // A stable hue per name, kept inside the page's cool range.
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
  const hue = 190 + (h % 70);
  return (
    <span
      className="v-avatar"
      aria-hidden="true"
      style={{ width: size, height: size, fontSize: size * 0.38, background: `hsl(${hue} 22% 88%)`, color: `hsl(${hue} 30% 26%)` }}
    >
      {letters}
    </span>
  );
}

export function Section({ children, className = "", ...rest }: React.HTMLAttributes<HTMLElement>) {
  return (
    <section className={"lp-sec " + className} {...rest}>
      <div className="lp-shell">{children}</div>
    </section>
  );
}
