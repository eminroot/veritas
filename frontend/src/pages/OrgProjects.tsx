import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, Camera, Clock, Coins, FileCheck2, FolderKanban, HardHat, ListChecks, MapPinned, Plus, Rocket, Send } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useOrgState } from "@/components/console/OrgStatus";
import { Empty, Notice, Page, PageHead, Panel, Rise, Tag } from "@/components/console/kit";
import ProjectCard from "@/components/donate/ProjectCard";
import { SampleMark, fmtDate } from "@/components/donate/bits";
import { ExportMenu } from "@/components/portfolio/ExportMenu";
import { organisationOf, projectsByOrg, raisedOf } from "@/data/projects";
import { listProjects, startProject } from "@/lib/passport";
import { orgPortfolio } from "@/lib/portfolio";
import { fmtCount, manat } from "@/lib/money";
import { ApiNotice } from "./Dashboard";

/** The sample organisation whose projects show what a running project looks like. */
const SAMPLE_ORG = "first-steps";
const SAMPLE_PROJECTS = projectsByOrg(SAMPLE_ORG);
const SAMPLE_ORG_NAME = organisationOf(SAMPLE_ORG)?.name ?? "A sample organisation";

/** What a project needs, in the order the Passport (the project's published plan) asks for it. */
const NEEDS = [
  { icon: ListChecks, title: "Stages", body: "The work in stages, each one something a photo can prove: foundations, walls, a roof." },
  { icon: Coins, title: "A budget per stage", body: "Line by line, in manat. Donations fill the stages in order." },
  { icon: Camera, title: "What counts as proof", body: "For each stage, the photos and documents your field team will capture." },
  { icon: HardHat, title: "A verified contractor", body: "Escrow pays the contractor directly when a stage is approved." },
  { icon: MapPinned, title: "The site", body: "Where the work is. Proof photos must be taken inside it." },
];

/** How an organisation gets verified, and what that unlocks. */
const REVIEW = [
  { icon: Send, title: "You send your details", body: "Legal name, VÖEN, director and bank account, with the registration documents." },
  { icon: Clock, title: "Veritas checks them", body: "A reviewer checks the state register, the VÖEN with the tax service, the director's ID and that the account is yours. Usually within two working days." },
  { icon: BadgeCheck, title: "Verified", body: "Or a note on what to fix, which you change and send again." },
  { icon: Rocket, title: "Plan and publish projects", body: "Write a project's stages, budget and proof here, then publish it so donors can give." },
];

/** Where an organisation stands in REVIEW: a rejected one sends its details again. */
function reviewStep(status: string | undefined): number | undefined {
  if (status === "submitted") return 1;
  if (status === "saved" || status === "draft" || status === "rejected") return 0;
  return undefined;
}

/** What to do next, or what to wait for, at each status before verification. */
function ReviewNext({ status }: { status: string | undefined }) {
  const send = (
    <Link to="/onboarding?resume=1" className="btn btn--primary">
      <Send />
      Send the application
    </Link>
  );
  const page = (
    <Link to="/organisation" className="link-btn">
      Open the organisation page
    </Link>
  );
  if (status === "submitted") {
    return (
      <div className="v-orgcta">
        <span>Your application is with Veritas. You will hear by email, usually within two working days.</span>
      </div>
    );
  }
  if (status === "rejected") {
    return (
      <div className="v-orgcta">
        <span>Veritas asked for changes. Read the reviewer's notes, change what they asked, and send it again.</span>
        {page}
      </div>
    );
  }
  if (status === "suspended") {
    return (
      <div className="v-orgcta">
        <span>Suspended: projects cannot raise money until Veritas lifts it.</span>
        {page}
      </div>
    );
  }
  return <div className="v-orgcta">{send}</div>;
}

function Steps({ items, current }: { items: typeof REVIEW; current?: number }) {
  return (
    <ol className={items.length === 4 ? "v-needs v-needs--four" : "v-needs"}>
      {items.map((n, i) => {
        const state = current === undefined ? "" : i < current ? " is-done" : i === current ? " is-now" : "";
        return (
          <li className={`v-need${state}`} key={n.title} aria-current={i === current ? "step" : undefined}>
            <span className="v-need__ico">
              <n.icon aria-hidden="true" />
            </span>
            <b>
              {i + 1}. {n.title}
            </b>
            <p>{n.body}</p>
            {i === current ? <span className="v-need__now">You are here</span> : null}
          </li>
        );
      })}
    </ol>
  );
}

