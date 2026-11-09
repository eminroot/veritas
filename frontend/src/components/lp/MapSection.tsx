import React, { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Map as MapIcon } from "lucide-react";
import { Btn, Eyebrow, Rv } from "./primitives";
import AzMap from "@/components/map/AzMap";
import { formatRegionValue, mapInputs, regionDetail } from "@/components/map/mapData";
import { SampleMark } from "@/components/donate/bits";
import { SAMPLE, totals } from "@/data/projects";
import { fmtCount, manat } from "@/lib/money";

/**
 * The landing page's map band: Azerbaijan by economic region, shaded by what donors
 * gave in the last 30 days, with every project pinned. Choosing a region opens the full
 * map on it; a pin opens its project.
 */
export default function MapSection() {
  const navigate = useNavigate();
  const { activity, values, pins } = useMemo(() => mapInputs(), []);
  const t = totals();

  return (
    <section className="lp-sec lp-sec--pad v-mapband" id="map">
      <div className="lp-shell">
        <Rv className="v-mapband__panel" data-tour="lp-map">
          <div className="v-mapband__map">
            <AzMap
              values={values}
              pins={pins}
              zoomable={false}
              formatValue={formatRegionValue}
              detail={regionDetail(activity)}
              onSelect={(k) => k && navigate(`/map?region=${k}`)}
              ariaLabel="Donations by region in the last 30 days. Choose a region to open it on the full map."
            />
          </div>
          <div className="v-mapband__say">
            {SAMPLE ? (
              <SampleMark />
            ) : (
              <span className="v-live__badge">
                <i />
                Live
              </span>
            )}
            <Eyebrow icon={MapIcon} tone="flat">
              Donation map
            </Eyebrow>
            <p className="v-mapband__big">
              <b>{fmtCount(t.recentDonations)}</b> donations in the last 30 days, totalling <b>{manat(t.recentRaised)}</b>.
              Thank you on behalf of every organisation.
            </p>
            <p className="lp-lead">Support the projects that need it most, and show what your region can do.</p>
            <Btn to="/map" label="Open the map" />
          </div>
        </Rv>
      </div>
    </section>
  );
}
