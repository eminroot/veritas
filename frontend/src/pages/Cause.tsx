import React, { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Map as MapIcon } from "lucide-react";
import { LpPage } from "@/components/lp/LpChrome";
import { Btn, Eyebrow, Rv } from "@/components/lp/primitives";
import ProjectCard from "@/components/donate/ProjectCard";
import { SampleMark } from "@/components/donate/bits";
import { CAUSES, causeOf } from "@/data/causes";
import { REGIONS, regionOf } from "@/data/regions";
import { PROJECTS, goalOf, raisedOf, releasedOf } from "@/data/projects";
import { fmtCount, manat, percentOf } from "@/lib/money";
import NotFound from "./NotFound";

type Sort = "active" | "closest" | "newest";

const SORTS: [Sort, string][] = [
  ["active", "Most given this month"],
  ["closest", "Closest to its goal"],
  ["newest", "Newest"],
];

/** One cause: its projects, filterable by region and sortable. */
export default function Cause() {
  const { cause: key } = useParams();
  const cause = causeOf(key);
  const [region, setRegion] = useState<string>("all");
  const [sort, setSort] = useState<Sort>("active");

  const all = useMemo(() => PROJECTS.filter((p) => p.cause === cause?.key), [cause]);
  const shown = useMemo(() => {
    const list = all.filter((p) => region === "all" || p.region === region);
    const by: Record<Sort, (a: (typeof list)[number], b: (typeof list)[number]) => number> = {
      active: (a, b) => b.recent.raised - a.recent.raised,
      closest: (a, b) => percentOf(raisedOf(b), goalOf(b)) - percentOf(raisedOf(a), goalOf(a)),
      newest: (a, b) => b.publishedAt.localeCompare(a.publishedAt),
    };
    // Live projects first: completed and stopped ones no longer need anything.
    const rank = (p: (typeof list)[number]) => (p.status === "live" ? 0 : p.status === "completed" ? 1 : 2);
    return [...list].sort((a, b) => rank(a) - rank(b) || by[sort](a, b));
  }, [all, region, sort]);

  if (!cause) return <NotFound />;

  const raised = all.reduce((s, p) => s + raisedOf(p), 0);
  const released = all.reduce((s, p) => s + releasedOf(p), 0);
  const donors = all.reduce((s, p) => s + p.donors, 0);
  const regions = REGIONS.filter((r) => all.some((p) => p.region === r.key));
  const others = CAUSES.filter((c) => c.key !== cause.key && PROJECTS.some((p) => p.cause === c.key)).slice(0, 8);

  return (
    <LpPage>
      <header className="lp-hero v-causehero">
        <div className="lp-shell v-causehero__grid">
          <div className="v-causehero__say">
            <Rv y={20}>
              <Link to="/donate" className="v-back">
                <ArrowLeft aria-hidden="true" />
                All causes
              </Link>
            </Rv>
            <Rv y={30} delay={40}>
              <Eyebrow icon={cause.icon}>{cause.label}</Eyebrow>
            </Rv>
            <Rv as="h1" y={48} delay={80} className="lp-d2">
              {cause.label}
            </Rv>
            <Rv as="p" y={56} delay={120} className="lp-lead">
              {cause.blurb}
            </Rv>
            <Rv y={60} delay={160}>
              <dl className="v-stats v-stats--row">
                <div>
                  <dt>Projects</dt>
                  <dd>{all.length}</dd>
                </div>
                <div>
                  <dt>Raised</dt>
                  <dd>{manat(raised)}</dd>
                </div>
                <div>
                  <dt>Paid out on proof</dt>
                  <dd>{manat(released)}</dd>
                </div>
                <div>
                  <dt>Donors</dt>
                  <dd>{fmtCount(donors)}</dd>
                </div>
              </dl>
            </Rv>
          </div>
          <Rv y={40} delay={120} className="v-causehero__photo">
            <img src={cause.photo} alt="" />
          </Rv>
        </div>
      </header>

      <section className="lp-sec lp-sec--pad">
        <div className="lp-shell">
          <div className="v-toolbar">
            <label className="v-select">
              <span>Region</span>
              <select value={region} onChange={(e) => setRegion(e.target.value)}>
                <option value="all">All regions</option>
                {regions.map((r) => (
                  <option key={r.key} value={r.key}>
                    {r.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="v-select">
              <span>Sort</span>
              <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
                {SORTS.map(([k, label]) => (
                  <option key={k} value={k}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <span className="v-toolbar__gap" />
            <SampleMark />
            <Link className="v-link" to={`/map?cause=${cause.key}${region !== "all" ? `&region=${region}` : ""}`}>
              <MapIcon aria-hidden="true" />
              On the map
            </Link>
          </div>

          {shown.length ? (
            <div className="v-pgrid">
              {shown.map((p, i) => (
                <Rv key={p.id} y={28} delay={(i % 3) * 70}>
                  <ProjectCard project={p} />
                </Rv>
              ))}
            </div>
          ) : (
            <div className="v-emptybox">
              <h2 className="lp-d5">No {cause.label.toLowerCase()} projects {region !== "all" ? `in ${regionOf(region)?.name}` : ""} yet</h2>
              <p className="lp-lead">
                New projects appear here as soon as a verified organisation publishes one. Meanwhile, these causes need help.
              </p>
            </div>
          )}

          {others.length ? (
            <div className="v-othercauses">
              <h2 className="lp-d5">Other causes</h2>
              <div className="v-othercauses__row">
                {others.map((c) => (
                  <Link key={c.key} to={`/causes/${c.key}`} className="v-chip">
                    <c.icon aria-hidden="true" />
                    {c.label}
                  </Link>
                ))}
                <Btn to="/donate" label="All causes" size="sm" variant="quiet" />
              </div>
            </div>
          ) : null}
        </div>
      </section>
    </LpPage>
  );
}
