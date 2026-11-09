import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowUpRight,
  BadgeCheck,
  Camera,
  Check,
  CircleDashed,
  Clock,
  Copy,
  FileCheck2,
  FileText,
  FolderHeart,
  FolderKanban,
  HandHeart,
  Hourglass,
  Landmark,
  Link2,
  Lock,
  Receipt,
  RotateCcw,
  ScrollText,
  ShieldCheck,
  Users,
  Vote,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useMyDonations } from "@/hooks/useAccount";
import { Empty, Page, PageHead, Panel, Rise, Stat, Tag } from "@/components/console/kit";
import { BarLegend, FundingBar, SampleMark, StatusTag, fmtDate } from "@/components/donate/bits";
import { ExportMenu } from "@/components/portfolio/ExportMenu";
import { EvidencePhotos, ViewDocument } from "@/components/proof/ProofViewer";
import { organisationOf, projectOf, type Project as ProjectData } from "@/data/projects";
import type { ProofDoc } from "@/data/sample-proof";
import { donorPortfolio, orgPortfolio, type MilestoneLine, type Portfolio, type View } from "@/lib/portfolio";
import { fmtCount, manat } from "@/lib/money";
import { ApiNotice } from "./Dashboard";
import "@/components/portfolio/portfolio.css";

/**
 * One project in a portfolio. For a donor (/portfolio/:id): how much they gave and where
 * that money is now, milestone by milestone. For an organisation (/organisation/projects/:id):
 * what the project raised. For both: the proof behind every milestone (photos, invoice,
 * e-kassa receipt, their fingerprints and the on-chain record, the 11 checks and the
 * officer's decision) and the donors' vote that followed.
 */

const WHERE = { released: "released", escrow: "in escrow", refunded: "refunded" } as const;

const DOC_ICON: Record<ProofDoc["kind"], React.ElementType> = {
  photos: Camera,
  manifest: ScrollText,
  invoice: FileText,
  receipt: Receipt,
  chain: Link2,
  decision: BadgeCheck,
  payment: Landmark,
};

function Hash({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="pf-hash"
      title={value}
      aria-label={`Copy the ${label} ${value}`}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1400);
        } catch {
          /* clipboard blocked */
        }
      }}
    >
      <small>{label}</small>
      <code>
        {value.slice(0, 14)}…{value.slice(-6)}
      </code>
      {copied ? <Check /> : <Copy />}
    </button>
  );
}

function quiet(m: MilestoneLine): string {
  switch (m.status) {
    case "waiting":
      return "Starts collecting once the milestone before it is funded. Its proof and its vote come after the work.";
    case "funding":
      return "Raising now. When the work is done, the field team sends photos from the site with the invoice and the e-kassa receipt; then come the checks, the officer and the donors' vote.";
    case "funded":
      return "Fully funded and held in escrow while the work is done. The proof comes when it is finished.";
    case "stopped":
      return "The project stopped before this work: what this milestone held went back to its donors, or to the projects they chose.";
    default:
      return "";
  }
}

