import { PROJECTS, raisedOf, regionActivity, type Project, type RegionActivity } from "@/data/projects";
import { manat, manatShort, fmtCount } from "@/lib/money";
import type { MapPin } from "./AzMap";

/** The map's inputs, from a list of projects: region values (money in the last 30 days)
 *  and one pin per project in Azerbaijan (projects abroad are listed beside the map). */
export function mapInputs(projects: Project[] = PROJECTS) {
  const activity = regionActivity(projects);
  const values: Record<string, number> = Object.fromEntries(Object.entries(activity).map(([k, a]) => [k, a.raised]));
  const pins: MapPin[] = projects.filter((p) => p.region !== null).map((p) => ({
    id: p.id,
    lat: p.lat,
    lng: p.lng,
    label: p.title,
    sub: `${manat(raisedOf(p))} raised · ${p.place}`,
    href: `/projects/${p.id}`,
    weight: raisedOf(p),
    done: p.status === "completed",
  }));
  return { activity, values, pins };
}

export const formatRegionValue = (v: number) => (v > 0 ? `${manatShort(v)} donated in the last 30 days` : "No donations in the last 30 days");

export function regionDetail(activity: Record<string, RegionActivity>) {
  return (key: string) => {
    const a = activity[key];
    if (!a) return "No projects here yet";
    return `${fmtCount(a.donations)} donations · ${a.projects} project${a.projects === 1 ? "" : "s"}`;
  };
}
