import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Check, Copy, HandHeart, Receipt, Repeat } from "lucide-react";
import { useMyDonations, sumDonations, type DonationRow } from "@/hooks/useAccount";
import { Empty, Page, PageHead, Panel, Rise, Seg, Tag } from "@/components/console/kit";
import { SampleMark, fmtDate } from "@/components/donate/bits";
import { SAMPLE_PLEDGES } from "@/data/sample-account";
import { projectOf } from "@/data/projects";
import { manat } from "@/lib/money";
import { donorPortfolio } from "@/lib/portfolio";
import { useAuth } from "@/contexts/AuthContext";
import { ExportMenu } from "@/components/portfolio/ExportMenu";
import { ApiNotice } from "./Dashboard";

type Filter = "all" | "escrow" | "released" | "refunded";

const matches = (r: DonationRow, f: Filter) =>
  f === "all" || (f === "escrow" && r.inEscrow > 0) || (f === "released" && r.released > 0) || (f === "refunded" && r.refunded > 0);

/** A donation's state in one word, from where its money is now. */
function state(r: DonationRow): [string, "ok" | "lime" | "warn" | undefined] {
  if (r.refunded === r.amount) return ["Refunded", "warn"];
  if (r.released === r.amount) return ["Released", "ok"];
  if (r.released > 0) return ["Partly released", "lime"];
  return ["In escrow", "lime"];
}

function CopyReceipt({ value }: { value: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      className="v-copy"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setDone(true);
          window.setTimeout(() => setDone(false), 1500);
        } catch {
          /* clipboard blocked */
        }
      }}
      aria-label={`Copy receipt ${value}`}
    >
      <code>{value}</code>
      {done ? <Check /> : <Copy />}
    </button>
  );
}

export default function Donations() {
  const { user } = useAuth();
  const { rows, sample, loading, error } = useMyDonations();
  const [filter, setFilter] = useState<Filter>("all");
  const t = sumDonations(rows);
  const shown = rows.filter((r) => matches(r, filter)).sort((a, b) => b.date.localeCompare(a.date));

  return (
    <Page>
      <PageHead
        eyebrow="Receipts"
        icon={Receipt}
        title="My donations"
        sub="Every gift, split into what has been released to the builders, what still waits in escrow and what came back to you."
        actions={
          <>
            {rows.length ? <ExportMenu build={() => donorPortfolio(rows, user?.displayName || user?.email || "Donor", sample)} /> : null}
            <Link to="/donate" className="btn btn--primary">
              <HandHeart />
              Give again
            </Link>
          </>
        }
      />
      <ApiNotice />

      <Rise>
        <Panel
          title={`${rows.length} donation${rows.length === 1 ? "" : "s"} · ${manat(t.given)}`}
          icon={Receipt}
          action={
            <div className="v-panelacts">
              {sample ? <SampleMark /> : null}
              <Seg<Filter>
                id="donations"
                value={filter}
                onChange={setFilter}
                options={[
                  { value: "all", label: "All" },
                  { value: "escrow", label: "In escrow" },
                  { value: "released", label: "Released" },
                  { value: "refunded", label: "Refunded" },
                ]}
              />
            </div>
          }
        >
          {error ? <p className="v-err">{error}</p> : null}
          {shown.length ? (
            <div className="v-table" role="table" aria-label="Donations">
              <div className="v-table__head" role="row">
                <span role="columnheader">Project</span>
                <span role="columnheader">Given</span>
                <span role="columnheader">Released</span>
                <span role="columnheader">In escrow</span>
                <span role="columnheader">Status</span>
              </div>
              {shown.map((r) => {
                const [label, tone] = state(r);
                return (
                  <div className="v-table__row" role="row" key={r.id}>
                    <span role="cell" className="v-table__proj">
                      {r.photo ? <img src={r.photo} alt="" /> : <span className="v-table__ph" />}
                      <span>
                        {projectOf(r.projectId) ? <Link to={`/portfolio/${r.projectId}`}>{r.projectTitle}</Link> : <b>{r.projectTitle}</b>}
                        <em>
                          {fmtDate(r.date)} · {r.kind === "pay_on_proof" ? "Pay on proof" : "Card"}
                          {r.receipt ? (
                            <>
                              {" · "}
                              <CopyReceipt value={r.receipt} />
                            </>
                          ) : null}
                        </em>
                      </span>
                    </span>
                    <span role="cell" className="tnum" data-label="Given">
                      {manat(r.amount)}
                    </span>
                    <span role="cell" className="tnum" data-label="Released">
                      {manat(r.released)}
                    </span>
                    <span role="cell" className="tnum" data-label="In escrow">
                      {manat(r.inEscrow)}
                    </span>
                    <span role="cell">
                      <Tag tone={tone}>{label}</Tag>
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <Empty
              icon={Receipt}
              title={loading ? "Loading…" : filter === "all" ? "No donations yet" : "None here"}
              body={filter === "all" ? "When you give, the receipt appears here with its money's state." : "Nothing in this state right now."}
            />
          )}
        </Panel>
      </Rise>

      {sample && SAMPLE_PLEDGES.length ? (
        <Rise delay={0.05}>
          <Panel title="Pay-on-Proof pledges" icon={Repeat} sub="Charged only when a milestone of the project is approved">
            <ul className="v-pledges">
              {SAMPLE_PLEDGES.map((p) => {
                const project = projectOf(p.projectId);
                return (
                  <li key={p.id}>
                    <span>
                      <Link to={`/projects/${p.projectId}`}>{project?.title ?? p.projectId}</Link>
                      <em>
                        {manat(p.perMilestone)} per approved milestone · {manat(p.charged)} charged so far
                      </em>
                    </span>
                    <Tag tone="lime">Active</Tag>
                  </li>
                );
              })}
            </ul>
          </Panel>
        </Rise>
      ) : null}
    </Page>
  );
}
