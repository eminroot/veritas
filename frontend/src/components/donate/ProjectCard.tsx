import React from "react";
import { Link } from "react-router-dom";
import { Lock, MapPin, RotateCcw, Users } from "lucide-react";
import { causeOf } from "@/data/causes";
import { regionOf } from "@/data/regions";
import {
  currentMilestone,
  goalOf,
  inEscrowOf,
  organisationOf,
  raisedOf,
  releasedOf,
  returnedOf,
  type Project,
} from "@/data/projects";
import { fmtCount, manat, percentOf } from "@/lib/money";
import { FundingBar, StatusTag, Verified } from "./bits";

/**
 * A project as a card: photo, cause, the organisation behind it, where it is, and its
 * money in one bar (released, in escrow, still needed). `row` is the compact version for
 * lists beside the map and on the dashboard; there `to` can send it somewhere other than
 * the public project page, and `extra` adds a column on the right.
 */
export default function ProjectCard({
  project: p,
  variant = "grid",
  className = "",
  to,
  extra,
}: {
  project: Project;
  variant?: "grid" | "row";
  className?: string;
  to?: string;
  extra?: React.ReactNode;
}) {
  const cause = causeOf(p.cause);
  const org = organisationOf(p.orgId);
  const region = regionOf(p.region);
  const goal = goalOf(p);
  const raised = raisedOf(p);
  const released = releasedOf(p);
  const escrow = inEscrowOf(p);
  const now = p.milestones[currentMilestone(p)];
  const CauseIcon = cause?.icon;

  if (variant === "row") {
    return (
      <Link to={to ?? `/projects/${p.id}`} className={`v-prow${extra ? " v-prow--extra" : ""} ${className}`}>
        <img className="v-prow__img" src={p.photo} alt="" loading="lazy" />
        <span className="v-prow__body">
          <span className="v-prow__title">{p.title}</span>
          <span className="v-prow__meta">
            <MapPin aria-hidden="true" />
            {p.place}
            {p.country ? `, ${p.country}` : null}
            <span aria-hidden="true">·</span>
            {manat(raised)} of {manat(goal)}
          </span>
          <FundingBar released={released} inEscrow={escrow} goal={goal} size="sm" />
        </span>
        {extra ? <span className="v-prow__extra">{extra}</span> : null}
      </Link>
    );
  }

  return (
    <Link to={`/projects/${p.id}`} className={`v-pcard ${className}`}>
      <span className="v-pcard__media">
        <img src={p.photo} alt="" loading="lazy" />
        {cause && CauseIcon ? (
          <span className="v-pcard__cause">
            <CauseIcon aria-hidden="true" />
            {cause.label}
          </span>
        ) : null}
        {p.status === "completed" ? <span className="v-pcard__done">Completed</span> : null}
        {p.status === "stopped" ? <span className="v-pcard__done v-pcard__done--stopped">Stopped</span> : null}
      </span>
      <span className="v-pcard__body">
        {org ? (
          <span className="v-pcard__org">
            <Verified label={org.name} />
          </span>
        ) : null}
        <span className="v-pcard__title">{p.title}</span>
        <span className="v-pcard__place">
          <MapPin aria-hidden="true" />
          {p.place}
          {region ? <span className="v-pcard__region"> · {region.name}</span> : null}
          {p.country ? <span className="v-pcard__region"> · {p.country}</span> : null}
        </span>
        <FundingBar released={released} inEscrow={escrow} goal={goal} />
        <span className="v-pcard__nums">
          <span>
            <b>{manat(raised)}</b> raised of {manat(goal)}
          </span>
          <span className="v-pcard__pct">{percentOf(raised, goal)}%</span>
        </span>
        <span className="v-pcard__foot">
          <span>
            <Users aria-hidden="true" />
            {fmtCount(p.donors)} donors
          </span>
          {p.status === "completed" ? (
            <span>
              <Lock aria-hidden="true" />
              All {manat(released)} paid out on proof
            </span>
          ) : p.status === "stopped" ? (
            <span>
              <RotateCcw aria-hidden="true" />
              {manat(returnedOf(p))} back to its donors
            </span>
          ) : (
            <span className="v-pcard__now">
              <StatusTag status={now.status} />
              <span className="v-pcard__nowtitle">{now.title}</span>
            </span>
          )}
        </span>
      </span>
    </Link>
  );
}
