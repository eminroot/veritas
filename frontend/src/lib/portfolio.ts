import type { Qapik } from "@/lib/money";
import {
  currentMilestone,
  goalOf,
  inEscrowOf,
  organisationOf,
  projectOf,
  raisedOf,
  releasedOf,
  returnedOf,
  type MilestoneStatus,
  type Organisation,
  type Project,
} from "@/data/projects";
import { ballotOf, proofOf, sampleVoteOf, type Ballot, type MilestoneProof } from "@/data/sample-proof";

/**
 * A portfolio as the console shows it and as its exports write it. For a donor: the
 * projects they gave to, with their own money in each, milestone by milestone. For an
 * organisation: its projects, with everything they raised. Every milestone carries the
 * proof behind it and the donors' vote on it.
 *
 * A donor's money in a project is split over its milestones the way escrow holds it: what
 * was released sits in the paid milestones, what waits sits in the milestones still open,
 * and what came back sits in the stopped ones, each in proportion to what the milestone
 * raised. The parts are whole qəpik and always add up to the donation.
 */

export type View = "donor" | "org";
/** Where a donor's money in a milestone is now. */
export type Where = "released" | "escrow" | "refunded";

/** A donation as a portfolio needs it; the console's donation rows have these fields and more. */
export type DonationRow = {
  id: string;
  projectId: string;
  projectTitle: string;
  date: string;
  kind: "card" | "pay_on_proof";
  amount: Qapik;
  released: Qapik;
  inEscrow: Qapik;
  refunded: Qapik;
  receipt: string | null;
};

export type MilestoneLine = {
  index: number;
  title: string;
  status: MilestoneStatus;
  budget: Qapik;
  funded: Qapik;
  due: string;
  paidAt?: string;
  /** The donor's money in this milestone (0 in an organisation's portfolio). */
  mine: Qapik;
  where: Where | null;
  proof: MilestoneProof | null;
  ballot: Ballot | null;
  /** Whether the donor had a receipt in this milestone's vote, and how they voted. */
  canVote: boolean;
  vote: "yes" | "no" | null;
};

export type ProjectFile = {
  project: Project;
  org: Organisation | undefined;
  goal: Qapik;
  raised: Qapik;
  released: Qapik;
  inEscrow: Qapik;
  returned: Qapik;
  /** The donor's donations to it, newest first. */
  donations: DonationRow[];
  mine: { given: Qapik; released: Qapik; inEscrow: Qapik; refunded: Qapik };
  milestones: MilestoneLine[];
};

export type Portfolio = {
  view: View;
  /** Whose portfolio: the donor's name or the organisation's. */
  owner: string;
  generatedAt: Date;
  sample: boolean;
  /** Set when the portfolio is narrowed to this one project. */
  focus?: string;
  /** Every donation, including any to a project the web app cannot show yet. */
  donations: DonationRow[];
  projects: ProjectFile[];
  totals: {
    given: Qapik;
    released: Qapik;
    inEscrow: Qapik;
    refunded: Qapik;
    goal: Qapik;
    raised: Qapik;
    donors: number;
  };
};

/** Split a whole amount by weights into whole parts that add up to it (largest remainder). */
export function spread(total: Qapik, weights: number[]): Qapik[] {
  const sum = weights.reduce((s, w) => s + Math.max(0, w), 0);
  if (total <= 0 || sum <= 0) return weights.map(() => 0);
  const raw = weights.map((w) => (total * Math.max(0, w)) / sum);
  const out = raw.map(Math.floor);
  let left = total - out.reduce((s, x) => s + x, 0);
  const order = raw.map((r, i) => [r - Math.floor(r), i] as const).sort((a, b) => b[0] - a[0]);
  for (let k = 0; left > 0 && k < order.length; k++, left--) out[order[k][1]] += 1;
  return out;
}

const OPEN: MilestoneStatus[] = ["funding", "funded", "evidence", "checked", "approved"];

function whereOf(status: MilestoneStatus): Where | null {
  if (status === "paid") return "released";
  if (status === "stopped") return "refunded";
  return OPEN.includes(status) ? "escrow" : null;
}

/** The weights for one kind of money, falling back to a single milestone when none qualifies. */
function weights(p: Project, keep: (s: MilestoneStatus) => boolean, fallback: number): number[] {
  const byFunds = p.milestones.map((m) => (keep(m.status) ? m.funded : 0));
  if (byFunds.some((w) => w > 0)) return byFunds;
  const any = p.milestones.findIndex((m) => keep(m.status));
  const at = any >= 0 ? any : fallback;
  return p.milestones.map((_, i) => (i === at ? 1 : 0));
}

