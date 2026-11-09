import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Building2, Check, Copy, HardHat, Lock, MapPin, RotateCcw, ShieldCheck, Users } from "lucide-react";
import { LpPage } from "@/components/lp/LpChrome";
import { Btn, Eyebrow, Rv } from "@/components/lp/primitives";
import MilestoneTimeline from "@/components/donate/MilestoneTimeline";
import ProjectProof from "@/components/proof/ProjectProof";
import { proofOf } from "@/data/sample-proof";
import DonateSheet from "@/components/donate/DonateSheet";
import ProjectCard from "@/components/donate/ProjectCard";
import { BarLegend, FundingBar, SampleMark, StatusTag, Verified, fmtDate } from "@/components/donate/bits";
import AzMap from "@/components/map/AzMap";
import { formatRegionValue, mapInputs } from "@/components/map/mapData";
import { causeOf } from "@/data/causes";
import { regionOf } from "@/data/regions";
import {
  PROJECTS,
  currentMilestone,
  goalOf,
  inEscrowOf,
  organisationOf,
  projectOf,
  projectsByOrg,
  raisedOf,
  releasedOf,
  returnedOf,
} from "@/data/projects";
import { fmtCount, manat, percentOf } from "@/lib/money";
import NotFound from "./NotFound";

export default function Project() {
  const { projectId } = useParams();
  const p = projectOf(projectId);
  const [giving, setGiving] = useState(false);
  const [copied, setCopied] = useState(false);
  if (!p) return <NotFound />;

  const cause = causeOf(p.cause);
  const region = regionOf(p.region);
  const org = organisationOf(p.orgId);
  const goal = goalOf(p);
  const raised = raisedOf(p);
  const released = releasedOf(p);
  const escrow = inEscrowOf(p);
  const now = p.milestones[currentMilestone(p)];
  const done = p.status === "completed";
  const stopped = p.status === "stopped";
  const { values, pins } = mapInputs([p]);
  const more = (org ? projectsByOrg(org.id) : PROJECTS).filter((x) => x.id !== p.id).slice(0, 3);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked: nothing to do */
    }
  };

  return (
    <LpPage>
      <header className="lp-hero v-phero">
        <div className="lp-shell">
          <Rv y={20}>
            <Link to={cause ? `/causes/${cause.key}` : "/donate"} className="v-back">
              <ArrowLeft aria-hidden="true" />
              {cause ? cause.label : "All causes"}
            </Link>
          </Rv>
          <Rv as="h1" y={40} delay={60} className="lp-d2 v-phero__title">
            {p.title}
          </Rv>
          <Rv y={50} delay={110} className="v-phero__meta">
            {org ? <Verified label={org.name} /> : null}
            <span>
              <MapPin aria-hidden="true" />
              {p.place}
              {region ? `, ${region.name}` : ""}
              {p.country ? `, ${p.country}` : ""}
            </span>
            <span>Published {fmtDate(p.publishedAt)}</span>
            <SampleMark />
          </Rv>
        </div>
      </header>

      <section className="lp-sec v-psec">
        <div className="lp-shell v-playout">
          <article className="v-pmain">
            <Rv y={30} className="v-pphoto">
              <img src={p.photo} alt="" />
              {cause ? (
                <span className="v-pcard__cause">
                  <cause.icon aria-hidden="true" />
                  {cause.label}
                </span>
              ) : null}
            </Rv>

            <p className="lp-lead v-pmain__lead">{p.summary}</p>
            {p.story.map((para, i) => (
              <p key={i} className="v-prose">
                {para}
              </p>
            ))}

            <h2 className="lp-d5 v-h">Milestones</h2>
            <p className="v-prose v-prose--quiet">
              The money for each milestone waits in escrow. It is paid to {p.contractor.name} only after photos from the site
              pass Veritas's checks and an officer approves them.
            </p>
            <MilestoneTimeline project={p} />

            {p.milestones.some((_, i) => proofOf(p, i)) ? (
              <>
                <h2 className="lp-d5 v-h">The proof</h2>
                <p className="v-prose v-prose--quiet">
                  {done
                    ? "Every payment on this project, with what proved it: the photos from the site, the documents and the donors' vote. Open any of them."
                    : "What proved each milestone so far: the photos from the site, the documents and the donors' vote. Open any of them."}
                </p>
                <ProjectProof project={p} />
              </>
            ) : null}

            <h2 className="lp-d5 v-h">Where the money is</h2>
            <div className="v-moneybox">
              <FundingBar released={released} inEscrow={escrow} goal={goal} size="lg" />
              <BarLegend released={released} inEscrow={escrow} toRaise={goal - raised} />
            </div>

            <h2 className="lp-d5 v-h">Updates</h2>
            <ul className="v-updates">
              {p.updates.map((u) => (
                <li key={u.date + u.text}>
                  <time dateTime={u.date}>{fmtDate(u.date, { day: "numeric", month: "short" })}</time>
                  <p>{u.text}</p>
                </li>
              ))}
            </ul>

            <h2 className="lp-d5 v-h">Who is doing the work</h2>
            <div className="v-who">
              {org ? (
                <div className="v-who__card">
                  <span className="v-who__ico">
                    <Building2 aria-hidden="true" />
                  </span>
                  <div>
                    <span className="v-who__k">Organisation</span>
                    <b>{org.name}</b>
                    <p>{org.about}</p>
                    <span className="v-who__meta">
                      {org.kind} · {org.city} · since {org.founded} · verified {fmtDate(org.verifiedAt, { month: "short", year: "numeric" })}
                    </span>
                  </div>
                </div>
              ) : null}
              <div className="v-who__card">
                <span className="v-who__ico">
                  <HardHat aria-hidden="true" />
                </span>
                <div>
                  <span className="v-who__k">Contractor, paid on proof</span>
                  <b>{p.contractor.name}</b>
                  <p>{p.contractor.trade}</p>
                  <span className="v-who__meta">Paid straight from escrow, never through the organisation</span>
                </div>
              </div>
            </div>

            <h2 className="lp-d5 v-h">Where</h2>
            {p.region ? (
              <div className="v-pmap">
                <AzMap compact values={values} pins={pins} focusPinId={p.id} formatValue={formatRegionValue} ariaLabel={`Where ${p.title} is`} />
                <Link className="v-link" to={`/map?region=${p.region}`}>
                  <MapPin aria-hidden="true" />
                  Other projects in {region?.name ?? "this region"}
                </Link>
              </div>
            ) : (
              <div className="v-pmap v-pmap--abroad">
                <p className="v-prose">
                  <MapPin aria-hidden="true" />
                  <b>
                    {p.place}, {p.country}.
                  </b>{" "}
                  Outside Azerbaijan, so not on the map. {org ? org.name : "The organisation"} is registered and verified in
                  Azerbaijan, and the photos from the site are checked the same way as at home.
                </p>
                <Link className="v-link" to="/map">
                  <MapPin aria-hidden="true" />
                  All projects on the map
                </Link>
              </div>
            )}
          </article>

          <aside className="v-pside">
            <div className="v-givecard">
              <span className="v-givecard__k">{done ? "Raised and paid out" : stopped ? "Raised before it stopped" : "Raised so far"}</span>
              <span className="v-givecard__big">{manat(raised)}</span>
              <span className="v-givecard__of">
                of {manat(goal)} · {percentOf(raised, goal)}%
              </span>
              <FundingBar released={released} inEscrow={escrow} goal={goal} />
              <dl className="v-givecard__nums">
                <div>
                  <dt>Released</dt>
                  <dd>{manat(released)}</dd>
                </div>
                <div>
                  <dt>In escrow</dt>
                  <dd>{manat(escrow)}</dd>
                </div>
                <div>
                  <dt>Donors</dt>
                  <dd>
                    <Users aria-hidden="true" />
                    {fmtCount(p.donors)}
                  </dd>
                </div>
              </dl>
              {!done && !stopped ? (
                <div className="v-givecard__now">
                  <span>Now</span>
                  <StatusTag status={now.status} />
                  <b>{now.title}</b>
                </div>
              ) : null}
              {done ? (
                <p className="v-givecard__done">
                  <Check aria-hidden="true" />
                  Complete: every manat was paid out against checked evidence.
                </p>
              ) : stopped && p.stop ? (
                <p className="v-givecard__done v-givecard__done--stopped">
                  <RotateCcw aria-hidden="true" />
                  Stopped on {fmtDate(p.stop.at)}. {p.stop.reason} {manat(p.stop.refunded)} went back to donors' cards and{" "}
                  {manat(p.stop.redirected)} to the projects they chose: {manat(returnedOf(p))} in all.
                </p>
              ) : (
                <Btn type="button" size="wide" label="Donate" onClick={() => setGiving(true)} />
              )}
              <button className="v-givecard__share" onClick={copy}>
                {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
                {copied ? "Link copied" : "Copy link to share"}
              </button>
            </div>

            <ul className="v-protect">
              <li>
                <ShieldCheck aria-hidden="true" />
                <span>
                  <b>Verified organisation.</b> Registration, documents and director checked by Veritas.
                </span>
              </li>
              <li>
                <Lock aria-hidden="true" />
                <span>
                  <b>Held in escrow.</b> Paid out milestone by milestone, only on checked proof.
                </span>
              </li>
              <li>
                <RotateCcw aria-hidden="true" />
                <span>
                  <b>Refunded if it stops.</b> Or moved to a similar project, if you choose.
                </span>
              </li>
            </ul>
          </aside>
        </div>
      </section>

      {more.length ? (
        <section className="lp-sec lp-sec--pad v-more">
          <div className="lp-shell">
            <Eyebrow icon={Building2} tone="flat">
              {org ? `More from ${org.name}` : "More projects"}
            </Eyebrow>
            <div className="v-pgrid" style={{ marginTop: 24 }}>
              {more.map((x) => (
                <ProjectCard key={x.id} project={x} />
              ))}
            </div>
          </div>
        </section>
      ) : null}

      <DonateSheet project={p} open={giving} onOpenChange={setGiving} />
    </LpPage>
  );
}