function Proof({ m, project }: { m: MilestoneLine; project: ProjectData }) {
  const pr = m.proof;
  if (!pr) return null;
  const automatic = pr.checks.filter((c) => c.how === "automatic");
  const passed = automatic.filter((c) => c.state === "passed").length;
  const all = pr.checks.every((c) => c.state === "passed");
  const d = pr.decision;
  return (
    <>
      <EvidencePhotos project={project} index={m.index} compact />
      <ul className="pf-docs">
        {pr.docs.map((doc) => {
          const Icon = DOC_ICON[doc.kind];
          return (
            <li key={doc.kind}>
              <span className="pf-docs__ico" aria-hidden="true">
                <Icon />
              </span>
              <span>
                <b>{doc.title}</b>
                <em>
                  {doc.detail} · {fmtDate(doc.date)}
                </em>
                {doc.cid ? (
                  <Hash label="IPFS" value={doc.cid} />
                ) : doc.tx ? (
                  <Hash label="Polygon tx" value={doc.tx} />
                ) : (
                  <Hash label="SHA-256" value={doc.fingerprint} />
                )}
              </span>
              <span className="pf-docs__side">
                <Tag tone={doc.public ? "ok" : undefined} icon={doc.public ? undefined : Lock}>
                  {doc.public ? "Public" : "Private"}
                </Tag>
                <ViewDocument project={project} index={m.index} doc={doc} />
              </span>
            </li>
          );
        })}
      </ul>
      <details className="pf-checks">
        <summary>
          {all ? <ShieldCheck aria-hidden="true" /> : <CircleDashed aria-hidden="true" />}
          {all ? "All 11 checks passed" : `${passed} of ${automatic.length} automatic checks passed`}
          <em>
            {automatic.length} automatic · {pr.checks.length - automatic.length} by the officer
          </em>
        </summary>
        <ol>
          {pr.checks.map((c) => (
            <li key={c.number} className={`is-${c.state}`}>
              {c.state === "passed" ? <Check aria-hidden="true" /> : c.state === "running" ? <Hourglass aria-hidden="true" /> : <Clock aria-hidden="true" />}
              <span>{c.title}</span>
              <small>
                {c.how === "automatic" ? "Automatic" : "Officer"}
                {c.state === "running" ? " · running" : c.state === "waiting" ? " · next" : ""}
              </small>
            </li>
          ))}
        </ol>
      </details>
      <p className="pf-officer">
        <BadgeCheck aria-hidden="true" />
        {d.state === "approved" ? (
          <span>
            Approved by <b>{d.officer}</b> ({d.firm}){d.at ? ` on ${fmtDate(d.at)}` : ""}: <q>{d.reason}</q>
          </span>
        ) : d.state === "reviewing" ? (
          <span>
            With the officer now: <b>{d.officer}</b> ({d.firm}).
          </span>
        ) : (
          <span>
            The officer, <b>{d.officer}</b> ({d.firm}), reviews it once the checks finish.
          </span>
        )}
      </p>
    </>
  );
}

function BallotView({ m, view }: { m: MilestoneLine; view: View }) {
  const b = m.ballot;
  if (!b) return null;
  const cast = b.yes + b.no;
  const yes = cast ? (b.yes * 100) / cast : 0;
  return (
    <>
      <p className="pf-ballot__q">{b.question}</p>
      <div className="pf-ballot__bar" role="img" aria-label={`${b.yes} yes, ${b.no} no`}>
        <i style={{ width: `${yes}%` }} />
      </div>
      <div className="pf-ballot__nums">
        <span>
          <b>{fmtCount(b.yes)}</b> yes
        </span>
        <span>
          <b>{fmtCount(b.no)}</b> no
        </span>
      </div>
      <div className="pf-ballot__facts">
        <span>
          Result
          <b>{b.state === "open" ? <Tag tone="lime">Open until {fmtDate(b.closes, { day: "numeric", month: "short" })}</Tag> : <Tag tone="ok">Passed, {Math.round(yes)}% yes</Tag>}</b>
        </span>
        <span>
          Turnout
          <b>
            {fmtCount(cast)} of {fmtCount(b.eligible)} receipts ({b.eligible ? Math.round((cast * 100) / b.eligible) : 0}%)
          </b>
        </span>
        <span>
          Window
          <b>
            {fmtDate(b.opened, { day: "numeric", month: "short" })} to {fmtDate(b.closes)}
          </b>
        </span>
      </div>
      {view === "donor" && m.canVote ? (
        <p className={"pf-you" + (m.vote === "yes" ? " pf-you--yes" : "")}>
          {b.state === "open" ? (
            <>
              <Clock aria-hidden="true" />
              You can vote in the Veritas app until {fmtDate(b.closes)}.
            </>
          ) : m.vote ? (
            <>
              <Check aria-hidden="true" />
              You voted {m.vote}.
            </>
          ) : (
            <>
              <CircleDashed aria-hidden="true" />
              You did not vote on this one.
            </>
          )}
        </p>
      ) : null}
    </>
  );
}

