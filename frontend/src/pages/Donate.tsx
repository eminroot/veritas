import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { BadgeCheck, HandHeart, Lock, Map as MapIcon, Sparkles } from "lucide-react";
import { LpPage, LpHero } from "@/components/lp/LpChrome";
import { Btn, Eyebrow, Rv } from "@/components/lp/primitives";
import ProjectCard from "@/components/donate/ProjectCard";
import { SampleMark } from "@/components/donate/bits";
import AzMap from "@/components/map/AzMap";
import { formatRegionValue, mapInputs, regionDetail } from "@/components/map/mapData";
import { CAUSES } from "@/data/causes";
import { PROJECTS } from "@/data/projects";

/**
 * Where "Donate" leads: the causes, as tiles, then what is popular this month.
 *
 * Unlike a personal fundraising site, every cause here is served by organisations:
 * registered charities, foundations and public unions that Veritas has verified. There
 * is no way to give to an individual's appeal, which the page says up front.
 */
const EASE = [0.16, 1, 0.3, 1] as const;

export default function Donate() {
  const counts = new Map<string, number>();
  for (const p of PROJECTS) if (p.status === "live") counts.set(p.cause, (counts.get(p.cause) ?? 0) + 1);
  const popular = [...PROJECTS].filter((p) => p.status === "live").sort((a, b) => b.recent.donations - a.recent.donations).slice(0, 6);
  const { activity, values, pins } = mapInputs();

  return (
    <LpPage>
      <LpHero
        eyebrow={<Eyebrow icon={HandHeart}>Donate</Eyebrow>}
        title="Choose a cause"
        lead="Every cause is served by organisations Veritas has verified, never by personal appeals. Whatever you give waits in escrow until the work is proven."
      >
        <ul className="v-promise">
          <li>
            <BadgeCheck aria-hidden="true" />
            Verified organisations only
          </li>
          <li>
            <Lock aria-hidden="true" />
            Held in escrow, milestone by milestone
          </li>
          <li>
            <Sparkles aria-hidden="true" />
            Refunded if a project stops
          </li>
        </ul>
      </LpHero>

      <section className="lp-sec lp-sec--pad v-causes" aria-labelledby="causes-title">
        <div className="lp-shell">
          <div className="v-causes__head">
            <h2 id="causes-title" className="lp-d4">
              What would you like to support?
            </h2>
            <SampleMark />
          </div>
          <div className="v-causegrid">
            {CAUSES.map((c, i) => {
              const n = counts.get(c.key) ?? 0;
              return (
                <motion.div
                  key={c.key}
                  initial={{ opacity: 0, y: 18 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-40px" }}
                  transition={{ duration: 0.5, ease: EASE, delay: (i % 6) * 0.05 }}
                >
                  <Link to={`/causes/${c.key}`} className="v-causetile">
                    <span className="v-causetile__box">
                      <c.icon aria-hidden="true" />
                    </span>
                    <span className="v-causetile__label">{c.label}</span>
                    <span className="v-causetile__count">{n ? `${n} project${n === 1 ? "" : "s"}` : "Coming soon"}</span>
                  </Link>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="lp-sec lp-sec--pad v-popular" aria-labelledby="popular-title">
        <div className="lp-shell">
          <div className="v-sechead">
            <div>
              <Rv>
                <Eyebrow icon={Sparkles} tone="flat">
                  This month
                </Eyebrow>
              </Rv>
              <Rv as="h2" delay={60} id="popular-title" className="lp-d3">
                Popular right now
              </Rv>
            </div>
            <Rv delay={120}>
              <Link className="v-link" to="/map">
                See them all on the map
              </Link>
            </Rv>
          </div>
          <div className="v-pgrid">
            {popular.map((p, i) => (
              <Rv key={p.id} y={28} delay={(i % 3) * 80}>
                <ProjectCard project={p} />
              </Rv>
            ))}
          </div>
        </div>
      </section>

      <section className="lp-sec lp-sec--pad" aria-labelledby="near-title">
        <div className="lp-shell">
          <Rv className="v-nearby">
            <div className="v-nearby__say">
              <Eyebrow icon={MapIcon} tone="flat">
                Near you
              </Eyebrow>
              <h2 id="near-title" className="lp-d4">
                Find a cause in your own region
              </h2>
              <p className="lp-lead">
                Fourteen economic regions, every project pinned where the work happens. Hover a region to see what it
                received this month.
              </p>
              <Btn to="/map" label="Open the map" />
            </div>
            <div className="v-nearby__map">
              <AzMap compact values={values} pins={pins} formatValue={formatRegionValue} detail={regionDetail(activity)} />
            </div>
          </Rv>
        </div>
      </section>
    </LpPage>
  );
}
