import React from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Building2, Check, FolderHeart, HandHeart, Lock, Newspaper, RotateCcw, Sparkles } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useMyDonations, sumDonations } from "@/hooks/useAccount";
import { Empty, Notice, Page, PageHead, Panel, Rise, Stat } from "@/components/console/kit";
import ProjectCard from "@/components/donate/ProjectCard";
import { SampleMark, fmtDate } from "@/components/donate/bits";
import { PROJECTS, currentMilestone, projectOf, type Project } from "@/data/projects";
import { readOrgDraft } from "@/lib/orgDraft";
import { manat } from "@/lib/money";
import { donorPortfolio } from "@/lib/portfolio";
import OrgStatus from "@/components/console/OrgStatus";
import { ExportMenu } from "@/components/portfolio/ExportMenu";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

/** The money, as one bar: released (slate), in escrow (lime), refunded (clay). */
function MoneyBar({ released, inEscrow, refunded }: { released: number; inEscrow: number; refunded: number }) {
  const total = released + inEscrow + refunded || 1;
  return (
    <div className="v-moneybar" role="img" aria-label={`${manat(released)} released, ${manat(inEscrow)} in escrow, ${manat(refunded)} refunded`}>
      {[
        ["rel", released],
        ["esc", inEscrow],
        ["ref", refunded],
      ].map(([k, v]) => (v ? <i key={k as string} className={`v-moneybar__${k}`} style={{ flex: (v as number) / total }} /> : null))}
    </div>
  );
}

export function ApiNotice() {
  const { api, connectApi } = useAuth();
  if (api.status === "connected" || api.status === "idle" || api.status === "connecting") return null;
  return (
    <Notice
      tone="warn"
      icon={AlertTriangle}
      action={
        <button className="btn btn--ghost" onClick={() => void connectApi()}>
          Try again
        </button>
      }
    >
      {api.status === "offline"
        ? "The Veritas API could not be reached, so this page shows sample data."
        : `The Veritas API did not open your account: ${api.message}`}
    </Notice>
  );
}

/**
 * Six live projects the person does not support yet, at different stages of the journey
 * (raising, the work under way, evidence being checked, a vote, approved), the causes they
 * already give to first.
 */
function suggestions(given: Project[], causes: Set<string>): Project[] {
  const pool = PROJECTS.filter((p) => p.status === "live" && !given.some((g) => g.id === p.id)).sort(
    (a, b) => Number(causes.has(b.cause)) - Number(causes.has(a.cause)) || b.recent.donations - a.recent.donations
  );
  const stages = new Set<string>();
  const first: Project[] = [];
  const rest: Project[] = [];
  for (const p of pool) {
    const stage = p.milestones[currentMilestone(p)].status;
    if (stages.has(stage)) rest.push(p);
    else {
      stages.add(stage);
      first.push(p);
    }
  }
  return [...first, ...rest].slice(0, 6);
}

