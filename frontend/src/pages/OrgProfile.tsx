import React from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Building2, FileCheck2, FileWarning, Users } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import OrgStatus, { useOrgState } from "@/components/console/OrgStatus";
import { Empty, Page, PageHead, Panel, Rise } from "@/components/console/kit";
import { DOCUMENT_KINDS, getCharity, type CharityOut } from "@/lib/api";
import { ApiNotice } from "./Dashboard";

/** The organisation: where its application stands, what it told Veritas, and its documents. */
export default function OrgProfile() {
  const { api } = useAuth();
  const org = useOrgState();
  const live = api.status === "connected" && Boolean(org?.charityId);
  const { data: charity } = useQuery({
    queryKey: ["charity", org?.charityId],
    queryFn: () => getCharity(org!.charityId!),
    enabled: live,
  });

  if (!org) {
    return (
      <Page>
        <PageHead eyebrow="Organisation" icon={Building2} title="No organisation yet" />
        <Empty
          icon={Building2}
          title="Register your organisation"
          body="Tell Veritas about the organisation and upload its documents to be verified."
          action={
            <Link to="/onboarding" className="btn btn--primary">
              Start the application
            </Link>
          }
        />
      </Page>
    );
  }

  const d: Partial<CharityOut> = charity ?? org.draft?.details ?? {};
  const docs = new Set<string>(charity?.documents?.map((x) => x.kind) ?? org.draft?.documents ?? []);
  const rows: [string, React.ReactNode][] = [
    ["Registered name", d.legal_name],
    ["VÖEN", d.voen],
    ["Legal form", d.legal_form],
    ["Address", d.legal_address],
    ["Director", d.director_name],
    ["Contact", [d.contact_email, d.contact_phone].filter(Boolean).join(" · ")],
    ["Website", d.website ? <a href={d.website} target="_blank" rel="noreferrer">{d.website}</a> : "None given"],
  ];

  return (
    <Page>
      <PageHead
        eyebrow="Organisation"
        icon={Building2}
        title={org.name}
        sub="What Veritas checks before your organisation can raise money, and where that check stands."
        actions={
          <Link to="/organisation/projects" className="btn btn--ghost">
            Projects
          </Link>
        }
      />
      <ApiNotice />

      <Rise>
        <OrgStatus />
      </Rise>

      {charity?.review_notes ? (
        <Rise delay={0.03}>
          <Panel title="Reviewer's notes" icon={FileWarning} tone="tint">
            <p className="v-prose">{charity.review_notes}</p>
          </Panel>
        </Rise>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Rise delay={0.05} className="lg:col-span-3">
          <Panel title="Details" icon={Building2} sub={org.source === "local" ? "Saved on this device" : "As Veritas has them"}>
            <dl className="v-deflist">
              {rows.map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{v || "—"}</dd>
                </div>
              ))}
            </dl>
          </Panel>
        </Rise>
        <Rise delay={0.07} className="lg:col-span-2">
          <Panel title="Documents" icon={FileCheck2} sub="Seen only by Veritas's reviewers">
            <ul className="v-doclist">
              {DOCUMENT_KINDS.filter((k) => k.kind !== "other").map((k) => (
                <li key={k.kind} className={docs.has(k.kind) ? "is-in" : ""}>
                  {docs.has(k.kind) ? <FileCheck2 aria-hidden="true" /> : <FileWarning aria-hidden="true" />}
                  {k.label}
                  <em>{docs.has(k.kind) ? "Attached" : org.status === "saved" ? "Attach when sending" : "Not attached"}</em>
                </li>
              ))}
            </ul>
          </Panel>
        </Rise>
      </div>

      <Rise delay={0.09}>
        <Panel title="Field team" icon={Users} sub="The people who photograph each milestone with the Veritas app">
          <Empty
            icon={Users}
            title={org.status === "verified" ? "Invite your field team" : "Available once verified"}
            body="Field workers sign in to the Veritas app on their phone and capture the evidence for each milestone at the site."
          />
        </Panel>
      </Rise>
    </Page>
  );
}