function MilestoneCard({ m, view, project }: { m: MilestoneLine; view: View; project: ProjectData }) {
  const contractor = project.contractor.name;
  const detailed = Boolean(m.proof || m.ballot);
  return (
    <article className={`pf-ms pf-ms--${m.status}`}>
      <header className="pf-ms__head">
        <span className={`pf-num pf-num--${m.status}`} aria-hidden="true">
          {m.status === "paid" ? <Check /> : m.index + 1}
        </span>
        <div className="pf-ms__title">
          <h3>{m.title}</h3>
          <p>
            {manat(m.funded)} of {manat(m.budget)} raised · {m.paidAt ? `paid to ${contractor} on ${fmtDate(m.paidAt)}` : `due ${fmtDate(m.due)}`}
          </p>
        </div>
        {view === "donor" && m.mine > 0 ? (
          <span className="pf-ms__mine">
            <b>{manat(m.mine)}</b>
            yours{m.where ? `, ${WHERE[m.where]}` : ""}
          </span>
        ) : null}
        <StatusTag status={m.status} />
      </header>
      {detailed ? (
        <div className="pf-ms__body">
          <section aria-label="Proof">
            <h4>
              <FileCheck2 aria-hidden="true" />
              Proof
            </h4>
            {m.proof ? <Proof m={m} project={project} /> : <p className="pf-none">No evidence has come in for this milestone.</p>}
          </section>
          <section aria-label="Donor vote">
            <h4>
              <Vote aria-hidden="true" />
              Donor vote
            </h4>
            {m.ballot ? (
              <BallotView m={m} view={view} />
            ) : (
              <p className="pf-none">
                {m.status === "checked"
                  ? "Opens when the officer approves this milestone: 72 hours, one receipt one vote."
                  : "When the checks finish and the officer approves, the donors vote for 72 hours."}
              </p>
            )}
          </section>
        </div>
      ) : (
        <p className="pf-ms__quiet">{quiet(m)}</p>
      )}
    </article>
  );
}

