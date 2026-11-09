import React, { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, Map as MapIcon, MapPin } from "lucide-react";
import { LpPage, LpHero } from "@/components/lp/LpChrome";
import { Eyebrow } from "@/components/lp/primitives";
import AzMap from "@/components/map/AzMap";
import { formatRegionValue, mapInputs, regionDetail } from "@/components/map/mapData";
import ProjectCard from "@/components/donate/ProjectCard";
import { SampleMark } from "@/components/donate/bits";
import { CAUSES, causeOf, type CauseKey } from "@/data/causes";
import { REGIONS, regionOf } from "@/data/regions";
import { PROJECTS, SAMPLE, isAbroad, totals } from "@/data/projects";
import { fmtCount, manat, manatShort } from "@/lib/money";

/**
 * The donation map: every project on Azerbaijan's 14 economic regions, shaded by what
 * donors gave there in the last 30 days. `?region=` and `?cause=` deep-link into it, so
 * the landing page and the project pages can open it on a place or a cause.
 */
/** A finger, not a mouse: the map moves and zooms differently (see the touch rules in veritas.css). */
const TOUCH = typeof window !== "undefined" && Boolean(window.matchMedia?.("(hover: none) and (pointer: coarse)").matches);

export default function MapPage() {
  const [params, setParams] = useSearchParams();
  const cause = (causeOf(params.get("cause"))?.key ?? "all") as CauseKey | "all";
  const selected = regionOf(params.get("region"))?.key ?? null;

  const set = (key: "cause" | "region", value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const projects = useMemo(() => (cause === "all" ? PROJECTS : PROJECTS.filter((p) => p.cause === cause)), [cause]);
  const { activity, values, pins } = useMemo(() => mapInputs(projects), [projects]);
  const t = totals(projects);
  const ranked = useMemo(
    () => REGIONS.map((r) => ({ r, a: activity[r.key] })).sort((x, y) => (y.a?.raised ?? 0) - (x.a?.raised ?? 0)),
    [activity]
  );
  const top = Math.max(1, ...ranked.map((x) => x.a?.raised ?? 0));
  const region = regionOf(selected);
  const here = selected ? projects.filter((p) => p.region === selected) : [];
  const abroad = projects.filter(isAbroad);
  const a = selected ? activity[selected] : undefined;

  return (
    <LpPage>
      <LpHero
        wide
        eyebrow={<Eyebrow icon={MapIcon}>Donation map</Eyebrow>}
        title="See where every manat goes"
        lead="Every project on Veritas, region by region. The darker a region, the more donors gave there in the last 30 days."
      />

      <section className="lp-sec v-mapsec">
        <div className="lp-shell">
          <div className="v-chips" role="group" aria-label="Filter by cause">
            <button className={"v-chip" + (cause === "all" ? " on" : "")} onClick={() => set("cause", null)} aria-pressed={cause === "all"}>
              All causes
            </button>
            {CAUSES.filter((c) => PROJECTS.some((p) => p.cause === c.key)).map((c) => (
              <button
                key={c.key}
                className={"v-chip" + (cause === c.key ? " on" : "")}
                onClick={() => set("cause", cause === c.key ? null : c.key)}
                aria-pressed={cause === c.key}
              >
                <c.icon aria-hidden="true" />
                {c.label}
              </button>
            ))}
          </div>

          <div className="v-mapgrid">
            <div className="v-mapgrid__map">
              <AzMap
                values={values}
                pins={pins}
                selected={selected}
                onSelect={(k) => set("region", k)}
                formatValue={formatRegionValue}
                detail={regionDetail(activity)}
                wheel="always"
                ariaLabel="Donation map of Azerbaijan. Choose a region to see its projects."
              />
              <p className="v-mapgrid__hint">{TOUCH ? "Drag sideways to move, use + and − to zoom, tap a region or a pin." : "Scroll to zoom, drag to move, click a region or a pin."}</p>
            </div>

            <aside className="v-mapgrid__side" aria-live="polite">
              <div className="v-live">
                {SAMPLE ? (
                  <SampleMark />
                ) : (
                  <span className="v-live__badge">
                    <i />
                    Live
                  </span>
                )}
              </div>
              <p className="v-mapstat">
                <b>{fmtCount(t.recentDonations)}</b> donations in the last 30 days, totalling <b>{manat(t.recentRaised)}</b>
                {cause !== "all" ? <> for {causeOf(cause)?.label.toLowerCase()}</> : null}. Thank you, on behalf of every
                organisation here.
              </p>

              <AnimatePresence mode="wait" initial={false}>
                {region ? (
                  <motion.div
                    key={region.key}
                    className="v-regioncard"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.22 }}
                  >
                    <button className="v-back" onClick={() => set("region", null)}>
                      <ArrowLeft aria-hidden="true" />
                      All regions
                    </button>
                    <h2 className="lp-d5">{region.name}</h2>
                    <p className="v-regioncard__az">{region.nameAz} iqtisadi rayonu</p>
                    <dl className="v-stats">
                      <div>
                        <dt>Last 30 days</dt>
                        <dd>{manat(a?.raised ?? 0)}</dd>
                      </div>
                      <div>
                        <dt>Donations</dt>
                        <dd>{fmtCount(a?.donations ?? 0)}</dd>
                      </div>
                      <div>
                        <dt>Projects</dt>
                        <dd>{a?.projects ?? 0}</dd>
                      </div>
                      <div>
                        <dt>Organisations</dt>
                        <dd>{a?.organisations ?? 0}</dd>
                      </div>
                    </dl>
                    <details className="v-districts">
                      <summary>
                        <MapPin aria-hidden="true" />
                        {region.districts.length} districts and cities
                      </summary>
                      <p>{region.districts.join(", ")}</p>
                    </details>
                    <div className="v-regioncard__list">
                      {here.length ? (
                        here.map((p) => <ProjectCard key={p.id} project={p} variant="row" />)
                      ) : (
                        <p className="v-empty">
                          No {cause !== "all" ? `${causeOf(cause)?.label.toLowerCase()} ` : ""}projects here yet.
                        </p>
                      )}
                    </div>
                  </motion.div>
                ) : (
                  <motion.ol
                    key="ranking"
                    className="v-rank"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.22 }}
                  >
                    {ranked.map(({ r, a: ra }, i) => (
                      <li key={r.key}>
                        <button className="v-rank__row" onClick={() => set("region", r.key)}>
                          <span className="v-rank__n">{i + 1}</span>
                          <span className="v-rank__name">
                            {r.name}
                            <i style={{ width: `${((ra?.raised ?? 0) / top) * 100}%` }} aria-hidden="true" />
                          </span>
                          <span className="v-rank__val">{ra ? manatShort(ra.raised) : "—"}</span>
                        </button>
                      </li>
                    ))}
                  </motion.ol>
                )}
              </AnimatePresence>
            </aside>
          </div>

          {abroad.length ? (
            <div className="v-abroad">
              <h2 className="lp-d5">Outside Azerbaijan</h2>
              <p className="v-prose v-prose--quiet">
                Organisations verified here also fund work abroad. The money waits in escrow and is released the same way: only
                on checked photos from the site.
              </p>
              <div className="v-pgrid">
                {abroad.map((p) => (
                  <ProjectCard key={p.id} project={p} />
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </section>
    </LpPage>
  );
}