export default function OrgProjects() {
  const { api } = useAuth();
  const org = useOrgState();
  const navigate = useNavigate();
  const verified = org?.status === "verified";
  const live = api.status === "connected" && Boolean(org?.charityId) && org?.source === "api";
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const projects = useQuery({
    queryKey: ["charity-projects", org?.charityId],
    queryFn: () => listProjects(org?.charityId as string),
    enabled: live,
  });

  const start = async () => {
    if (!org?.charityId) return;
    setStarting(true);
    setStartError(null);
    try {
      const project = await startProject(org.charityId);
      navigate(`/organisation/projects/plan/${project.id}`);
    } catch (err) {
      setStartError(err instanceof Error ? err.message : "The project could not be started. Try again.");
      setStarting(false);
    }
  };

  const canStart = verified && live;
  return (
    <Page>
      <PageHead
        eyebrow={org?.name ?? "Organisation"}
        icon={FolderKanban}
        title="Projects"
        sub="Each project is published as a Passport: its stages, budget, proof, contractor and site, fixed before the first donation."
        actions={
          <>
            <ExportMenu build={() => orgPortfolio(SAMPLE_PROJECTS, SAMPLE_ORG_NAME, true)} />
            <button
              className="btn btn--primary"
              disabled={!canStart || starting}
              onClick={() => void start()}
              title={verified ? (live ? undefined : "The Veritas API cannot be reached right now") : "Available once Veritas has verified the organisation"}
            >
              <Plus />
              {starting ? "Starting…" : "New project"}
            </button>
          </>
        }
      />
      <ApiNotice />
      {startError ? <Notice tone="warn">{startError}</Notice> : null}

      {!verified ? (
        <Rise>
          <Panel title="Getting verified" icon={BadgeCheck} sub="Only verified organisations can raise money. This is how it goes, and what it unlocks.">
            <Steps items={REVIEW} current={reviewStep(org?.status)} />
            {org ? <ReviewNext status={org.status} /> : null}
          </Panel>
        </Rise>
      ) : null}

      {verified && live ? (
        <Rise delay={0.03}>
          <Panel title="Your projects" icon={FolderKanban} sub="Drafts stay private until you publish them.">
            {projects.data?.length ? (
              <ul className="v-pledges">
                {projects.data.map((p) => (
                  <li key={p.id}>
                    <span>
                      <Link to={`/organisation/projects/plan/${p.id}`}>{p.title || "Untitled project"}</Link>
                      <em>Started {fmtDate(p.created_at)}</em>
                    </span>
                    {p.published_version ? (
                      <Tag tone="ok" icon={FileCheck2}>
                        Published
                      </Tag>
                    ) : (
                      <Tag tone="lime">Draft</Tag>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty
                icon={FolderKanban}
                title={projects.isPending ? "Loading your projects…" : "No projects yet"}
                body="Start one: write its stages, the budget of each, and what will prove the work. Publish it when Veritas finds nothing missing."
                action={
                  <button className="btn btn--primary" onClick={() => void start()} disabled={starting}>
                    <Plus />
                    New project
                  </button>
                }
              />
            )}
          </Panel>
        </Rise>
      ) : null}

      <Rise delay={0.05}>
        <Panel
          title="Example projects"
          icon={FolderKanban}
          sub={`${SAMPLE_ORG_NAME}'s projects, to show what a running one looks like. Open one for its money, proof and votes.`}
          action={<SampleMark />}
        >
          <div className="v-plist">
            {SAMPLE_PROJECTS.map((p) => (
              <ProjectCard
                key={p.id}
                project={p}
                variant="row"
                to={`/organisation/projects/${p.id}`}
                extra={
                  <span className="pf-mine">
                    <b>{manat(raisedOf(p))}</b>
                    {fmtCount(p.donors)} donors
                  </span>
                }
              />
            ))}
          </div>
        </Panel>
      </Rise>

      <Rise delay={0.07}>
        <Panel title="What a project needs" icon={ListChecks}>
          <Steps items={NEEDS} />
        </Panel>
      </Rise>
    </Page>
  );
}