export default function PortfolioProject({ view = "donor" }: { view?: View }) {
  const { projectId } = useParams();
  const { user } = useAuth();
  const { rows, sample } = useMyDonations();
  const project = projectOf(projectId);
  const donor = view === "donor";
  const build = (): Portfolio =>
    donor
      ? donorPortfolio(rows, user?.displayName || user?.email || "Donor", sample, project?.id ?? "")
      : orgPortfolio(project ? [project] : [], organisationOf(project?.orgId)?.name ?? "Organisation", true, project?.id ?? "");
  const file = build().projects[0];
  const back = donor ? { to: "/dashboard", label: "Your portfolio", icon: FolderHeart } : { to: "/organisation/projects", label: "Your projects", icon: FolderKanban };

  if (!project || !file) {
    return (
      <Page>
        <PageHead eyebrow={<Link to={back.to}>{back.label}</Link>} icon={back.icon} title={project?.title ?? "Project not found"} />
        <Panel>
          <Empty
            icon={back.icon}
            title={project ? "You have not given to this project yet" : "There is no such project"}
            body={project ? "Projects you give to appear in your portfolio, with your money in them, their proof and their votes." : "It may have been removed, or the link is wrong."}
            action={
              <Link to={project ? `/projects/${project.id}` : back.to} className="btn btn--primary">
                {project ? "See the project" : `Back to ${back.label.toLowerCase()}`}
              </Link>
            }
          />
        </Panel>
      </Page>
    );
  }

  const p = file.project;
  const gifts = file.donations.length;

  return (
    <Page>
      <PageHead
        eyebrow={<Link to={back.to}>{back.label}</Link>}
        icon={back.icon}
        title={p.title}
        sub={`${file.org?.name ?? ""} · ${p.place}${p.country ? `, ${p.country}` : ""} · built by ${p.contractor.name}`}
        actions={
          <>
            <Link to={`/projects/${p.id}`} className="btn btn--ghost">
              Public page
              <ArrowUpRight />
            </Link>
            <ExportMenu build={build} />
          </>
        }
      />
      <ApiNotice />

      <Rise>
        <div className="v-statrow">
          {donor ? (
            <>
              <Stat label="You gave" value={manat(file.mine.given)} icon={HandHeart} foot={`${gifts} donation${gifts === 1 ? "" : "s"}`} />
              <Stat label="Released" value={manat(file.mine.released)} icon={Check} foot={`Paid to ${p.contractor.name} on proof`} />
              <Stat label="In escrow" value={manat(file.mine.inEscrow)} icon={Lock} lime foot="Waiting for proof" />
              <Stat label="Refunded" value={manat(file.mine.refunded)} icon={RotateCcw} foot={p.status === "stopped" ? "The project stopped" : "Nothing has come back"} />
            </>
          ) : (
            <>
              <Stat label="Raised" value={manat(file.raised)} icon={HandHeart} foot={`of ${manat(file.goal)}`} />
              <Stat label="Released" value={manat(file.released)} icon={Check} foot="Paid to the contractor on proof" />
              <Stat label="In escrow" value={manat(file.inEscrow)} icon={Lock} lime foot="Waiting for proof" />
              <Stat label="Donors" value={fmtCount(p.donors)} icon={Users} foot={`Published ${fmtDate(p.publishedAt)}`} />
            </>
          )}
        </div>
      </Rise>

      <Rise delay={0.04}>
        <Panel
          title={donor ? "Your money, milestone by milestone" : "The money, milestone by milestone"}
          icon={Lock}
          sub={donor ? "Escrow holds each gift in the milestones; each part is paid out only when that milestone is proven" : "Each milestone's money is paid to the contractor only when its work is proven"}
          action={sample || !donor ? <SampleMark /> : null}
        >
          <FundingBar released={file.released} inEscrow={file.inEscrow} goal={file.goal} />
          <BarLegend released={file.released} inEscrow={file.inEscrow} toRaise={file.goal - file.raised} />
          <div className="pf-money" role="table" aria-label="Milestones">
            <div className="pf-money__head" role="row">
              <span role="columnheader">Milestone</span>
              <span role="columnheader">Raised</span>
              <span role="columnheader">Budget</span>
              <span role="columnheader">{donor ? "Yours" : "Paid out"}</span>
              <span role="columnheader" style={{ textAlign: "right" }}>
                Status
              </span>
            </div>
            {file.milestones.map((m) => (
              <div className={"pf-money__row" + (donor && m.mine > 0 ? " is-mine" : "")} role="row" key={m.index}>
                <span className="pf-money__ms" role="cell">
                  <span className={`pf-num pf-num--${m.status}`} aria-hidden="true">
                    {m.status === "paid" ? <Check /> : m.index + 1}
                  </span>
                  <span>
                    <b>{m.title}</b>
                    <em>{m.paidAt ? `Paid ${fmtDate(m.paidAt)}` : `Due ${fmtDate(m.due)}`}</em>
                  </span>
                </span>
                <span className="tnum" role="cell">
                  {manat(m.funded)}
                </span>
                <span className="tnum" role="cell">
                  {manat(m.budget)}
                </span>
                <span className="tnum pf-money__mine pf-money__mine-cell" role="cell">
                  {donor ? (
                    m.mine > 0 ? (
                      <>
                        <b>{manat(m.mine)}</b>
                        <em>{m.where ? WHERE[m.where] : ""}</em>
                      </>
                    ) : (
                      "—"
                    )
                  ) : m.status === "paid" ? (
                    manat(m.funded)
                  ) : (
                    "—"
                  )}
                </span>
                <span className="pf-money__status" role="cell">
                  <StatusTag status={m.status} />
                </span>
              </div>
            ))}
          </div>
          {donor && gifts ? (
            <>
              <p className="pf-gifts__label">Your donations to it</p>
              <ul className="pf-gifts">
                {file.donations.map((d) => (
                  <li key={d.id}>
                    <span>{fmtDate(d.date)}</span>
                    <span>{d.kind === "pay_on_proof" ? "Pay on proof" : "Card"}</span>
                    {d.receipt ? <code className="pf-gifts__receipt">Receipt {d.receipt}</code> : null}
                    <b>{manat(d.amount)}</b>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </Panel>
      </Rise>

      {p.stop ? (
        <Rise delay={0.06}>
          <div className="pf-stop">
            <RotateCcw aria-hidden="true" />
            <span>
              <b>Stopped on {fmtDate(p.stop.at)}.</b> {p.stop.reason} {manat(p.stop.refunded)} was refunded to donors' cards, and {manat(p.stop.redirected)} moved
              to other projects by the donors who chose that.
            </span>
          </div>
        </Rise>
      ) : null}

      <Rise delay={0.08}>
        <Panel title="Proof and votes" icon={ShieldCheck} sub="What proves each milestone's work, and how its donors voted before it was paid">
          <p className="pf-rule">
            <Vote aria-hidden="true" />
            <span>
              After the officer approves a milestone, its donors vote for 72 hours. One receipt is one vote, with at least ₼5 behind it, and more than half of
              the votes cast must say yes. If fewer than 10% vote, the vote runs once for 48 hours more; if turnout is still low, the officer's decision stands.
            </span>
          </p>
          <div className="pf-stack">
            {file.milestones.map((m) => (
              <MilestoneCard key={m.index} m={m} view={view} project={p} />
            ))}
          </div>
        </Panel>
      </Rise>
    </Page>
  );
}