export function projectFile(p: Project, donations: DonationRow[] = []): ProjectFile {
  const mine = donations.reduce(
    (t, d) => ({
      given: t.given + d.amount,
      released: t.released + d.released,
      inEscrow: t.inEscrow + d.inEscrow,
      refunded: t.refunded + d.refunded,
    }),
    { given: 0, released: 0, inEscrow: 0, refunded: 0 }
  );
  const last = p.milestones.length - 1;
  const first = donations.reduce((d, x) => (x.date < d ? x.date : d), "9999-12-31");
  // Released money went to milestones paid after the first gift, when there are any.
  const paidSince = p.milestones.some((m) => m.status === "paid" && (m.paidAt ?? "") >= first);
  const released = spread(
    mine.released,
    weights(p, (s) => s === "paid", 0).map((w, i) => (!paidSince || (p.milestones[i].paidAt ?? "") >= first ? w : 0))
  );
  const waiting = spread(mine.inEscrow, weights(p, (s) => OPEN.includes(s), currentMilestone(p)));
  const back = spread(mine.refunded, weights(p, (s) => s === "stopped", last));
  const donor = donations.map((d) => d.id).join(",");

  const milestones = p.milestones.map((m, i): MilestoneLine => {
    const amount = released[i] + waiting[i] + back[i];
    const ballot = ballotOf(p, i);
    // A receipt votes only on what opened after the gift.
    const canVote = Boolean(ballot) && amount > 0 && first <= (ballot as Ballot).opened;
    return {
      index: i,
      title: m.title,
      status: m.status,
      budget: m.budget,
      funded: m.funded,
      due: m.due,
      paidAt: m.paidAt,
      mine: amount,
      where: amount > 0 ? whereOf(m.status) : null,
      proof: proofOf(p, i),
      ballot,
      canVote,
      vote: canVote && ballot ? sampleVoteOf(ballot, donor) : null,
    };
  });

  return {
    project: p,
    org: organisationOf(p.orgId),
    goal: goalOf(p),
    raised: raisedOf(p),
    released: releasedOf(p),
    inEscrow: inEscrowOf(p),
    returned: returnedOf(p),
    donations: [...donations].sort((a, b) => b.date.localeCompare(a.date)),
    mine,
    milestones,
  };
}

function summed(view: View, donations: DonationRow[], projects: ProjectFile[]): Portfolio["totals"] {
  const giving = donations.reduce(
    (t, d) => ({ given: t.given + d.amount, released: t.released + d.released, inEscrow: t.inEscrow + d.inEscrow, refunded: t.refunded + d.refunded }),
    { given: 0, released: 0, inEscrow: 0, refunded: 0 }
  );
  const raising = projects.reduce(
    (t, f) => ({
      goal: t.goal + f.goal,
      raised: t.raised + f.raised,
      released: t.released + f.released,
      inEscrow: t.inEscrow + f.inEscrow,
      refunded: t.refunded + f.returned,
      donors: t.donors + f.project.donors,
    }),
    { goal: 0, raised: 0, released: 0, inEscrow: 0, refunded: 0, donors: 0 }
  );
  return view === "donor"
    ? { ...giving, goal: raising.goal, raised: raising.raised, donors: raising.donors }
    : { given: 0, ...raising };
}

/** A donor's portfolio from their donations; `only` narrows it to one project. */
export function donorPortfolio(rows: DonationRow[], owner: string, sample: boolean, only?: string): Portfolio {
  const ids = [...new Set(rows.map((r) => r.projectId))].filter((id) => !only || id === only);
  const projects = ids
    .map((id) => projectOf(id))
    .filter((p): p is Project => Boolean(p))
    .map((p) => projectFile(p, rows.filter((r) => r.projectId === p.id)));
  const donations = only ? rows.filter((r) => r.projectId === only) : rows;
  return {
    view: "donor",
    owner,
    generatedAt: new Date(),
    sample,
    focus: only,
    donations,
    projects,
    totals: summed("donor", donations, projects),
  };
}

/** An organisation's portfolio: its projects, with everything they raised; `only` narrows it to one. */
export function orgPortfolio(projects: Project[], owner: string, sample: boolean, only?: string): Portfolio {
  const files = projects.filter((p) => !only || p.id === only).map((p) => projectFile(p));
  return { view: "org", owner, generatedAt: new Date(), sample, focus: only, donations: [], projects: files, totals: summed("org", [], files) };
}

/** "veritas-portfolio-2026-11-08": a file name without its extension. */
export function fileBase(portfolio: Portfolio): string {
  const what = portfolio.focus ? portfolio.focus : portfolio.view === "org" ? portfolio.owner : "portfolio";
  const slug = what
    .replace(/[əƏ]/g, "e")
    .replace(/ı/g, "i")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 48);
  const d = portfolio.generatedAt;
  const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return `veritas-${slug || "export"}-${day}`;
}