export default function Dashboard() {
  const { user, accountType } = useAuth();
  const { rows, sample, loading } = useMyDonations();
  const t = sumDonations(rows);
  const name = user?.firstName || user?.email?.split("@")[0] || "there";

  const given = [...new Set(rows.map((r) => r.projectId))].map((id) => projectOf(id)).filter(Boolean) as NonNullable<ReturnType<typeof projectOf>>[];
  const mine = (id: string) => rows.filter((r) => r.projectId === id).reduce((s, r) => s + r.amount, 0);
  const owner = user?.displayName || user?.email || "Donor";
  const causes = new Set(given.map((p) => p.cause));
  const suggest = suggestions(given, causes);
  const news = given
    .flatMap((p) => p.updates.map((u) => ({ ...u, project: p })))
    .sort((a, b) => b.date.localeCompare(a.date))
    .slice(0, 5);
  const org = accountType === "organisation";

  return (
    <Page>
      <PageHead
        eyebrow={org ? readOrgDraft(user?.id)?.details.legal_name ?? "Your organisation" : "Donor"}
        icon={org ? Building2 : HandHeart}
        title={`${greeting()}, ${name}`}
        sub="Where every manat you gave is now: released to the builders, still waiting in escrow, or back with you."
        actions={
          <>
            {rows.length ? <ExportMenu build={() => donorPortfolio(rows, owner, sample)} /> : null}
            <Link to="/donations" className="btn btn--ghost">
              My donations
            </Link>
            <Link to="/donate" className="btn btn--primary">
              <HandHeart />
              Give
            </Link>
          </>
        }
      />

      <ApiNotice />

      {org ? (
        <Rise>
          <OrgStatus compact />
        </Rise>
      ) : null}

      <Rise delay={0.04}>
        <div className="v-statrow">
          <Stat label="Given" value={manat(t.given)} icon={HandHeart} foot={`${t.projects.size} project${t.projects.size === 1 ? "" : "s"}`} />
          <Stat label="In escrow" value={manat(t.inEscrow)} icon={Lock} lime foot="Waiting for proof" />
          <Stat label="Released" value={manat(t.released)} icon={Check} foot="Paid to builders on proof" />
          <Stat label="Refunded" value={manat(t.refunded)} icon={RotateCcw} foot="From stopped projects" />
        </div>
      </Rise>

      <Rise delay={0.06}>
        <Panel title="Where your money is" icon={Lock} action={sample ? <SampleMark /> : null}>
          {t.given > 0 ? (
            <>
              <MoneyBar released={t.released} inEscrow={t.inEscrow} refunded={t.refunded} />
              <div className="v-legend v-legend--console">
                <span>
                  <i className="v-legend__rel" />
                  Released <b>{manat(t.released)}</b>
                </span>
                <span>
                  <i className="v-legend__esc" />
                  In escrow <b>{manat(t.inEscrow)}</b>
                </span>
                <span>
                  <i className="v-legend__ref" />
                  Refunded <b>{manat(t.refunded)}</b>
                </span>
              </div>
            </>
          ) : (
            <Empty
              icon={HandHeart}
              title={loading ? "Loading your donations…" : "Nothing given yet"}
              body="Choose a cause and a project; your gift appears here the moment it is in escrow."
              action={
                <Link to="/donate" className="btn btn--primary">
                  Browse causes
                </Link>
              }
            />
          )}
        </Panel>
      </Rise>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Rise delay={0.08} className="lg:col-span-3">
          <Panel
            title="Projects you support"
            icon={FolderHeart}
            sub="What you gave to each. Open one for your money in it, its proof and the donors' votes."
            action={sample ? <SampleMark /> : null}
          >
            {given.length ? (
              <div className="v-plist">
                {given.map((p) => (
                  <ProjectCard
                    key={p.id}
                    project={p}
                    variant="row"
                    to={`/portfolio/${p.id}`}
                    extra={
                      <span className="pf-mine">
                        <b>{manat(mine(p.id))}</b>
                        you gave
                      </span>
                    }
                  />
                ))}
              </div>
            ) : (
              <Empty icon={FolderHeart} title="No projects yet" body="Projects you give to are followed here automatically." />
            )}
          </Panel>
        </Rise>
        <Rise delay={0.1} className="lg:col-span-2">
          <Panel title="Latest news" icon={Newspaper}>
            {news.length ? (
              <ul className="v-feed">
                {news.map((n) => (
                  <li key={n.project.id + n.date + n.text}>
                    <time dateTime={n.date}>{fmtDate(n.date, { day: "numeric", month: "short" })}</time>
                    <div>
                      <Link to={`/projects/${n.project.id}`}>{n.project.title}</Link>
                      <p>{n.text}</p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty icon={Newspaper} title="Quiet for now" body="Evidence, approvals and payments on your projects appear here." />
            )}
          </Panel>
        </Rise>
      </div>

      <Rise delay={0.12}>
        <Panel title="You might also support" icon={Sparkles} sub={causes.size ? "Closest to the causes you already give to" : "Popular this month"}>
          <div className="v-pgrid v-pgrid--console">
            {suggest.map((p) => (
              <ProjectCard key={p.id} project={p} />
            ))}
          </div>
        </Panel>
      </Rise>
    </Page>
  );
}
